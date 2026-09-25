# -*- coding: utf-8 -*-
import win32file
import json

def decode_chunked_full(b):
    out = bytearray()
    i = 0
    while i < len(b):
        nl = b.find(b'\r\n', i)
        if nl == -1:
            break
        line = b[i:nl].split(b';')[0].strip()
        if not line:
            i = nl + 2
            continue
        try:
            sz = int(line, 16)
        except ValueError:
            break
        if sz == 0:
            break
        start = nl + 2
        chunk = b[start:start+sz]
        out.extend(chunk)
        i = start + sz + 2
    return bytes(out)

def test_api():
    pipe_name = r'\\.\pipe\verge-mihomo'
    handle = win32file.CreateFile(pipe_name, win32file.GENERIC_READ | win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, None)
    req = 'GET /connections HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer plokij\r\nConnection: close\r\n\r\n'
    win32file.WriteFile(handle, req.encode('utf-8'))

    raw_bytes = bytearray()
    while True:
        try:
            hr, chunk = win32file.ReadFile(handle, 65536)
            if not chunk:
                break
            raw_bytes.extend(chunk)
        except Exception:
            break
    win32file.CloseHandle(handle)

    header, _, body = bytes(raw_bytes).partition(b'\r\n\r\n')
    decoded = decode_chunked_full(body)
    if decoded:
        try:
            data = json.loads(decoded.decode('utf-8', errors='ignore'))
            down_mb = data.get('downloadTotal', 0) / (1024 * 1024)
            up_mb = data.get('uploadTotal', 0) / (1024 * 1024)
            print(f"Download Total: {down_mb:.2f} MB ({down_mb/1024:.2f} GB)")
            print(f"Upload Total:   {up_mb:.2f} MB ({up_mb/1024:.2f} GB)")
            conns = data.get('connections', [])
            print(f"Active Conns Count: {len(conns)}")
            
            # Print top connections
            conns.sort(key=lambda x: x.get('download', 0), reverse=True)
            print("\n=== TOP 20 ACTIVE CONNECTIONS ===")
            for c in conns[:20]:
                meta = c.get('metadata', {})
                proc = meta.get('processPath', '') or meta.get('process', '')
                proc_name = proc.split('\\')[-1] if proc else 'unknown'
                host = meta.get('host', '') or meta.get('destinationIP', '')
                c_down = c.get('download', 0) / (1024 * 1024)
                c_up = c.get('upload', 0) / (1024 * 1024)
                chains = ' -> '.join(c.get('chains', []))
                rule = c.get('rule', '')
                print(f"  {proc_name:<22s} | {host:<35s} | Down:{c_down:7.2f}MB Up:{c_up:7.2f}MB | Rule:{rule:<22s} | {chains}")
        except Exception as e:
            print("JSON parse error:", e)

if __name__ == '__main__':
    test_api()
