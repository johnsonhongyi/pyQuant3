#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=instock:johnson250103-sina-runtime-perf-hotfix8-20261006
BASE=instock:johnson250103-sina-runtime-perf-hotfix7-20261006-v3
test "$(docker inspect inStock --format '{{.Config.Image}}')" = "$BASE"
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Image already exists: $IMAGE" >&2
    exit 1
fi
BUILD=$(mktemp -d /tmp/instock-stats-build.XXXXXX)
trap 'rm -rf "$BUILD"' EXIT
mkdir -p "$BUILD/JSONData" "$BUILD/job" "$BUILD/web/templates" "$BUILD/perf_hotfix_20261006/job"
cp "$ROOT/JSONData/history_cache.py" "$BUILD/JSONData/"
cp "$ROOT/job/run_statistics.py" "$ROOT/job/strategy_enter-edit.py" "$BUILD/job/"
cp "$ROOT/perf_hotfix_20261006/job/strategy_data_daily_job.py" "$BUILD/perf_hotfix_20261006/job/"
cp "$ROOT/web/web_service.py" "$BUILD/web/"
cp "$ROOT/web/templates/manual_strategy_refresh.html" "$BUILD/web/templates/"
cp "$ROOT/deploy/Dockerfile.performance-hotfix8-20261006" "$BUILD/Dockerfile"
docker build --pull=false --cpuset-cpus=0 --memory=512m --memory-swap=512m -t "$IMAGE" "$BUILD"
docker run --rm --network none --cpus=1 --memory=256m --entrypoint /usr/local/bin/python3 "$IMAGE" -c \
    "import sys,logging; logging.disable(logging.CRITICAL); logging.basicConfig(handlers=[logging.NullHandler()]);sys.path.insert(0,'/data/InStock');sys.path.insert(0,'/data/InStock/instock/job');from instock.job.run_statistics import history;import instock.web.web_service;import strategy_data_daily_job;import runpy;runpy.run_path('/data/InStock/instock/job/strategy_enter-edit.py',run_name='smoke')" >/dev/null 2>&1
echo "Built and import-checked $IMAGE"
