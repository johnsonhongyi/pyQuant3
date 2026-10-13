#!/usr/bin/env bash
##pwsh -NoProfile -ExecutionPolicy Bypass -File "stock-strategy\build-and-deploy.ps1"
set -Eeuo pipefail
umask 077

command -v flock >/dev/null 2>&1 || { echo 'flock is required.' >&2; exit 1; }
exec 9>/run/lock/stockstrategy-deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }

ARCHIVE=
RELEASE=
if [ "$#" -ge 1 ]; then ARCHIVE="$1"; fi
if [ "$#" -ge 2 ]; then RELEASE="$2"; fi
[ -n "$ARCHIVE" ] || { echo 'Release archive is required.' >&2; exit 2; }
[[ "$RELEASE" =~ ^[0-9]{14}$ ]] || { echo 'Invalid release tag.' >&2; exit 2; }
[ "$#" -eq 3 ] && [ "$3" = "--allow-layered-image" ] || { echo 'Explicit --allow-layered-image authorization is required before creating a backend image.' >&2; exit 2; }

PROJECT=/root/johnson/stock-strategy
DATA_ROOT=/mnt/4TB/dockerf/stockstrategy
NETWORK=stockstrategy-net
MANAGED_LABEL=io.easy-stock.managed
STAGE=$(CDPATH= cd -- "$(dirname -- "$ARCHIVE")" && pwd)
UNPACK="$STAGE/unpacked"
API_IMAGE="stockstrategy/backend:$RELEASE"
API_BASE_IMAGE="stockstrategy/backend:flatbase-20261010171545"
API_BASE_IMAGE_ID="sha256:ed8cbe9544efbcd5f4a50039b79884d43d1d2b662dc9ee6715325c1525d52d6d"
RELEASE_NOTE='Web user authentication and LAN access.'
API_BACKUP="stockstrategy-api-rollback-$RELEASE"
WEB_BACKUP="stockstrategy-web-rollback-$RELEASE"
IMAGE_BUILDER="stockstrategy-image-stage-$RELEASE"
API_CHECK="stockstrategy-api-check-$RELEASE"
WEB_DIST="$DATA_ROOT/app/web-dist/$RELEASE"
ROLLBACK_DIR="$DATA_ROOT/rollback/$RELEASE"
RUNTIME_ROOT="$DATA_ROOT/runtime/$RELEASE"
API_TMP="$RUNTIME_ROOT/api/tmp"
API_RUN="$RUNTIME_ROOT/api/run"
WEB_TMP="$RUNTIME_ROOT/web/tmp"
WEB_RUN="$RUNTIME_ROOT/web/run"
WEB_CACHE="$RUNTIME_ROOT/web/cache"
SMOKE_ROOT="$ROLLBACK_DIR/smoke"
SMOKE_CREATED=0
API_OLD_MOVED=0
WEB_OLD_MOVED=0
API_NEW_CREATED=0
WEB_NEW_CREATED=0
SOURCE_UPDATED=0
SUCCESS=0

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_mount() {
    container=$1
    source=$2
    destination=$3
    rw=$4
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\t%s\t%t\n" .Type .Source .Destination .RW}}{{end}}' "$container")
    printf '%s\n' "$mounts" | awk -F '\t' -v source="$source" -v destination="$destination" -v rw="$rw" \
        '$1 == "bind" && $2 == source && $3 == destination && $4 == rw {found=1} END {exit !found}' \
        || fail "$container is missing required persistent bind mount $source -> $destination (rw=$rw)."
}

mount_count() {
    local container=$1 mounts unexpected
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\n" .Type .Destination}}{{end}}' "$container") || return 1
    unexpected=$(printf '%s\n' "$mounts" | awk -F '\t' '$1 == "volume" || ($1 == "tmpfs" && ($2 == "/tmp" || $2 == "/run" || $2 == "/var/cache" || $2 == "/var/cache/nginx")) {print $1 ":" $2}')
    [ -z "$unexpected" ] || return 2
    printf '%s\n' "$mounts" | awk -F '\t' '$1 == "bind" {count++} END {print count+0}'
}

