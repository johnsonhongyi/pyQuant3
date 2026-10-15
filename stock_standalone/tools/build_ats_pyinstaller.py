"""Build ATS with writable local caches and isolated-import diagnostics."""
import os
from pathlib import Path
import sys


def traced_import(package):
    import faulthandler
    print("[DLL import] " + package, flush=True)
    faulthandler.dump_traceback_later(30, repeat=True)
    try:
        __import__(package)
    except Exception:
        pass  # Match PyInstaller's optional DLL-path import probing behavior.
    finally:
        faulthandler.cancel_dump_traceback_later()


def main():
    root = Path(__file__).absolute().parents[1]
    os.chdir(root)
    for variable, directory in (
        ("NUMBA_CACHE_DIR", root / "build/ipo_feedback_cache"),
        ("TEMP", root / "build/ipo_feedback_temp"),
        ("TMP", root / "build/ipo_feedback_temp"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(directory)
    import PyInstaller.__main__
    from PyInstaller import isolated
    original_call = isolated.Python.call

    def traced_call(self, function, *args, **kwargs):
        if function.__name__ == "import_library":
            function = traced_import
        return original_call(self, function, *args, **kwargs)

    isolated.Python.call = traced_call
    try:
        PyInstaller.__main__.run(sys.argv[1:] or [
            "--noconfirm", "--distpath", "dist/ipo_feedback_release",
            "--workpath", "build/ipo_feedback_release", "ats.spec",
        ])
    finally:
        isolated.Python.call = original_call


if __name__ == "__main__":
    main()
