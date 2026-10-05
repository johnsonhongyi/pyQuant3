#!/usr/bin/env bash
set -euo pipefail

BUILD=/mnt/4TB/dockerf/stock/instockBuild-tdx-20261004
IMAGE=instock:johnson250103-balanced-fastscan-$(date +%Y%m%d)

pct exec 102 -- docker build --pull=false --cpuset-cpus=0 --memory=512m --memory-swap=512m -t "$IMAGE" -f "$BUILD/Dockerfile" "$BUILD"
exec pct exec 102 -- env IMAGE="$IMAGE" bash "$BUILD/deploy/instock-docker-tdx-20261004.sh"