require_mount_count() {
    container=$1
    expected=$2
    actual=$(mount_count "$container") || fail "$container has non-bind mounts; all writable runtime paths must use external bind mounts."
    [ "$actual" = "$expected" ] || fail "$container has $actual external mounts; expected exactly $expected managed bind mounts."
}

container_runtime_root() {
    local container=$1 release
    release=$(docker inspect --format '{{ index .Config.Labels "io.easy-stock.app-version" }}' "$container")
    [[ "$release" =~ ^[0-9]{14}$ ]] || fail "$container has no valid release label for runtime mounts."
    printf '%s/runtime/%s\n' "$DATA_ROOT" "$release"
}

require_api_mount_contract() {
    container=$1
    expected_count=$2
    require_mount_count "$container" "$expected_count"
    require_mount "$container" "$DATA_ROOT/data" /data true
    require_mount "$container" /mnt/4TB/dockerf/stock/forwardp /data/instock/forwardp false
    require_mount "$container" "$DATA_ROOT/logs/backend" /logs/backend true
    require_mount "$container" "$DATA_ROOT/logs/service" /logs/service false
    require_mount "$container" /etc/cron.d/stockstrategy-market-append /config/stockstrategy-market-append.cron false
    if [ "$expected_count" = 6 ] || [ "$expected_count" = 8 ]; then
        require_mount "$container" "$DATA_ROOT/config/trading-calendar.json" /config/trading-calendar.json false
    fi
    if [ "$expected_count" = 8 ]; then
        require_mount "$container" "$(container_runtime_root "$container")/api/tmp" /tmp true
        require_mount "$container" "$(container_runtime_root "$container")/api/run" /run true
    fi
}

require_web_mount_contract() {
    container=$1
    expected_count=$2
    require_mount_count "$container" "$expected_count"
    require_mount "$container" "$DATA_ROOT/logs/web" /logs/web true
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\t%s\t%t\n" .Type .Source .Destination .RW}}{{end}}' "$container")
    printf '%s\n' "$mounts" | awk -F '\t' -v prefix="$DATA_ROOT/app/web-dist/" \
        '$1 == "bind" && index($2, prefix) == 1 && $3 == "/usr/share/nginx/html" && $4 == "false" {found=1} END {exit !found}' \
        || fail "$container is missing its read-only web release bind mount under $DATA_ROOT/app/web-dist."
    if [ "$expected_count" = 5 ]; then
        require_mount "$container" "$(container_runtime_root "$container")/web/tmp" /tmp true
        require_mount "$container" "$(container_runtime_root "$container")/web/run" /run true
        require_mount "$container" "$(container_runtime_root "$container")/web/cache" /var/cache true
    fi
}

require_readonly_root() {
    container=$1
    readonly=$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container")
    [ "$readonly" = true ] || fail "$container root filesystem is writable; persistent changes must use external mounts."
}

