"""Supply Conda's SQLite dependency to an ATS standalone distribution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize(dist, python_env):
    dist, python_env = Path(dist).resolve(), Path(python_env).resolve()
    extension = dist / '_sqlite3.pyd'
    origin = python_env / 'DLLs' / '_sqlite3.pyd'
    if not (dist / 'ATS_Terminal.exe').is_file():
        raise ValueError('ATS standalone executable is required')
    if not origin.is_file() or digest(extension) != digest(origin):
        raise ValueError('SQLite extension does not match the selected build environment')
    source, target = python_env / 'Library' / 'bin' / 'sqlite3.dll', dist / 'sqlite3.dll'
    source_digest = digest(source)
    if target.exists() and digest(target) != source_digest:
        raise ValueError('Existing SQLite dependency differs from the build environment')
    if not target.exists():
        shutil.copy2(source, target)
    result = dict(dependency=str(target), sha256=source_digest,
                  source=str(source), extension_sha256=digest(extension),
                  scope='standalone DLL closure; runtime smoke still required')
    (dist / 'ats_dependency_provenance.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', required=True)
    parser.add_argument('--python-env', required=True)
    args = parser.parse_args()
    finalize(args.dist, args.python_env)
