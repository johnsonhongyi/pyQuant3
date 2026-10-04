#!/usr/bin/env bash
set -euo pipefail

BUILD=/mnt/4TB/dockerf/stock/instockBuild-tdx-20261004
IMAGE=instock:johnson250103-manual-refresh-20261004

docker build --pull=false -t "$IMAGE" -f "$BUILD/Dockerfile" "$BUILD"
exec /root/johnson/InStock/instock-docker-tdx-20261004.sh
