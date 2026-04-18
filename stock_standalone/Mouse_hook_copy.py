import time
import win32api
import win32con

# =========================
# 参数（可调）
# =========================
CLICK_TIMEOUT = 0.25
DOUBLE_MIN = 0.05
RIGHT_TIMEOUT = 1.5
POLL_INTERVAL = 0.005  # 5ms

# =========================
# 状态机（核心）
# =========================
class ClickState:
    __slots__ = ("last_click", "clicks", "double_flag")

    def __init__(self):
        self.last_click = 0.0
        self.clicks = 0
        self.double_flag = False

state = ClickState()

# =========================
# 键盘操作
# =========================
def key_esc():
    win32api.keybd_event(0x1B, 0, 0, 0)
    win32api.keybd_event(0x1B, 0, win32con.KEYEVENTF_KEYUP, 0)

def key_copy():
    # Ctrl + Insert（比 Ctrl+C 更通用）
    win32api.keybd_event(0x11, 0, 0, 0)   # Ctrl down
    win32api.keybd_event(0x2D, 0, 0, 0)   # Ins down
    win32api.keybd_event(0x2D, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(0x11, 0, win32con.KEYEVENTF_KEYUP, 0)

# =========================
# 核心逻辑
# =========================
def handle_left_up():
    now = time.perf_counter()
    dt = now - state.last_click

    if dt > CLICK_TIMEOUT:
        # 新点击序列
        state.clicks = 1
        state.double_flag = False
    else:
        state.clicks += 1
        if state.clicks == 2 and dt > DOUBLE_MIN:
            state.double_flag = True

    state.last_click = now

def handle_right_up():
    now = time.perf_counter()

    if state.double_flag and (now - state.last_click < RIGHT_TIMEOUT):
        print(f"[TRIGGER] double+right copy ({now - state.last_click:.3f}s)")
        key_esc()
        time.sleep(0.01)
        key_copy()

    # reset
    state.double_flag = False
    state.clicks = 0

# =========================
# 主循环（优化版）
# =========================
def main():
    state_left = win32api.GetKeyState(0x01)
    state_right = win32api.GetKeyState(0x02)

    while True:
        a = win32api.GetKeyState(0x01)
        b = win32api.GetKeyState(0x02)

        # 左键变化
        if a != state_left:
            state_left = a
            if a >= 0:  # left up
                handle_left_up()

        # 右键变化
        if b != state_right:
            state_right = b
            if b >= 0:  # right up
                handle_right_up()

        time.sleep(POLL_INTERVAL)

# =========================
# 启动
# =========================
if __name__ == "__main__":
    print("🚀 Mouse hook started (optimized)")
    main()