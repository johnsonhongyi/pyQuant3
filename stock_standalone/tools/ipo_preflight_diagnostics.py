# -*- coding: utf-8 -*-
"""
tools/ipo_preflight_diagnostics.py
----------------------------------
新股情绪感知与自学习决策系统 — 一键全方位环境与数据自检诊断工具
- CLI 推理资源诊断：Antigravity CLI (agy 优先) 与 Codex CLI 探活测试与延迟；
- 配置与数据库诊断：YAML 配置文件、首日双锚封存库、SQLite 增量迁移列；
- 指标数据扫描：针对指定股票代码 (默认 301689)，检查可读取缓存并标记未核验的数据域；
- 缺失数据补齐途径编排与可解释问题回馈：给出精准的因果诊断、阻断原因与修复操作指南。
"""

import sys
import os
import time
import json
import sqlite3
import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from ats.strategy.ipo_data_contracts import (
    PREHEAT_REQUIRED_FIELDS,
    LIVE_HEAT_REQUIRED_FIELDS,
    LRRM_REQUIRED_FIELDS,
    REGIME_REQUIRED_FIELDS,
)
from ats.llm.antigravity_cli_backend import AntigravityCLIBackend


def check_cli_resources() -> Dict[str, Any]:
    """1. 检查大模型 CLI 推理资源与优先级链路"""
    print("\n" + "=" * 70)
    print("【1. 大模型 CLI 推理资源诊断】")
    print("=" * 70)

    results = {
        "priority_1_antigravity_cli": {"available": False, "latency_ms": 0.0, "status": "未就绪"},
        "priority_2_codex_cli": {"available": False, "status": "未安装/未在PATH"},
        "fallback_rule_engine": {"available": True, "status": "100% 规则保底始终就绪 (零耗时)"},
    }

    # 1. Antigravity CLI (Priority 1)
    backend = AntigravityCLIBackend()
    if backend.is_available():
        print(f"[*] 发现 Antigravity CLI: {backend.cli_path}")
        print("    正在执行轻量连通性探活 (Prompt: Ping-Pong)...")
        res = backend.invoke(
            prompt="请回复纯JSON: {\"status\": \"ok\", \"service\": \"antigravity_cli\"}",
            timeout_override=backend.timeout_seconds,
        )
        if res.get("success"):
            dur = res.get("duration_ms", 0.0)
            results["priority_1_antigravity_cli"]["available"] = True
            results["priority_1_antigravity_cli"]["latency_ms"] = dur
            results["priority_1_antigravity_cli"]["status"] = f"正常可用 (耗时: {dur:.1f}ms)"
            print(f"    [√] Antigravity CLI 探活成功！响应耗时: {dur:.1f}ms")
        else:
            err = res.get("error_msg", "未知错误")
            results["priority_1_antigravity_cli"]["status"] = f"离线/错误: {err[:60]}"
            print(f"    [!] Antigravity CLI 响应异常: {err[:80]}")
    else:
        print(f"    [×] 未检测到 agy CLI 路径 ({backend.cli_path})")

    # 2. Codex CLI (Priority 2): distinguish the stable install from the
    # version-hashed executable that the desktop app injects into its PATH.
    codex_which = shutil.which("codex")
    candidates = []

    def classify_codex_path(path: Path, fallback: str) -> str:
        normalized = str(path).replace("\\", "/").casefold()
        if "/appdata/local/openai/codex/bin/" in normalized:
            return "Codex 桌面应用版本目录"
        if "/programs/openai/codex/bin/" in normalized:
            return "官方独立安装器固定入口"
        if "/appdata/roaming/npm/" in normalized or "/node_modules/" in normalized:
            return "npm 全局命令"
        if "/.codex/bin/" in normalized:
            return "用户 .codex/bin"
        return fallback

    def add_candidate(raw_path: str, source: str) -> None:
        if not raw_path:
            return
        path = Path(raw_path)
        if not path.is_file():
            return
        source = classify_codex_path(path, source)
        key = os.path.normcase(os.path.abspath(str(path)))
        if not any(item[0] == key for item in candidates):
            candidates.append((key, path, source))

    if codex_which:
        add_candidate(codex_which, "当前 PATH")

    stable_codex = None
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        user_profile = os.environ.get("USERPROFILE")
        app_data = os.environ.get("APPDATA")
        if local_app_data:
            stable_codex = Path(local_app_data) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
            add_candidate(str(stable_codex), "官方独立安装器固定入口")
            desktop_bin = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            if desktop_bin.is_dir():
                for path in sorted(desktop_bin.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
                    add_candidate(str(path), "Codex 桌面应用版本目录")
        if user_profile:
            add_candidate(str(Path(user_profile) / ".codex" / "bin" / "codex.exe"), "用户 .codex/bin")
        if app_data:
            add_candidate(str(Path(app_data) / "npm" / "codex.cmd"), "npm 全局命令")

    def run_codex(path: Path, *args: str, timeout: float = 8.0):
        command = [str(path), *args]
        if sys.platform == "win32" and path.suffix.lower() in {".cmd", ".bat"}:
            cmd_args = subprocess.list2cmdline(list(args))
            command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", f'""{path}" {cmd_args}"']
        child_env = os.environ.copy()
        if sys.platform == "win32":
            home_dir = child_env.get("HOME") or child_env.get("USERPROFILE")
            if home_dir:
                if not child_env.get("HOME"):
                    child_env["HOME"] = home_dir
                if not child_env.get("CODEX_HOME"):
                    child_env["CODEX_HOME"] = str(Path(home_dir) / ".codex")
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=child_env,
        )

    probes = []
    for key, path, source in candidates:
        try:
            probe = run_codex(path, "--version")
            output = "\n".join(part for part in (probe.stdout, probe.stderr) if part)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            version = next((line for line in lines if line.casefold().startswith("codex-cli ")), "未知版本")
            probes.append({"key": key, "path": path, "source": source, "ok": probe.returncode == 0, "version": version})
        except subprocess.TimeoutExpired:
            probes.append({"key": key, "path": path, "source": source, "ok": False, "version": "版本探活超时"})
        except OSError as exc:
            probes.append({"key": key, "path": path, "source": source, "ok": False, "version": f"无法启动: {exc}"})

    path_key = os.path.normcase(os.path.abspath(codex_which)) if codex_which else None
    path_probe = next((probe for probe in probes if probe["key"] == path_key), None)
    stable_key = os.path.normcase(os.path.abspath(str(stable_codex))) if stable_codex else None
    stable_probe = next((probe for probe in probes if probe["key"] == stable_key), None)
    if path_probe and path_probe["ok"]:
        cli_status = f"{path_probe['version']} ({path_probe['source']})"
    elif stable_probe and stable_probe["ok"]:
        cli_status = "固定入口可运行，但当前 PATH 未解析到它"
    elif path_probe:
        cli_status = path_probe["version"]
    else:
        cli_status = "未安装/未在当前 PATH"

    results["priority_2_codex_cli"].update({
        "available": bool((path_probe and path_probe["ok"]) or (stable_probe and stable_probe["ok"])),
        "on_path": bool(path_probe and path_probe["ok"]),
        "path": codex_which,
        "version": path_probe["version"] if path_probe else None,
        "source": path_probe["source"] if path_probe else None,
        "stable_install": bool(stable_probe and stable_probe["ok"]),
        "status": cli_status,
    })

    for probe in probes:
        state = "√" if probe["ok"] else "×"
        print(f"    [{state}] {probe['version']} | {probe['source']}: {probe['path']}")

    if path_probe and "桌面应用版本目录" in path_probe["source"]:
        print("    [!] 当前 PATH 命中桌面应用按版本哈希管理的副本；升级后目录会变化，应使用固定安装入口。")
    elif not path_probe and stable_probe and stable_probe["ok"]:
        print("    [!] 独立 CLI 已安装，但当前终端 PATH 未解析到它；请新开终端刷新 PATH。")
    elif not path_probe:
        print("    [!] 当前 PATH 找不到可运行的 Codex CLI；桌面应用内置 CLI 不等于系统级 CLI。")
    elif not path_probe["ok"]:
        print("    [!] PATH 中的 Codex 命令无法通过 --version；检查安装残缺或 PATH 冲突。")

    if sys.platform == "win32" and not os.environ.get("HOME"):
        results["priority_2_codex_cli"]["home_env_warning"] = True
        print("    [!] 当前父进程未设置 HOME；CLI 探测子进程将按 USERPROFILE 补齐 HOME/CODEX_HOME。")

    login_probe = path_probe if path_probe and path_probe["ok"] else stable_probe
    if login_probe and login_probe["ok"]:
        try:
            login = run_codex(login_probe["path"], "login", "status", timeout=8.0)
            login_text = f"{login.stdout}\n{login.stderr}".casefold()
            if "not logged in" in login_text or "not logged-in" in login_text:
                login_status = "未登录"
            elif "logged in" in login_text or "authenticated" in login_text:
                login_status = "已登录"
            else:
                login_status = f"状态未知 (exit={login.returncode})"
            results["priority_2_codex_cli"]["login_status"] = login_status
            print(f"    [*] Codex 登录状态: {login_status}")
        except subprocess.TimeoutExpired:
            results["priority_2_codex_cli"]["login_status"] = "状态探测超时"
            print("    [!] Codex 登录状态探测超时")
        except OSError as exc:
            results["priority_2_codex_cli"]["login_status"] = f"状态探测失败: {exc}"
            print(f"    [!] Codex 登录状态探测失败: {exc}")

    print("[*] 纯规则兜底: 本次未演练离线切换、耗时或交易主链路影响")
    return results


