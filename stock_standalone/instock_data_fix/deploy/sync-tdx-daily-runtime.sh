#!/bin/sh
set -eu

if [ "$#" -lt 1 ]; then
    echo "usage: sync-tdx-daily-runtime.sh STAGE_DIR [BACKUP_DIR]" >&2
    exit 64
fi
STAGE_DIR=$(cd "$1" && pwd)
BACKUP_DIR=${2:-"$STAGE_DIR/backup"}
INSTOCK_ROOT=${INSTOCK_ROOT:-/data/InStock/instock}
PYTHON=${INSTOCK_PYTHON:-/usr/local/bin/python3}
[ -x "$PYTHON" ] || { echo "missing project Python runtime: $PYTHON" >&2; exit 69; }

for required in tdx_hq.py stockfetch.py basic_data_daily_job.py requirements-tdx-hq.txt; do
    test -f "$STAGE_DIR/$required" || { echo "missing staged file: $required" >&2; exit 66; }
done
mkdir -p "$BACKUP_DIR" "$INSTOCK_ROOT/cache"
SYNC_STARTED=0
rollback() {
    status=$?
    if [ "$status" -ne 0 ] && [ "$SYNC_STARTED" -eq 1 ]; then
        set +e
        for target in core/stockfetch.py job/basic_data_daily_job.py core/tdx_hq.py; do
            name=$(basename "$target")
            if [ -f "$BACKUP_DIR/$name.before" ]; then
                install -m 0644 "$BACKUP_DIR/$name.before" "$INSTOCK_ROOT/$target.codex-rollback"
                mv -f "$INSTOCK_ROOT/$target.codex-rollback" "$INSTOCK_ROOT/$target"
            elif [ -f "$BACKUP_DIR/$name.absent" ]; then
                rm -f "$INSTOCK_ROOT/$target"
            fi
        done
    fi
    exit "$status"
}
trap rollback EXIT

exec 9>"$INSTOCK_ROOT/cache/strategy_enter.lock"
flock -n 9 || { echo "strategy_enter.lock is busy; deployment aborted" >&2; exit 73; }

for target in core/stockfetch.py job/basic_data_daily_job.py core/tdx_hq.py; do
    name=$(basename "$target")
    if [ -f "$INSTOCK_ROOT/$target" ]; then
        cp -p "$INSTOCK_ROOT/$target" "$BACKUP_DIR/$name.before"
    else
        : > "$BACKUP_DIR/$name.absent"
    fi
done

PYTHONPYCACHEPREFIX="$STAGE_DIR/pycache" "$PYTHON" -m py_compile \
    "$STAGE_DIR/tdx_hq.py" "$STAGE_DIR/stockfetch.py" "$STAGE_DIR/basic_data_daily_job.py"
"$PYTHON" -m pip install --disable-pip-version-check --no-cache-dir \
    -r "$STAGE_DIR/requirements-tdx-hq.txt"

SYNC_STARTED=1
install -m 0644 "$STAGE_DIR/tdx_hq.py" "$INSTOCK_ROOT/core/tdx_hq.py.codex-tmp"
mv -f "$INSTOCK_ROOT/core/tdx_hq.py.codex-tmp" "$INSTOCK_ROOT/core/tdx_hq.py"
install -m 0644 "$STAGE_DIR/stockfetch.py" "$INSTOCK_ROOT/core/stockfetch.py.codex-tmp"
mv -f "$INSTOCK_ROOT/core/stockfetch.py.codex-tmp" "$INSTOCK_ROOT/core/stockfetch.py"
install -m 0644 "$STAGE_DIR/basic_data_daily_job.py" "$INSTOCK_ROOT/job/basic_data_daily_job.py.codex-tmp"
mv -f "$INSTOCK_ROOT/job/basic_data_daily_job.py.codex-tmp" "$INSTOCK_ROOT/job/basic_data_daily_job.py"
cmp -s "$STAGE_DIR/tdx_hq.py" "$INSTOCK_ROOT/core/tdx_hq.py"
cmp -s "$STAGE_DIR/stockfetch.py" "$INSTOCK_ROOT/core/stockfetch.py"
cmp -s "$STAGE_DIR/basic_data_daily_job.py" "$INSTOCK_ROOT/job/basic_data_daily_job.py"
"$PYTHON" -c "import importlib.metadata; print('pytdx', importlib.metadata.version('pytdx'))"
sha256sum "$INSTOCK_ROOT/core/tdx_hq.py" "$INSTOCK_ROOT/core/stockfetch.py" \
    "$INSTOCK_ROOT/job/basic_data_daily_job.py"
SYNC_STARTED=0
echo "TDX runtime sync complete; backup=$BACKUP_DIR"
