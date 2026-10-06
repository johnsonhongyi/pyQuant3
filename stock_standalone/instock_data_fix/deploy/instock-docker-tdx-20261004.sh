#!/usr/bin/env bash
set -euo pipefail

IMAGE=${IMAGE:-instock:johnson250103-sina-runtime-perf-hotfix6-20261006}
STAMP=$(date +%Y%m%d%H%M%S)
ROLLBACK=inStock-rollback-$STAMP
FAILED=inStock-failed-tdx-$STAMP
ENV_FILE=/run/inStock-tdx-$STAMP.env
STOCK_ROOT=/mnt/4TB/dockerf/stock

docker image inspect "$IMAGE" >/dev/null
docker inspect inStock >/dev/null
test -d "$STOCK_ROOT/forwardp"
test -d "$STOCK_ROOT/log"
test -d "$STOCK_ROOT/instockcache"
test -d "$STOCK_ROOT/instrategy"
if docker inspect "$ROLLBACK" >/dev/null 2>&1; then
    echo "Rollback container $ROLLBACK already exists; refusing a second deployment." >&2
    exit 1
fi

docker inspect inStock --format '{{range .Config.Env}}{{println .}}{{end}}' > "$ENV_FILE"
chmod 600 "$ENV_FILE"
trap 'rm -f "$ENV_FILE"' EXIT

exec 9>"$STOCK_ROOT/instockcache/strategy_enter.lock"
if ! /usr/bin/flock -w 3600 -E 75 9; then
    echo "Timed out waiting for the active InStock job lock; deployment was not started." >&2
    exit 75
fi

docker update --restart=no inStock >/dev/null
docker stop inStock >/dev/null
docker rename inStock "$ROLLBACK"

if ! docker run -dit --name inStock --link=mariadb \
    --restart=always --log-opt max-size=10m --log-opt max-file=2 \
    --cpus=2 --memory=1280m --memory-swap=1280m --pids-limit=128 \
    -p 9988:9988 \
    -v "$STOCK_ROOT/log:/data/InStock/instock/log" \
    -v "$STOCK_ROOT/instockcache:/data/InStock/instock/cache" \
    -v "$STOCK_ROOT/instrategy:/data/InStock/instock/core/strategy" \
    -v "$STOCK_ROOT/forwardp:/data/InStock/instock/forwardp:rw" \
    --env-file "$ENV_FILE" -e TDX_FORWARDP_DIR=/data/InStock/instock/forwardp \
    "$IMAGE"; then
    docker rename "$ROLLBACK" inStock
    docker update --restart=always inStock >/dev/null
    docker start inStock >/dev/null
    exit 1
fi

sleep 8
if [ "$(docker inspect inStock --format '{{.State.Running}}')" != true ]; then
    docker logs --tail 80 inStock
    docker rename inStock "$FAILED" >/dev/null 2>&1 || true
    docker rename "$ROLLBACK" inStock
    docker update --restart=always inStock >/dev/null
    docker start inStock >/dev/null
    exit 1
fi

echo "Started $IMAGE. Previous container is preserved as $ROLLBACK."
