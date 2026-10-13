"""Read-only RAMDisk inspector; shares the Tk application's path configuration."""
import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, ttk


PURPOSES = {
    'favorite_stocks.json': '共享自选股、板块、关注来源和删除记录',
    'system_linkage.sqlite3': '联动指令、防重复记录、上下文、事件和待发送信息',
    'instock_tk.log': 'Tk 运行日志与故障排查记录',
}


def inventory(runtime_root, app_root):
    root, app = Path(runtime_root), Path(app_root)
    rows = []
    if not root.is_dir():
        return rows
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            local = app / path.name
            identity = hashlib.sha256(str(local).casefold().encode('utf-8')).hexdigest()[:16]
            mapped = identity == directory.name
            stat = path.stat()
            marker = path.with_name(path.name + '.archived_day')
            status = '未见归档标记'
            if marker.exists():
                revision = marker.read_text(encoding='utf-8').strip().split(':')
                status = '归档后有变化'
                if len(revision) == 3 and revision[1:] == [str(stat.st_mtime_ns), str(stat.st_size)]:
                    status = '已归档此版本'
            purpose = PURPOSES.get(path.name, '运行协调/辅助文件')
            if path.name.endswith('.lock'):
                purpose, status = '并发写入协调锁；存在不等于正在占用', '辅助文件'
            elif path.name.endswith(('.reclaim_time', '.archived_day')):
                purpose, status = '清理/归档进度标记', '辅助文件'
            rows.append({'path': path, 'size': stat.st_size, 'mtime': stat.st_mtime,
                         'local': str(local) if mapped else '其他程序目录（选择对应程序目录后识别）',
                         'purpose': purpose, 'status': status})
    return rows


def preview(path, table=None):
    """Bound all reads; SQLite is opened in read-only mode, never immutable."""
    path = Path(path)
    if path.suffix in ('.sqlite3', '.db'):
        # Some Windows RAMDisk drivers do not implement GetFinalPathNameByHandle.
        # abspath normalizes lexically; resolve() can fail with WinError 1.
        uri = Path(os.path.abspath(path)).as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=0.5)) as db:
            db.execute('PRAGMA query_only=ON')
            deadline = time.monotonic() + 2.0
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            if table is None:
                if not tables:
                    return '数据库中没有业务表。', tables
                table = tables[0]
            if table not in tables:
                raise ValueError('无效表名')
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [r[1] for r in db.execute('PRAGMA table_info(' + quoted + ')')]
            # Slice each value in SQL so large payloads cannot fill UI memory.
            fields = ','.join('substr(CAST("' + c.replace('"', '""') + '" AS TEXT),1,4000)' for c in columns)
            data = db.execute('SELECT ' + fields + ' FROM ' + quoted + ' LIMIT 101').fetchall()
            text = '\n\n'.join(json.dumps(dict(zip(columns, row)), ensure_ascii=False, indent=2) for row in data[:100])
            return f'表：{table}（每字段最多 4000 字符）\n\n' + (text or '（此表暂无记录）') + ('\n\n仅展示前 100 行。' if len(data) > 100 else ''), tables
    if path.suffix == '.log':
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 128 * 1024))
            data = stream.read(128 * 1024)
        return '最近最多 128 KB 日志：\n' + data.decode('utf-8', errors='replace'), []
    with path.open('rb') as stream:
        data = stream.read(256 * 1024 + 1)
    if len(data) > 256 * 1024:
        return '文件较大，仅展示前 256 KB：\n' + data[:256 * 1024].decode('utf-8', errors='replace'), []
    text = data.decode('utf-8', errors='replace')
    if path.suffix == '.json':
        text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    return text or '（空文件）', []


