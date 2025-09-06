# import tkinter as tk
# import json
# import os
# import threading

# CONFIG_FILE = "window_config.json"
# WINDOW_GEOMETRIES = {}
# WINDOWS_BY_ID = {}
# save_timer = None

# def load_window_positions():
#     """从配置文件加载所有窗口的位置。"""
#     global WINDOW_GEOMETRIES
#     if os.path.exists(CONFIG_FILE):
#         with open(CONFIG_FILE, "r") as f:
#             try:
#                 WINDOW_GEOMETRIES = json.load(f)
#                 print("所有窗口配置已加载。")
#             except (json.JSONDecodeError, FileNotFoundError):
#                 print("配置文件损坏或不存在，使用默认窗口位置。")
#     else:
#         print("未找到配置文件，使用默认位置。")

# def save_window_positions():
#     """将所有窗口的位置和大小保存到配置文件。"""
#     global WINDOW_GEOMETRIES, save_timer
#     if save_timer:
#         save_timer.cancel()
    
#     # 确保文件写入在程序退出前完成
#     try:
#         with open(CONFIG_FILE, "w") as f:
#             json.dump(WINDOW_GEOMETRIES, f)
#         print("所有窗口配置已保存。")
#     except IOError as e:
#         print(f"写入配置文件时出错: {e}")

# def schedule_save_positions():
#     """安排一个延迟保存，避免过于频繁的写入。"""
#     global save_timer
#     if save_timer:
#         save_timer.cancel()
#     save_timer = threading.Timer(1.0, save_window_positions) # 延迟1秒保存
#     save_timer.start()

# def update_window_position(window_id):
#     """更新单个窗口的位置到全局字典。"""
#     window = WINDOWS_BY_ID.get(window_id)
#     if window and window.winfo_exists():
#         WINDOW_GEOMETRIES[window_id] = window.geometry()
#         schedule_save_positions()

# def create_window(root, window_id, is_main=False):
#     """创建一个新窗口，并加载其位置。"""
#     if is_main:
#         window = root
#     else:
#         window = tk.Toplevel(root)
    
#     window.title(f"窗口 - {window_id}")
#     WINDOWS_BY_ID[window_id] = window
    
#     if window_id in WINDOW_GEOMETRIES:
#         window.geometry(WINDOW_GEOMETRIES[window_id])
#     else:
#         if is_main:
#             window.geometry("400x300+100+100")
#         else:
#             window.geometry("300x200+200+200")
    
#     window.bind("<Configure>", lambda event: update_window_position(window_id))
#     window.protocol("WM_DELETE_WINDOW", lambda: on_closing(window, window_id))
    
#     tk.Label(window, text=f"这是窗口: {window_id}", padx=20, pady=20).pack()
    
#     return window

# def on_closing(window, window_id):
#     """在窗口关闭时调用。"""
#     if window.winfo_exists():
#         del WINDOWS_BY_ID[window_id]
#         update_window_position(window_id) # 确保保存最后的配置
#         window.destroy()

#     if not WINDOWS_BY_ID: # 如果所有窗口都已关闭
#         print("所有窗口已关闭。正在保存配置并退出...")
#         save_window_positions()
#         root.quit()

# def create_additional_window():
#     """创建一个新的 Toplevel 窗口。"""
#     new_window_id = f"toplevel_{len(WINDOWS_BY_ID)}"
#     create_window(root, new_window_id)

# # 主程序入口
# if __name__ == "__main__":
#     root = tk.Tk()
#     load_window_positions()
    
#     create_window(root, "main", is_main=True)
    
#     tk.Button(root, text="创建新窗口", command=create_additional_window).pack(pady=10)
    
#     # 确保主窗口关闭时整个应用退出
#     root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, "main"))

#     root.mainloop()




import tkinter as tk
import tkinter.ttk as ttk
import json
import os
import threading

CONFIG_FILE = "window_config.json"
WINDOW_GEOMETRIES = {}
WINDOWS_BY_ID = {}
save_timer = None

# --- 窗口管理和配置保存逻辑 (与之前相同) ---
def load_window_positions():
    global WINDOW_GEOMETRIES
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                WINDOW_GEOMETRIES = json.load(f)
                print("所有窗口配置已加载。")
            except (json.JSONDecodeError, FileNotFoundError):
                print("配置文件损坏或不存在，使用默认窗口位置。")
    else:
        print("未找到配置文件，使用默认位置。")

def save_window_positions():
    global WINDOW_GEOMETRIES, save_timer
    if save_timer:
        save_timer.cancel()
    
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(WINDOW_GEOMETRIES, f)
        print("所有窗口配置已保存。")
    except IOError as e:
        print(f"写入配置文件时出错: {e}")

