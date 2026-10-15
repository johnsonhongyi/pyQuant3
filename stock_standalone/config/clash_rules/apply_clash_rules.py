# -*- coding: utf-8 -*-
"""
apply_clash_rules.py — 一键将量化金融、微软更新直连与白名单分流规则同步至 Clash Verge Rev
核心效果:
1. 股票金融、通达信行情、EA/Steam 游戏满速直连 (毫秒级响应);
2. Windows 系统更新、VS 2019/更新、Defender 病毒库、Office 强制直连 (彻底阻断几十 GB 流量偷跑);
3. 策略组优化: Microsoft、Apple、Download 默认选定 DIRECT;
4. 兜底规则重构: 尾部彻底改为 MATCH,DIRECT (白名单模式: 仅明确的外网请求走代理，其余未知流量全部走直连).
"""

import sys
import os
import shutil
import time
import re
import yaml
import subprocess
import requests

CLASH_VERGE_REV_DIR = os.path.expandvars(r"%APPDATA%\io.github.clash-verge-rev.clash-verge-rev")
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# GPT/ChatGPT authentication and Codex requests must share one proxy group.
PROTECTED_AI_RULES = (
    "DOMAIN-SUFFIX,chatgpt.com,Research + AI",
    "DOMAIN-SUFFIX,openai.com,Research + AI",
    "DOMAIN-SUFFIX,oaistatic.com,Research + AI",
    "DOMAIN-SUFFIX,oaiusercontent.com,Research + AI",
    "DOMAIN-SUFFIX,oaistatsig.com,Research + AI",
    "DOMAIN-SUFFIX,openaimerge.com,Research + AI",
    "DOMAIN-SUFFIX,workos.com,Research + AI",
    "DOMAIN-SUFFIX,workoscdn.com,Research + AI",
    "DOMAIN,workos.imgix.net,Research + AI",
    "DOMAIN-SUFFIX,ct.sendgrid.net,Research + AI",
    "DOMAIN,challenges.cloudflare.com,Research + AI",
)
PROTECTED_AI_DOMAINS = {rule.split(",", 2)[1].lower() for rule in PROTECTED_AI_RULES}


def patch_protected_ai_rules(content):
    """Place managed ChatGPT/Codex routes before all generated profile rules."""
    lines = content.splitlines()
    rules_index = next(
        (index for index, line in enumerate(lines) if re.match(r"^rules\s*:\s*(?:#.*)?$", line)),
        None,
    )
    if rules_index is None:
        return content, False

    end_index = len(lines)
    for index in range(rules_index + 1, len(lines)):
        line = lines[index]
        stripped = line.lstrip()
        if line.strip() and not line[0].isspace() and not stripped.startswith(("#", "-")):
            end_index = index
            break

    indent_counts = {}
    for line in lines[rules_index + 1:end_index]:
        indent_match = re.match(r"^(\s*)-\s+", line)
        if indent_match:
            indent = indent_match.group(1)
            indent_counts[indent] = indent_counts.get(indent, 0) + 1
    rule_indent = max(indent_counts, key=indent_counts.get) if indent_counts else "  "
    kept_rules = []
    for line in lines[rules_index + 1:end_index]:
        raw = line.strip()
        if raw.startswith("-"):
            raw = raw[1:].strip()
        raw = raw.split("#", 1)[0].strip().strip("\"'")
        fields = [field.strip().strip("\"'") for field in raw.split(",")]
        if (
            len(fields) >= 2
            and fields[0].upper() in ("DOMAIN", "DOMAIN-SUFFIX")
            and fields[1].lower() in PROTECTED_AI_DOMAINS
        ):
            continue
        if raw.lower() == "process-name,msedge.exe,direct":
            continue
        rule_match = re.match(r"^\s*-\s+(.*)$", line)
        kept_rules.append(f"{rule_indent}- {rule_match.group(1)}" if rule_match else line)

    managed_rules = [f"{rule_indent}- {rule}" for rule in PROTECTED_AI_RULES]
    lines = lines[:rules_index + 1] + managed_rules + kept_rules + lines[end_index:]
    return "\n".join(lines) + "\n", True


def get_rule_backup_paths():
    base = CURRENT_DIR
    return {
        "merge": os.path.join(base, "clash_custom_direct_rules.yaml"),
        "script": os.path.join(base, "clash_custom_direct_script.js"),
        "dns": os.path.join(base, "clash_dns_fakeip_filter.yaml"),
    }


