"""Lossless resident bar columns and bounded decoding of legacy cache files."""
import io
import pickle
import zlib
from collections.abc import Sequence

import numpy as np


class CompactBarRecords(Sequence):
    """Expose independent row dictionaries while retaining only typed columns.

    Pickle deliberately exports ordinary lists so existing ATS/TK executables
    can continue reading the shared cache without importing this new class.
    """

    def __init__(self, records):
        self._size = len(records)
        self._columns = {}
        keys = dict.fromkeys(key for row in records for key in row)
        for key in keys:
            values = [row.get(key) for row in records]
            missing = np.array([key not in row for row in records], dtype=bool)
            mask = np.packbits(missing) if missing.any() else None
            if all(type(value) is str for value in values):
                vocabulary = tuple(dict.fromkeys(values))
                lookup = {value: index for index, value in enumerate(vocabulary)}
                dtype = np.uint8 if len(vocabulary) <= 256 else (
                    np.uint16 if len(vocabulary) <= 65536 else np.uint32)
                data = np.array([lookup[value] for value in values], dtype=dtype)
                kind = vocabulary
            elif all(type(value) is float for value in values):
                data, kind = np.array(values, dtype=np.float64), 'float'
            elif all(type(value) is int and -(2**63) <= value < 2**63 for value in values):
                data, kind = np.array(values, dtype=np.int64), 'int'
            elif all(type(value) is bool for value in values):
                data, kind = np.array(values, dtype=bool), 'bool'
            else:
                data, kind = tuple(values), None
            self._columns[key] = (data, kind, mask)

    def __len__(self):
        return self._size

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self._size))]
        if index < 0:
            index += self._size
        if index < 0 or index >= self._size:
            raise IndexError(index)
        row = {}
        for key, (data, kind, mask) in self._columns.items():
            if mask is not None and (int(mask[index // 8]) >> (7 - index % 8)) & 1:
                continue
            value = data[index]
            if isinstance(kind, tuple):
                value = kind[int(value)]
            elif kind is not None:
                value = value.item()
            row[key] = value
        return row

    def __eq__(self, other):
        if not isinstance(other, Sequence) or len(self) != len(other):
            return False
        return all(left == right for left, right in zip(self, other))

    def __reduce__(self):
        return list, (), None, iter(self)

    def to_frame(self, tail_records=(), row_mask=None):
        """Build an independent frame by columns, optionally appending new bars."""
        import pandas as pd

        selected = slice(None) if row_mask is None else np.asarray(row_mask, dtype=bool)
        size = self._size if row_mask is None else int(selected.sum())
        if not size and not tail_records:
            return pd.DataFrame()
        columns = {}
        tail_keys = dict.fromkeys(key for row in tail_records for key in row)
        keys = dict.fromkeys(self._columns)
        keys.update(tail_keys)
        for key in keys:
            if not size and key not in tail_keys:
                continue
            if key in self._columns:
                data, kind, missing = self._columns[key]
                if isinstance(kind, tuple):
                    values = np.asarray(kind, dtype=object)[data[selected]]
                elif kind is not None:
                    values = data[selected]
                else:
                    values = list(data) if row_mask is None else [
                        value for value, keep in zip(data, selected) if keep]
                if missing is not None:
                    mask = np.unpackbits(missing, count=self._size)[selected]
                    if mask.all() and key not in tail_keys:
                        continue
                    values = list(values)
                    for index in np.flatnonzero(mask):
                        values[index] = np.nan
            else:
                values, kind = [np.nan] * size, None
            if tail_records:
                tail = [row.get(key, np.nan) for row in tail_records]
                compatible = (
                    kind == 'float' and all(type(value) is float for value in tail)
                    or kind == 'int' and all(type(value) is int and
                        -(2**63) <= value < 2**63 for value in tail)
                    or kind == 'bool' and all(type(value) is bool for value in tail))
                if compatible:
                    values = np.concatenate((values, np.asarray(tail, dtype=data.dtype)))
                else:
                    values = values.tolist() if isinstance(values, np.ndarray) else list(values)
                    values.extend(tail)
            columns[key] = values
        return pd.DataFrame(columns, index=range(size + len(tail_records)), copy=True)

    @property
    def nbytes(self):
        """Column buffers only; dictionaries/strings add small metadata overhead."""
        return sum(getattr(data, 'nbytes', 0) + (mask.nbytes if mask is not None else 0)
                   for data, _, mask in self._columns.values())


class _ZlibReader(io.RawIOBase):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.decoder = zlib.decompressobj()
        self.pending = b''

    def readable(self):
        return True

    def readinto(self, target):
        while not self.decoder.eof:
            compressed = self.pending or self.source.read(65536)
            if not compressed:
                raise EOFError('Incomplete compressed cache')
            decoded = self.decoder.decompress(compressed, len(target))
            self.pending = self.decoder.unconsumed_tail
            if decoded:
                target[:len(decoded)] = decoded
                return len(decoded)
        return 0


def read_cache_payload(path):
    # Never retain the whole compressed file and its decompressed byte string.
    with open(path, 'rb') as source:
        with io.BufferedReader(_ZlibReader(source), buffer_size=65536) as decoded:
            payload = pickle.load(decoded)
            # Consume the zlib trailer too, detecting truncated/corrupt archives.
            while decoded.read(65536):
                pass
            return payload


def write_cache_payload(payload, destination):
    """Stream the compatible pickle through zlib without a full raw buffer."""
    compressor = zlib.compressobj(1)

    class Writer:
        def write(self, data):
            destination.write(compressor.compress(data))
            return memoryview(data).nbytes

    pickle.dump(payload, Writer(), protocol=pickle.HIGHEST_PROTOCOL)
    destination.write(compressor.flush())
