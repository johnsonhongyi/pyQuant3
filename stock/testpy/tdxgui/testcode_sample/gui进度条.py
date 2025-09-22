import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk
import queue
import time

# ----------------------------
# 模拟 fetch_and_process 逻辑
# ----------------------------
def process_item(item):
    # 这里放原来的计算逻辑
    time.sleep(0.2)  # 模拟耗时
    return item**2

def fetch_and_process_bg(data_list, progress_queue):
    total = len(data_list)
    results = []
    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        futures = {executor.submit(process_item, item): idx for idx, item in enumerate(data_list)}
        for i, future in enumerate(as_completed(futures)):
            res = future.result()
            results.append(res)
            progress_queue.put(i + 1)  # 把当前进度发送给 GUI
    return results

# ----------------------------
# GUI
# ----------------------------
class App:
    def __init__(self, root, data_list):
        self.root = root
        self.data_list = data_list
        self.progress_queue = queue.Queue()

        self.progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(padx=20, pady=20)
        self.status_label = tk.Label(root, text="初始化...")
        self.status_label.pack()

        self.progress["maximum"] = len(data_list)

        # 启动后台线程处理多进程任务
        import threading
        threading.Thread(target=self.run_bg, daemon=True).start()
        self.root.after(100, self.update_progress)

    def run_bg(self):
        self.results = fetch_and_process_bg(self.data_list, self.progress_queue)
        self.progress_queue.put("DONE")

    def update_progress(self):
        try:
            while True:
                val = self.progress_queue.get_nowait()
                if val == "DONE":
                    self.status_label.config(text="完成!")
                    self.progress["value"] = len(self.data_list)
                    return
                else:
                    self.progress["value"] = val
                    self.status_label.config(text=f"处理中... {val}/{len(self.data_list)}")
        except queue.Empty:
            pass
        self.root.after(100, self.update_progress)


if __name__ == "__main__":
    multiprocessing.freeze_support()  # exe 必须
    root = tk.Tk()
    root.title("多进程 GUI 进度条示例")
    data_list = list(range(50))
    app = App(root, data_list)
    root.mainloop()
