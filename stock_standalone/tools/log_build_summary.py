# -*- coding: utf-8 -*-
"""
tools/log_build_summary.py
Nuitka 批量打包结果历史汇总与性能对比记录器 (追加模式)

职责：
1. 收集本次打包的执行状态、单项耗时、产物大小及总耗时；
2. 读取本批次 Nuitka clcache 命中率、请求数与未命中数；
3. 统计本地 .nuitka_cache 增量缓存目录体积与健康度；
4. 读取 nuitka_batch_build_last_summary.txt 历史记录，计算与上一次构建的耗时对比（节约时间与百分比）；
5. 综合判定缓存命中状态（🔥 热缓存命中加速 / ❄️ 冷启动全量编译 / ⚡ 零变更纯复用）；
6. 以追加模式（Append）写入 nuitka_batch_build_last_summary.txt，同时在终端高保真输出本次构建卡片。
"""

import os
import sys
import re
import json
import argparse
import datetime
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# 跨环境与管道重定向 UTF-8 中文输出适配
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def format_duration(seconds: int) -> str:
    """将秒数格式化为中文分秒表示"""
    if seconds < 0:
        seconds = abs(seconds)
    mins = seconds // 60
    secs = seconds % 60
    if mins > 0:
        return f"{mins}分{secs}秒"
    return f"{secs}秒"


def get_dir_size_str(path: Path) -> Tuple[int, str]:
    """计算目录体积大小并返回字节数及格式化字符串"""
    if not path.exists():
        return 0, "未创建"
    try:
        total = 0
        for entry in os.scandir(str(path)):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                for root, _, files in os.walk(entry.path):
                    for f in files:
                        try:
                            total += os.path.getsize(os.path.join(root, f))
                        except (OSError, FileNotFoundError):
                            pass
        if total >= 1024 ** 3:
            return total, f"{total / (1024 ** 3):.2f} GB"
        elif total >= 1024 ** 2:
            return total, f"{total / (1024 ** 2):.1f} MB"
        elif total >= 1024:
            return total, f"{total / 1024:.1f} KB"
        return total, f"{total} B"
    except Exception as e:
        return 0, f"计算异常 ({e})"


def query_sccache_stats() -> Dict[str, Any]:
    """查询 sccache 运行状态与缓存命中统计"""
    result = {
        "available": False,
        "requests": 0,
        "hits": 0,
        "misses": 0,
        "hit_rate_str": "-",
        "summary": "未启用或未运行"
    }
    try:
        p = subprocess.run(
            ["sccache", "--show-stats", "--stats-format", "json"],
            capture_output=True,
            text=True,
            timeout=3
        )
        if p.returncode == 0 and p.stdout.strip():
            data = json.loads(p.stdout)
            stats = data.get("stats", {})
            requests = stats.get("compile_requests", 0)
            hits = sum(stats.get("cache_hits", {}).get("counts", {}).values())
            misses = sum(stats.get("cache_misses", {}).get("counts", {}).values())
            rate_str = f"{(hits / requests * 100):.1f}%" if requests > 0 else "-"
            result.update({
                "available": True,
                "requests": requests,
                "hits": hits,
                "misses": misses,
                "hit_rate_str": rate_str,
                "summary": f"请求: {requests} | 命中: {hits} | 未命中: {misses} | 命中率: {rate_str}"
            })
            return result
    except Exception:
        pass

    # 回退尝试纯文本正则提取
    try:
        p = subprocess.run(
            ["sccache", "--show-stats"],
            capture_output=True,
            text=True,
            timeout=3
        )
        if p.returncode == 0 and p.stdout.strip():
            text = p.stdout
            m_req = re.search(r"Compile requests(?:\s+executed)?\s+(\d+)", text)
            m_hits = re.search(r"Cache hits\s+(\d+)", text)
            m_miss = re.search(r"Cache misses\s+(\d+)", text)
            m_rate = re.search(r"Cache hits rate\s+([\d\.\-]+%?)", text)
            if m_req:
                requests = int(m_req.group(1))
                hits = int(m_hits.group(1)) if m_hits else 0
                misses = int(m_miss.group(1)) if m_miss else 0
                rate_str = m_rate.group(1) if m_rate else "-"
                result.update({
                    "available": True,
                    "requests": requests,
                    "hits": hits,
                    "misses": misses,
                    "hit_rate_str": rate_str,
                    "summary": f"请求: {requests} | 命中: {hits} | 未命中: {misses} | 命中率: {rate_str}"
                })
    except Exception:
        pass

    return result


