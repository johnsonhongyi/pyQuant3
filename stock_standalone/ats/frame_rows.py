"""Lazy row mappings retain every dynamic column without wide dict expansion."""
from collections.abc import Mapping


class FrameRow(Mapping):
    def __init__(self, columns, positions, values):
        self._columns, self._positions, self._values = columns, positions, values

    def __getitem__(self, key):
        return self._values[self._positions[key]]

    def __iter__(self):
        return iter(self._columns)

    def __len__(self):
        return len(self._columns)


def iter_frame_rows(frame):
    if not frame.index.is_unique or not frame.columns.is_unique:
        yield from frame.to_dict('index').items()
        return
    columns = tuple(frame.columns)
    positions = {col: i for i, col in enumerate(columns)}
    for code, values in zip(frame.index, frame.itertuples(index=False, name=None)):
        yield code, FrameRow(columns, positions, values)
