import win32gui

def enum_callback(hwnd, _):
    if win32gui.IsWindowVisible(hwnd):
        title = win32gui.GetWindowText(hwnd)
        if title:
            print(f"HWND: {hwnd} | Title: {title}")

print("--- Visible Windows ---")
win32gui.EnumWindows(enum_callback, None)
