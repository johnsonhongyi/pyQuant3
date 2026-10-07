#!/usr/bin/env bash
set -euo pipefail

STOCK_ROOT=/mnt/4TB/dockerf/stock
IMAGE=instock:johnson250103-sina-runtime-perf-hotfix12-20261006
EXPECTED_BASE=instock:johnson250103-sina-runtime-perf-hotfix11-20261006
STAMP=$(date +%Y%m%d%H%M%S)
ROLLBACK=inStock-rollback-perf-$STAMP
FAILED=inStock-failed-perf-$STAMP
ENV_FILE=/run/inStock-perf-$STAMP.env

docker image inspect "$IMAGE" >/dev/null
docker inspect inStock >/dev/null
RUNNING_IMAGE=$(docker inspect inStock --format '{{.Config.Image}}')
if [ "$RUNNING_IMAGE" != "$EXPECTED_BASE" ]; then
    echo "Active image changed ($RUNNING_IMAGE); refusing deployment." >&2
    exit 1
fi
for path in forwardp log instockcache instrategy; do
    test -d "$STOCK_ROOT/$path"
done

docker inspect inStock --format '{{range .Config.Env}}{{println .}}{{end}}' > "$ENV_FILE"
chmod 600 "$ENV_FILE"
trap 'rm -f "$ENV_FILE"' EXIT

exec 9>"$STOCK_ROOT/instockcache/strategy_enter.lock"
if ! /usr/bin/flock -w 3600 -E 75 9; then
    echo "Timed out waiting for InStock's strategy lock; deployment was not started." >&2
    exit 75
fi

docker update --restart=no inStock >/dev/null
docker stop inStock >/dev/null
docker rename inStock "$ROLLBACK"

if ! docker run -dit --name inStock --link=mariadb \
    --restart=always --log-opt max-size=10m --log-opt max-file=2 \
    --cpus=2 --cpu-shares=256 --memory=1280m --memory-swap=1280m --pids-limit=128 \
    --tmpfs /run/instock-history:rw,noexec,nosuid,size=96m \
    -e INSTOCK_HISTORY_CACHE_DIR=/run/instock-history -e INSTOCK_HISTORY_CACHE_MB=0 \
    -e INSTOCK_STATIC_RESULT_CACHE=1 -e INSTOCK_STREAM_STRATEGIES=1 -e INSTOCK_SCAN_BATCH_SIZE=64 -e INSTOCK_HIST_LOOKBACK_ROWS=150 -e INSTOCK_DEFER_BACKTEST=1 -e INSTOCK_STRATEGY_PREPARED_DIR=/data/InStock/instock/cache/hist -e INSTOCK_PERF_VERSION=hotfix12-20261006 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
    -p 9988:9988 \
    -v "$STOCK_ROOT/log:/data/InStock/instock/log" \
    -v "$STOCK_ROOT/instockcache:/data/InStock/instock/cache" \
    -v "$STOCK_ROOT/instrategy:/data/InStock/instock/core/strategy" \
    -v "$STOCK_ROOT/forwardp:/data/InStock/instock/forwardp:rw" \
    --env-file "$ENV_FILE" -e TDX_FORWARDP_DIR=/data/InStock/instock/forwardp \
    "$IMAGE"; then
    if docker inspect inStock >/dev/null 2>&1; then
        docker rename inStock "$FAILED"
    fi
    docker rename "$ROLLBACK" inStock
    docker update --restart=always inStock >/dev/null
    docker start inStock >/dev/null
    exit 1
fi

HEALTHY=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if docker exec inStock python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:9988/instock/api/manual-strategy-refresh")' >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done

if [ "$HEALTHY" -ne 1 ]; then
    echo "Healthcheck failed; rolling back..." >&2
    docker stop inStock >/dev/null 2>&1 || true
    docker rename inStock "$FAILED" >/dev/null 2>&1 || true
    docker rename "$ROLLBACK" inStock
    docker update --restart=always inStock >/dev/null
    docker start inStock >/dev/null
    exit 2
fi

echo "Deployment of $IMAGE succeeded; rollback container retained as $ROLLBACK."