require_clean_container_layer() {
    container=$1
    strict=false
    if [ "$#" -ge 2 ]; then strict=$2; fi
    changes=$(docker diff "$container") || fail "Could not inspect writable-layer changes for $container."
    unexpected=$(printf '%s\n' "$changes" | awk -v strict="$strict" '
        NF < 2 { next }
        $2 == "/config" || $2 == "/config/stockstrategy-market-append.cron" || $2 == "/config/trading-calendar.json" { next }
        $2 == "/data" { next }
        $2 == "/logs" || index($2, "/logs/") == 1 { next }
        $2 == "/tmp" || index($2, "/tmp/") == 1 || $2 == "/run" || index($2, "/run/") == 1 || $2 == "/var/run" || index($2, "/var/run/") == 1 || $2 == "/var/cache" || $2 == "/var" || $2 == "/var/cache/nginx" || index($2, "/var/cache/nginx/") == 1 {
            if (strict == "true") print
            next
        }
        $2 == "/usr" || $2 == "/usr/sbin" || $2 == "/usr/sbin/docker-init" { next }
        { print }
    ')
    [ -z "$unexpected" ] || fail "$container has unmounted writable-layer changes; externalize or explicitly preserve them before rebuilding: $unexpected"
}

restore_source_snapshot() {
    archive=$1
    restore_root=$(mktemp -d "$PROJECT/.source-restore.XXXXXX") || return 1
    previous_root="$restore_root/source.previous"
    if ! tar -xzf "$archive" -C "$restore_root" || [ ! -d "$restore_root/source" ]; then
        rm -rf -- "$restore_root"
        return 1
    fi
    if ! mv -- "$PROJECT/source" "$previous_root"; then
        rm -rf -- "$restore_root"
        return 1
    fi
    if mv -- "$restore_root/source" "$PROJECT/source"; then
        rm -rf -- "$previous_root" "$restore_root"
        return 0
    fi
    mv -- "$previous_root" "$PROJECT/source"
    rm -rf -- "$restore_root"
    return 1
}

rollback() {
    result=$?
    set +e
    docker rm -f "$API_CHECK" "$IMAGE_BUILDER" >/dev/null 2>&1
    if [ "$SMOKE_CREATED" -eq 1 ] && [ "$SMOKE_ROOT" = "$ROLLBACK_DIR/smoke" ] && [ -d "$SMOKE_ROOT" ] && [ ! -L "$SMOKE_ROOT" ]; then
        rm -rf -- "$SMOKE_ROOT"
    fi
    if [ "$SUCCESS" -ne 1 ]; then
        if [ "$WEB_NEW_CREATED" -eq 1 ]; then docker rm -f stockstrategy-web >/dev/null 2>&1; fi
        if [ "$API_NEW_CREATED" -eq 1 ]; then docker rm -f stockstrategy-api >/dev/null 2>&1; fi
        if [ "$SOURCE_UPDATED" -eq 1 ] && [ -s "$ROLLBACK_DIR/source.tar.gz" ]; then
            restore_source_snapshot "$ROLLBACK_DIR/source.tar.gz" >/dev/null 2>&1
        fi
        if [ "$WEB_OLD_MOVED" -eq 1 ]; then
            docker rename "$WEB_BACKUP" stockstrategy-web >/dev/null 2>&1
            docker update --restart=always stockstrategy-web >/dev/null 2>&1
            docker start stockstrategy-web >/dev/null 2>&1
        elif docker inspect stockstrategy-web >/dev/null 2>&1; then
            docker update --restart=always stockstrategy-web >/dev/null 2>&1
            docker start stockstrategy-web >/dev/null 2>&1
        fi
        if [ "$API_OLD_MOVED" -eq 1 ]; then
            docker rename "$API_BACKUP" stockstrategy-api >/dev/null 2>&1
            docker update --restart=always stockstrategy-api >/dev/null 2>&1
            docker start stockstrategy-api >/dev/null 2>&1
        elif docker inspect stockstrategy-api >/dev/null 2>&1; then
            docker update --restart=always stockstrategy-api >/dev/null 2>&1
            docker start stockstrategy-api >/dev/null 2>&1
        fi
        [ -d "$WEB_DIST" ] && rm -rf -- "$WEB_DIST"
        docker image rm "$API_IMAGE" >/dev/null 2>&1
    else
        docker update --restart=no "$WEB_BACKUP" "$API_BACKUP" >/dev/null 2>&1
        [ -d "$ROLLBACK_DIR" ] && touch "$ROLLBACK_DIR/COMPLETE"
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
old_api_mounts=$(mount_count stockstrategy-api) || fail 'Current API has invalid runtime mounts.'
case "$old_api_mounts" in 5|6|8) ;; *) fail "Current API has unsupported external mount count: $old_api_mounts" ;; esac
require_api_mount_contract stockstrategy-api "$old_api_mounts"
old_web_mounts=$(mount_count stockstrategy-web) || fail 'Current web has invalid runtime mounts.'
case "$old_web_mounts" in 2|5) ;; *) fail "Current web has unsupported external mount count: $old_web_mounts" ;; esac
require_web_mount_contract stockstrategy-web "$old_web_mounts"
require_clean_container_layer stockstrategy-api
require_clean_container_layer stockstrategy-web
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
[ -s "$UNPACK/docker/stockstrategy-market-append.cron" ] || fail 'Updated market append cron schedule is missing.'
[ -s "$UNPACK/docker/rollback-prebuilt.sh" ] || fail 'Rollback helper is missing.'

# Persistent runtime configuration is operator-managed; reject package drift before touching it.
cmp -s "$UNPACK/source/easy-stock-service/trading-calendar.json" "$DATA_ROOT/config/trading-calendar.json" \
    || fail 'Release trading calendar differs from persistent configuration; review that config change separately.'
