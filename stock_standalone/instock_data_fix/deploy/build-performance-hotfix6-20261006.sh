#!/usr/bin/env bash
set -euo pipefail

STOCK_ROOT=/mnt/4TB/dockerf/stock
OVERLAY=$STOCK_ROOT/instock-overlay-perf-hotfix6-20261006
BUILD=$STOCK_ROOT/instockBuild-perf-hotfix6-20261006
BASE=instock:johnson250103-sina-runtime-perf-hotfix5-20261006
IMAGE=instock:johnson250103-sina-runtime-perf-hotfix6-20261006
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

docker inspect inStock >/dev/null
RUNNING_IMAGE=$(docker inspect inStock --format '{{.Config.Image}}')
if [ "$RUNNING_IMAGE" != "$BASE" ]; then
    echo "Active image changed ($RUNNING_IMAGE); refusing stale-base build $BASE." >&2
    exit 1
fi
docker image inspect "$BASE" >/dev/null
docker image inspect "$IMAGE" >/dev/null 2>&1 && {
    echo "Image tag already exists: $IMAGE" >&2
    exit 1
}
test -f "$OVERLAY/cron/root"
test ! -e "$BUILD"

mkdir -p "$BUILD/cron" "$STOCK_ROOT/image-backups"
install -m 0644 "$OVERLAY/cron/root" "$BUILD/cron/root"
install -m 0644 "$SCRIPT_DIR/Dockerfile.performance-hotfix6-20261006" "$BUILD/Dockerfile"

docker build --pull=false --cpuset-cpus=0 --memory=768m --memory-swap=768m \
    -t "$IMAGE" -f "$BUILD/Dockerfile" "$BUILD"

if ! docker run --rm --network none --entrypoint /usr/local/bin/python3 "$IMAGE" -c \
    "from pathlib import Path; p=Path('/var/spool/cron/crontabs/root').read_text(); assert 'INSTOCK_REQUIRE_TRADE_DATE=1' in p and 'INSTOCK_SMALL_STRATEGIES_ONLY=1' in p" >/dev/null 2>&1; then
    echo "Trading-day cron guard smoke failed." >&2
    exit 1
fi
if ! docker run --rm --network none --entrypoint /bin/sh "$IMAGE" -c \
    "crontab -u root /var/spool/cron/crontabs/root && crontab -l >/dev/null" >/dev/null 2>&1; then
    echo "Cron syntax smoke failed." >&2
    exit 1
fi
echo "Trading-day cron guard smoke passed"

IMAGE_BACKUP=$STOCK_ROOT/image-backups/instock-sina-runtime-perf-hotfix6-20261006.tar
docker image save "$IMAGE" -o "$IMAGE_BACKUP"
sha256sum "$IMAGE_BACKUP" > "$IMAGE_BACKUP.sha256"
echo "Built and smoke-checked $IMAGE; backup: $IMAGE_BACKUP"
