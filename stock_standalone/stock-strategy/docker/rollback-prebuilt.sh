#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [ "$#" -ne 1 ] || ! [[ "$1" =~ ^[0-9]{14}$ ]]; then
    echo 'Usage: rollback-prebuilt.sh <deployment-release-id>' >&2
    exit 2
fi
RELEASE=$1

command -v flock >/dev/null 2>&1 || { echo 'flock is required.' >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo 'Docker is unavailable.' >&2; exit 1; }
exec 9>/run/lock/stockstrategy-deploy.lock
flock -n 9 || { echo 'Another deployment or rollback is running.' >&2; exit 1; }

PROJECT=/root/johnson/stock-strategy
DATA_ROOT=/mnt/4TB/dockerf/stockstrategy
ROLLBACK_DIR="$DATA_ROOT/rollback/$RELEASE"
API_BACKUP="stockstrategy-api-rollback-$RELEASE"
WEB_BACKUP="stockstrategy-web-rollback-$RELEASE"
STAMP=$(date +%Y%m%d%H%M%S)
API_FORWARD="stockstrategy-api-forward-$STAMP"
WEB_FORWARD="stockstrategy-web-forward-$STAMP"
ATTEMPT_DIR="$ROLLBACK_DIR/rollback-attempt-$STAMP"
API_CURRENT_MOVED=0
WEB_CURRENT_MOVED=0
API_TARGET_MOVED=0
WEB_TARGET_MOVED=0
FILES_UPDATED=0
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

require_runtime_mount() {
    local container=$1 role=$2 leaf=$3 destination=$4 release
    release=$(docker inspect --format '{{ index .Config.Labels "io.easy-stock.app-version" }}' "$container")
    [[ "$release" =~ ^[0-9]{14}$ ]] || fail "$container has no valid release label for runtime mounts."
    require_mount "$container" "$DATA_ROOT/runtime/$release/$role/$leaf" "$destination" true
}

require_readonly_root() {
    container=$1
    readonly=$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container")
    [ "$readonly" = true ] || fail "$container root filesystem is writable."
}

require_api_mount_contract() {
    container=$1
    actual=$(mount_count "$container") || fail "$container has non-bind mounts; external bind mounts are required."
    case "$actual" in
        5) ;;
        6) require_mount "$container" "$DATA_ROOT/config/trading-calendar.json" /config/trading-calendar.json false ;;
        8)
            require_mount "$container" "$DATA_ROOT/config/trading-calendar.json" /config/trading-calendar.json false
            require_runtime_mount "$container" api tmp /tmp
            require_runtime_mount "$container" api run /run
            ;;
        *) fail "$container has $actual external mounts; expected the old or current API contract." ;;
    esac
    require_mount "$container" "$DATA_ROOT/data" /data true
    require_mount "$container" /mnt/4TB/dockerf/stock/forwardp /data/instock/forwardp false
    require_mount "$container" "$DATA_ROOT/logs/backend" /logs/backend true
    require_mount "$container" "$DATA_ROOT/logs/service" /logs/service false
    require_mount "$container" /etc/cron.d/stockstrategy-market-append /config/stockstrategy-market-append.cron false
}

require_web_mount_contract() {
    container=$1
    actual=$(mount_count "$container") || fail "$container has non-bind mounts; external bind mounts are required."
    case "$actual" in
        2) ;;
        5)
            require_runtime_mount "$container" web tmp /tmp
            require_runtime_mount "$container" web run /run
            require_runtime_mount "$container" web cache /var/cache
            ;;
        *) fail "$container has $actual external mounts; expected the old or current web contract." ;;
    esac
    require_mount "$container" "$DATA_ROOT/logs/web" /logs/web true
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\t%s\t%t\n" .Type .Source .Destination .RW}}{{end}}' "$container")
    printf '%s\n' "$mounts" | awk -F '\t' -v prefix="$DATA_ROOT/app/web-dist/" '$1 == "bind" && index($2, prefix) == 1 && $3 == "/usr/share/nginx/html" && $4 == "false" {found=1} END {exit !found}' || fail "$container is missing its read-only web release bind mount under $DATA_ROOT/app/web-dist."
}

replace_source() {
    archive=$1
    suffix=$2
    restore_root=$(mktemp -d "$PROJECT/.source-restore-$suffix.XXXXXX")
    previous_root="$restore_root.previous"
    tar -xzf "$archive" -C "$restore_root"
    [ -d "$restore_root/source" ] || { rm -rf -- "$restore_root"; return 1; }
    mv -- "$PROJECT/source" "$previous_root"
    if mv -- "$restore_root/source" "$PROJECT/source"; then
        rm -rf -- "$previous_root" "$restore_root"
        return 0
    fi
    mv -- "$previous_root" "$PROJECT/source"
    rm -rf -- "$restore_root"
    return 1
}

