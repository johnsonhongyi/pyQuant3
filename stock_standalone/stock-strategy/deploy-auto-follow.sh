#!/bin/sh
# Deploy only the independent paper worker. Never rebuild/restart API or Web.
set -eu
release=${1:?usage: deploy-auto-follow.sh YYYYMMDDHHMMSS archive.tar.gz}
archive=${2:?archive required}
case "$release" in *[!0-9]*|'') echo 'Invalid release' >&2; exit 2;; esac
[ "${#release}" -eq 14 ] || exit 2
DATA=/mnt/4TB/dockerf/stockstrategy
BASE=$DATA/auto-follow
TARGET=$BASE/releases/$release
UNIT=/etc/systemd/system/stockstrategy-auto-follow.service
mountpoint -q /mnt/4TB
test -f "$DATA/.stockstrategy-managed"
test -f /root/johnson/stock-strategy/.stockstrategy-managed
exec 9>/run/lock/stockstrategy-deploy.lock
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
for container in stockstrategy-api stockstrategy-web; do
    test "$(docker inspect -f '{{.State.Health.Status}}' "$container")" = healthy
    test "$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$container")" = true
done
test ! -e "$TARGET"
mkdir -p "$TARGET" "$DATA/data/auto-follow" "$DATA/logs/service"
chown root:10001 "$DATA/data/auto-follow"
chmod 2770 "$DATA/data/auto-follow"
tar -xzf "$archive" -C "$TARGET"
find "$TARGET" -type f -exec chmod 0644 {} +
cd "$TARGET"
sha256sum -c SHA256SUMS
test -f "$DATA/config/trading-calendar.json"
export EASY_STOCK_FOLLOW_SERVICE_DIR="$TARGET/source/easy-stock-service"
export EASY_STOCK_FOLLOW_CONFIG="$TARGET/config.json"
export EASY_STOCK_DATA_DB="$DATA/data/auto-follow/http-cache.db"
export TRADING_CALENDAR_PATH="$DATA/config/trading-calendar.json"
export PYTHONDONTWRITEBYTECODE=1
ln -s "$DATA/logs/service" "$TARGET/source/easy-stock-service/logs"
# Smoke uses a separate account, never the running account.
/usr/bin/python3 "$TARGET/auto_follow.py" --dry-run --db "$DATA/data/auto-follow/preflight-$release/account.db"
/usr/bin/python3 -m unittest test_auto_follow test_follow_research test_follow_ai -q
systemd-analyze verify "$TARGET/stockstrategy-auto-follow.service"
previous=$(readlink "$BASE/current" 2>/dev/null || true)
printf '%s\n' "$previous" > "$TARGET/PREVIOUS"
if [ -f "$UNIT" ]; then cp -p "$UNIT" "$TARGET/previous.service"; fi
rollback() {
    status=$?
    trap - EXIT
    if [ "$status" -ne 0 ]; then
        systemctl stop stockstrategy-auto-follow.service || true
        if [ -n "$previous" ]; then ln -sfn "$previous" "$BASE/current"; fi
        if [ -f "$TARGET/previous.service" ]; then
            cp -p "$TARGET/previous.service" "$UNIT"
            systemctl daemon-reload
            systemctl restart stockstrategy-auto-follow.service || true
        else
            systemctl disable stockstrategy-auto-follow.service || true
            mv "$UNIT" "$TARGET/failed.service"
            systemctl daemon-reload
        fi
        printf 'FAILED=%s\n' "$status" > "$TARGET/FAILED"
    fi
    exit "$status"
}
trap rollback EXIT
systemctl stop stockstrategy-auto-follow.service || true
for name in account.db control.db http-cache.db; do
    for file in "$DATA/data/auto-follow/$name" "$DATA/data/auto-follow/$name-wal" "$DATA/data/auto-follow/$name-shm"; do
        if [ -f "$file" ]; then chown root:10001 "$file"; chmod 0660 "$file"; fi
    done
done
ln -sfn "$TARGET" "$BASE/current"
install -m 0644 "$TARGET/stockstrategy-auto-follow.service" "$UNIT"
systemctl daemon-reload
systemctl enable stockstrategy-auto-follow.service
systemctl restart stockstrategy-auto-follow.service
sleep 3
systemctl is-active --quiet stockstrategy-auto-follow.service
for container in stockstrategy-api stockstrategy-web; do
    test "$(docker inspect -f '{{.State.Health.Status}}' "$container")" = healthy
done
printf 'RELEASE=%s\nMODE=paper\n' "$release" > "$TARGET/COMPLETE"
systemctl show stockstrategy-auto-follow.service -p ActiveState -p SubState -p MainPID -p NRestarts
printf 'paper_release=%s\n' "$release"
