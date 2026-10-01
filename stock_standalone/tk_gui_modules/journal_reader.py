"""Read complete journal lines without loading the whole file into the GUI."""


def read_journal_tail(path, lines=300):
    with open(path, 'rb') as stream:
        stream.seek(0, 2)
        end = stream.tell()
        start, chunks, count = end, [], 0
        while start > 0 and count <= lines:
            size = min(8192, start)
            start -= size
            stream.seek(start)
            chunk = stream.read(size)
            chunks.append(chunk)
            count += chunk.count(b'\n')
    data = b''.join(reversed(chunks))
    boundary = data.rfind(b'\n') + 1
    complete = data[:boundary]
    return complete.splitlines()[-lines:], end - len(data) + boundary


def read_journal_increment(path, offset, limit=200):
    records = []
    with open(path, 'rb') as stream:
        stream.seek(offset)
        for _ in range(limit):
            line = stream.readline()
            if not line or not line.endswith(b'\n'):
                break
            records.append(line)
            offset = stream.tell()
    return records, offset
