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


VALID_THEMES = ("pitch_dark", "deep_navy", "pro_charcoal")
DEFAULT_THEME = "pitch_dark"


def _atomic_write_preferences(data):
    path = _preferences_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix="sbc_preferences_", suffix=".tmp", delete=False) as handle:
            temporary_path = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def _valid_code(code):
    return bool(re.fullmatch(r"[0-9]{6}", code)) and code != "000000"


def get_sbc_default_code():
    code = str(_read_preferences().get("sbc_default_code", "")).strip()
    return code if _valid_code(code) else "600733"


def set_sbc_default_code(code):
    code = str(code).strip()
    if not _valid_code(code):
        raise ValueError("请输入有效的六位数字股票代码，不能使用 000000。")
    data = _read_preferences()
    data["sbc_default_code"] = code
    _atomic_write_preferences(data)


def get_sbc_theme_mode() -> str:
    """获取 SBC 主题模式：pitch_dark (暗夜极黑) / deep_navy (深海邃蓝) / pro_charcoal (雅致炭灰)"""
    mode = str(_read_preferences().get("sbc_theme_mode", DEFAULT_THEME)).strip()
    return mode if mode in VALID_THEMES else DEFAULT_THEME


def set_sbc_theme_mode(mode: str) -> None:
    """持久化保存 SBC 主题模式"""
    if mode not in VALID_THEMES:
        mode = DEFAULT_THEME
    data = _read_preferences()
    data["sbc_theme_mode"] = mode
    _atomic_write_preferences(data)


def get_sbc_show_boll() -> bool:
    """获取 K 线是否显示 BOLL 布林带 (默认 True)"""
    val = _read_preferences().get("sbc_show_boll", True)
    return bool(val) if val is not None else True


def set_sbc_show_boll(enabled: bool) -> None:
    """持久化保存 K 线是否显示 BOLL 布林带"""
    data = _read_preferences()
    data["sbc_show_boll"] = bool(enabled)
    _atomic_write_preferences(data)

