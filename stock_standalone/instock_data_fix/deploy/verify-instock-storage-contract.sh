#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/instock-storage-contract.sh"

command -v docker >/dev/null 2>&1 || instock_fail 'Docker is unavailable.'
docker info >/dev/null 2>&1 || instock_fail 'Docker daemon is unavailable.'
instock_require_external_disk
[ "$(docker inspect --format '{{.State.Running}}' inStock 2>/dev/null || true)" = true ] || instock_fail 'inStock is not running.'
instock_assert_managed_mounts inStock
[ "$(docker inspect --format '{{.State.Running}}' mariadb 2>/dev/null || true)" = true ] || instock_fail 'MariaDB container is not running.'
instock_assert_mariadb_mounts

printf 'InStock existing four data mounts: verified\n'
docker inspect --format 'Image={{.Config.Image}} ReadonlyRootfs={{.HostConfig.ReadonlyRootfs}} LogDriver={{.HostConfig.LogConfig.Type}} Network={{.HostConfig.NetworkMode}} Restart={{.HostConfig.RestartPolicy.Name}}' inStock
docker inspect --size --format 'Container writable-layer size: {{.SizeRw}} bytes' inStock
printf 'Git HEAD: '
docker exec inStock git -C /data/InStock rev-parse --short HEAD
printf 'Git branch: '
docker exec inStock git -C /data/InStock branch --show-current
printf 'Modified/untracked Git paths: '
docker exec inStock sh -c 'git -C /data/InStock status --short | wc -l'
printf 'Container diff paths: '
docker diff inStock | wc -l
printf 'Image information:\n'
bash "$SCRIPT_DIR/describe-instock-image.sh" inStock
printf 'External data root: %s\n' "$INSTOCK_DATA_ROOT"
