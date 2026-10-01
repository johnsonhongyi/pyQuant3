# -*- coding: utf-8 -*-
"""
本地 OpenAI Codex CLI 运行模型与 Token 消耗统计工具
读取 ~/.codex/sessions/**/*.jsonl 本地会话归档，汇总真实模型、输入输出 Token、思考 Token 与缓存命中。
"""
import os
import sys
import glob
import json
import collections
import datetime
from datetime import timezone, timedelta
import argparse

# 确保在 Windows 控制台（GBK）下安全输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def format_tokens(n):
    """格式化 Token 数量，自动附加中文易读单位（万/亿）"""
    if n >= 100_000_000:
        return f"{n:,} ({n / 100_000_000:.2f}亿)"
    elif n >= 10_000:
        return f"{n:,} ({n / 10_000:.2f}万)"
    else:
        return f"{n:,}"

def get_codex_stats(days_back=7):
    root = os.path.expanduser("~/.codex/sessions")
    if not os.path.exists(root):
        print(f"未找到 Codex 会话目录: {root}")
        return

    tz = timezone(timedelta(hours=8))
    cutoff_date = (datetime.datetime.now(tz) - timedelta(days=days_back)).date().isoformat()

    daily = collections.defaultdict(collections.Counter)
    models = collections.defaultdict(collections.Counter)
    seen_responses = set()

    # 递归匹配所有 jsonl
    all_files = glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
    for fn in all_files:
        turn_models = {}
        try:
            with open(fn, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    p = o.get("payload") or {}
                    # 记录每轮请求绑定的模型
                    if o.get("type") == "turn_context":
                        turn_id = p.get("turn_id")
                        model_name = p.get("model")
                        if turn_id and model_name:
                            turn_models[turn_id] = model_name
                        continue
                    # 记录 Token 消耗
                    if o.get("type") == "token_usage_record":
                        rid = p.get("response_id")
                        if rid and rid in seen_responses:
                            continue
                        if rid:
                            seen_responses.add(rid)

                        u = p.get("usage") or p.get("turn_token_usage") or {}
                        ts_str = o.get("timestamp")
                        try:
                            d = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(tz).date().isoformat()
                        except Exception:
                            d = "未知日期"

                        if d < cutoff_date and d != "未知日期":
                            continue

                        vals = {
                            "input_tokens": int(u.get("input_tokens", 0) or 0),
                            "cached_input_tokens": int(u.get("cached_input_tokens", 0) or 0),
                            "output_tokens": int(u.get("output_tokens", 0) or 0),
                            "reasoning_output_tokens": int(u.get("reasoning_output_tokens", 0) or 0),
                            "total_tokens": int(u.get("total_tokens", 0) or 0),
                        }
                        turn_id = p.get("turn_id")
                        m = turn_models.get(turn_id, "default_model")

                        daily[d].update(vals)
                        daily[d]["turns"] += 1

                        models[(d, m)].update(vals)
                        models[(d, m)]["turns"] += 1
        except Exception:
            continue

    if not daily:
        print(f"近 {days_back} 天内未发现 Codex 本地会话 Token 记录。")
        return

    print("=" * 80)
    print(f"[*] 本地 Codex 模型与 Token 消耗统计 (近 {days_back} 天)")
    print("=" * 80)
    for d in sorted(daily.keys()):
        stat = daily[d]
        print(f"\n[+] 日期 【{d}】 累计交互轮次: {stat['turns']} 轮")
        print(f"   |-- 总 Token 消耗:     {format_tokens(stat['total_tokens'])}")
        print(f"   |-- 提示词输入 (Prompt): {format_tokens(stat['input_tokens'])} (其中缓存命中: {format_tokens(stat['cached_input_tokens'])})")
        print(f"   \\-- 模型回答 (Output):   {format_tokens(stat['output_tokens'])} (其中思考消耗: {format_tokens(stat['reasoning_output_tokens'])})")
        print("   [-] 实际执行模型细分:")
        for (m_date, m_name), m_stat in sorted(models.items()):
            if m_date == d:
                tot_str = format_tokens(m_stat['total_tokens'])
                rsn_str = format_tokens(m_stat['reasoning_output_tokens'])
                print(f"       * 模型: {m_name:<18} | 轮次: {m_stat['turns']:>4} | 总消耗: {tot_str:<22} | 思考 Token: {rsn_str}")

    grand_total = collections.Counter()
    for s in daily.values():
        grand_total.update(s)

    print("\n" + "=" * 80)
    print("[*] 总计汇总 (Grand Total):")
    print(f"   * 总轮次:     {grand_total['turns']} 轮")
    print(f"   * 总 Token:   {format_tokens(grand_total['total_tokens'])}")
    print(f"   * 输入 Token: {format_tokens(grand_total['input_tokens'])} (缓存加速: {format_tokens(grand_total['cached_input_tokens'])})")
    print(f"   * 输出 Token: {format_tokens(grand_total['output_tokens'])} (深度思考: {format_tokens(grand_total['reasoning_output_tokens'])})")
    print("=" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="统计本地 Codex 运行模型与 Token 消耗")
    parser.add_argument("--days", type=int, default=7, help="查看最近几天的数据 (默认 7 天)")
    args = parser.parse_args()
    get_codex_stats(args.days)