def check_configs_and_database() -> Dict[str, Any]:
    """2. 检查系统配置文件与底层数据库增量列"""
    print("\n" + "=" * 70)
    print("【2. 配置文件与 SQLite 数据库自检】")
    print("=" * 70)

    results = {}
    config_dir = Path(app_dir) / "config"

    # 检查配置文件
    sentiment_yaml = config_dir / "ipo_sentiment.yaml"
    anchors_json = config_dir / "listing_anchors.json"

    if sentiment_yaml.is_file():
        print(f"    [√] 配置文件存在: config/ipo_sentiment.yaml ({sentiment_yaml.stat().st_size} bytes)")
        results["ipo_sentiment_yaml"] = True
    else:
        print(f"    [!] 缺失配置文件: config/ipo_sentiment.yaml (门禁与TTL阈值尚未固化)")
        results["ipo_sentiment_yaml"] = False

    if anchors_json.is_file():
        print(f"    [√] 物理锚点库存在: config/listing_anchors.json ({anchors_json.stat().st_size} bytes)")
        results["listing_anchors_json"] = True
    else:
        print(f"    [!] 物理锚点库尚未生成: config/listing_anchors.json (次日及以上标的双锚失守检测需此文件)")
        results["listing_anchors_json"] = False

    # 检查 market_pulse.db
    db_path = Path(app_dir) / "market_pulse.db"
    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(daily_sentiment)")
            cols = {row[1] for row in cursor.fetchall()}
            conn.close()
            has_lrrm = "lrrm_state" in cols
            has_regime = "ipo_regime_state" in cols
            if has_lrrm and has_regime:
                print(f"    [√] market_pulse.db 增量字段就绪: lrrm_state, ipo_regime_state 已存在")
                results["db_columns_migrated"] = True
            else:
                print(f"    [!] market_pulse.db 缺少增量列 (lrrm_state: {has_lrrm}, ipo_regime_state: {has_regime})")
                results["db_columns_migrated"] = False
        except Exception as e:
            print(f"    [×] 读取 market_pulse.db 失败: {e}")
            results["db_columns_migrated"] = False
    else:
        print(f"    [!] market_pulse.db 数据库文件尚未创建，系统将在初次启动时自动建表")
        results["db_columns_migrated"] = False

    return results


