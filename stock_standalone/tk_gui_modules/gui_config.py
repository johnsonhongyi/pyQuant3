import os
from typing import Optional
from sys_utils import get_base_path, get_conf_path

_base_dir: str = get_base_path()
_datacsv_dir: str = os.path.join(_base_dir, "datacsv")

# Ensure directories exist
os.makedirs(_datacsv_dir, exist_ok=True)

def _get_path(filename: str, base: str) -> str:
    path = get_conf_path(filename, base)
    if not path:
        path = os.path.join(base, filename)
    return str(path)

WINDOW_CONFIG_FILE: str = _get_path("window_config.json", _base_dir)
WINDOW_CONFIG_FILE2: str = _get_path("scale2_window_config.json", _base_dir)
MONITOR_LIST_FILE: str = _get_path("monitor_category_list.json", _base_dir)
MONITOR_LIST_FILE_PATH: str = MONITOR_LIST_FILE
CONFIG_FILE: str = _get_path("display_cols.json", _base_dir)
SEARCH_HISTORY_FILE: str = _get_path("search_history.json", _datacsv_dir)
ICON_PATH: str = _get_path("MonitorTK.ico", _base_dir)
