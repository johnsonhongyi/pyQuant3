"""Portable market data adapters integrated directly inside instock package."""

import sys
from . import history_cache
from . import prepared_history
from . import sina_data
from . import tdx_data_Day

# Provide backward-compatibility alias if JSONData is queried directly
alias = sys.modules.get('JSONData')
if alias is None:
    sys.modules['JSONData'] = sys.modules[__name__]
else:
    # Ensure backward compatible attributes are attached
    for name in ('history_cache', 'prepared_history', 'sina_data', 'tdx_data_Day'):
        if not hasattr(alias, name):
            setattr(alias, name, getattr(sys.modules[__name__], name))

__all__ = ['history_cache', 'prepared_history', 'sina_data', 'tdx_data_Day']
