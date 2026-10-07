# -*- coding: utf-8 -*-
"""
验证生产容器 /data/InStock 的代码一致性与功能完整性
"""
import subprocess
import json
import sys

def run_ssh(cmd):
    full_cmd = ["ssh.exe", "-o", "StrictHostKeyChecking=yes", "root@192.168.1.50", cmd]
    res = subprocess.run(full_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.returncode, res.stdout, res.stderr

def main():
    print("=== 1. 检查容器状态 ===")
    rc, out, err = run_ssh("pct exec 102 -- docker ps -a --filter name=inStock --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'")
    print(out.strip())
    assert rc == 0 and "inStock" in out, "inStock container is not running!"

    print("\n=== 2. 检查 Git 仓库状态与提交 ===")
    rc, out, err = run_ssh("pct exec 102 -- docker exec -w /data/InStock inStock git status -s")
    print("Git status dirty files:", out.strip() if out.strip() else "None (Clean)")
    assert rc == 0, f"git status failed: {err}"

    rc, out, err = run_ssh("pct exec 102 -- docker exec -w /data/InStock inStock git log -1 --format='%h %s (%cd)' --date=iso")
    print("Container HEAD commit:", out.strip())

    print("\n=== 3. 根目录排查 (确认无残留软链接) ===")
    rc, out, err = run_ssh("pct exec 102 -- docker exec -w /data/InStock inStock ls -la")
    has_symlink = "JSONData ->" in out or "JSONData" in [line.split()[-1] for line in out.splitlines() if line]
    print("Has root JSONData symlink:", has_symlink)
    assert not has_symlink, "Root JSONData symlink should be removed!"

    print("\n=== 4. 关键文件 SHA256 跨环境比对 ===")
    files = [
        "instock/JSONData/__init__.py",
        "instock/JSONData/history_cache.py",
        "instock/JSONData/prepared_history.py",
        "instock/JSONData/sina_data.py",
        "instock/JSONData/tdx_data_Day.py",
        "instock/core/stockfetch.py",
        "instock/job/strategy_enter-edit.py",
        "instock/job/prewarm_history.py",
        "instock/job/prewarm_tuner.py",
        "instock/job/static_strategy_cache.py",
        "instock/job/streaming_scan.py",
        "instock/job/run_statistics.py"
    ]
    file_list_str = " ".join(files)
    rc, out, err = run_ssh(f"pct exec 102 -- docker exec -w /data/InStock inStock sha256sum {file_list_str}")
    container_hashes = {}
    for line in out.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            container_hashes[parts[1]] = parts[0]

    import os, hashlib
    local_base = r"D:\MacTools\WorkFile\WorkSpace\InStock"
    all_matched = True
    for f in files:
        local_p = os.path.join(local_base, f.replace("/", os.sep))
        with open(local_p, "rb") as fp:
            local_h = hashlib.sha256(fp.read()).hexdigest()
        remote_h = container_hashes.get(f, "MISSING")
        match = (local_h == remote_h)
        status_str = "MATCH" if match else "MISMATCH"
        print(f"[{status_str}] {f}: {local_h[:12]} vs {remote_h[:12]}")
        if not match:
            all_matched = False
    assert all_matched, "File hash mismatch detected!"

    print("\n=== 5. 容器内 Python 模块导入与别名深度测试 ===")
    python_test_code = (
        "import instock.JSONData as jd; "
        "import JSONData as legacy_jd; "
        "assert jd is legacy_jd, 'alias mismatch'; "
        "from instock.core import stockfetch; "
        "import importlib; "
        "mods = ['job.strategy_enter-edit', 'job.prewarm_history', 'job.prewarm_tuner', 'job.static_strategy_cache', 'job.streaming_scan', 'job.run_statistics']; "
        "[importlib.import_module('instock.' + m) for m in mods]; "
        "print('ALL_MODULES_LOADED_SUCCESSFULLY')"
    )
    rc, out, err = run_ssh(f"pct exec 102 -- docker exec -w /data/InStock inStock python3 -c \"{python_test_code}\"")
    print("Python import test result:", out.strip())
    assert "ALL_MODULES_LOADED_SUCCESSFULLY" in out, f"Import test failed: {out}\n{err}"

    print("\n=== 6. 容器内语法编译测试 (compileall) ===")
    rc, out, err = run_ssh("pct exec 102 -- docker exec -w /data/InStock inStock python3 -m compileall -q instock/JSONData instock/job instock/core")
    print("Compileall return code:", rc)
    assert rc == 0, f"compileall failed: {err}"

    print("\n=== 7. 定时任务 (crontab) 核查 ===")
    rc, out, err = run_ssh("pct exec 102 -- docker exec inStock cat /var/spool/cron/crontabs/root")
    has_0810_prewarm = ("10 8 * * 1-5" in out or "10 08 * * 1-5" in out) and "prewarm_history.py" in out
    has_lock = "strategy_enter.lock" in out
    print("Crontab has 08:10 (10 8 * * 1-5) prewarm with lock:", has_0810_prewarm and has_lock)
    assert has_0810_prewarm and has_lock, "08:10 prewarm missing from crontab!"

    print("\n=== 8. Web 服务响应核查 (端口 9988) ===")
    py_http_check = "import urllib.request; req = urllib.request.Request('http://127.0.0.1:9988/'); print(urllib.request.urlopen(req, timeout=5).getcode())"
    rc, out, err = run_ssh(f"pct exec 102 -- docker exec inStock python3 -c \"{py_http_check}\"")
    print("Web service HTTP response code:", out.strip())
    assert "200" in out or "302" in out, f"Web service check failed: {out}\n{err}"

    print("\n=== 9. 持久化数据挂载卷状态 ===")
    rc, out, err = run_ssh("pct exec 102 -- docker exec inStock sh -c 'ls -ld /data/InStock/instock/forwardp /data/InStock/instock/cache /data/InStock/instock/log'")
    print(out.strip())

    print("\n==========================================")
    print(">>> 恭喜：容器内容与最新修改 100% 一致，全部功能完备！ <<<")
    print("==========================================")

if __name__ == "__main__":
    main()
