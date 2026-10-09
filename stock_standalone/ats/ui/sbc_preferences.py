"""Persistent SBC preferences independent of window layouts and snapshots."""
import json
import os
import re
import tempfile


def _preferences_path():
    layout_path = os.environ.get("SBC_LAYOUT_CONFIG_PATH")
    if layout_path:
        directory = os.path.dirname(os.path.abspath(layout_path))
    else:
        from sys_utils import get_app_root
        directory = os.path.join(get_app_root(), "config")
    return os.path.join(directory, "sbc_launcher_preferences.json")


def _read_preferences():
    try:
        with open(_preferences_path(), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _valid_code(code):
    return bool(re.fullmatch(r"[0-9]{6}", code)) and code != "000000"


def get_sbc_default_code():
    code = str(_read_preferences().get("sbc_default_code", "")).strip()
    return code if _valid_code(code) else "600733"


def set_sbc_default_code(code):
    code = str(code).strip()
    if not _valid_code(code):
        raise ValueError("请输入有效的六位数字股票代码，不能使用 000000。")
    path = _preferences_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    data = _read_preferences()
    data["sbc_default_code"] = code
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix="sbc_preferences_", suffix=".tmp", delete=False) as handle:
            temporary_path = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