def get_clcache_info() -> Tuple[int, str]:
    """获取 Nuitka Windows 内置 clcache 编译缓存体积"""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    if "CLCACHE_DIR" in os.environ:
        candidates.append(Path(os.environ["CLCACHE_DIR"]))
    if local_appdata:
        candidates.append(Path(local_appdata) / "Nuitka" / "Nuitka" / "Cache" / "clcache")
    for cand in candidates:
        if cand.exists():
            return get_dir_size_str(cand)
    return 0, "未创建"


def parse_build_timestamp(value: str) -> Optional[datetime.datetime]:
    """从批处理时间戳中提取本地时间，避免误读上一次构建的统计文件"""
    match = re.search(
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2}\s+\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?)",
        value,
    )
    if not match:
        return None

    timestamp = match.group(1).replace(",", ".")
    date_formats = (
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    )
    for date_format in date_formats:
        try:
            return datetime.datetime.strptime(timestamp, date_format)
        except ValueError:
            continue
    return None


def get_current_clcache_stats(
    build_dir: Path,
    module_args: List[str],
    start_timestamp: str,
    end_timestamp: str,
) -> Dict[str, Dict[str, int]]:
    """读取本批次每个 Nuitka 目标的 Scons clcache 统计文件"""
    module_build_dirs = {
        "tk": ("instock_MonitorTK.build", "instock_MonitorTK.onefile-build"),
        "ats": ("run_ats.build", "run_ats.onefile-build"),
        "multi": ("multi_period_dialog.build", "multi_period_dialog.onefile-build"),
    }
    start_time = parse_build_timestamp(start_timestamp)
    end_time = parse_build_timestamp(end_timestamp)
    if start_time is None or end_time is None:
        return {}

    stats_by_module: Dict[str, Dict[str, int]] = {}

    for item in module_args:
        delim = "#" if "#" in item else "|"
        parts = item.split(delim)
        if len(parts) < 4:
            continue

        module = parts[1].strip().lower()
        if parts[3].strip().lower() not in ("成功", "success"):
            continue

        relative_dirs = module_build_dirs.get(module)
        if not relative_dirs:
            continue

        module_hits = 0
        module_misses = 0
        stats_files = 0
        for relative_dir in relative_dirs:
            stats_dir = build_dir / relative_dir
            if not stats_dir.is_dir():
                continue

            for stats_path in stats_dir.glob("clcache-stats.*.txt"):
                try:
                    modified = datetime.datetime.fromtimestamp(stats_path.stat().st_mtime)
                    if modified < start_time - datetime.timedelta(seconds=5):
                        continue
                    if modified > end_time + datetime.timedelta(seconds=30):
                        continue

                    data = json.loads(stats_path.read_text(encoding="utf-8", errors="replace"))
                    module_hits += max(0, int(data.get("CacheHits", 0)))
                    module_misses += max(0, int(data.get("CacheMisses", 0)))
                    stats_files += 1
                except (OSError, ValueError, TypeError):
                    continue

        stats_by_module[module] = {
            "hits": module_hits,
            "misses": module_misses,
            "files": stats_files,
        }

    return stats_by_module


def get_sccache_cache_info() -> Tuple[int, str]:
    """获取 sccache 本地磁盘缓存体积"""
    candidates = []
    if "SCCACHE_DIR" in os.environ:
        candidates.append(Path(os.environ["SCCACHE_DIR"]))
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Mozilla" / "sccache" / "cache")
    candidates.append(Path("D:/sccache"))
    for cand in candidates:
        if cand.exists():
            b, s = get_dir_size_str(cand)
            if b > 0:
                return b, s
    for cand in candidates:
        if cand.exists():
            return get_dir_size_str(cand)
    return 0, "未创建"


def extract_history_stats(summary_log_path: Path) -> Tuple[int, Optional[int]]:
    """
    从既有 summary 日志中提取历史构建总批次数与最近一次耗时（秒）
    """
    if not summary_log_path.exists():
        return 0, None
    try:
        content = summary_log_path.read_text(encoding="utf-8", errors="replace")
        # 查找所有历史记录耗时匹配
        durations = [int(s) for s in re.findall(r"\[共\s*(\d+)\s*秒\]", content)]
        # 查找历史标题次数 (兼容 Nuitka / PyInstaller / 批量打包)
        batch_headers = len(re.findall(r"【(?:Nuitka|PyInstaller|批量打包)", content))
        total_records = max(len(durations), batch_headers)
        last_sec = durations[-1] if durations else None
        return total_records, last_sec
    except Exception:
        return 0, None


