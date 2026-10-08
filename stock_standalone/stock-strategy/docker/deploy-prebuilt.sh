#!/usr/bin/env bash
##pwsh -NoProfile -ExecutionPolicy Bypass -File "stock-strategy\build-and-deploy.ps1"
set -Eeuo pipefail
umask 077

ARCHIVE=
RELEASE=
if [ "$#" -ge 1 ]; then ARCHIVE="$1"; fi
if [ "$#" -ge 2 ]; then RELEASE="$2"; fi
[ -n "$ARCHIVE" ] || { echo 'Release archive is required.' >&2; exit 2; }
[[ "$RELEASE" =~ ^[0-9]{14}$ ]] || { echo 'Invalid release tag.' >&2; exit 2; }

PROJECT=/root/johnson/stock-strategy
DATA_ROOT=/mnt/4TB/dockerf/stockstrategy
NETWORK=stockstrategy-net
MANAGED_LABEL=io.easy-stock.managed
STAGE=$(CDPATH= cd -- "$(dirname -- "$ARCHIVE")" && pwd)
UNPACK="$STAGE/unpacked"
API_IMAGE="stockstrategy/backend:$RELEASE"
WEB_IMAGE="stockstrategy/web:$RELEASE"
API_BACKUP="stockstrategy-api-rollback-$RELEASE"
WEB_BACKUP="stockstrategy-web-rollback-$RELEASE"
IMAGE_BUILDER="stockstrategy-image-stage-$RELEASE"
API_CHECK="stockstrategy-api-check-$RELEASE"
WEB_DIST="$DATA_ROOT/app/web-dist/$RELEASE"
CALENDAR_BACKUP="$STAGE/trading-calendar.previous.json"
MARKET_APPEND_BACKUP="$STAGE/market-append.previous.sh"
API_OLD_MOVED=0
WEB_OLD_MOVED=0
API_NEW_CREATED=0
WEB_NEW_CREATED=0
CALENDAR_UPDATED=0
MARKET_APPEND_UPDATED=0
SUCCESS=0

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

rollback() {
    result=$?
    set +e
    docker rm -f "$API_CHECK" "$IMAGE_BUILDER" >/dev/null 2>&1
    if [ "$SUCCESS" -ne 1 ]; then
        if [ "$WEB_NEW_CREATED" -eq 1 ]; then docker rm -f stockstrategy-web >/dev/null 2>&1; fi
        if [ "$API_NEW_CREATED" -eq 1 ]; then docker rm -f stockstrategy-api >/dev/null 2>&1; fi
        if [ "$WEB_OLD_MOVED" -eq 1 ]; then
            docker rename "$WEB_BACKUP" stockstrategy-web >/dev/null 2>&1
            docker start stockstrategy-web >/dev/null 2>&1
        elif docker inspect stockstrategy-web >/dev/null 2>&1; then
            docker start stockstrategy-web >/dev/null 2>&1
        fi
        if [ "$API_OLD_MOVED" -eq 1 ]; then
            docker rename "$API_BACKUP" stockstrategy-api >/dev/null 2>&1
            docker start stockstrategy-api >/dev/null 2>&1
        elif docker inspect stockstrategy-api >/dev/null 2>&1; then
            docker start stockstrategy-api >/dev/null 2>&1
        fi
        if [ "$CALENDAR_UPDATED" -eq 1 ] && [ -f "$CALENDAR_BACKUP" ]; then
            install -m 0644 "$CALENDAR_BACKUP" "$DATA_ROOT/config/trading-calendar.json"
            ln -sfn "$DATA_ROOT/config/trading-calendar.json" "$PROJECT/source/easy-stock-service/trading-calendar.json"
        fi
        if [ "$MARKET_APPEND_UPDATED" -eq 1 ] && [ -f "$MARKET_APPEND_BACKUP" ]; then
            install -m 0755 "$MARKET_APPEND_BACKUP" "$PROJECT/docker/market-append.sh"
        fi
        [ -d "$WEB_DIST" ] && rm -rf -- "$WEB_DIST"
        docker image rm "$API_IMAGE" >/dev/null 2>&1
    else
        docker rm "$WEB_BACKUP" "$API_BACKUP" >/dev/null 2>&1
    fi
    exit "$result"
}
trap rollback EXIT

