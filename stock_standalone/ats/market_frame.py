"""Immutable publication helpers for the ATS live market frame."""

from typing import Tuple

import pandas as pd


def merge_diff_version(base: pd.DataFrame, diff: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:
    """Return a new frame version while leaving every previously published frame intact.

    Pandas versions before Copy-on-Write is enabled share blocks between shallow
    copies. Copy each changed column before patching it; untouched columns remain
    shared and read-only across frame versions.
    """
    if base is None or base.empty:
        return diff.copy(deep=False), False
    if diff is None or diff.empty:
        return base, False

    updated = base.copy(deep=False)
    for column in diff.columns:
        if column not in updated.columns:
            updated[column] = diff[column].reindex(updated.index)

    common_index = base.index.intersection(diff.index)
    if len(common_index):
        for column in diff.columns:
            try:
                values = diff.loc[common_index, column]
                valid_index = values[values.notna()].index
                if len(valid_index):
                    changed = updated[column].copy(deep=True)
                    changed.loc[valid_index] = diff.loc[valid_index, column]
                    updated[column] = changed
            except Exception:
                # Preserve the existing per-column degradation contract: one
                # malformed field must not discard valid updates in other fields.
                continue

    new_index = diff.index.difference(base.index)
    if len(new_index):
        updated = pd.concat([updated, diff.loc[new_index]])
    return updated, bool(len(new_index))