def main():
    parser = argparse.ArgumentParser(description="Build Summary Logger (Append Mode)")
    parser.add_argument("--builder", default="nuitka", choices=["nuitka", "pyinstaller"], help="Packaging builder framework")
    parser.add_argument("--summary-log", required=True, help="Path to summary log file")
    parser.add_argument("--build-dir", required=True, help="Build output directory (dist or build)")
    parser.add_argument("--root-dir", required=True, help="Root workspace directory")
    parser.add_argument("--build-mode", default="standard", help="Build mode")
    parser.add_argument("--plan-count", type=int, default=1, help="Total modules planned")
    parser.add_argument("--success-count", type=int, default=0, help="Successful modules")
    parser.add_argument("--fail-count", type=int, default=0, help="Failed modules")
    parser.add_argument("--start-timestamp", default="", help="Start timestamp string")
    parser.add_argument("--end-timestamp", default="", help="End timestamp string")
    parser.add_argument("--diff-sec", type=int, default=0, help="Total elapsed seconds")
    parser.add_argument("--diff-str", default="0秒", help="Total elapsed formatted string")
    parser.add_argument("--module", action="append", default=[], help="Module info string: idx#mod#title#status#time#size#exe")

    args = parser.parse_args()

    summary_log = Path(args.summary_log).resolve()
    root_dir = Path(args.root_dir).resolve()
    build_dir = Path(args.build_dir).resolve()

    # 1. 提取历史记录与构建序号
    history_count, prev_sec = extract_history_stats(summary_log)
    current_batch_no = history_count + 1

    # 2. 计算耗时对比
    if prev_sec is not None:
        delta = args.diff_sec - prev_sec
        if delta < 0:
            saved = abs(delta)
            pct = (saved / prev_sec * 100) if prev_sec > 0 else 0
            time_comparison = f"相比上次耗时 ({format_duration(prev_sec)}) 缩短 {format_duration(saved)} (-{pct:.1f}%) [编译性能显著提升]"
        elif delta > 0:
            added = delta
            pct = (added / prev_sec * 100) if prev_sec > 0 else 0
            time_comparison = f"相比上次耗时 ({format_duration(prev_sec)}) 增加 {format_duration(added)} (+{pct:.1f}%)"
        else:
            time_comparison = f"与上次耗时完全持平 ({format_duration(args.diff_sec)})"
    else:
        time_comparison = "首次记录 (暂无前序对比基准)"

    # 3. 统计缓存与评估状态
    if args.builder == "pyinstaller":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        py_cache_dir = Path(local_appdata) / "pyinstaller" if local_appdata else Path()
        py_cache_bytes, py_cache_size_str = get_dir_size_str(py_cache_dir)
        build_dir_path = root_dir / "build"
        build_bytes, build_size_str = get_dir_size_str(build_dir_path)

        if args.diff_sec <= 10 and args.success_count > 0:
            cache_eval = "[秒级极速复用] 产物与二进制缓存 100% 命中复用"
        elif build_bytes > 50 * 1024 * 1024 and args.diff_sec <= 180:
            cache_eval = f"[增量分析就绪] build/ 中间分析缓存已复用 ({build_size_str})"
        elif args.diff_sec >= 600:
            cache_eval = "[全量冷构建] 耗时较长，首次全量打包或中间缓存已清理"
        else:
            cache_eval = f"[常规增量构建] 本地二进制缓存复用 (PyInstaller 缓存 {py_cache_size_str})"
    else:
        nuitka_cache_path = root_dir / ".nuitka_cache"
        nuitka_bytes, nuitka_size_str = get_dir_size_str(nuitka_cache_path)

        clcache_bytes, clcache_size_str = get_clcache_info()
        clcache_stats_by_module = get_current_clcache_stats(
            build_dir,
            args.module,
            args.start_timestamp,
            args.end_timestamp,
        )
        cache_module_details = []
        total_clcache_hits = 0
        total_clcache_misses = 0
        missing_cache_stats = []
        for module, stats in clcache_stats_by_module.items():
            if not stats["files"]:
                missing_cache_stats.append(module)
                cache_module_details.append(f"{module} 无本批次统计")
                continue

            hits = stats["hits"]
            misses = stats["misses"]
            requests = hits + misses
            total_clcache_hits += hits
            total_clcache_misses += misses
            rate = (hits / requests * 100) if requests else 0.0
            cache_module_details.append(
                f"{module} 命中 {hits}/{requests} ({rate:.1f}%)，未命中 {misses}"
            )

        total_clcache_requests = total_clcache_hits + total_clcache_misses
        if clcache_bytes > 0:
            compiler_cache_summary = f"clcache [{clcache_size_str}] (Nuitka Windows Clang-cl 缓存)"
        else:
            compiler_cache_summary = "clcache 缓存目录未检测到"

        if total_clcache_requests:
            rate = total_clcache_hits / total_clcache_requests * 100
            if missing_cache_stats:
                cache_eval = (
                    f"[部分统计] 已统计模块的 clcache 命中 "
                    f"{total_clcache_hits}/{total_clcache_requests} ({rate:.1f}%)；"
                    f"缺少统计: {', '.join(missing_cache_stats)}"
                )
            else:
                cache_eval = (
                    f"[clcache 实际命中 {total_clcache_hits}/{total_clcache_requests} "
                    f"({rate:.1f}%)] 本次 C 编译缓存复用率"
                )
        elif clcache_stats_by_module:
            if missing_cache_stats:
                cache_eval = f"[缓存状态未知] 部分模块无本批次统计: {', '.join(missing_cache_stats)}"
            else:
                cache_eval = "[本次无 C 编译请求] clcache 统计文件存在，但未记录命中或未命中"
        else:
            cache_eval = "[缓存状态未知] 未找到本批次 clcache 统计，目录体积和构建时长不能代表命中率"

    # 4. 解析模块清单并构建表格
    builder_title = "PyInstaller" if args.builder == "pyinstaller" else "Nuitka"
    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append(f"     【{builder_title} 批量打包历史记录与性能对比】(追加模式 / 第 {current_batch_no} 次构建)")
    lines.append("=" * 80)
    lines.append(f"构建批次时间 : {args.start_timestamp} -> {args.end_timestamp}")
    lines.append(f"构建模式选项 : {args.build_mode}")
    lines.append("-" * 80)
    lines.append("序号  模块标识   执行状态   单项耗时       产物大小      目标产物文件")
    lines.append("-" * 80)

    for item in args.module:
        delim = "#" if "#" in item else "|"
        parts = item.split(delim)
        if len(parts) >= 7:
            idx, mod, title, status, m_time, m_size, exe = parts[:7]
            if not m_size.strip():
                artifact_path = build_dir / exe
                try:
                    artifact_bytes = artifact_path.stat().st_size if artifact_path.is_file() else 0
                    m_size = f"{artifact_bytes / (1024 * 1024):.1f} MB" if artifact_bytes else "未生成"
                except OSError:
                    m_size = "未生成"
            # 对齐格式
            lines.append(f"  {idx}.   {mod:<8} [{status}]    {m_time:<12} {m_size:<12} {exe}")
        elif len(parts) >= 5:
            idx, mod, status, m_time, m_size = parts[:5]
            lines.append(f"  {idx}.   {mod:<8} [{status}]    {m_time:<12} {m_size}")

    lines.append("-" * 80)
    lines.append(f"构建任务汇总 : 总计 {args.plan_count} 个 ｜ 成功: {args.success_count} 个 ｜ 失败: {args.fail_count} 个")
    lines.append(f"任务启动时间 : {args.start_timestamp}")
    lines.append(f"任务完成时间 : {args.end_timestamp}")
    lines.append(f"本次总体耗时 : {args.diff_str} [共 {args.diff_sec} 秒]")
    lines.append(f"历史耗时对比 : {time_comparison}")
    lines.append(f"缓存命中评估 : {cache_eval}")
    if args.builder == "pyinstaller":
        lines.append(f"二进制缓存   : PyInstaller 缓存 [{py_cache_size_str}] ｜ build 中间分析 [{build_size_str}]")
    else:
        lines.append(f"增量缓存体积 : .nuitka_cache [{nuitka_size_str}] ｜ 编译器缓存 (clcache) [{clcache_size_str}]")
        lines.append(f"编译器缓存   : {compiler_cache_summary}")
        lines.append(
            "本次 clcache  : "
            + (" ｜ ".join(cache_module_details) if cache_module_details else "未取得本批次命中明细")
        )
    lines.append(f"产物输出路径 : {build_dir}")
    lines.append(f"历史归档路径 : {build_dir / 'archive'} [保留最近 7 天版本]")
    lines.append("=" * 80)

    report_text = "\n".join(lines) + "\n"

    # 6. 在控制台打印当前批次卡片
    print(report_text)

    # 7. 以追加模式 (Append) 写入日志文件，保证 UTF-8 编码
    summary_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(summary_log, "a", encoding="utf-8") as f:
            f.write(report_text)
    except Exception as e:
        print(f"[警告] 写入追加日志失败 ({summary_log}): {e}")


if __name__ == "__main__":
    main()