def open_viewer(parent=None):
    from linkage_storage import configured_ramdisk_root
    from JohnsonUtil import commonTips as cct
    window = tk.Toplevel(parent) if parent else tk.Tk()
    window.title('运行数据查看器（只读）')
    window.geometry('1100x750')
    runtime_root = configured_ramdisk_root() / 'instock_runtime'
    app_root = tk.StringVar(window, value=str(cct.get_app_root()))
    ttk.Label(window, text=f'运行目录：{runtime_root}').pack(anchor='w', padx=8, pady=4)
    bar = ttk.Frame(window)
    bar.pack(fill='x', padx=8)
    ttk.Label(bar, text='程序目录：').pack(side='left')
    ttk.Entry(bar, textvariable=app_root).pack(side='left', fill='x', expand=True)
    results = Queue()
    state = {'generation': 0, 'rows': {}, 'closed': False}
    status = tk.StringVar(window, value='选择文件查看内容；数据库可选择具体表。')
    tree = ttk.Treeview(window, columns=('size', 'status', 'purpose'), height=9)
    tree.heading('#0', text='文件 / 目录标识')
    for column, label, width in [('size', '大小', 90), ('status', '归档状态', 140), ('purpose', '用途', 420)]:
        tree.heading(column, text=label)
        tree.column(column, width=width)
    tree.pack(fill='x', padx=8, pady=6)
    tables = ttk.Combobox(window, state='readonly')
    tables.pack(fill='x', padx=8)
    ttk.Label(window, textvariable=status, wraplength=1050).pack(anchor='w', padx=8)
    body = ttk.Frame(window)
    body.pack(fill='both', expand=True, padx=8, pady=6)
    text = tk.Text(body, wrap='none', state='disabled')
    scroll = ttk.Scrollbar(body, command=text.yview)
    horizontal = ttk.Scrollbar(body, orient='horizontal', command=text.xview)
    text.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
    scroll.pack(side='right', fill='y')
    horizontal.pack(side='bottom', fill='x')
    text.pack(fill='both', expand=True)

    def submit(operation):
        state['generation'] += 1
        generation = state['generation']
        def work():
            try:
                results.put((generation, operation(), None))
            except Exception as exc:
                results.put((generation, None, str(exc)))
        threading.Thread(target=work, daemon=True, name='RuntimeInspector').start()

    def refresh():
        root = app_root.get()
        submit(lambda: ('inventory', inventory(runtime_root, root)))

    def choose():
        selected = filedialog.askdirectory(parent=window, initialdir=app_root.get())
        if selected:
            app_root.set(selected)
            refresh()

    def selected(event=None, table=None):
        selection = tree.selection()
        if not selection:
            return
        row = state['rows'].get(selection[0])
        if row is None:
            return
        status.set(f"原始路径：{row['local']} | {row['status']} | {row['purpose']}")
        if table is None:
            tables.set('')
            tables['values'] = ()
        text.configure(state='normal')
        text.delete('1.0', 'end')
        text.insert('1.0', '正在读取…')
        text.configure(state='disabled')
        submit(lambda: ('preview', preview(row['path'], table)))

    def poll():
        if state['closed']:
            return
        try:
            while True:
                generation, result, error = results.get_nowait()
                if generation != state['generation']:
                    continue
                if error:
                    status.set('读取失败（可刷新重试）：' + error)
                    text.configure(state='normal')
                    text.delete('1.0', 'end')
                    text.insert('1.0', '读取失败：' + error)
                    text.configure(state='disabled')
                    continue
                kind, data = result
                if kind == 'inventory':
                    tree.delete(*tree.get_children())
                    state['rows'].clear()
                    for row in data:
                        item = tree.insert('', 'end', text=f"{row['path'].parent.name}/{row['path'].name}",
                                           values=(f"{row['size'] / 1024:.1f} KB", row['status'], row['purpose']))
                        state['rows'][item] = row
                else:
                    content, names = data
                    tables['values'] = names
                    if names and tables.get() not in names:
                        tables.set(names[0])
                    text.configure(state='normal')
                    text.delete('1.0', 'end')
                    text.insert('1.0', content)
                    text.configure(state='disabled')
        except Empty:
            pass
        window.after(100, poll)

    def close():
        state['closed'] = True
        window.destroy()

    ttk.Button(bar, text='选择程序目录', command=choose).pack(side='left', padx=4)
    ttk.Button(bar, text='刷新', command=refresh).pack(side='left')
    tree.bind('<<TreeviewSelect>>', selected)
    tables.bind('<<ComboboxSelected>>', lambda event: selected(table=tables.get()))
    window.protocol('WM_DELETE_WINDOW', close)
    refresh()
    poll()
    if parent is None:
        window.mainloop()
    return window


if __name__ == '__main__':
    open_viewer()
