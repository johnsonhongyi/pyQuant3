#!/usr/bin/env bash
set -euo pipefail

BUILD=/mnt/4TB/dockerf/stock/instockBuild-tdx-20261004
IMAGE=instock:runtime-build-$(date +%Y%m%d%H%M%S)

pct exec 102 -- docker image inspect instock:runtime-sina-runtime-perf-hotfix6-20261006 >/dev/null
pct exec 102 -- docker build --pull=false --cpuset-cpus=0 --memory=768m --memory-swap=768m -t "$IMAGE" -f "$BUILD/Dockerfile" "$BUILD"
pct exec 102 -- env IMAGE="$IMAGE" bash "$BUILD/deploy/instock-docker-tdx-20261004.sh"
