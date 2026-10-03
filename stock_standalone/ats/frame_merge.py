"""Batch compatible numeric diff columns; preserve the legacy sparse semantics."""
import os

import numpy as np
import pandas as pd


def merge_sparse_frame(cache, diff):
    for col in diff.columns:
        if col not in cache.columns:
            cache[col] = diff[col]
    common = cache.index.intersection(diff.index)
    if len(common):
        batched = set()
        if (os.environ.get("ATS_BATCH_DIFF", "1") != "0"
                and cache.index.is_unique and diff.index.is_unique
                and cache.columns.is_unique and diff.columns.is_unique):
            rows = cache.index.get_indexer(common)
            aligned = diff.loc[common]
            groups = {}
            for col in diff.columns:
                dtype = cache[col].dtype
                if (isinstance(dtype, np.dtype) and dtype.kind in "biufc"
                        and dtype == aligned[col].dtype):
                    groups.setdefault(dtype.str, []).append(col)
            for cols in groups.values():
                positions = cache.columns.get_indexer(cols)
                incoming = aligned[cols].to_numpy()
                old = cache.iloc[rows, positions].to_numpy()
                values = np.where(pd.notna(incoming), incoming, old)
                cache.iloc[rows, positions] = values
                batched.update(cols)
        for col in diff.columns:
            if col in batched:
                continue
            values = diff.loc[common, col]
            valid = values.notna()
            indices = valid[valid].index
            if len(indices):
                cache.loc[indices, col] = diff.loc[indices, col]
    new = diff.index.difference(cache.index)
    if len(new):
        cache = pd.concat([cache, diff.loc[new]])
    return cache