command -v docker >/dev/null 2>&1 || fail 'Docker is unavailable.'
docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable.'
mountpoint -q /mnt/4TB || fail '/mnt/4TB is not mounted.'
[ -f "$PROJECT/.stockstrategy-managed" ] || fail 'Project marker is missing.'
[ -f "$DATA_ROOT/.stockstrategy-managed" ] || fail 'Persistent-data marker is missing.'
[ -f "$DATA_ROOT/config/backend.env" ] || fail 'Backend environment file is missing.'
[ -f "$PROJECT/docker/nginx.conf" ] || fail 'Managed nginx configuration is missing.'
[ -f "$PROJECT/docker/web-entrypoint.sh" ] || fail 'Managed web entrypoint is missing.'
[ -f /etc/cron.d/stockstrategy-market-append ] || fail 'Installed market append cron schedule is missing.'

available_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
data_free_kb=$(df -Pk /mnt/4TB | awk 'END {print $4}')
docker_root=$(docker info --format '{{.DockerRootDir}}')
docker_free_kb=$(df -Pk "$docker_root" | awk 'END {print $4}')
[ "$available_kb" -ge 524288 ] || fail 'Less than 512 MiB host memory is available; delaying deployment.'
[ "$data_free_kb" -ge 1048576 ] || fail 'Less than 1 GiB is free on the persistent disk.'
[ "$docker_free_kb" -ge 1048576 ] || fail 'Less than 1 GiB is free in Docker storage.'

for name in stockstrategy-api stockstrategy-web; do
    [ "$(docker inspect --format '{{.State.Health.Status}}' "$name" 2>/dev/null || true)" = healthy ] || fail "$name is unhealthy; refusing to replace it."
    [ "$(docker inspect --format '{{ index .Config.Labels "io.easy-stock.managed" }}' "$name")" = stockstrategy ] || fail "$name is not marked as managed."
    [ "$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$name")" = always ] || fail "$name does not use restart policy always."
done
case "$(docker inspect --format '{{.Config.Image}}' stockstrategy-api)" in stockstrategy/backend:*) ;; *) fail 'Current API image is not the managed backend image.' ;; esac
case "$(docker inspect --format '{{.Config.Image}}' stockstrategy-web)" in stockstrategy/web:*) ;; *) fail 'Current web image is not the managed web image.' ;; esac
docker network inspect "$NETWORK" >/dev/null 2>&1 || fail 'Managed Docker network is missing.'

[ -s "$ARCHIVE" ] || fail 'Release archive is missing.'
mkdir -p "$UNPACK"
tar -xzf "$ARCHIVE" -C "$UNPACK"
[ -s "$UNPACK/backend/easy-stock-backend" ] || fail 'Prebuilt backend binary is missing.'
[ -s "$UNPACK/web-dist/index.html" ] || fail 'Prebuilt frontend index is missing.'
[ -s "$UNPACK/source/easy-stock-service/trading-calendar.json" ] || fail 'Source trading calendar is missing.'
[ -s "$UNPACK/docker/market-append.sh" ] || fail 'Updated market append script is missing.'

cp -a "$DATA_ROOT/config/trading-calendar.json" "$CALENDAR_BACKUP"
calendar_tmp="$DATA_ROOT/config/.trading-calendar.$RELEASE.tmp"
install -m 0644 "$UNPACK/source/easy-stock-service/trading-calendar.json" "$calendar_tmp"
python3 - "$calendar_tmp" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as source:
    data = json.load(source)
if data.get("schema_version") != 1 or not isinstance(data.get("markets"), dict):
    raise SystemExit("Trading calendar schema is invalid")
PY
mv -f -- "$calendar_tmp" "$DATA_ROOT/config/trading-calendar.json"
CALENDAR_UPDATED=1

