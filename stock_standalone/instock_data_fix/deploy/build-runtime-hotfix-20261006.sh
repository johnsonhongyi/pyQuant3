#!/usr/bin/env bash
set -euo pipefail

STOCK_ROOT=/mnt/4TB/dockerf/stock
OVERLAY=$STOCK_ROOT/instock-overlay-runtime-hotfix-20261006
BUILD=$STOCK_ROOT/instockBuild-runtime-hotfix4-20261006
BASE=instock:johnson250103-sina-runtime-hotfix3-20261006
IMAGE=instock:johnson250103-sina-runtime-hotfix4-20261006
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

docker inspect inStock >/dev/null
RUNNING_IMAGE=$(docker inspect inStock --format '{{.Config.Image}}')
if [ "$RUNNING_IMAGE" != "$BASE" ]; then
    echo "Active image changed ($RUNNING_IMAGE); refusing to build from stale base $BASE." >&2
    exit 1
fi
docker image inspect "$BASE" >/dev/null
docker image inspect "$IMAGE" >/dev/null 2>&1 && {
    echo "Image tag already exists: $IMAGE" >&2
    exit 1
}
test -f "$OVERLAY/job/basic_data_daily_job.py"
test -f "$OVERLAY/job/execute_daily_job.py"
test -f "$OVERLAY/cron/root"
test ! -e "$BUILD"

mkdir -p "$BUILD/job" "$BUILD/cron" "$STOCK_ROOT/image-backups"
install -m 0644 "$OVERLAY/job/basic_data_daily_job.py" "$BUILD/job/basic_data_daily_job.py"
install -m 0644 "$OVERLAY/job/execute_daily_job.py" "$BUILD/job/execute_daily_job.py"
install -m 0644 "$OVERLAY/cron/root" "$BUILD/cron/root"
install -m 0644 "$SCRIPT_DIR/Dockerfile.runtime-hotfix-20261006" "$BUILD/Dockerfile"

docker build --pull=false --cpuset-cpus=0 --memory=768m --memory-swap=768m \
    -t "$IMAGE" -f "$BUILD/Dockerfile" "$BUILD"

if ! docker run --rm --network none --entrypoint /usr/local/bin/python3 "$IMAGE" -c \
    "import configparser; from pathlib import Path; import instock.job.execute_daily_job as daily; import instock.job.basic_data_daily_job as spot; c=configparser.ConfigParser(); c.read('/data/InStock/supervisor/supervisord.conf'); assert c.getboolean('program:run_job','autostart') is False; assert callable(daily.main) and callable(spot.main)" >/dev/null 2>&1; then
    echo "Daily-job startup-gate smoke failed." >&2
    exit 1
fi
echo "Daily-job startup-gate smoke passed"

IMAGE_BACKUP=$STOCK_ROOT/image-backups/instock-sina-runtime-hotfix4-20261006.tar
docker image save "$IMAGE" -o "$IMAGE_BACKUP"
sha256sum "$IMAGE_BACKUP" > "$IMAGE_BACKUP.sha256"
echo "Built and smoke-checked $IMAGE; backup: $IMAGE_BACKUP"