cmp -s "$UNPACK/docker/market-append.sh" "$PROJECT/docker/market-append.sh" \
    || fail 'Release market-append script differs from installed host configuration; review that config change separately.'
cmp -s "$UNPACK/docker/stockstrategy-market-append.cron" /etc/cron.d/stockstrategy-market-append \
    || fail 'Release cron schedule differs from installed configuration; review that config change separately.'

old_api_image=$(docker inspect --format '{{.Config.Image}}' stockstrategy-api)
old_web_image=$(docker inspect --format '{{.Config.Image}}' stockstrategy-web)
[[ "$old_api_image" =~ ^stockstrategy/backend:[0-9]{14}$ ]] || fail "Current API image tag is not a release tag: $old_api_image"
[[ "$old_web_image" =~ ^stockstrategy/web:[0-9]{14}$ ]] || fail "Current web image tag is not a release tag: $old_web_image"
docker image inspect "$old_api_image" >/dev/null 2>&1 || fail 'Current backend runtime image is unavailable.'
docker image inspect "$old_web_image" >/dev/null 2>&1 || fail 'Current web image is unavailable.'

[ "$(docker image inspect --format '{{.Id}}' "$API_BASE_IMAGE")" = "$API_BASE_IMAGE_ID" ] || fail "Pinned flat backend base is missing or changed: $API_BASE_IMAGE"
[ "$(docker image inspect --format '{{ index .Config.Labels "io.easy-stock.flat-base" }}' "$API_BASE_IMAGE")" = 20261010171545 ] || fail 'Pinned backend base label is invalid.'
api_base_layers=$(docker image inspect --format '{{len .RootFS.Layers}}' "$API_BASE_IMAGE")
[ "$api_base_layers" = 1 ] || fail "Pinned backend base must contain exactly one layer; got $api_base_layers."
base_first_layer=$(docker image inspect --format '{{index .RootFS.Layers 0}}' "$API_BASE_IMAGE")
old_api_layers=$(docker image inspect --format '{{len .RootFS.Layers}}' "$old_api_image")
old_api_first_layer=$(docker image inspect --format '{{index .RootFS.Layers 0}}' "$old_api_image")
[ "$old_api_first_layer" = "$base_first_layer" ] || fail 'Current API does not descend from the pinned flat backend base.'
[ "$old_api_layers" = "$api_base_layers" ] || [ "$old_api_layers" = "$((api_base_layers + 1))" ] || fail "Current API has $old_api_layers layers; expected the flat base or one release layer."
docker run --rm --network none --entrypoint /bin/sh "$API_BASE_IMAGE" -ec 'test -x /app/easy-stock-backend' || fail 'Pinned flat backend base is missing its application binary.'
[ ! -e "$ROLLBACK_DIR" ] || fail "Rollback snapshot already exists for release $RELEASE."
[ ! -L "$DATA_ROOT/runtime" ] || fail 'Runtime root is a symlink.'
if [ -e "$DATA_ROOT/runtime" ] && [ ! -d "$DATA_ROOT/runtime" ]; then fail 'Runtime root is not a directory.'; fi
[ ! -e "$RUNTIME_ROOT" ] && [ ! -L "$RUNTIME_ROOT" ] || fail "Runtime directory already exists for release $RELEASE."
mkdir -m 0700 -p "$ROLLBACK_DIR"
tar -czf "$ROLLBACK_DIR/source.tar.gz" -C "$PROJECT" source
cp -a "$DATA_ROOT/config/trading-calendar.json" "$ROLLBACK_DIR/trading-calendar.json"
cp -a "$PROJECT/docker/market-append.sh" "$ROLLBACK_DIR/market-append.sh"
cp -a /etc/cron.d/stockstrategy-market-append "$ROLLBACK_DIR/stockstrategy-market-append.cron"
printf 'release=%s\nrelease_note=%s\napi_image=%s\nweb_image=%s\napi_base_image=%s\n' \
    "$RELEASE" "$RELEASE_NOTE" "$old_api_image" "$old_web_image" "$API_BASE_IMAGE" > "$ROLLBACK_DIR/manifest.txt"