mkdir -p "$PROJECT/source" "$DATA_ROOT/app/web-dist" "$DATA_ROOT/logs/backend" "$DATA_ROOT/logs/web" "$DATA_ROOT/logs/service"
cp -a "$UNPACK/source/." "$PROJECT/source/"
ln -sfn "$DATA_ROOT/config/trading-calendar.json" "$PROJECT/source/easy-stock-service/trading-calendar.json"
cp -a "$PROJECT/docker/market-append.sh" "$MARKET_APPEND_BACKUP"
MARKET_APPEND_UPDATED=1
install -m 0755 "$UNPACK/docker/market-append.sh" "$PROJECT/docker/.market-append.$RELEASE.tmp"
mv -f -- "$PROJECT/docker/.market-append.$RELEASE.tmp" "$PROJECT/docker/market-append.sh"
mkdir -p "$WEB_DIST"
cp -a "$UNPACK/web-dist/." "$WEB_DIST/"
chown -R 101:101 "$DATA_ROOT/logs/web"

old_api_image=$(docker inspect --format '{{.Config.Image}}' stockstrategy-api)
old_web_image=$(docker inspect --format '{{.Config.Image}}' stockstrategy-web)
docker image inspect "$old_api_image" >/dev/null 2>&1 || fail 'Current backend runtime image is unavailable.'
docker image inspect "$old_web_image" >/dev/null 2>&1 || fail 'Current web image is unavailable.'

# Reuse the current runtime image; Go and Node compilers never run on the memory-limited LXC host.
docker create --name "$IMAGE_BUILDER" --network none --user 0:0 --memory=96m --memory-swap=96m --cpus=0.25 --pids-limit=32 --log-opt max-size=1m --log-opt max-file=1 --entrypoint /bin/sh "$old_api_image" -c 'sleep 300' >/dev/null
docker cp "$UNPACK/backend/easy-stock-backend" "$IMAGE_BUILDER:/tmp/easy-stock-backend"
docker start "$IMAGE_BUILDER" >/dev/null
docker exec "$IMAGE_BUILDER" /bin/sh -ec 'cp /tmp/easy-stock-backend /app/easy-stock-backend && chown 10001:10001 /app/easy-stock-backend && chmod 0755 /app/easy-stock-backend && rm -f /tmp/easy-stock-backend'
docker stop -t 1 "$IMAGE_BUILDER" >/dev/null
docker commit --change 'USER 10001:10001' --change 'ENTRYPOINT ["/app/easy-stock-backend"]' --change 'CMD []' --change "LABEL $MANAGED_LABEL=stockstrategy" "$IMAGE_BUILDER" "$API_IMAGE" >/dev/null
docker rm "$IMAGE_BUILDER" >/dev/null
docker tag "$old_web_image" "$WEB_IMAGE"

# Smoke-test the new executable with temporary paths, no external network, and no persistent database.
docker run -d --name "$API_CHECK" --network none --memory=112m --memory-swap=112m --cpus=0.25 --pids-limit=32 --log-opt max-size=1m --log-opt max-file=1 \
    -e A_STOCK_ADDR=127.0.0.1:20081 -e A_STOCK_APP_VERSION="$RELEASE-check" \
    -e A_STOCK_DATA_ROOT=/tmp/easy-stock-check -e A_STOCK_TRADING_CALENDAR=/config/trading-calendar.json \
    -e A_STOCK_DATA_DB=/tmp/easy-stock-check/stock-data.db -e A_STOCK_LOG_DIR=/tmp/easy-stock-check/logs \
    -e A_STOCK_SETTINGS_PATH=/tmp/easy-stock-check/settings.json -e A_STOCK_MASTERY_CACHE=/tmp/easy-stock-check/mastery \
    -e A_STOCK_HERMES_HOME=/tmp/easy-stock-check/hermes -e A_STOCK_HERMES_WORKDIR=/app \
    -e HOME=/tmp -e XDG_CONFIG_HOME=/tmp/config -e TZ=Asia/Hong_Kong \
    -v "$DATA_ROOT/config/trading-calendar.json:/config/trading-calendar.json:ro" "$API_IMAGE" >/dev/null
