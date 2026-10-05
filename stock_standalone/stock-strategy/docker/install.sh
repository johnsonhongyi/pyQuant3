#!/bin/sh
set -eu

PROJECT=/root/johnson/stock-strategy
DATA_ROOT=/mnt/4TB/dockerf/stockstrategy
DISK=/mnt/4TB
NETWORK=stockstrategy-net
STAGE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_TAG=$(date -u +%Y%m%d%H%M%S)
WEB_DIST="$DATA_ROOT/app/web-dist/$BUILD_TAG"
SHARED_DB="$DATA_ROOT/data/easy-stock/stock-data.db"
MANAGED_LABEL=io.easy-stock.managed
SERVICE="$PROJECT/source/easy-stock-service"
WEB_SOURCE="$PROJECT/source/easy-stock-web"
GO_BACKEND_SOURCE="$PROJECT/source/easy-stock-analysis/backend"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

ensure_image() {
    image=$1
    if ! docker image inspect "$image" >/dev/null 2>&1; then
        docker pull "$image"
    fi
}

require_empty_or_managed() {
    path=$1
    marker=$2
    if [ -e "$path" ] && [ ! -f "$path/$marker" ]; then
        existing=$(find "$path" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)
        [ -z "$existing" ] || fail "$path contains unmanaged files; refusing to overwrite them."
    fi
}

command -v docker >/dev/null 2>&1 || fail 'Docker is not installed on the host.'
docker info >/dev/null 2>&1 || fail 'Docker daemon is not available.'
[ -d "$DISK/dockerf" ] || fail "$DISK/dockerf does not exist."
mountpoint -q "$DISK" || fail "$DISK is not a mounted filesystem."

DISK_FREE_KB=$(df -Pk "$DISK" | awk 'END {print $4}')
DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}')
DOCKER_FREE_KB=$(df -Pk "$DOCKER_ROOT" | awk 'END {print $4}')
[ "$DISK_FREE_KB" -ge 1048576 ] || fail 'Less than 1 GiB is free on the 4TB data disk.'
[ "$DOCKER_FREE_KB" -ge 2097152 ] || fail 'Less than 2 GiB is free on Docker storage; refusing to pull/build images.'

require_empty_or_managed "$PROJECT" .stockstrategy-managed
require_empty_or_managed "$DATA_ROOT" .stockstrategy-managed

mkdir -p "$PROJECT/source" "$PROJECT/docker" "$DATA_ROOT/data/easy-stock" "$DATA_ROOT/data/service" \
    "$DATA_ROOT/data/hermes-home" "$DATA_ROOT/data/trading-mastery" "$DATA_ROOT/logs/backend" \
    "$DATA_ROOT/logs/web" "$DATA_ROOT/logs/service" \
    "$DATA_ROOT/config" "$DATA_ROOT/app/web-dist"

if [ "$STAGE" != "$PROJECT" ]; then
    cp -a "$STAGE/source/." "$PROJECT/source/"
    cp -a "$STAGE/docker/." "$PROJECT/docker/"
    install -m 0755 "$STAGE/install.sh" "$PROJECT/install.sh"

    for name in data logs reviews screenshots; do
        if [ -d "$STAGE/initial-service-state/$name" ]; then
            case "$name" in
                data) target="$DATA_ROOT/data/service" ;;
                logs) target="$DATA_ROOT/logs/service" ;;
                reviews) target="$DATA_ROOT/data/service/reviews" ;;
                screenshots) target="$DATA_ROOT/data/service/screenshots" ;;
            esac
            mkdir -p "$target"
            cp -a -n "$STAGE/initial-service-state/$name/." "$target/"
        fi
    done
else
	[ -f "$GO_BACKEND_SOURCE/go.mod" ] || fail 'Installed Go backend source is missing.'
	[ -f "$PROJECT/docker/backend.Dockerfile" ] || fail 'Installed Docker configuration is missing.'
fi

[ -f "$GO_BACKEND_SOURCE/go.mod" ] || fail "Go backend source is missing: $GO_BACKEND_SOURCE"
[ -f "$GO_BACKEND_SOURCE/cmd/server/main.go" ] || fail 'Go backend entry point is missing.'