def get_profile_component_uids(profiles_yaml_path, component_type, fallback_uid=None):
    """Return only registered component IDs of the requested Clash profile type."""
    try:
        with open(profiles_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        uids = [
            item.get("uid")
            for item in data.get("items", [])
            if isinstance(item, dict)
            and item.get("type") == component_type
            and isinstance(item.get("uid"), str)
            and re.fullmatch(r"[A-Za-z0-9_-]+", item["uid"])
        ]
        if fallback_uid and fallback_uid not in uids:
            uids.insert(0, fallback_uid)
        return list(dict.fromkeys(uids))
    except Exception as e:
        print(f"  [-] Warning on reading profile components ({component_type}): {e}")
        return [fallback_uid] if fallback_uid else []

def update_profiles_yaml(profiles_yaml_path):
    """确保 profiles.yaml 中的策略组默认选中 DIRECT (Microsoft, Apple, Download)"""
    if not os.path.exists(profiles_yaml_path):
        return
    try:
        with open(profiles_yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        modified = False
        items = data.get('items', [])
        for item in items:
            if item.get('type') == 'remote' and 'selected' in item:
                selected_list = item['selected']
                selected_map = {s.get('name'): s for s in selected_list if isinstance(s, dict)}
                
                for group_name in ['Microsoft', 'Apple', 'Download']:
                    if group_name in selected_map:
                        if selected_map[group_name].get('now') != 'DIRECT':
                            selected_map[group_name]['now'] = 'DIRECT'
                            modified = True
                    else:
                        selected_list.append({'name': group_name, 'now': 'DIRECT'})
                        modified = True
        
        if modified:
            with open(profiles_yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
            print(f"  [+] Updated profiles.yaml: Microsoft & Apple default selected to DIRECT")
    except Exception as e:
        print(f"  [-] Warning on updating profiles.yaml: {e}")

def patch_clash_runtime_yaml(clash_verge_yaml_path):
    """Patch generated runtime configs with stable AI egress rules and direct fallback."""
    for ypath in [clash_verge_yaml_path, clash_verge_yaml_path.replace("clash-verge.yaml", "clash-verge-check.yaml")]:
        if not os.path.exists(ypath):
            continue
        try:
            with open(ypath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            content, route_rules_patched = patch_protected_ai_rules(content)
            if not route_rules_patched:
                print(f"  [-] Warning: no top-level rules section found in {ypath}; skipped runtime patch")
                continue
            
            # 1. 确保 proxy-groups 中 Microsoft, Apple, Download 的首选项为 DIRECT
            # 替换 Microsoft 代理组里的第一个项为 DIRECT
            # 简单安全的正则/字符串替换
            old_ms_block = """- name: Microsoft\n  type: select\n  proxies:\n  - US-Balancer-"""
            new_ms_block = """- name: Microsoft\n  type: select\n  proxies:\n  - DIRECT\n  - US-Balancer-"""
            if old_ms_block in content:
                content = content.replace(old_ms_block, new_ms_block)
            
            old_apple_block = """- name: Apple\n  type: select\n  proxies:\n  - US-Balancer-"""
            new_apple_block = """- name: Apple\n  type: select\n  proxies:\n  - DIRECT\n  - US-Balancer-"""
            if old_apple_block in content:
                content = content.replace(old_apple_block, new_apple_block)

            # 2. 尾部兜底重构: 将 MATCH,Default Proxy 改写为白名单直连链
            # 匹配最后的 MATCH,...
            lines = content.splitlines()
            cleaned_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("- MATCH,") or stripped.startswith("MATCH,"):
                    continue
                cleaned_lines.append(line)
            
            # 追加白名单安全尾链
            # 检查是否有 GEOSITE,gfw
            has_gfw = any("GEOSITE,gfw" in l for l in cleaned_lines)
            if not has_gfw:
                cleaned_lines.append("- GEOSITE,gfw,Default Proxy")
            cleaned_lines.append("- GEOIP,CN,DIRECT")
            cleaned_lines.append("- GEOIP,PRIVATE,DIRECT")
            cleaned_lines.append("- MATCH,DIRECT")

            new_content = "\n".join(cleaned_lines) + "\n"
            with open(ypath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"  [+] Patched runtime yaml -> {ypath} (WhiteList Mode: MATCH,DIRECT)")
        except Exception as e:
            print(f"  [-] Warning on patching {ypath}: {e}")

def apply_rules():
    print("=" * 68)
    print("[Quant Stock System & Whitelist Traffic Guard - Clash Verge Rev]")
    print("=" * 68)

    if not os.path.exists(CLASH_VERGE_REV_DIR):
        print(f"[ERROR] Clash Verge Rev directory not found: {CLASH_VERGE_REV_DIR}")
        return False

    print(f"[OK] Located Clash Verge Rev dir: {CLASH_VERGE_REV_DIR}")
    paths = get_rule_backup_paths()
    profiles_dir = os.path.join(CLASH_VERGE_REV_DIR, "profiles")
    profiles_yaml_path = os.path.join(CLASH_VERGE_REV_DIR, "profiles.yaml")

    # 1. Sync only registered Merge components; never overwrite proxies/groups/remote profiles.
    if os.path.exists(paths["merge"]):
        for uid in get_profile_component_uids(profiles_yaml_path, "merge", "Merge"):
            dest_merge = os.path.join(profiles_dir, f"{uid}.yaml")
            shutil.copyfile(paths["merge"], dest_merge)
            print(f"  [1/5] Synced Merge component -> {dest_merge}")

    # 2. Sync registered Rules components using Clash Verge's `prepend` key.
    if os.path.exists(paths["merge"]):
        with open(paths["merge"], "r", encoding="utf-8") as f:
            content = f.read()
        content_rules = content.replace("prepend-rules:", "prepend:")
        for uid in get_profile_component_uids(profiles_yaml_path, "rules"):
            rules_file = os.path.join(profiles_dir, f"{uid}.yaml")
            with open(rules_file, "w", encoding="utf-8") as f:
                f.write(content_rules)
            print(f"  [2/5] Synced Rules component -> {rules_file}")

    # 3. Sync only registered Script components so the dynamic egress patch is active.
    if os.path.exists(paths["script"]):
        for uid in get_profile_component_uids(profiles_yaml_path, "script", "Script"):
            dest_script = os.path.join(profiles_dir, f"{uid}.js")
            shutil.copyfile(paths["script"], dest_script)
            print(f"  [3/5] Synced Script component -> {dest_script}")

    # 4. 更新 profiles.yaml 策略组选定状态
    update_profiles_yaml(profiles_yaml_path)

    # 5. 更新 dns_config.yaml
    dest_dns = os.path.join(CLASH_VERGE_REV_DIR, "dns_config.yaml")
    if os.path.exists(dest_dns):
        try:
            with open(dest_dns, "r", encoding="utf-8") as f:
                dns_content = f.read()
            
            domains = [
                "*.sinajs.cn", "*.gtimg.cn", "*.eastmoney.com", "*.10jqka.com.cn", "*.upchina.com", "*.tdx.com.cn",
                "*.windowsupdate.com", "*.update.microsoft.com", "*.microsoft.com", "*.windows.com", "*.apple.com",
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
            print(f"  [4/5] Updated DNS Fake-IP Whitelist -> {dest_dns}")
        except Exception as e:
            print(f"  [4/5] Warning on updating dns_config.yaml: {e}")

    # 6. 修补当前运行时的 clash-verge.yaml
    runtime_yaml = os.path.join(CLASH_VERGE_REV_DIR, "clash-verge.yaml")
    patch_clash_runtime_yaml(runtime_yaml)

    # 7. 重启 mihomo 核心以立即应用最新配置
    if not restart_mihomo_core():
        print("\n[PARTIAL] Files were patched, but Mihomo did not confirm the reload.")
        return False

    print("\n[SUCCESS] Whitelist Mode & Direct Rules applied successfully!")
    return True

def restart_mihomo_core():
    """通过 Windows 命名管道发送 HTTP 请求，实现零丢包、零报错的毫秒级热重载与策略组切换"""
    try:
        import win32file
        pipe_name = r"\\.\pipe\verge-mihomo"
        
        # 1. 切换 Microsoft, Apple, Download 策略组至 DIRECT
        for group in ['Microsoft', 'Apple', 'Download']:
            try:
                handle = win32file.CreateFile(pipe_name, win32file.GENERIC_READ | win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, None)
                body = f'{{"name": "DIRECT"}}'
                req = f"PUT /proxies/{group} HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer plokij\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n{body}"
                win32file.WriteFile(handle, req.encode('utf-8'))
                hr, resp = win32file.ReadFile(handle, 1024)
                win32file.CloseHandle(handle)
                status = resp.split(b"\r\n")[0].decode(errors='ignore')
                print(f"  [5/5] Set Proxy Group '{group}' -> DIRECT ({status})")
            except Exception as ge:
                print(f"  [5/5] Warning setting proxy group {group}: {ge}")

        # 2. 发送热重载指令
        handle = win32file.CreateFile(pipe_name, win32file.GENERIC_READ | win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, None)
        body = '{"path": "", "payload": ""}'
        req = f"PUT /configs?force=true HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer plokij\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n{body}"
        win32file.WriteFile(handle, req.encode('utf-8'))
        hr, resp = win32file.ReadFile(handle, 1024)
        win32file.CloseHandle(handle)
        status = resp.split(b"\r\n")[0].decode(errors='ignore')
        if not status.startswith(("HTTP/1.1 200", "HTTP/1.1 204")):
            print(f"  [-] Mihomo reload rejected via Named Pipe ({status})")
            return False
        print(f"  [5/5] Hot-reloaded Mihomo core via Named Pipe ({status})")
        time.sleep(1)
        return True
    except Exception as e:
        print(f"  [5/5] Warning on pipe hot reload: {e}")
        return False

def test_speed():
    print("\n" + "=" * 68)
    print("[Testing Realtime Latency & Whitelist Direct Connectivity]")
    print("=" * 68)
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
