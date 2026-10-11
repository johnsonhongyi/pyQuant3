#!/bin/sh
set -eu

script=${1##*/}
printf 'Refusing legacy hotfix/build path: %s. Feature code must be updated in the existing /data/InStock Git working tree or synchronized file-by-file; do not rebuild the image or change the existing container mounts/settings. See DOCKER_DATA_CONTRACT.md.\n' "$script" >&2
exit 78