(
    cd "$ROLLBACK_DIR"
    sha256sum source.tar.gz trading-calendar.json market-append.sh stockstrategy-market-append.cron manifest.txt > SHA256SUMS
)

mkdir -p "$PROJECT/source" "$DATA_ROOT/app/web-dist" "$DATA_ROOT/logs/backend" "$DATA_ROOT/logs/web" "$DATA_ROOT/logs/service"
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
SOURCE_UPDATED=1
cp -a "$UNPACK/source/." "$PROJECT/source/"
ln -sfn "$DATA_ROOT/config/trading-calendar.json" "$PROJECT/source/easy-stock-service/trading-calendar.json"
mkdir -p "$WEB_DIST"
cp -a "$UNPACK/web-dist/." "$WEB_DIST/"
chown 101:101 "$DATA_ROOT/logs/web"

# Build every release from the same verified one-layer backend base; never inherit the previous release.
docker create --name "$IMAGE_BUILDER" --network none --user 0:0 --memory=96m --memory-swap=96m --cpus=0.25 --pids-limit=32 --log-opt max-size=1m --log-opt max-file=1 --entrypoint /bin/sh "$API_BASE_IMAGE" -c 'sleep 300' >/dev/null
docker cp "$UNPACK/backend/easy-stock-backend" "$IMAGE_BUILDER:/tmp/easy-stock-backend"
docker start "$IMAGE_BUILDER" >/dev/null
docker exec "$IMAGE_BUILDER" /bin/sh -ec 'cp /tmp/easy-stock-backend /app/easy-stock-backend && chown 10001:10001 /app/easy-stock-backend && chmod 0755 /app/easy-stock-backend && rm -f /tmp/easy-stock-backend'
docker stop -t 1 "$IMAGE_BUILDER" >/dev/null
docker commit --change 'USER 10001:10001' --change 'ENTRYPOINT ["/app/easy-stock-backend"]' --change 'CMD []' \
    --change "LABEL $MANAGED_LABEL=stockstrategy" --change "LABEL io.easy-stock.app-version=$RELEASE" \
    --change "LABEL io.easy-stock.release-note=\"$RELEASE_NOTE\"" "$IMAGE_BUILDER" "$API_IMAGE" >/dev/null
api_layers=$(docker image inspect --format '{{len .RootFS.Layers}}' "$API_IMAGE")
expected_api_layers=$((api_base_layers + 1))
[ "$api_layers" = "$expected_api_layers" ] || fail "Backend release image has $api_layers layers; expected $expected_api_layers from the pinned flat base."
[ "$(docker image inspect --format '{{ index .Config.Labels "io.easy-stock.release-note" }}' "$API_IMAGE")" = "$RELEASE_NOTE" ] || fail 'Backend release note label is missing.'
docker rm "$IMAGE_BUILDER" >/dev/null

