"""Apply one verified copy-boundary fix to the mounted strategy source."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

path = Path(os.environ.get('INSTOCK_STRATEGY_SOURCE', '/data/InStock/instock/core/strategy/enter.py'))
expected = 'ee2bb49512e298375b6bec5a074d8e8766cbb8c136c99c2695f502f1a51291d7'
before = path.read_bytes()
old = b'        data = data.loc[mask]\n'
new = b'        data = data.loc[mask].copy()\n'
if before.count(new) == 1 and hashlib.sha256(before.replace(new, old)).hexdigest() == expected:
    print('Verified copy fix already applied')
    raise SystemExit(0)
if hashlib.sha256(before).hexdigest() != expected:
    raise SystemExit('Strategy source changed; refusing stale patch')
if before.count(old) != 1:
    raise SystemExit('Expected exactly one date-filter boundary')
backup = path.with_name('enter.py.bak-copy-20261006')
if backup.exists():
    raise SystemExit('Backup exists; refusing overwrite')
shutil.copy2(path, backup)
fd, temporary = tempfile.mkstemp(prefix='enter-copy-', suffix='.tmp', dir=path.parent)
try:
    with os.fdopen(fd, 'wb') as stream:
        stream.write(before.replace(old, new))
    os.chmod(temporary, path.stat().st_mode)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
print('Applied one-line date-filter copy fix; backup preserved')
