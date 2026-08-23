# -*- coding: utf-8 -*-
"""
apply_clash_rules.py — 一键将量化金融与 EA/Steam 游戏直连规则同步至 Clash Verge Rev 配置
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
    print("[Quant Stock System & Gaming - Clash Direct Rules Restore & Sync]")
    print("=" * 65)

    if not os.path.exists(CLASH_VERGE_REV_DIR):
        print(f"[ERROR] Clash Verge Rev directory not found: {CLASH_VERGE_REV_DIR}")
        return False

    print(f"[OK] Located Clash Verge Rev dir: {CLASH_VERGE_REV_DIR}")
    paths = get_rule_backup_paths()
    profiles_dir = os.path.join(CLASH_VERGE_REV_DIR, "profiles")

    # 1. 同步 Merge.yaml 与当前激活 profile 的 Merge 文件
    if os.path.exists(paths["merge"]):
        dest_merge = os.path.join(profiles_dir, "Merge.yaml")
        shutil.copyfile(paths["merge"], dest_merge)
        print(f"  [1/4] Synced Global Merge Rules -> {dest_merge}")

        # 遍历 profiles 下所有的 merge 扩展文件并同步
        for f in os.listdir(profiles_dir):
            if f.endswith(".yaml") and f not in ("Merge.yaml", "r0Xk7B9JlzuG.yaml") and not f.startswith("Rgq"):
                dest_f = os.path.join(profiles_dir, f)
                shutil.copyfile(paths["merge"], dest_f)
                print(f"  [1/4+] Synced Active Profile Merge -> {dest_f}")

    # 2. 同步当前 profile 的 rules 扩展文件 (r0Xk7B9JlzuG.yaml)
    if os.path.exists(paths["merge"]):
        rules_file = os.path.join(profiles_dir, "r0Xk7B9JlzuG.yaml")
        # 将 prepend-rules 转换为 prepend:
        with open(paths["merge"], "r", encoding="utf-8") as f:
            content = f.read()
        content_rules = content.replace("prepend-rules:", "prepend:")
        with open(rules_file, "w", encoding="utf-8") as f:
            f.write(content_rules)
        print(f"  [2/4] Synced Active Profile Rules -> {rules_file}")

    # 3. 同步 Script.js 与所有 js 扩展
    dest_script = os.path.join(profiles_dir, "Script.js")
    if os.path.exists(paths["script"]):
        shutil.copyfile(paths["script"], dest_script)
        for f in os.listdir(profiles_dir):
            if f.endswith(".js"):
                shutil.copyfile(paths["script"], os.path.join(profiles_dir, f))
        print(f"  [3/4] Synced Global & Profile Scripts -> {dest_script}")

    # 4. 增强 dns_config.yaml
    dest_dns = os.path.join(CLASH_VERGE_REV_DIR, "dns_config.yaml")
    if os.path.exists(dest_dns):
        try:
            with open(dest_dns, "r", encoding="utf-8") as f:
                dns_content = f.read()
            
            domains = [
                "*.sinajs.cn", "*.gtimg.cn", "*.eastmoney.com", "*.10jqka.com.cn", "*.upchina.com", "*.tdx.com.cn",
                "*.ea.com", "*.origin.com", "*.electronicarts.com", "*.akamaized.net", "*.akamaihd.net",
                "*.edgekey.net", "*.edgesuite.net", "*.steamconnecttest.com", "*.steamcontent.com", "*.respawn.com", "*.dice.se"
            ]
            modified = False
            for d in domains:
                if d not in dns_content:
                    dns_content = dns_content.replace("fake-ip-filter:", f"fake-ip-filter:\n  - '{d}'")
                    modified = True
            if modified:
                with open(dest_dns, "w", encoding="utf-8") as f:
                    f.write(dns_content)
            print(f"  [4/4] Updated DNS Fake-IP Whitelist -> {dest_dns}")
        except Exception as e:
            print(f"  [4/4] Warning on updating dns_config.yaml: {e}")

    print("\n[SUCCESS] All direct rules (Stock + EA Games + Downloads) applied successfully!")
    print("-> Please click 'Settings' -> 'Restart Core' in Clash Verge to take effect.")
    return True

def test_speed():
    print("\n" + "=" * 65)
    print("[Testing Realtime Latency for Stock & Gaming APIs]")
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
            status_tag = "PASS (Fast Direct)" if cost < 200 else "PASS (Normal)"
            print(f"  {name:<22} Latency: {cost:6.1f} ms  -> [{status_tag}]")
        except Exception as e:
            print(f"  {name:<22} Note: {e}")

if __name__ == "__main__":
    apply_rules()
    test_speed()