restore_files() {
    snapshot=$1
    replace_source "$snapshot/source.tar.gz" "$STAMP" || return 1
    install -m 0644 "$snapshot/trading-calendar.json" "$DATA_ROOT/config/trading-calendar.json" || return 1
    ln -sfn "$DATA_ROOT/config/trading-calendar.json" "$PROJECT/source/easy-stock-service/trading-calendar.json" || return 1
    install -m 0755 "$snapshot/market-append.sh" "$PROJECT/docker/market-append.sh" || return 1
    install -m 0644 "$snapshot/stockstrategy-market-append.cron" /etc/cron.d/stockstrategy-market-append || return 1
}

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

reverse_rollback() {
    result=$?
    set +e
    if [ "$SUCCESS" -ne 1 ]; then
        if [ "$FILES_UPDATED" -eq 1 ] && [ -s "$ATTEMPT_DIR/source.tar.gz" ]; then
            restore_files "$ATTEMPT_DIR"
        fi
        if [ "$WEB_TARGET_MOVED" -eq 1 ]; then
            docker stop -t 10 stockstrategy-web >/dev/null 2>&1
            docker rename stockstrategy-web "$WEB_BACKUP" >/dev/null 2>&1
            docker update --restart=no "$WEB_BACKUP" >/dev/null 2>&1
        fi
        if [ "$API_TARGET_MOVED" -eq 1 ]; then
            docker stop -t 10 stockstrategy-api >/dev/null 2>&1
            docker rename stockstrategy-api "$API_BACKUP" >/dev/null 2>&1
            docker update --restart=no "$API_BACKUP" >/dev/null 2>&1
        fi
        if [ "$WEB_CURRENT_MOVED" -eq 1 ]; then
            docker rename "$WEB_FORWARD" stockstrategy-web >/dev/null 2>&1
            docker update --restart=always stockstrategy-web >/dev/null 2>&1
            docker start stockstrategy-web >/dev/null 2>&1
        elif docker inspect stockstrategy-web >/dev/null 2>&1; then
            docker update --restart=always stockstrategy-web >/dev/null 2>&1
            docker start stockstrategy-web >/dev/null 2>&1
        fi
        if [ "$API_CURRENT_MOVED" -eq 1 ]; then
            docker rename "$API_FORWARD" stockstrategy-api >/dev/null 2>&1
            docker update --memory=1g --memory-swap=1g --cpus=2.00 --restart=always stockstrategy-api >/dev/null 2>&1
            docker start stockstrategy-api >/dev/null 2>&1
        elif docker inspect stockstrategy-api >/dev/null 2>&1; then
            docker update --memory=1g --memory-swap=1g --cpus=2.00 --restart=always stockstrategy-api >/dev/null 2>&1
            docker start stockstrategy-api >/dev/null 2>&1
        fi
        printf 'Rollback failed; attempted to restore the pre-rollback deployment. Check Docker health and %s.\n' "$ATTEMPT_DIR" >&2
    fi
    exit "$result"
}
trap reverse_rollback EXIT

docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable.'
mountpoint -q /mnt/4TB || fail '/mnt/4TB is not mounted.'
[ -f "$PROJECT/.stockstrategy-managed" ] || fail 'Project marker is missing.'
[ -f "$DATA_ROOT/.stockstrategy-managed" ] || fail 'Persistent-data marker is missing.'
[ -f "$ROLLBACK_DIR/COMPLETE" ] || fail "Complete rollback snapshot is missing for release $RELEASE."
[ -s "$ROLLBACK_DIR/source.tar.gz" ] || fail 'Source snapshot is missing.'
for file in trading-calendar.json market-append.sh stockstrategy-market-append.cron manifest.txt SHA256SUMS; do
    [ -s "$ROLLBACK_DIR/$file" ] || fail "Rollback snapshot file is missing: $file"
done
(
    cd "$ROLLBACK_DIR"
    sha256sum -c SHA256SUMS >/dev/null
) || fail 'Rollback snapshot checksum validation failed.'
[ ! -e "$DATA_ROOT/rollback/$RELEASE/ROLLED_BACK_AT" ] || fail "Release $RELEASE was already rolled back."
if docker inspect "$API_FORWARD" >/dev/null 2>&1 || docker inspect "$WEB_FORWARD" >/dev/null 2>&1; then
    fail 'Forward container name collision.'
fi

