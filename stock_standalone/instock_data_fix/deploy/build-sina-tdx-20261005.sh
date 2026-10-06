#!/usr/bin/env bash
set -euo pipefail

STOCK_ROOT=/mnt/4TB/dockerf/stock
SOURCE_CTX=$STOCK_ROOT/instockBuild-tdx-20261004
OVERLAY=$STOCK_ROOT/instock-overlay-sina-tdx-20261005
BUILD=$STOCK_ROOT/instockBuild-sina-tdx-20261005
BASE=instock:johnson250103-balanced-fastscan-20261005
IMAGE=instock:johnson250103-sina-tdx-20261005
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
test -d "$SOURCE_CTX"
test -f "$OVERLAY/core/stockfetch.py"
test -f "$OVERLAY/core/singleton_stock.py"
test -f "$OVERLAY/core/eastmoney_daily.py"
test -f "$OVERLAY/core/crawling/stock_selection.py"
test -f "$OVERLAY/job/strategy_enter-edit.py"
test -f "$OVERLAY/job/basic_data_daily_job.py"
test -f "$OVERLAY/JSONData/sina_data.py"
test -f "$OVERLAY/JSONData/tdx_data_Day.py"
test -f "$OVERLAY/cron/root"
test ! -e "$BUILD"

mkdir -p "$STOCK_ROOT/image-backups"
BASE_BACKUP=$STOCK_ROOT/image-backups/instock-balanced-fastscan-20261005-pre-sina-tdx.tar
if [ ! -f "$BASE_BACKUP" ]; then
    docker image save "$BASE" -o "$BASE_BACKUP"
    sha256sum "$BASE_BACKUP" > "$BASE_BACKUP.sha256"
fi

cp -a "$SOURCE_CTX" "$BUILD"
install -D -m 0644 "$OVERLAY/core/stockfetch.py" "$BUILD/core/stockfetch.py"
install -D -m 0644 "$OVERLAY/core/singleton_stock.py" "$BUILD/core/singleton_stock.py"
install -D -m 0644 "$OVERLAY/core/eastmoney_daily.py" "$BUILD/core/eastmoney_daily.py"
install -D -m 0644 "$OVERLAY/core/crawling/stock_selection.py" "$BUILD/core/crawling/stock_selection.py"
install -D -m 0644 "$OVERLAY/job/strategy_enter-edit.py" "$BUILD/job/strategy_enter-edit.py"
install -D -m 0644 "$OVERLAY/job/basic_data_daily_job.py" "$BUILD/job/basic_data_daily_job.py"
install -D -m 0644 "$OVERLAY/JSONData/sina_data.py" "$BUILD/JSONData/sina_data.py"
install -D -m 0644 "$OVERLAY/JSONData/tdx_data_Day.py" "$BUILD/JSONData/tdx_data_Day.py"
install -D -m 0644 "$OVERLAY/cron/root" "$BUILD/cron/root"
install -m 0644 "$SCRIPT_DIR/Dockerfile.sina-tdx" "$BUILD/Dockerfile"

docker build --pull=false --cpuset-cpus=0 --memory=768m --memory-swap=768m \
    -t "$IMAGE" -f "$BUILD/Dockerfile" "$BUILD"

if ! docker run --rm --network none --entrypoint /usr/local/bin/python3 "$IMAGE" -c \
    "from JSONData.sina_data import _symbol; from instock.core.stockfetch import fetch_stocks, fetch_etfs, fetch_etf_hist, backfill_tdx_daily_data, apply_dynamic_volume_ratio, _dynamic_volume_ratio; from instock.core.eastmoney_daily import request_eastmoney_json, fetch_external_once; from instock.core.singleton_stock import stock_data; import instock.job.basic_data_daily_job; assert _symbol('510300') == 'sh510300' and _symbol('920001') == 'bj920001'; assert _dynamic_volume_ratio(300, [100] * 5, 0.5) == 4.5" >/dev/null 2>&1; then
    echo "InStock import and volume-ratio smoke failed." >&2
    exit 1
fi
echo "InStock import and volume-ratio smoke passed"

IMAGE_BACKUP=$STOCK_ROOT/image-backups/instock-sina-tdx-20261005.tar
docker image save "$IMAGE" -o "$IMAGE_BACKUP"
sha256sum "$IMAGE_BACKUP" > "$IMAGE_BACKUP.sha256"
echo "Built and smoke-checked $IMAGE; backup: $IMAGE_BACKUP"