def check_stock_data_coverage(code: str) -> Dict[str, Any]:
    """3. 扫描可读取缓存，并区分缺失数据与尚未核验的数据域"""
    metric_total = sum(map(len, (
        PREHEAT_REQUIRED_FIELDS,
        LIVE_HEAT_REQUIRED_FIELDS,
        LRRM_REQUIRED_FIELDS,
        REGIME_REQUIRED_FIELDS,
    )))
    print("\n" + "=" * 70)
    print(f"【3. 个股 {metric_total} 项数据契约覆盖度与补齐编排扫描 (标的: {code})】")
    print("=" * 70)

    # 检查本地缓存源
    cache_path = Path(app_dir) / "config" / "new_stock_data_cache.json"
    cached_data = {}
    if cache_path.is_file():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f).get(code, {})
        except Exception:
            pass

    print(f"{'指标域 (Domain)':<16} | {'指标项 (Metric Field)':<28} | {'当前状态':<10} | {'补齐编排途径 (Acquisition Route)'}")
    print("-" * 95)

    stats = {"ready": 0, "missing": 0, "unverified": 0, "total": 0}

    # A. Pre-Heat (8项)
    for field in PREHEAT_REQUIRED_FIELDS:
        stats["total"] += 1
        val = cached_data.get(field)
        if val is not None:
            stats["ready"] += 1
            status = "√ 就绪"
            route = "本地已缓存 (config/new_stock_data_cache.json)"
        else:
            stats["missing"] += 1
            status = "× 缺失"
            route = "途径: 1) TDX本地主数据 -> 2) 东方财富新股发行公告爬虫"
        print(f"{'IPO Pre-Heat':<16} | {field:<28} | {status:<10} | {route}")

    # B. Live Heat (12项): no live market feed is read by this preflight.
    for field in LIVE_HEAT_REQUIRED_FIELDS:
        stats["total"] += 1
        status = "○ 未核验"
        route = "需运行 ATS 并读取盘中分时行情流后确认"
        stats["unverified"] += 1
        print(f"{'IPO Live Heat':<16} | {field:<28} | {status:<10} | {route}")

    # C. LRRM 宏观流动性 (11项): schema presence does not prove data readiness.
    for field in LRRM_REQUIRED_FIELDS:
        stats["total"] += 1
        stats["unverified"] += 1
        status = "○ 未核验"
        route = "需查询 market_pulse.db 中最新有效 daily_sentiment 记录"
        print(f"{'LRRM 宏观流动性':<16} | {field:<28} | {status:<10} | {route}")

    # D. IPO Regime 横截面 (10项): no sample rows are read by this preflight.
    for field in REGIME_REQUIRED_FIELDS:
        stats["total"] += 1
        stats["unverified"] += 1
        status = "○ 未核验"
        route = "需核对 IPO 样本统计任务与最新统计时间"
        print(f"{'IPO Regime 态':<16} | {field:<28} | {status:<10} | {route}")

    print("-" * 95)
    print(
        f"数据指标汇总: 总计 {stats['total']} 项 | 已核验就绪 {stats['ready']} 项 "
        f"| 已确认缺失 {stats['missing']} 项 | 未核验 {stats['unverified']} 项"
    )
    return stats


