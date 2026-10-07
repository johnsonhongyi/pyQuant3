"""Backward-compatibility proxy for instock.JSONData."""

import sys

try:
    from instock.JSONData import *  # noqa: F401, F403
    from instock.JSONData import history_cache, prepared_history, sina_data, tdx_data_Day  # noqa: F401
except ImportError:
    pass
