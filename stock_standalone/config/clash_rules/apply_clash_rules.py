# -*- coding: utf-8 -*-
"""
apply_clash_rules.py — 一键将量化金融直连规则同步至 Clash Verge Rev 配置
"""

import sys
import os
import shutil
import time
import requests

CLASH_VERGE_REV_DIR = os.path.expandvars(r"%APPDATA%\io.github.clash-verge-rev.clash-verge-rev")
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_rule_backup_paths():
    base = CURRENT_DIR
    return {
        "merge": os.path.join(base, "clash_custom_direct_rules.yaml"),
        "script": os.path.join(base, "clash_custom_direct_script.js"),
        "dns": os.path.join(base, "clash_dns_fakeip_filter.yaml"),
    }

def apply_rules():
    print("=" * 65)
    print("[Quant Stock System - Clash Direct Rules Restore & Sync Tool]")
    print("=" * 65)

    if not os.path.exists(CLASH_VERGE_REV_DIR):
        print(f"[ERROR] Clash Verge Rev directory not found: {CLASH_VERGE_REV_DIR}")
        return False

    print(f"[OK] Located Clash Verge Rev dir: {CLASH_VERGE_REV_DIR}")
    paths = get_rule_backup_paths()

    # 1. 同步 Merge.yaml
    dest_merge = os.path.join(CLASH_VERGE_REV_DIR, "profiles", "Merge.yaml")
    if os.path.exists(paths["merge"]):
        shutil.copyfile(paths["merge"], dest_merge)
        print(f"  [1/3] Synced Global Merge Rules -> {dest_merge}")

    # 2. 同步 Script.js
    dest_script = os.path.join(CLASH_VERGE_REV_DIR, "profiles", "Script.js")
    if os.path.exists(paths["script"]):
        shutil.copyfile(paths["script"], dest_script)
        print(f"  [2/3] Synced Global Script -> {dest_script}")

    # 3. 增强 dns_config.yaml
    dest_dns = os.path.join(CLASH_VERGE_REV_DIR, "dns_config.yaml")
    if os.path.exists(dest_dns):
        try:
            with open(dest_dns, "r", encoding="utf-8") as f:
                dns_content = f.read()
            
            domains = ["*.sinajs.cn", "*.gtimg.cn", "*.eastmoney.com", "*.10jqka.com.cn", "*.upchina.com", "*.tdx.com.cn"]
            modified = False
            for d in domains:
                if d not in dns_content:
                    dns_content = dns_content.replace("fake-ip-filter:", f"fake-ip-filter:\n  - '{d}'")
                    modified = True
            if modified:
                with open(dest_dns, "w", encoding="utf-8") as f:
                    f.write(dns_content)
            print(f"  [3/3] Updated DNS Fake-IP Whitelist -> {dest_dns}")
        except Exception as e:
            print(f"  [3/3] Warning on updating dns_config.yaml: {e}")

    print("\n[SUCCESS] All direct rules applied successfully!")
    print("-> Please click 'Settings' -> 'Restart Core' in Clash Verge to take effect.")
    return True

def test_speed():
    print("\n" + "=" * 65)
    print("[Testing Realtime Latency for Stock APIs]")
    print("=" * 65)
    targets = [
        ("Sina Realtime", "http://hq.sinajs.cn/list=sh600519,sz000001"),
        ("Tencent Realtime", "http://qt.gtimg.cn/q=sh600519,sz000001"),
        ("Eastmoney Realtime", "http://push2.eastmoney.com/api/qt/stock/get?secid=1.600519&fields=f43,f57,f58")
    ]
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'})
    for name, u in targets:
        t0 = time.time()
        try:
            r = s.get(u, timeout=5)
            cost = (time.time() - t0) * 1000
            status_tag = "PASS (Fast Direct)" if cost < 150 else "PASS (Normal)"
            print(f"  {name:<20} Latency: {cost:6.1f} ms  -> [{status_tag}]")
        except Exception as e:
            print(f"  {name:<20} Error: {e}")

if __name__ == "__main__":
    apply_rules()
    test_speed()
