#!/usr/bin/env bash
set -euo pipefail

STOCK_ROOT=/mnt/4TB/dockerf/stock
IMAGE=instock:johnson250103-sina-tdx-20261005
EXPECTED_BASE=instock:johnson250103-balanced-fastscan-20261005
STAMP=$(date +%Y%m%d%H%M%S)
ROLLBACK=inStock-rollback-sina-$STAMP
FAILED=inStock-failed-sina-$STAMP
ENV_FILE=/run/inStock-sina-$STAMP.env

docker image inspect "$IMAGE" >/dev/null
docker inspect inStock >/dev/null
RUNNING_IMAGE=$(docker inspect inStock --format '{{.Config.Image}}')
if [ "$RUNNING_IMAGE" != "$EXPECTED_BASE" ]; then
    echo "Active image changed ($RUNNING_IMAGE); refusing deployment." >&2
    exit 1
fi
test -d "$STOCK_ROOT/forwardp"
test -d "$STOCK_ROOT/log"
test -d "$STOCK_ROOT/instockcache"
test -d "$STOCK_ROOT/instrategy"
if docker inspect "$ROLLBACK" >/dev/null 2>&1; then
    echo "Rollback container already exists: $ROLLBACK" >&2
    exit 1
fi

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

HEALTHY=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if docker exec inStock /usr/local/bin/python3 -c \
        "import urllib.request; response=urllib.request.urlopen('http://127.0.0.1:9988/', timeout=5); assert response.status == 200"; then
        HEALTHY=1
        break
    fi
    sleep 5
done

if [ "$HEALTHY" != 1 ]; then
    docker logs --tail 80 inStock 2>&1 \
        | sed -E 's#(mysql\+pymysql://[^:/@]+:)[^@]*@#\1***@#g; s/(db_password=)[^ ]+/\1***/g' || true
    docker stop inStock >/dev/null 2>&1 || true
    docker rename inStock "$FAILED" >/dev/null 2>&1 || true
    docker rename "$ROLLBACK" inStock
    docker update --restart=always inStock >/dev/null
    docker start inStock >/dev/null
    exit 1
fi

echo "Started $IMAGE; previous container preserved as $ROLLBACK."