# Smoke-test with isolated external paths, no external network, and no persistent database.
mkdir -m 0700 -p "$SMOKE_ROOT/api/tmp" "$SMOKE_ROOT/api/run"
chown 10001:10001 "$SMOKE_ROOT/api/tmp" "$SMOKE_ROOT/api/run"
chmod 0700 "$SMOKE_ROOT/api/tmp" "$SMOKE_ROOT/api/run"
SMOKE_CREATED=1
docker run -d --name "$API_CHECK" --network none --read-only --mount "type=bind,source=$SMOKE_ROOT/api/tmp,target=/tmp" --mount "type=bind,source=$SMOKE_ROOT/api/run,target=/run" --memory=112m --memory-swap=112m --cpus=0.25 --pids-limit=32 --log-opt max-size=1m --log-opt max-file=1 \
    -e A_STOCK_ADDR=127.0.0.1:20081 -e A_STOCK_APP_VERSION="$RELEASE-check" -e A_STOCK_BOOTSTRAP_PASSWORD=isolated-smoke-only-password \
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
    --name stockstrategy-api --label "$MANAGED_LABEL=stockstrategy" --label "io.easy-stock.app-version=$RELEASE" \
    --label "io.easy-stock.release-note=$RELEASE_NOTE" --restart always --network "$NETWORK" --init \
    --read-only --mount "type=bind,source=$API_TMP,target=/tmp" --mount "type=bind,source=$API_RUN,target=/run" \
    --memory=512m --memory-swap=512m --cpus=1.00 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1:20081/api/health || exit 1' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=30s \
    --env-file "$DATA_ROOT/config/backend.env" \
    -e A_STOCK_ADDR=0.0.0.0:20081 -e A_STOCK_APP_VERSION="$RELEASE" \
    -e A_STOCK_DATA_ROOT=/data -e A_STOCK_TRADING_CALENDAR=/config/trading-calendar.json \
    -e A_STOCK_DATA_DB=/data/easy-stock/stock-data.db -e A_STOCK_LOG_DIR=/logs/backend \
    -e A_STOCK_TDX_FORWARDP_DIR=/data/instock/forwardp \
    -v /mnt/4TB/dockerf/stock/forwardp:/data/instock/forwardp:ro \
    -e A_STOCK_SETTINGS_PATH=/data/easy-stock/settings.json -e A_STOCK_MASTERY_CACHE=/data/trading-mastery \
    -e A_STOCK_HERMES_HOME=/data/hermes-home -e A_STOCK_HERMES_WORKDIR=/app \
    -e HOME=/data -e XDG_CONFIG_HOME=/data/config -e TZ=Asia/Hong_Kong \
    -v "$DATA_ROOT/config/trading-calendar.json:/config/trading-calendar.json:ro" \
    -v "$DATA_ROOT/data:/data" \
    -v "$DATA_ROOT/logs/backend:/logs/backend" \
    -v "$DATA_ROOT/logs/service:/logs/service:ro" \
    -v /etc/cron.d/stockstrategy-market-append:/config/stockstrategy-market-append.cron:ro \
    "$API_IMAGE" >/dev/null
API_NEW_CREATED=1
require_api_mount_contract stockstrategy-api 8
require_readonly_root stockstrategy-api

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
    --name stockstrategy-web --label "$MANAGED_LABEL=stockstrategy" --label "io.easy-stock.app-version=$RELEASE" \
    --label "io.easy-stock.release-note=$RELEASE_NOTE" --restart always --network "$NETWORK" \
    --read-only --mount "type=bind,source=$WEB_TMP,target=/tmp" --mount "type=bind,source=$WEB_RUN,target=/run" \
    --mount "type=bind,source=$WEB_CACHE,target=/var/cache" \
    --memory=128m --memory-swap=128m --cpus=0.50 --pids-limit=128 \
    --log-opt max-size=10m --log-opt max-file=3 \
    --health-cmd='wget -q -T 5 -O /dev/null http://127.0.0.1/' \
    --health-interval=10s --health-timeout=5s --health-retries=6 --health-start-period=10s \
    -p 192.168.50.60:20073:80 \
    -v "$WEB_DIST:/usr/share/nginx/html:ro" -v "$DATA_ROOT/logs/web:/logs/web" \
    --entrypoint /bin/sh "$old_web_image" /usr/share/nginx/html/.runtime/web-entrypoint.sh >/dev/null
WEB_NEW_CREATED=1
require_web_mount_contract stockstrategy-web 5
require_readonly_root stockstrategy-web
wait_healthy stockstrategy-web 30 || fail 'New web container did not become healthy; rolling back.'
docker exec stockstrategy-web wget -q -T 10 -O /dev/null http://127.0.0.1/api/health || fail 'Web-to-API health check failed; rolling back.'
require_clean_container_layer stockstrategy-api true
require_clean_container_layer stockstrategy-web true

install -m 0755 "$UNPACK/docker/rollback-prebuilt.sh" "$PROJECT/docker/.rollback-prebuilt.$RELEASE.tmp"
mv -f -- "$PROJECT/docker/.rollback-prebuilt.$RELEASE.tmp" "$PROJECT/docker/rollback-prebuilt.sh"
docker update --restart=no "$WEB_BACKUP" "$API_BACKUP" >/dev/null
touch "$ROLLBACK_DIR/COMPLETE"
SUCCESS=1
printf 'Deployment healthy: release=%s, url=http://192.168.50.60:20073; rollback= bash %s/docker/rollback-prebuilt.sh %s\n' "$RELEASE" "$PROJECT" "$RELEASE"
