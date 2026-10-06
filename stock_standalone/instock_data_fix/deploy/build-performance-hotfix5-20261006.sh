#!/usr/bin/env bash
set -euo pipefail

STOCK_ROOT=/mnt/4TB/dockerf/stock
OVERLAY=$STOCK_ROOT/instock-overlay-perf-hotfix5-20261006
BUILD=$STOCK_ROOT/instockBuild-perf-hotfix5-20261006
BASE=instock:johnson250103-sina-runtime-hotfix4-20261006
IMAGE=instock:johnson250103-sina-runtime-perf-hotfix5-20261006
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
for file in scan_helpers.py strategy_data_daily_job.py indicators_data_daily_job.py klinepattern_data_daily_job.py; do
    test -f "$OVERLAY/job/$file"
done
test ! -e "$BUILD"

mkdir -p "$BUILD/job" "$STOCK_ROOT/image-backups"
for file in scan_helpers.py strategy_data_daily_job.py indicators_data_daily_job.py klinepattern_data_daily_job.py; do
    install -m 0644 "$OVERLAY/job/$file" "$BUILD/job/$file"
done
install -m 0644 "$SCRIPT_DIR/Dockerfile.performance-hotfix5-20261006" "$BUILD/Dockerfile"

docker build --pull=false --cpuset-cpus=0 --memory=768m --memory-swap=768m \
    -t "$IMAGE" -f "$BUILD/Dockerfile" "$BUILD"

if ! docker run --rm --network none --entrypoint /usr/local/bin/python3 "$IMAGE" -c \
    "import sys; sys.path.insert(0, '/data/InStock/instock/job'); import strategy_data_daily_job as s, indicators_data_daily_job as i, klinepattern_data_daily_job as k; from scan_helpers import bounded_results; assert callable(s.main) and callable(i.main) and callable(k.main) and callable(bounded_results)" >/dev/null 2>&1; then
    echo "Performance-job import smoke failed." >&2
    exit 1
fi
echo "Performance-job import smoke passed"

IMAGE_BACKUP=$STOCK_ROOT/image-backups/instock-sina-runtime-perf-hotfix5-20261006.tar
docker image save "$IMAGE" -o "$IMAGE_BACKUP"
sha256sum "$IMAGE_BACKUP" > "$IMAGE_BACKUP.sha256"
echo "Built and smoke-checked $IMAGE; backup: $IMAGE_BACKUP"