for name in stockstrategy-api stockstrategy-web; do
    [ "$(docker inspect --format '{{.State.Health.Status}}' "$name" 2>/dev/null || true)" = healthy ] || fail "$name is unhealthy; refusing rollback."
    [ "$(docker inspect --format '{{ index .Config.Labels "io.easy-stock.managed" }}' "$name")" = stockstrategy ] || fail "$name is not managed."
    [ "$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$name")" = always ] || fail "$name does not use restart policy always."
done
require_api_mount_contract stockstrategy-api
require_web_mount_contract stockstrategy-web
current_api_mounts=$(mount_count stockstrategy-api)
current_web_mounts=$(mount_count stockstrategy-web)
if [ "$current_api_mounts" = 8 ]; then require_readonly_root stockstrategy-api; fi
if [ "$current_web_mounts" = 5 ]; then require_readonly_root stockstrategy-web; fi
for name in "$API_BACKUP" "$WEB_BACKUP"; do
    [ "$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)" = exited ] || fail "Stopped rollback container is missing: $name"
    [ "$(docker inspect --format '{{ index .Config.Labels "io.easy-stock.managed" }}' "$name")" = stockstrategy ] || fail "$name is not managed."
done
require_api_mount_contract "$API_BACKUP"
require_web_mount_contract "$WEB_BACKUP"
backup_api_mounts=$(mount_count "$API_BACKUP")
backup_web_mounts=$(mount_count "$WEB_BACKUP")
if [ "$backup_api_mounts" = 8 ]; then require_readonly_root "$API_BACKUP"; fi
if [ "$backup_web_mounts" = 5 ]; then require_readonly_root "$WEB_BACKUP"; fi
expected_api=$(sed -n 's/^api_image=//p' "$ROLLBACK_DIR/manifest.txt")
expected_web=$(sed -n 's/^web_image=//p' "$ROLLBACK_DIR/manifest.txt")
[ "$(docker inspect --format '{{.Config.Image}}' "$API_BACKUP")" = "$expected_api" ] || fail 'Rollback API container does not match its snapshot manifest.'
[ "$(docker inspect --format '{{.Config.Image}}' "$WEB_BACKUP")" = "$expected_web" ] || fail 'Rollback web container does not match its snapshot manifest.'
docker image inspect "$expected_api" >/dev/null 2>&1 || fail 'Rollback API image is missing.'
docker image inspect "$expected_web" >/dev/null 2>&1 || fail 'Rollback web image is missing.'
docker network inspect stockstrategy-net >/dev/null 2>&1 || fail 'Managed Docker network is missing.'

mkdir -m 0700 "$ATTEMPT_DIR"
tar -czf "$ATTEMPT_DIR/source.tar.gz" -C "$PROJECT" source
cp -a "$DATA_ROOT/config/trading-calendar.json" "$ATTEMPT_DIR/trading-calendar.json"
cp -a "$PROJECT/docker/market-append.sh" "$ATTEMPT_DIR/market-append.sh"
cp -a /etc/cron.d/stockstrategy-market-append "$ATTEMPT_DIR/stockstrategy-market-append.cron"
FILES_UPDATED=1

docker update --restart=no stockstrategy-web stockstrategy-api >/dev/null
docker stop -t 10 stockstrategy-web stockstrategy-api >/dev/null
docker rename stockstrategy-web "$WEB_FORWARD"
WEB_CURRENT_MOVED=1
docker rename stockstrategy-api "$API_FORWARD"
API_CURRENT_MOVED=1

restore_files "$ROLLBACK_DIR" || fail 'Could not restore the deployment source/configuration snapshot.'
docker rename "$WEB_BACKUP" stockstrategy-web
WEB_TARGET_MOVED=1
docker rename "$API_BACKUP" stockstrategy-api
API_TARGET_MOVED=1
docker update --memory=1g --memory-swap=1g --cpus=2.00 --restart=always stockstrategy-api >/dev/null
docker update --restart=always stockstrategy-web >/dev/null
docker start stockstrategy-api >/dev/null
wait_healthy stockstrategy-api 45 || fail 'Restored API did not become healthy.'
docker start stockstrategy-web >/dev/null
wait_healthy stockstrategy-web 30 || fail 'Restored web container did not become healthy.'
docker exec stockstrategy-web wget -q -T 10 -O /dev/null http://127.0.0.1/api/health || fail 'Restored web-to-API health check failed.'

docker update --restart=no "$API_FORWARD" "$WEB_FORWARD" >/dev/null
date -Is > "$ROLLBACK_DIR/ROLLED_BACK_AT"
SUCCESS=1
printf 'Rollback healthy: restored release snapshot %s; current containers retained as %s / %s. Persistent databases were not modified.\n' "$RELEASE" "$API_FORWARD" "$WEB_FORWARD"
