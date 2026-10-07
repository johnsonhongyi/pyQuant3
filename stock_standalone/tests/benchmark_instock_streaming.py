"""Full-universe cold/warm scan; persistent cache only, no strategy writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, '/data/InStock')
from instock.job.run_statistics import history

path = '/tmp/streaming-benchmark-' + uuid.uuid4().hex + '.sqlite'
os.environ['INSTOCK_RUN_STATS_PATH'] = path
records = []
baseline = json.loads(Path('/tmp/static-cache-baseline.json').read_text())
for label in ('all-cache-build', 'all-warm', 'small-warm'):
    env = os.environ.copy()
    env.update(INSTOCK_SMALL_STRATEGIES_ONLY='1' if label == 'small-warm' else '0', INSTOCK_SCAN_DRY_RUN='1',
               INSTOCK_RUN_ID='benchmark-' + label, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    with open('/tmp/streaming-benchmark.log', 'a') as output:
        result = subprocess.run([sys.executable, '/data/InStock/instock/job/strategy_enter-edit.py'],
                                env=env, stdout=output, stderr=subprocess.STDOUT, timeout=1200)
    if result.returncode:
        rows = history()['small' if label == 'small-warm' else 'all']
        raise SystemExit(json.dumps(dict(phase=label, returncode=result.returncode,
            error=rows[0].get('error') if rows else 'No completion record')))
    record = history()['small' if label == 'small-warm' else 'all'][0]
    summary = dict(phase=label, seconds=record['duration_seconds'], peak_rss_mb=record.get('peak_rss_mb'),
                   read_mb=round(record.get('io_delta', {}).get('read_bytes', 0) / 1048576, 2),
                   cache=record.get('cache'), stages=record['stages'])
    records.append(summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    for stage in record['stages'][1:]:
        assert stage['scan']['result_sha256'] == baseline['strategies'][stage['name']]['digest']
assert records[0]['stages'][0]['stocks'] == records[1]['stages'][0]['stocks']
for first, second in zip(records[0]['stages'][1:], records[1]['stages'][1:]):
    assert first['scan']['matched'] == second['scan']['matched']
    assert first['scan']['result_sha256'] == second['scan']['result_sha256']
for first, second in zip(records[1]['stages'][1:3], records[2]['stages'][1:]):
    assert first['scan']['result_sha256'] == second['scan']['result_sha256']
print('Build/warm full-market results consistent; strategy tables unchanged', flush=True)
