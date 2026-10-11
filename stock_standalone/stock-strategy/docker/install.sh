#!/bin/sh
set -eu
[ "$#" -eq 1 ] && [ "$1" = "--allow-image-build" ] || { echo 'Initial image creation requires explicit --allow-image-build authorization.' >&2; exit 2; }

PROJECT=/root/johnson/stock-strategy
DATA_ROOT=/mnt/4TB/dockerf/stockstrategy
DISK=/mnt/4TB
NETWORK=stockstrategy-net
STAGE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_TAG=$(date -u +%Y%m%d%H%M%S)
WEB_DIST="$DATA_ROOT/app/web-dist/$BUILD_TAG"
RUNTIME_ROOT="$DATA_ROOT/runtime/$BUILD_TAG"
API_TMP="$RUNTIME_ROOT/api/tmp"
API_RUN="$RUNTIME_ROOT/api/run"
WEB_TMP="$RUNTIME_ROOT/web/tmp"
WEB_RUN="$RUNTIME_ROOT/web/run"
WEB_CACHE="$RUNTIME_ROOT/web/cache"
SHARED_DB="$DATA_ROOT/data/easy-stock/stock-data.db"
MANAGED_LABEL=io.easy-stock.managed
RUNTIME_IMAGE_FILE="$DATA_ROOT/config/backend-runtime-image"
SERVICE="$PROJECT/source/easy-stock-service"
CALENDAR_SOURCE="$STAGE/source/easy-stock-service/trading-calendar.json"
CALENDAR_FILE="$DATA_ROOT/config/trading-calendar.json"
WEB_SOURCE="$PROJECT/source/easy-stock-web"
GO_BACKEND_SOURCE="$PROJECT/source/easy-stock-analysis/backend"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_mount() {
    container=$1
    source=$2
    destination=$3
    rw=$4
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\t%s\t%t\n" .Type .Source .Destination .RW}}{{end}}' "$container")
    printf '%s\n' "$mounts" | awk -F '\t' -v source="$source" -v destination="$destination" -v rw="$rw" \
        '$1 == "bind" && $2 == source && $3 == destination && $4 == rw {found=1} END {exit !found}' \
        || fail "$container is missing required external bind mount $source -> $destination (rw=$rw)."
}

require_persistent_mount_count() {
    container=$1
    expected=$2
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\n" .Type .Destination}}{{end}}' "$container") || fail "Could not inspect mounts for $container."
    unexpected=$(printf '%s\n' "$mounts" | awk -F '\t' '$1 == "volume" || ($1 == "tmpfs" && ($2 == "/tmp" || $2 == "/run" || $2 == "/var/cache" || $2 == "/var/cache/nginx")) {print $1 ":" $2}')
    [ -z "$unexpected" ] || fail "$container has a volume or temporary mount on a managed runtime path."
    actual=$(printf '%s\n' "$mounts" | awk -F '\t' '$1 == "bind" {count++} END {print count+0}')
    [ "$actual" = "$expected" ] || fail "$container has $actual external bind mounts; expected exactly $expected."
}

require_api_mount_contract() {
    require_persistent_mount_count stockstrategy-api 7
    require_mount stockstrategy-api "$DATA_ROOT/data" /data true
    require_mount stockstrategy-api /mnt/4TB/dockerf/stock/forwardp /data/instock/forwardp false
    require_mount stockstrategy-api "$DATA_ROOT/logs/backend" /logs/backend true
    require_mount stockstrategy-api "$DATA_ROOT/logs/service" /logs/service false
    require_mount stockstrategy-api /etc/cron.d/stockstrategy-market-append /config/stockstrategy-market-append.cron false
    require_mount stockstrategy-api "$API_TMP" /tmp true
    require_mount stockstrategy-api "$API_RUN" /run true
}

require_web_mount_contract() {
    require_persistent_mount_count stockstrategy-web 5
    require_mount stockstrategy-web "$DATA_ROOT/logs/web" /logs/web true
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\t%s\t%t\n" .Type .Source .Destination .RW}}{{end}}' stockstrategy-web)
    printf '%s\n' "$mounts" | awk -F '\t' -v prefix="$DATA_ROOT/app/web-dist/" '$1 == "bind" && index($2, prefix) == 1 && $3 == "/usr/share/nginx/html" && $4 == "false" {found=1} END {exit !found}' || fail 'Web container is missing its read-only external release bind mount.'
    require_mount stockstrategy-web "$WEB_TMP" /tmp true
    require_mount stockstrategy-web "$WEB_RUN" /run true
    require_mount stockstrategy-web "$WEB_CACHE" /var/cache true
}