mkdir -p "$SERVICE"
for pair in "data:$DATA_ROOT/data/service" "logs:$DATA_ROOT/logs/service" \
    "reviews:$DATA_ROOT/data/service/reviews" "screenshots:$DATA_ROOT/data/service/screenshots"; do
    name=${pair%%:*}
    target=${pair#*:}
    path="$SERVICE/$name"
    mkdir -p "$target"
    if [ -d "$path" ] && [ ! -L "$path" ]; then
        cp -a -n "$path/." "$target/"
        rm -rf -- "$path"
    elif [ -e "$path" ] && [ ! -L "$path" ]; then
        fail "$path exists and is not a directory; refusing to replace it."
    fi
    ln -sfn "$target" "$path"
done

if [ ! -f "$DATA_ROOT/config/backend.env" ]; then
    cat > "$DATA_ROOT/config/backend.env" <<'EOF'
# Optional API token. When set, the web build embeds it in browser assets.
A_STOCK_TOKEN=
EOF
    chmod 0600 "$DATA_ROOT/config/backend.env"
fi
if [ ! -e "$SERVICE/.env" ]; then
    ln -s "$DATA_ROOT/config/backend.env" "$SERVICE/.env"
fi
install -m 0755 "$PROJECT/install.sh" "$PROJECT/deploy.sh"
touch "$PROJECT/.stockstrategy-managed" "$DATA_ROOT/.stockstrategy-managed"

API_TOKEN=$(sed -n 's/^A_STOCK_TOKEN=//p' "$DATA_ROOT/config/backend.env" | head -n 1)

for name in stockstrategy-api stockstrategy-web; do
    id=$(docker ps -aq --filter "name=^/$name$")
    [ -z "$id" ] && continue
    label=$(docker inspect --format "{{ index .Config.Labels \"$MANAGED_LABEL\" }}" "$id")
    [ "$label" = stockstrategy ] || fail "Container $name already exists and is not managed by this deployment."
done

port_owner=$(docker ps --filter publish=20073 --format '{{.Names}}' | head -n 1)
if ss -ltnH 2>/dev/null | awk '$4 ~ /:20073$/ {found=1} END {exit !found}'; then
    [ "$port_owner" = stockstrategy-web ] || fail 'TCP port 20073 is already used by another service.'
fi

ensure_image debian:bookworm-slim
ensure_image golang:1.26-alpine
ensure_image node:24-alpine
ensure_image nginx:stable-alpine

docker build --memory=768m --label "$MANAGED_LABEL=stockstrategy" \
    --tag "stockstrategy/backend:$BUILD_TAG" \
    --file "$PROJECT/docker/backend.Dockerfile" "$GO_BACKEND_SOURCE"
docker build --memory=128m --label "$MANAGED_LABEL=stockstrategy" \
    --tag "stockstrategy/web:$BUILD_TAG" \
    --file "$PROJECT/docker/web.Dockerfile" "$PROJECT/docker"

mkdir -p "$WEB_DIST"
docker run --rm \
    --memory=768m --memory-swap=768m --cpus=1.50 --pids-limit=128 \
    --log-opt max-size=5m --log-opt max-file=1 \
    -e "VITE_A_STOCK_TOKEN=$API_TOKEN" \
    -v "$WEB_SOURCE:/source:ro" \
    -v "$WEB_DIST:/output" \
    node:24-alpine sh -ec 'mkdir -p /tmp/web && cp -a /source/. /tmp/web/ && cd /tmp/web && npm ci --no-audit --no-fund && npm run build && cp -a dist/. /output/'
[ -s "$WEB_DIST/index.html" ] || fail 'Frontend build did not produce index.html.'

chown -R 10001:10001 "$DATA_ROOT/data" "$DATA_ROOT/logs/backend" "$DATA_ROOT/logs/service"
chown -R 101:101 "$DATA_ROOT/logs/web"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
    docker network create --driver bridge --label "$MANAGED_LABEL=stockstrategy" "$NETWORK" >/dev/null
fi

for name in stockstrategy-api stockstrategy-web; do
    docker rm -f "$name" >/dev/null 2>&1 || true
done

docker run -d \
    --name stockstrategy-api \
    --label "$MANAGED_LABEL=stockstrategy" \
    --restart always \
    --network "$NETWORK" \
    --init \
    --memory=512m --memory-swap=512m --cpus=1.00 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1:20081/api/health || exit 1' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=30s \
    --env-file "$DATA_ROOT/config/backend.env" \
    -e A_STOCK_ADDR=0.0.0.0:20081 \
    -e A_STOCK_APP_VERSION="$BUILD_TAG" \
    -e A_STOCK_DATA_ROOT=/data \
    -e A_STOCK_DATA_DB=/data/easy-stock/stock-data.db \
    -e A_STOCK_LOG_DIR=/logs/backend \
    -e A_STOCK_SETTINGS_PATH=/data/easy-stock/settings.json \
    -e A_STOCK_MASTERY_CACHE=/data/trading-mastery \
    -e A_STOCK_HERMES_HOME=/data/hermes-home \
    -e A_STOCK_HERMES_WORKDIR=/app \
    -e HOME=/data \
    -e XDG_CONFIG_HOME=/data/config \
    -e TZ=Asia/Hong_Kong \
    -v "$DATA_ROOT/data:/data" \
    -v "$DATA_ROOT/logs/backend:/logs/backend" \
    "stockstrategy/backend:$BUILD_TAG"

docker run -d \
    --name stockstrategy-web \
    --label "$MANAGED_LABEL=stockstrategy" \
    --restart always \
    --network "$NETWORK" \
    --memory=128m --memory-swap=128m --cpus=0.50 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1/' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=10s \
    -p 192.168.50.60:20073:80 \
    -v "$WEB_DIST:/usr/share/nginx/html:ro" \
    -v "$DATA_ROOT/logs/web:/logs/web" \
    "stockstrategy/web:$BUILD_TAG"

wait_healthy() {
    name=$1
    attempt=0
    while [ "$attempt" -lt 45 ]; do
        status=$(docker inspect --format '{{.State.Health.Status}}' "$name" 2>/dev/null || true)
        [ "$status" = healthy ] && return 0
        [ "$status" = unhealthy ] && break
        attempt=$((attempt + 1))
        sleep 2
    done
    docker logs --tail 60 "$name" >&2 || true
    fail "Container $name did not become healthy."
}

wait_healthy stockstrategy-api
wait_healthy stockstrategy-web

link_shared_database() {
    old_path=$1
    [ "$old_path" = "$SHARED_DB" ] && return 0
    shared_real=$(readlink -f -- "$SHARED_DB")
    old_real=$(readlink -f -- "$old_path" 2>/dev/null || true)
    [ "$old_real" = "$shared_real" ] && return 0
    if [ -d "$old_path" ] && [ ! -L "$old_path" ]; then
        fail "Expected a database file at $old_path; refusing to replace a directory."
    fi
    if [ -e "$old_path" ] || [ -L "$old_path" ]; then
        backup="$old_path.pre-unified-$BUILD_TAG"
        [ ! -e "$backup" ] && [ ! -L "$backup" ] || fail "Database backup path already exists: $backup"
        mv -- "$old_path" "$backup"
    fi
    ln -s "$SHARED_DB" "$old_path"
}

for old_database in \
    "$DATA_ROOT/data/service/bars.db" \
    "$DATA_ROOT/data/service/market-http-cache.db" \
    "$DATA_ROOT/data/easy-stock/reviews.db" \
    "$DATA_ROOT/data/easy-stock/portfolio-inspections.db" \
    "$DATA_ROOT/data/easy-stock/stock-research.db" \
    "$DATA_ROOT/data/easy-stock/market-emotion.db" \
    "$DATA_ROOT/data/easy-stock/market-provider-cache.db" \
    "$DATA_ROOT/data/easy-stock/theme-radar.db"; do
    link_shared_database "$old_database"
done

health=$(docker exec stockstrategy-web wget -q -T 10 -O - http://127.0.0.1/api/health)
printf 'API health: %s\n' "$health"
printf 'Web URL: http://192.168.50.60:20073\n'
printf 'Project files: %s\n' "$PROJECT"
printf 'Persistent root: %s\n' "$DATA_ROOT"
printf 'Unified SQLite database: %s\n' "$SHARED_DB"
printf 'Logs: %s/logs/{backend,web,service}\n' "$DATA_ROOT"
printf 'Auto-start: Docker restart policy "always"\n'

for old_dist in "$DATA_ROOT/app/web-dist/"*; do
    [ -d "$old_dist" ] || continue
    [ "$old_dist" = "$WEB_DIST" ] || rm -rf -- "$old_dist"
done
docker image prune -af --filter "label=$MANAGED_LABEL=stockstrategy" >/dev/null
