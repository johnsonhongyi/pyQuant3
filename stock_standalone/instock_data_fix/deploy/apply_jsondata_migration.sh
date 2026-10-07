#!/bin/bash
set -e

echo "=== [1/5] Inside lock boundary ==="

BACKUP_DIR="/tmp/inStock-backup-jsondata-$(date +%Y%m%d%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -a /data/InStock/JSONData "$BACKUP_DIR/"
cp -a /data/InStock/instock/core/stockfetch.py "$BACKUP_DIR/"
cp -a /data/InStock/instock/job/strategy_enter-edit.py "$BACKUP_DIR/"
cp -a /data/InStock/instock/job/prewarm_history.py "$BACKUP_DIR/"
cp -a /data/InStock/instock/job/run_statistics.py "$BACKUP_DIR/"
echo "=== [2/5] Backed up files to $BACKUP_DIR ==="

rm -rf /tmp/sync_stage
mkdir -p /tmp/sync_stage
tar -xf /tmp/tmp_jsondata_sync.tar -C /tmp/sync_stage

echo "=== [3/5] Installing instock/JSONData package ==="
mkdir -p /data/InStock/instock/JSONData
cp -a /tmp/sync_stage/instock/JSONData/* /data/InStock/instock/JSONData/

echo "=== [4/5] Updating consumer files ==="
cp -f /tmp/sync_stage/core/stockfetch.py /data/InStock/instock/core/stockfetch.py
cp -f /tmp/sync_stage/job/strategy_enter-edit.py /data/InStock/instock/job/strategy_enter-edit.py
cp -f /tmp/sync_stage/job/prewarm_history.py /data/InStock/instock/job/prewarm_history.py
cp -f /tmp/sync_stage/job/run_statistics.py /data/InStock/instock/job/run_statistics.py

echo "=== [5/5] Setting up backward-compatibility symlink /data/InStock/JSONData ==="
if [ ! -L /data/InStock/JSONData ]; then
    mv /data/InStock/JSONData "$BACKUP_DIR/original_JSONData_dir"
fi
ln -sfn /data/InStock/instock/JSONData /data/InStock/JSONData

echo "=== Verifying Python imports inside container ==="
python3 -c "import instock.JSONData.prepared_history as ph; import instock.JSONData.tdx_data_Day as td; print('VERIFIED_INSTOCK_JSONDATA_OK')"
python3 -c "import JSONData.prepared_history as ph; print('VERIFIED_JSONDATA_LINK_OK')"
python3 -c "import instock.core.stockfetch as sf; print('VERIFIED_STOCKFETCH_OK')"
python3 -c "import instock.job.run_statistics as rs; print('VERIFIED_RUN_STATISTICS_OK')"

rm -rf /tmp/sync_stage
echo "=== ALL DONE: instock/JSONData migration successfully applied! ==="
