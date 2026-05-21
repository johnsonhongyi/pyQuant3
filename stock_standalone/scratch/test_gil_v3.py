# -*- coding: utf-8 -*-
import time
import threading
import tkinter as tk
from tk_gil_monitor import install, TraceQueue, TraceLock, gil_mark, block_mark

def simulate_cpu_bound_work():
    gil_mark("simulate_cpu_bound_work:start")
    print("[Test] Starting CPU-bound work...")
    # Simulate a loop that holds the GIL
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 1.5:
        # tight loop to starve UI
        pass
    print("[Test] Finished CPU-bound work.")
    gil_mark("simulate_cpu_bound_work:end")

def simulate_blocking_queue():
    q = TraceQueue(name="test_q")
    print("[Test] Putting item to queue...")
    q.put("hello")
    print("[Test] Getting item from queue...")
    item = q.get()
    print(f"[Test] Got: {item}")

def simulate_lock_hold():
    lock = TraceLock("test_lock", timeout=2.0)
    def holder():
        with lock:
            print("[Test] Lock held by background thread...")
            time.sleep(2.5)
            print("[Test] Lock released by background thread.")

    threading.Thread(target=holder, daemon=True).start()
    time.sleep(0.5)
    print("[Test] Main thread trying to acquire lock (expect timeout/slow log)...")
    with lock:
        print("[Test] Main thread acquired lock!")

def main():
    root = tk.Tk()
    root.title("GIL Radar v3 Test")
    root.geometry("200x100")

    # Install monitor
    monitor = install(root=root, freeze_threshold=1.0, enabled=True, cpu_sampling=True)

    tk.Button(root, text="Tight GIL Loop", command=simulate_cpu_bound_work).pack(pady=5)
    tk.Button(root, text="Blocking Queue", command=simulate_blocking_queue).pack(pady=5)
    tk.Button(root, text="Lock Timeout", command=simulate_lock_hold).pack(pady=5)

    # Let root close automatically after 5 seconds to run headless tests or allow quick verification
    def auto_test():
        print("--- RUNNING AUTOMATED GIL STUCK TEST ---")
        simulate_cpu_bound_work()
        
        print("--- RUNNING QUEUE BLOCK TEST ---")
        simulate_blocking_queue()
        
        print("--- RUNNING LOCK BLOCK TEST ---")
        simulate_lock_hold()
        
        print("--- AUTOMATED TESTS COMPLETED ---")
        root.destroy()

    root.after(1000, auto_test)
    root.mainloop()

if __name__ == "__main__":
    main()