def print_feedback_and_next_steps():
    """4. 总结问题反馈与可执行修复指南"""
    print("\n" + "=" * 70)
    print("【4. 诊断结论反馈与自检修复操作指南】")
    print("=" * 70)
    print("""
[因果反馈与当前状态裁决]：
1. 【大模型推理资源】：
   - 本脚本只探测 CLI 可执行性/登录状态与 Antigravity 的单次响应；
   - 尚未验证 Codex 模型调用、CLI 沙箱隔离、超时回退路径或交易延迟。

2. 【缺失数据自动补齐编排】：
   - 当前只核对上市前先验数据的本地缓存；自动抓取与缓存新鲜度未核验；
   - 宏观流动性仅检查数据库结构，盘中数据和 IPO 横截面样本均未核验。

3. 【UI 查看状态入口】：
   - 方式 1 (独立测试推荐)：运行 `python tools/run_ipo_learning_console.py`，秒级打开监控控制台与仲裁对话框；
   - 方式 2 (主系统联机)：运行 `python run_ats.py`，在顶部选择【Tab 5: IPO 自学习监控】。
""")


def main():
    parser = argparse.ArgumentParser(description="新股情绪感知与自学习决策系统一键自检诊断")
    parser.add_argument("--code", "-c", default="301689", help="需要自检的股票代码 (默认: 301689)")
    args = parser.parse_args()

    print("\n[*] 开始执行新股情绪感知与自学习决策系统全量自检 (Preflight Diagnostics)...")
    check_cli_resources()
    check_configs_and_database()
    check_stock_data_coverage(args.code)
    print_feedback_and_next_steps()


if __name__ == "__main__":
    main()
