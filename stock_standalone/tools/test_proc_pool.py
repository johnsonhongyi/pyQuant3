import subprocess
import base64

def run_remote_python(code_str):
    b64 = base64.b64encode(code_str.encode('utf-8')).decode('ascii')
    cmd = ["ssh", "root@192.168.1.50", f"pct exec 102 -- docker exec inStock python3 -c \"import base64; exec(base64.b64decode('{b64}').decode('utf-8'))\""]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return res

if __name__ == '__main__':
    test_script = """
import os, sys, time, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

import concurrent.futures
import importlib
see = importlib.import_module("instock.job.strategy_enter-edit")

print("Checking os.cpu_count():", os.cpu_count())
"""
    res = run_remote_python(test_script)
    print(res.stdout)
    if res.stderr:
        print(res.stderr)
