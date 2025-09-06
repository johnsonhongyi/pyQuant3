import tkinter as tk
from tkinter import ttk

def create_monitor_window(main_root):
    """
    创建并返回监控窗口（Toplevel）。
    """
    monitor_window = tk.Toplevel(main_root)
    monitor_window.title("监控窗口")
    monitor_label = tk.Label(monitor_window, text="这是监控窗口")
    monitor_label.pack(pady=20, padx=20)
    monitor_window.geometry("300x200+550+150") # 宽300，高200，左上角位于屏幕(550, 150)

    return monitor_window


# --- 协调函数（与上面相同） ---
def find_and_bring_to_front(monitor_id):
    """
    根据ID找到窗口并拉到最前。
    """
    if monitor_id in monitor_windows and monitor_windows[monitor_id].winfo_exists():
        bring_both_to_front(root, monitor_windows[monitor_id])
    else:
        print(f"窗口 {monitor_id} 不存在或已关闭。")
def main():
    main_root = tk.Tk()
    main_root.title("主窗口")
    main_label = tk.Label(main_root, text="这是主窗口")
    main_label.pack(pady=20, padx=20)

    # 设置主窗口的尺寸和位置
    main_root.geometry("400x300+100+100") # 宽400，高300，左上角位于屏幕(100, 100)
    # 创建监控窗口
    monitor_window = create_monitor_window(main_root)

    def on_window_focus(event):
        """
        当任意窗口获得焦点时，协调两个窗口到最前。
        """
        bring_both_to_front(main_root, monitor_window)
    
    # 绑定 <FocusIn> 事件
    main_root.bind("<FocusIn>", on_window_focus)
    monitor_window.bind("<FocusIn>", on_window_focus)
    
    main_root.mainloop()

# --- 协调函数（与上面相同） ---
def bring_both_to_front(main_window, monitor_window):
    if main_window and main_window.winfo_exists():
        main_window.lift()
        main_window.attributes('-topmost', 1)
        main_window.attributes('-topmost', 0)
    
    if monitor_window and monitor_window.winfo_exists():
        monitor_window.lift()
        monitor_window.attributes('-topmost', 1)
        monitor_window.attributes('-topmost', 0)





if __name__ == "__main__":
    main()





# import tkinter as tk
# import platform
# import subprocess

# # Dictionary to hold references to the monitor windows
# monitor_windows = {}

# def find_and_bring_to_front(window_id):
#     """
#     Finds a window by its ID and brings it to the front.
#     Uses platform-specific methods for reliability.

#     Args:
#         window_id (str): The ID of the window to find and bring forward.
#     """
#     if window_id in monitor_windows:
#         window = monitor_windows[window_id]
#         try:
#             if platform.system() == 'Darwin':  # macOS
#                 tmpl = 'tell application "System Events" to set frontmost of every process whose unix id is {} to true'
#                 script = tmpl.format(subprocess.check_output(['/bin/sh', '-c', 'ps -p %d -o ppid= | xargs ps -p | tail -n 1 | awk "{print $1}"' % window.winfo_id()]).strip().decode())
#                 subprocess.check_call(['/usr/bin/osascript', '-e', script])
#             else:  # Other systems (Windows, Linux)
#                 window.attributes('-topmost', True)
#                 window.attributes('-topmost', False)
#         except Exception as e:
#             print(f"Failed to bring window to front: {e}")
#     else:
#         print(f"Window with ID '{window_id}' not found.")

# def bring_both_to_front(main_window):
#     """
#     Brings the main window and all monitor windows to the front.

#     Args:
#         main_window (tk.Tk): The main application window.
#     """
#     # Bring the main window to the front first
#     main_window.attributes('-topmost', True)
#     main_window.attributes('-topmost', False)

#     # Bring all monitor windows to the front
#     for window_id in list(monitor_windows.keys()):
#         if window_id in monitor_windows:
#             window = monitor_windows[window_id]
#             try:
#                 window.attributes('-topmost', True)
#                 window.attributes('-topmost', False)
#             except tk.TclError:
#                 # Handle case where window may have been closed
#                 del monitor_windows[window_id]

# def create_monitor_window(main_window, window_id):
#     """
#     Creates a new Toplevel (monitor) window and adds it to the global dictionary.

#     Args:
#         main_window (tk.Tk): The main application window.
#         window_id (str): A unique identifier for the new window.
#     """
#     if window_id in monitor_windows:
#         find_and_bring_to_front(window_id)
#         return

#     # Create a new Toplevel window
#     new_window = tk.Toplevel(main_window)
#     new_window.title(f"Monitor Window - {window_id}")
#     new_window.geometry("300x200")

#     # Store the new window in the dictionary
#     monitor_windows[window_id] = new_window

#     # Add content to the window
#     tk.Label(new_window, text=f"This is monitor window '{window_id}'").pack(pady=10)
#     tk.Button(new_window, text="Bring All Windows to Front", command=lambda: bring_both_to_front(main_window)).pack(pady=5)
#     tk.Button(new_window, text="Close", command=new_window.destroy).pack(pady=5)
    
#     # Handle the case where a monitor window is closed
#     def on_close():
#         del monitor_windows[window_id]
#         new_window.destroy()
#     new_window.protocol("WM_DELETE_WINDOW", on_close)

#     print(f"Created new monitor window: {window_id}")

# def setup_main_window():
#     """
#     Sets up the main Tkinter window with controls for creating and managing monitor windows.
#     """
#     main_window = tk.Tk()
#     main_window.title("Main Control Window")
#     main_window.geometry("400x300")

#     tk.Label(main_window, text="Main Application", font=("Arial", 16)).pack(pady=10)

#     tk.Button(main_window, text="Create Monitor Window 1", command=lambda: create_monitor_window(main_window, "Window1")).pack(pady=5)
#     tk.Button(main_window, text="Create Monitor Window 2", command=lambda: create_monitor_window(main_window, "Window2")).pack(pady=5)
#     tk.Button(main_window, text="Bring Both to Front", command=lambda: bring_both_to_front(main_window)).pack(pady=10)

#     main_window.mainloop()

# if __name__ == "__main__":
#     setup_main_window()
