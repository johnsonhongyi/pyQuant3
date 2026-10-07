import subprocess
import base64
import time

def run_remote_python(code_str):
    b64 = base64.b64encode(code_str.encode('utf-8')).decode('ascii')
    cmd = ["ssh", "root@192.168.1.50", f"pct exec 102 -- docker exec inStock python3 -c \"import base64; exec(base64.b64decode('{b64}').decode('utf-8'))\""]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return res

if __name__ == '__main__':
    # 1. 静态结果缓存直出测试
    script_static = """
import os, sys, time, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')
import importlib
see = importlib.import_module("instock.job.strategy_enter-edit")
os.environ['INSTOCK_STREAM_STRATEGIES'] = '1'
os.environ['INSTOCK_STATIC_RESULT_CACHE'] = '1'

t0 = time.perf_counter()
print("=== 4-CORE STATIC CACHE HIT TEST ===")
see.strategy_enter(small_strategies_only=True)
print(f"=== STATIC CACHE HIT WALL CLOCK: {time.perf_counter() - t0:.2f}s ===")
"""
    print("Testing 4-Core Static Result Cache...")
    res = run_remote_python(script_static)
    print("RETURN CODE:", res.returncode)
    print("STDOUT:\n", res.stdout)
    if res.stderr:
        print("STDERR:\n", res.stderr)

    # 2. 真实全量 4 核重算测试
    script_recompute = """
import os, sys, time, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')
import importlib
see = importlib.import_module("instock.job.strategy_enter-edit")
os.environ['INSTOCK_STREAM_STRATEGIES'] = '1'
os.environ['INSTOCK_STATIC_RESULT_CACHE'] = '0'

t0 = time.perf_counter()
print("=== 4-CORE RECOMPUTE (5544 STOCKS x 2 STRATEGIES) ===")
see.strategy_enter(small_strategies_only=True)
print(f"=== 4-CORE RECOMPUTE WALL CLOCK: {time.perf_counter() - t0:.2f}s ===")
"""
    print("\nTesting 4-Core Full Recomputation (4 workers concurrent)...")
    res2 = run_remote_python(script_recompute)
    print("RETURN CODE:", res2.returncode)
    print("STDOUT:\n", res2.stdout)
    if res2.stderr:
        print("STDERR:\n", res2.stderr)
