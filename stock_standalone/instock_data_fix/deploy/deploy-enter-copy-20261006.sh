#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/4TB/dockerf/stock
test "$(docker inspect inStock --format '{{.Config.Image}}')" = instock:johnson250103-sina-runtime-perf-hotfix9-20261006
test -f /tmp/fix-enter-copy-20261006.py
docker cp /tmp/fix-enter-copy-20261006.py inStock:/tmp/fix-enter-copy-20261006.py
docker exec inStock /usr/local/bin/python3 /tmp/fix-enter-copy-20261006.py
# Existing jobs have already imported this module. Atomic replacement affects
# the next subprocess/cron run without restarting or interrupting active jobs.
echo 'Mounted strategy source patched; effective from the next strategy run'
