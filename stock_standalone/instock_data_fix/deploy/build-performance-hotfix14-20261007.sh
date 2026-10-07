#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=instock:johnson250103-sina-runtime-perf-hotfix14-20261007
BASE=instock:johnson250103-sina-runtime-perf-hotfix13-20261007

test "$(docker inspect inStock --format '{{.Config.Image}}')" = "$BASE"
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Image already exists: $IMAGE" >&2
    exit 1
fi

BUILD=$(mktemp -d /tmp/instock-tdx-gap-build.XXXXXX)
trap 'rm -rf "$BUILD"' EXIT
mkdir -p "$BUILD/core" "$BUILD/JSONData"
cp "$ROOT/core/stockfetch.py" "$BUILD/core/"
cp "$ROOT/JSONData/history_cache.py" "$ROOT/JSONData/tdx_data_Day.py" "$BUILD/JSONData/"
cp "$ROOT/deploy/Dockerfile.performance-hotfix14-20261007" "$BUILD/Dockerfile"
docker build --pull=false --cpuset-cpus=0 --memory=512m --memory-swap=512m -t "$IMAGE" "$BUILD"
docker run --rm --network none --cpus=1 --memory=256m --entrypoint /usr/local/bin/python3 "$IMAGE" -c \
    "import logging,sys; logging.disable(logging.CRITICAL); sys.path.insert(0,'/data/InStock'); from instock.core.stockfetch import repair_tdx_history_gaps, _fetch_tencent_tdx_history_gap; assert callable(repair_tdx_history_gaps) and callable(_fetch_tencent_tdx_history_gap)" >/dev/null 2>&1
echo "Built and import-checked $IMAGE"
