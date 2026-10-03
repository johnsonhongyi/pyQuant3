"""Plan capacity matrix: batch IPC merge must match rollback semantics."""
import numpy as np
import pandas as pd
import pytest

from ats.frame_merge import merge_sparse_frame


@pytest.mark.parametrize('rows', [1000, 5000, 10000])
@pytest.mark.parametrize('columns', [32, 128, 256])
@pytest.mark.parametrize('fraction', [0, .01, .1, 1.0])
@pytest.mark.parametrize('wide', [False, True])
def test_capacity_matrix_keeps_all_field_values(monkeypatch, rows, columns, fraction, wide):
    rng = np.random.RandomState(42)
    names = ['close', 'volume'] + [f'dynamic_{i}' for i in range(columns - 3)]
    frame = pd.DataFrame(rng.randn(rows, columns - 1), columns=names,
                         index=[f'{600000+i:06d}' for i in range(rows)])
    frame['name'] = 'stock'
    changed = int(rows * fraction)
    selected = frame.columns if wide else ['close', 'volume']
    diff = frame.iloc[:changed].loc[:, selected].copy()
    numeric = diff.select_dtypes(include=[np.number]).columns
    diff.loc[:, numeric] += .25
    if changed:
        diff.loc[diff.index[::3], numeric] = np.nan
        if wide:
            diff['name'] = 'revised'
    monkeypatch.setenv('ATS_BATCH_DIFF', '0')
    expected = merge_sparse_frame(frame.copy(deep=True), diff)
    monkeypatch.setenv('ATS_BATCH_DIFF', '1')
    actual = merge_sparse_frame(frame.copy(deep=True), diff)
    pd.testing.assert_frame_equal(actual, expected)
    assert list(actual.columns) == list(frame.columns)
    assert list(actual.index) == list(frame.index)