api_check_ok=0
for _ in $(seq 1 30); do
    if docker exec "$API_CHECK" wget -q -T 2 -O /dev/null http://127.0.0.1:20081/api/health >/dev/null 2>&1; then api_check_ok=1; break; fi
    status=$(docker inspect --format '{{.State.Status}}' "$API_CHECK" 2>/dev/null || true)
    [ "$status" = running ] || break
    sleep 2
done
[ "$api_check_ok" -eq 1 ] || fail 'Predeployment API health check failed; live containers are unchanged.'
docker rm -f "$API_CHECK" >/dev/null

docker stop -t 10 stockstrategy-web stockstrategy-api >/dev/null
docker rename stockstrategy-web "$WEB_BACKUP"
WEB_OLD_MOVED=1
docker rename stockstrategy-api "$API_BACKUP"
API_OLD_MOVED=1

docker run -d \
    --name stockstrategy-api --label "$MANAGED_LABEL=stockstrategy" --restart always --network "$NETWORK" --init \
    --memory=512m --memory-swap=512m --cpus=1.00 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1:20081/api/health || exit 1' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=30s \
    --env-file "$DATA_ROOT/config/backend.env" \
    -e A_STOCK_ADDR=0.0.0.0:20081 -e A_STOCK_APP_VERSION="$RELEASE" \
    -e A_STOCK_DATA_ROOT=/data -e A_STOCK_TRADING_CALENDAR=/data/config/trading-calendar.json \
    -e A_STOCK_DATA_DB=/data/easy-stock/stock-data.db -e A_STOCK_LOG_DIR=/logs/backend \
    -e A_STOCK_SETTINGS_PATH=/data/easy-stock/settings.json -e A_STOCK_MASTERY_CACHE=/data/trading-mastery \
    -e A_STOCK_HERMES_HOME=/data/hermes-home -e A_STOCK_HERMES_WORKDIR=/app \
    -e HOME=/data -e XDG_CONFIG_HOME=/data/config -e TZ=Asia/Hong_Kong \
    -v "$DATA_ROOT/data:/data" -v "$DATA_ROOT/logs/backend:/logs/backend" \
    -v "$DATA_ROOT/logs/service:/logs/service:ro" \
    -v /etc/cron.d/stockstrategy-market-append:/config/stockstrategy-market-append.cron:ro \
    "$API_IMAGE" >/dev/null
API_NEW_CREATED=1

wait_healthy() {
    name=$1
    attempts=$2
    while [ "$attempts" -gt 0 ]; do
        status=$(docker inspect --format '{{.State.Health.Status}}' "$name" 2>/dev/null || true)
        [ "$status" = healthy ] && return 0
        [ "$status" = unhealthy ] && break
        attempts=$((attempts - 1))
        sleep 2
    done
    return 1
}
wait_healthy stockstrategy-api 45 || fail 'New API did not become healthy; rolling back.'

docker run -d \
    --name stockstrategy-web --label "$MANAGED_LABEL=stockstrategy" --restart always --network "$NETWORK" \
    --memory=128m --memory-swap=128m --cpus=0.50 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1/' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=10s \
    -p 192.168.50.60:20073:80 \
    -v "$WEB_DIST:/usr/share/nginx/html:ro" -v "$DATA_ROOT/logs/web:/logs/web" "$WEB_IMAGE" >/dev/null
WEB_NEW_CREATED=1
wait_healthy stockstrategy-web 30 || fail 'New web container did not become healthy; rolling back.'
docker exec stockstrategy-web wget -q -T 10 -O /dev/null http://127.0.0.1/api/health || fail 'Web-to-API health check failed; rolling back.'

SUCCESS=1
printf 'Deployment healthy: release=%s, url=http://192.168.50.60:20073; persistent data and logs retained.\n' "$RELEASE"
