#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$SCRIPT_DIR/legacy-deployment-disabled.sh" "$0"
