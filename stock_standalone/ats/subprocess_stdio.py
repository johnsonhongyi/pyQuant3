"""Keep frozen SBC startup failures observable without a console."""
import os
import sys


def ensure_sbc_stdio():
    if os.environ.get("ATS_SBC_SUBPROCESS") != "1" and not any(
        arg in ("--sbc", "--sbc-hold", "--hold-sbc", "--hold") for arg in sys.argv[1:]
    ):
        return
    for name in ("stdout", "stderr", "__stdout__", "__stderr__"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass
    if not os.environ.get("ATS_SBC_LOG_PATH") and sys.stdout is not None and sys.stderr is not None:
        return
    root = os.path.dirname(os.path.abspath(sys.executable))
    path = os.environ.get("ATS_SBC_LOG_PATH") or os.path.join(root, "logs", "sbc", "sbc_startup.log")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        stream = open(path, "a", encoding="utf-8", errors="backslashreplace", buffering=1)
        for name in ("stdout", "stderr", "__stdout__", "__stderr__"):
            setattr(sys, name, stream)
    except OSError:
        pass
