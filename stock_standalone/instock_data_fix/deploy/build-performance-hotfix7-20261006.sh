#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=instock:johnson250103-sina-runtime-perf-hotfix7-20261006-v3
BASE=instock:johnson250103-sina-runtime-perf-hotfix7-20261006-v2
test "$(docker inspect inStock --format '{{.Config.Image}}')" = "$BASE"
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Image already exists: $IMAGE" >&2
    exit 1
fi
BUILD=$(mktemp -d /tmp/instock-cache-build.XXXXXX)
trap 'rm -rf "$BUILD"' EXIT
mkdir -p "$BUILD/JSONData" "$BUILD/core" "$BUILD/job"
cp "$ROOT/JSONData/history_cache.py" "$ROOT/JSONData/tdx_data_Day.py" "$BUILD/JSONData/"
cp "$ROOT/core/singleton_stock.py" "$BUILD/core/"
cp "$ROOT/core/stockfetch.py" "$BUILD/core/"
cp "$ROOT/job/strategy_enter-edit.py" "$ROOT/job/realtime_candidates.py" "$BUILD/job/"
cp "$ROOT/deploy/Dockerfile.performance-hotfix7-20261006" "$BUILD/Dockerfile"
docker build --pull=false --cpuset-cpus=0 --memory=512m --memory-swap=512m -t "$IMAGE" "$BUILD"
docker run --rm --network none --memory=256m --cpus=1 --entrypoint /usr/local/bin/python3 "$IMAGE" -c \
    "import sys; sys.path.insert(0, '/data/InStock'); from JSONData.history_cache import load_history; from instock.job.realtime_candidates import select_candidates; import runpy; runpy.run_path('/data/InStock/instock/job/strategy_enter-edit.py', run_name='smoke')" >/dev/null 2>&1
echo "Built and import-checked $IMAGE"