require_readonly_root() {
    container=$1
    [ "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container")" = true ] || fail "$container root filesystem is not read-only."
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
[ ! -L "$DATA_ROOT/runtime" ] || fail 'Runtime root is a symlink; refusing to use it.'
if [ -e "$DATA_ROOT/runtime" ] && [ ! -d "$DATA_ROOT/runtime" ]; then fail 'Runtime root is not a directory.'; fi
[ ! -e "$RUNTIME_ROOT" ] && [ ! -L "$RUNTIME_ROOT" ] || fail "Runtime directory already exists for build $BUILD_TAG."

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

[ -f "$CALENDAR_SOURCE" ] || fail "Trading calendar file is missing: $CALENDAR_SOURCE"
[ ! -L "$CALENDAR_FILE" ] || fail "Trading calendar target is a symlink; refusing to replace it: $CALENDAR_FILE"
if [ -e "$CALENDAR_FILE" ] && [ ! -f "$CALENDAR_FILE" ]; then
    fail "Trading calendar target is not a regular file: $CALENDAR_FILE"
fi
if [ -f "$CALENDAR_FILE" ]; then
    cmp -s "$CALENDAR_SOURCE" "$CALENDAR_FILE" || fail 'Bundled and external trading calendars differ; refusing to overwrite existing external configuration.'
else
    install -m 0644 "$CALENDAR_SOURCE" "$CALENDAR_FILE"
fi

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
[ -f "$PROJECT/docker/market-append.sh" ] || fail 'Market append scheduler script is missing.'
[ -f "$PROJECT/docker/stockstrategy-market-append.cron" ] || fail 'Market append cron schedule is missing.'
command -v flock >/dev/null 2>&1 || fail 'flock is required for safe market append scheduling.'
command -v crontab >/dev/null 2>&1 || fail 'cron is required for market append scheduling.'

mkdir -p "$SERVICE"
for pair in "data:$DATA_ROOT/data/service" "logs:$DATA_ROOT/logs/service" \
    "reviews:$DATA_ROOT/data/service/reviews" "screenshots:$DATA_ROOT/data/service/screenshots"; do
    name=${pair%%:*}
    target=${pair#*:}
    path="$SERVICE/$name"
    mkdir -p "$target"
    if [ -d "$path" ] && [ ! -L "$path" ]; then
        source_item=$(find "$path" -mindepth 1 -print -quit)
        target_item=$(find "$target" -mindepth 1 -print -quit)
        if [ -n "$source_item" ] && [ -n "$target_item" ]; then
            fail "Both source and external target contain $name data; refusing an ambiguous merge."
        fi
        if [ -n "$source_item" ]; then
            cp -a "$path/." "$target/"
            diff -qr -- "$path" "$target" >/dev/null || fail "External copy verification failed for $name; original data was retained."
        fi
        rm -rf -- "$path"
    elif [ -e "$path" ] && [ ! -L "$path" ]; then
        fail "$path exists and is not a directory; refusing to replace it."
    elif [ -L "$path" ]; then
        source_target=$(realpath -e -- "$path") || fail "$path is a broken symlink; refusing to replace it."
        external_target=$(realpath -e -- "$target") || fail "$target is unavailable."
        [ "$source_target" = "$external_target" ] || fail "$path already points to a different data directory."
    fi
    ln -sfn "$target" "$path"
done

rm -f "$SERVICE/trading-calendar.json"
ln -sfn "$CALENDAR_FILE" "$SERVICE/trading-calendar.json"

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
    [ -z "$id" ] || fail "Container $name already exists; refusing to remove its container layer. Use deploy-prebuilt.sh for a managed release."
done

port_owner=$(docker ps --filter publish=20073 --format '{{.Names}}' | head -n 1)
if ss -ltnH 2>/dev/null | awk '$4 ~ /:20073$/ {found=1} END {exit !found}'; then
    [ "$port_owner" = stockstrategy-web ] || fail 'TCP port 20073 is already used by another service.'
fi

ensure_image debian:bookworm-slim
ensure_image golang:1.26-alpine
ensure_image node:24-alpine
ensure_image nginx:stable-alpine

RUNTIME_DOCKERFILE="$PROJECT/docker/backend-runtime.Dockerfile"
[ -s "$RUNTIME_DOCKERFILE" ] || fail "Backend runtime Dockerfile is missing: $RUNTIME_DOCKERFILE"
runtime_sha=$(sha256sum "$RUNTIME_DOCKERFILE" | awk '{print $1}')
RUNTIME_IMAGE="stockstrategy/backend-runtime:base-$(printf '%s' "$runtime_sha" | cut -c1-12)"
previous_runtime_image=
if [ -L "$RUNTIME_IMAGE_FILE" ]; then
    fail "Pinned backend runtime image record is a symlink: $RUNTIME_IMAGE_FILE"
fi
if [ -e "$RUNTIME_IMAGE_FILE" ] && [ ! -f "$RUNTIME_IMAGE_FILE" ]; then
    fail "Pinned backend runtime image record is not a regular file: $RUNTIME_IMAGE_FILE"
fi
if [ -s "$RUNTIME_IMAGE_FILE" ]; then
    previous_runtime_image=$(cat "$RUNTIME_IMAGE_FILE")
    printf '%s\n' "$previous_runtime_image" | grep -Eq '^stockstrategy/backend-runtime:base-[0-9a-f]{12}$' || fail 'Pinned backend runtime image record is invalid.'
fi
if docker image inspect "$RUNTIME_IMAGE" >/dev/null 2>&1; then
    [ "$(docker image inspect --format '{{ index .Config.Labels "io.easy-stock.runtime-base" }}' "$RUNTIME_IMAGE")" = stockstrategy ] || fail "Runtime image has an invalid label: $RUNTIME_IMAGE"
    [ "$(docker image inspect --format '{{ index .Config.Labels "io.easy-stock.runtime-dockerfile" }}' "$RUNTIME_IMAGE")" = "$runtime_sha" ] || fail "Runtime image does not match its Dockerfile: $RUNTIME_IMAGE"
else
    [ "$previous_runtime_image" != "$RUNTIME_IMAGE" ] || fail "Pinned backend runtime image is missing; refusing to rebuild it from a potentially changed Debian base: $RUNTIME_IMAGE"
    docker build --memory=384m --memory-swap=384m --cpus=0.50 \
        --label "$MANAGED_LABEL=stockstrategy" --label "io.easy-stock.runtime-dockerfile=$runtime_sha" \
        --file "$PROJECT/docker/backend-runtime.Dockerfile" --tag "$RUNTIME_IMAGE" "$PROJECT/docker"
fi
[ "$(docker image inspect --format '{{ index .Config.Labels "io.easy-stock.runtime-base" }}' "$RUNTIME_IMAGE")" = stockstrategy ] || fail 'Backend runtime base image has an invalid label.'
[ "$(docker image inspect --format '{{ index .Config.Labels "io.easy-stock.runtime-dockerfile" }}' "$RUNTIME_IMAGE")" = "$runtime_sha" ] || fail 'Backend runtime image recipe hash does not match.'
docker run --rm --network none --entrypoint /bin/sh "$RUNTIME_IMAGE" -ec 'test ! -e /app/easy-stock-backend' || fail 'Backend runtime base unexpectedly contains the application binary.'
printf '%s\n' "$RUNTIME_IMAGE" > "$RUNTIME_IMAGE_FILE.tmp"
mv -f -- "$RUNTIME_IMAGE_FILE.tmp" "$RUNTIME_IMAGE_FILE"

docker build --memory=768m --label "$MANAGED_LABEL=stockstrategy" \
    --build-arg "BACKEND_RUNTIME_IMAGE=$RUNTIME_IMAGE" \
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

export EASY_STOCK_DATA_DB="$SHARED_DB"
if ! (cd "$SERVICE" && /usr/bin/python3 bars.py --universe >/dev/null && /usr/bin/python3 bars_us.py --universe >/dev/null); then
    fail 'Unable to seed the shared database with the existing CN/US automatic update lists.'
fi
unset EASY_STOCK_DATA_DB

chown -R 10001:10001 "$DATA_ROOT/data" "$DATA_ROOT/logs/backend" "$DATA_ROOT/logs/service"
chown -R 101:101 "$DATA_ROOT/logs/web"
mkdir -m 0700 -p "$DATA_ROOT/runtime"
mkdir -m 0700 "$RUNTIME_ROOT"
mkdir -m 0700 -p "$API_TMP" "$API_RUN" "$WEB_TMP" "$WEB_RUN"
mkdir -m 0755 -p "$WEB_CACHE/nginx"
chown 10001:10001 "$API_TMP" "$API_RUN"
chmod 0700 "$API_TMP" "$API_RUN"
chown 0:0 "$WEB_TMP" "$WEB_RUN"
chmod 1777 "$WEB_TMP"
chmod 0755 "$WEB_RUN"
chown 0:0 "$WEB_CACHE"
chmod 0755 "$WEB_CACHE"
chown 101:101 "$WEB_CACHE/nginx"
chmod 0750 "$WEB_CACHE/nginx"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
    docker network create --driver bridge --label "$MANAGED_LABEL=stockstrategy" "$NETWORK" >/dev/null
fi

docker run -d \
    --name stockstrategy-api \
    --label "$MANAGED_LABEL=stockstrategy" \
    --restart always \
    --network "$NETWORK" \
    --init \
    --read-only --mount "type=bind,source=$API_TMP,target=/tmp" --mount "type=bind,source=$API_RUN,target=/run" \
    --memory=512m --memory-swap=512m --cpus=1.00 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1:20081/api/health || exit 1' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=30s \
    --env-file "$DATA_ROOT/config/backend.env" \
    -e A_STOCK_ADDR=0.0.0.0:20081 \
    -e A_STOCK_APP_VERSION="$BUILD_TAG" \
    -e A_STOCK_DATA_ROOT=/data \
    -e A_STOCK_TRADING_CALENDAR=/data/config/trading-calendar.json \
    -e A_STOCK_DATA_DB=/data/easy-stock/stock-data.db \
    -e A_STOCK_TDX_FORWARDP_DIR=/data/instock/forwardp \
    -v /mnt/4TB/dockerf/stock/forwardp:/data/instock/forwardp:ro \
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
    -v "$DATA_ROOT/logs/service:/logs/service:ro" \
    -v "$PROJECT/docker/stockstrategy-market-append.cron:/config/stockstrategy-market-append.cron:ro" \
    "stockstrategy/backend:$BUILD_TAG"
require_api_mount_contract
require_readonly_root stockstrategy-api

docker run -d \
    --name stockstrategy-web \
    --label "$MANAGED_LABEL=stockstrategy" \
    --restart always \
    --network "$NETWORK" \
    --read-only --mount "type=bind,source=$WEB_TMP,target=/tmp" --mount "type=bind,source=$WEB_RUN,target=/run" \
    --mount "type=bind,source=$WEB_CACHE,target=/var/cache" \
    --memory=128m --memory-swap=128m --cpus=0.50 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1/' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=10s \
    -p 192.168.50.60:20073:80 \
    -v "$WEB_DIST:/usr/share/nginx/html:ro" \
    -v "$DATA_ROOT/logs/web:/logs/web" \
    "stockstrategy/web:$BUILD_TAG"
require_web_mount_contract
require_readonly_root stockstrategy-web

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

chmod 0755 "$PROJECT/docker/market-append.sh"
install -m 0644 "$PROJECT/docker/stockstrategy-market-append.cron" /etc/cron.d/stockstrategy-market-append
systemctl enable --now cron

health=$(docker exec stockstrategy-web wget -q -T 10 -O - http://127.0.0.1/api/health)
printf 'API health: %s\n' "$health"
printf 'Web URL: http://192.168.50.60:20073\n'
printf 'Project files: %s\n' "$PROJECT"
printf 'Persistent root: %s\n' "$DATA_ROOT"
printf 'Unified SQLite database: %s\n' "$SHARED_DB"
printf 'Logs: %s/logs/{backend,web,service}\n' "$DATA_ROOT"
printf 'Auto-start: Docker restart policy "always"\n'