def schedule_save_positions():
    global save_timer
    if save_timer:
        save_timer.cancel()
    save_timer = threading.Timer(1.0, save_window_positions)
    save_timer.start()

def update_window_position(window_id):
    window = WINDOWS_BY_ID.get(window_id)
    if window and window.winfo_exists():
        WINDOW_GEOMETRIES[window_id] = window.geometry()
        schedule_save_positions()

# --- 自定义标题栏功能 ---
def move_window(event):
    window = event.widget.winfo_toplevel()
    window.geometry(f'+{event.x_root}+{event.y_root}')

def create_custom_title_bar(window, title_text, height=15):
    window.overrideredirect(True)
    title_bar = tk.Frame(window, bg='lightgray', height=height, relief='raised', bd=0)
    title_bar.pack(fill='x', side='top')
    title_bar.bind("<B1-Motion>", move_window)
    
    title_label = tk.Label(title_bar, text=title_text, bg='lightgray', font=('Arial', int(height/2)), fg='black')
    title_label.pack(side='left', padx=5, pady=2)
    
    close_button = tk.Button(title_bar, text='X', command=window.destroy, bg='red', fg='white', relief='flat')
    close_button.pack(side='right')

    content_frame = tk.Frame(window, bg='white')
    content_frame.pack(fill='both', expand=True)
    
    return content_frame

# --- 整合 Treeview 和 PanedWindow 的窗口创建函数 ---
def create_monitored_window(root, window_id, is_main=False):
    if is_main:
        window = root
        title_text = "主窗口 (带Treeview)"
    else:
        window = tk.Toplevel(root)
        title_text = f"子窗口 - {window_id}"
    
    WINDOWS_BY_ID[window_id] = window
    
    content_frame = create_custom_title_bar(window, title_text, height=20)
    
    if window_id in WINDOW_GEOMETRIES:
        window.geometry(WINDOW_GEOMETRIES[window_id])
    else:
        if is_main:
            window.geometry("800x600+100+100")
        else:
            window.geometry("600x400+200+200")
    
    window.bind("<Configure>", lambda event: update_window_position(window_id))
    window.protocol("WM_DELETE_WINDOW", lambda: on_closing(window, window_id))

    paned_window = ttk.PanedWindow(content_frame, orient=tk.HORIZONTAL)
    paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    left_frame = ttk.Frame(paned_window, relief="sunken")
    paned_window.add(left_frame, weight=1)
    
    right_frame = ttk.Frame(paned_window, relief="sunken")
    paned_window.add(right_frame, weight=2)
    
    tree_frame = ttk.Frame(left_frame)
    tree_frame.pack(fill=tk.BOTH, expand=True)
    
    tree_view = ttk.Treeview(tree_frame, columns=("size", "date"))
    tree_view.heading("#0", text="文件/目录")
    tree_view.heading("size", text="大小")
    tree_view.heading("date", text="修改日期")
    tree_view.column("#0", stretch=tk.YES)
    tree_view.column("size", width=100)
    tree_view.column("date", width=150)
    
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree_view.yview)
    tree_view.configure(yscrollcommand=vsb.set)
    
    tree_view.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    
    tree_view.insert('', 'end', text="目录 A", open=True)
    tree_view.insert('', 'end', text="目录 B", open=False)
    tree_view.insert('I001', 'end', text="文件 A1", values=("1.2MB", "2023-01-01"))
    
    # 额外添加一个 Frame，用于放置创建新窗口的按钮，防止被 PanedWindow 遮挡
    button_frame = ttk.Frame(right_frame)
    button_frame.pack(side='bottom', pady=10)
    tk.Button(button_frame, text="创建新窗口", command=lambda: create_additional_window(root)).pack()

    # 返回窗口对象和内容区域
    return window, content_frame

def on_closing(window, window_id):
    if window.winfo_exists():
        del WINDOWS_BY_ID[window_id]
        update_window_position(window_id)
        window.destroy()

    if not WINDOWS_BY_ID:
        print("所有窗口已关闭。正在保存配置并退出...")
        save_window_positions()
        root.quit()

def create_additional_window(root):
    new_window_id = f"toplevel_{len(WINDOWS_BY_ID)}"
    create_monitored_window(root, new_window_id)

# 主程序入口
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    
    load_window_positions()
    
    main_window, main_content_frame = create_monitored_window(root, "main", is_main=True)
    
    # 显示主窗口
    main_window.deiconify()

    root.mainloop()
