# -*- coding: utf-8 -*-
"""
本地 OpenAI Codex CLI 运行模型与 Token 消耗统计工具
读取 ~/.codex/sessions/**/*.jsonl 本地会话归档，汇总真实模型、输入输出 Token、思考 Token、缓存命中率、
以及工业级【纯生成吐率 (Gen TPS)】与【端到端吞吐率 (E2E TPS)】双维度性能分析。
包含终端 CJK 中文字符宽度感知与绝对数据对齐格式化渲染。
"""
import os
import sys
import glob
import json
import collections
import datetime
from datetime import timezone, timedelta
import argparse
import unicodedata

# 确保在 Windows 控制台（GBK）下安全输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def cell_width(val):
    """计算字符串在终端中的真实显示宽度 (中文等宽字符计为 2，半角字符计为 1)"""
    w = 0
    for c in str(val):
        w += 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
    return w

def pad_cell(val, width, align="left"):
    """根据真实显示宽度对齐填充空格"""
    val_str = str(val)
    cur_w = cell_width(val_str)
    pad = max(0, width - cur_w)
    if align == "right":
        return " " * pad + val_str
    elif align == "center":
        left = pad // 2
        right = pad - left
        return " " * left + val_str + " " * right
    else:
        return val_str + " " * pad

def format_tokens(n):
    """格式化 Token 数量，自动附加中文易读单位（万/亿）"""
    if n >= 100_000_000:
        return f"{n:,} ({n / 100_000_000:.2f}亿)"
    elif n >= 10_000:
        return f"{n:,} ({n / 10_000:.2f}万)"
    else:
        return f"{n:,}"

def load_model_metadata():
    """从本地 ~/.codex/models_cache.json 加载官方模型映射字典"""
    path = os.path.expanduser("~/.codex/models_cache.json")
    meta = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                d = json.load(f)
                for m in d.get("models", []):
                    slug = m.get("slug")
                    if slug:
                        meta[slug] = {
                            "display_name": m.get("display_name", slug),
                            "description": m.get("description", ""),
                            "default_reasoning": m.get("default_reasoning_level", "low")
                        }
        except Exception:
            pass
    return meta

def get_codex_stats(days_back=7, show_recent_routes=10):
    root = os.path.expanduser("~/.codex/sessions")
    if not os.path.exists(root):
        print(f"未找到 Codex 会话目录: {root}")
        return

    model_meta = load_model_metadata()
    tz = timezone(timedelta(hours=8))
    cutoff_date = (datetime.datetime.now(tz) - timedelta(days=days_back)).date().isoformat()

    daily = collections.defaultdict(collections.Counter)
    models = collections.defaultdict(collections.Counter)

    # 纯生成耗时 (扣除工具与离线耗时)
    daily_gen_durations = collections.defaultdict(float)
    models_gen_durations = collections.defaultdict(float)

    # 端到端挂钟耗时 (包含工具调用全流程)
    daily_e2e_durations = collections.defaultdict(float)
    models_e2e_durations = collections.defaultdict(float)

    seen_responses = set()
    session_route_history = []

    # 递归匹配所有 jsonl
    all_files = glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
    all_files.sort(key=os.path.getmtime)

    for fn in all_files:
        turn_models = {}
        client_requested_model = None
        session_created_time = "未知时间"
        session_total_tokens = 0
        session_in_tokens = 0
        session_cached_tokens = 0
        session_out_tokens = 0
        session_gen_dur = 0.0
        session_e2e_dur = 0.0
        session_actual_models = collections.Counter()
        session_efforts = set()

        call_start_time = None
        turn_start_time = None
        cur_model = "default_model"

        try:
            with open(fn, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    p = o.get("payload") or {}
                    event_type = o.get("type")
                    ts_str = o.get("timestamp")
                    cur_dt = None
                    if ts_str:
                        try:
                            cur_dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(tz)
                        except Exception:
                            cur_dt = None

                    # 捕获客户端初始请求或设置的模型
                    if "thread_settings" in p and not client_requested_model:
                        client_requested_model = p["thread_settings"].get("model")

                    # 1. 轮次开始
                    if event_type == "turn_context":
                        turn_id = p.get("turn_id")
                        model_name = p.get("model")
                        effort = p.get("effort")
                        if effort:
                            session_efforts.add(effort)
                        if turn_id and model_name:
                            turn_models[turn_id] = model_name
                            session_actual_models[model_name] += 1
                            cur_model = model_name
                        if cur_dt:
                            call_start_time = cur_dt
                            turn_start_time = cur_dt
                        continue

                    # 2. 工具执行完毕，结果送回模型，恢复纯生成计时
                    if event_type == "response_item" and p.get("type") in ("custom_tool_call_output", "tool_output"):
                        if cur_dt:
                            call_start_time = cur_dt
                        continue

                    # 3. 记录 Token 消耗并核算速率
                    if event_type == "token_usage_record":
                        rid = p.get("response_id")
                        if rid and rid in seen_responses:
                            continue
                        if rid:
                            seen_responses.add(rid)

                        u = p.get("usage") or p.get("turn_token_usage") or {}
                        d = cur_dt.date().isoformat() if cur_dt else "未知日期"
                        if session_created_time == "未知时间" and cur_dt:
                            session_created_time = cur_dt.strftime("%m-%d %H:%M:%S")

                        out_tok = int(u.get("output_tokens", 0) or 0)
                        vals = {
                            "input_tokens": int(u.get("input_tokens", 0) or 0),
                            "cached_input_tokens": int(u.get("cached_input_tokens", 0) or 0),
                            "output_tokens": out_tok,
                            "reasoning_output_tokens": int(u.get("reasoning_output_tokens", 0) or 0),
                            "total_tokens": int(u.get("total_tokens", 0) or 0),
                        }

                        # 计算本次 LLM 调用的【纯生成耗时】 (扣除工具运行与空闲等待)
                        gen_dur = 0.0
                        if call_start_time and cur_dt:
                            elapsed = (cur_dt - call_start_time).total_seconds()
                            if 0.5 <= elapsed <= 180.0 and out_tok > 0:
                                gen_dur = elapsed
                        call_start_time = None

                        # 计算本轮的【端到端耗时】 (从用户发起轮次到该响应产生的挂钟时间)
                        e2e_dur = 0.0
                        if turn_start_time and cur_dt:
                            elapsed_e2e = (cur_dt - turn_start_time).total_seconds()
                            if 0.5 <= elapsed_e2e <= 600.0:
                                e2e_dur = elapsed_e2e

                        session_total_tokens += vals["total_tokens"]
                        session_in_tokens += vals["input_tokens"]
                        session_cached_tokens += vals["cached_input_tokens"]
                        session_out_tokens += out_tok
                        session_gen_dur += gen_dur
                        session_e2e_dur += e2e_dur

                        if d >= cutoff_date or d == "未知日期":
                            turn_id = p.get("turn_id")
                            m = turn_models.get(turn_id, cur_model)

                            daily[d].update(vals)
                            daily[d]["turns"] += 1
                            daily_gen_durations[d] += gen_dur
                            if e2e_dur > 0:
                                daily_e2e_durations[d] += e2e_dur

                            models[(d, m)].update(vals)
                            models[(d, m)]["turns"] += 1
                            models_gen_durations[(d, m)] += gen_dur
                            if e2e_dur > 0:
                                models_e2e_durations[(d, m)] += e2e_dur

            # 记录会话级路由快照
            if session_total_tokens > 0:
                sid = os.path.basename(fn).replace(".jsonl", "")
                if sid.startswith("rollout-"):
                    sid = sid.split("-")[-1]
                top_actual = session_actual_models.most_common(1)[0][0] if session_actual_models else "unknown"
                sess_gen_tps = (session_out_tokens / session_gen_dur) if session_gen_dur > 0 else 0.0
                sess_e2e_tps = (session_out_tokens / session_e2e_dur) if session_e2e_dur > 0 else 0.0
                session_route_history.append({
                    "time": session_created_time,
                    "session_id": sid[:12],
                    "req_model": client_requested_model or "(Auto/默认)",
                    "actual_model": top_actual,
                    "efforts": "/".join(session_efforts) if session_efforts else "default",
                    "total_tokens": session_total_tokens,
                    "in_tokens": session_in_tokens,
                    "cached_tokens": session_cached_tokens,
                    "gen_tps": sess_gen_tps,
                    "e2e_tps": sess_e2e_tps,
                })
        except Exception:
            continue

    if not daily:
        print(f"近 {days_back} 天内未发现 Codex 本地会话 Token 记录。")
        return

    banner_width = 118
    print("=" * banner_width)
    print(f"[*] 本地 OpenAI Codex 运行模型路由、Token 消耗与【纯生成吐率 vs 端到端吞吐】双维度审计报告 (近 {days_back} 天)")
    print("=" * banner_width)

    for d in sorted(daily.keys()):
        stat = daily[d]
        in_tok = stat["input_tokens"]
        cached_tok = stat["cached_input_tokens"]
        hit_rate = (cached_tok / in_tok * 100.0) if in_tok > 0 else 0.0

        # 速率计算
        d_gen_dur = daily_gen_durations[d]
        d_gen_tps = (stat["output_tokens"] / d_gen_dur) if d_gen_dur > 0 else 0.0
        d_e2e_dur = daily_e2e_durations[d]
        d_e2e_out_tps = (stat["output_tokens"] / d_e2e_dur) if d_e2e_dur > 0 else 0.0
        d_e2e_tot_tps = (stat["total_tokens"] / d_e2e_dur) if d_e2e_dur > 0 else 0.0

        print(f"\n[+] 日期 【{d}】 交互轮次: {stat['turns']} 轮")
        print(f"   |-- 总 Token 消耗:     {format_tokens(stat['total_tokens'])}")
        print(f"   |-- 提示词输入 (Prompt): {format_tokens(in_tok)}")
        print(f"   |   \\-- 缓存命中 Token:  {format_tokens(cached_tok)} | 🎯 缓存命中率: {hit_rate:.2f}%")
        print(f"   \\-- 模型回答 (Output):   {format_tokens(stat['output_tokens'])} (其中思考消耗: {format_tokens(stat['reasoning_output_tokens'])})")
        print(f"       ├─ ⚡ 纯生成吐字速率 (Gen TPS):     {d_gen_tps:.1f} token/s  (模型纯推理吐字速度，对应社区实测)")
        print(f"       ├─ ⏱️ 端到端输出吐率 (E2E Out TPS): {d_e2e_out_tps:.1f} token/s  (含多轮交互、工具执行挂钟输出速度)")
        print(f"       └─ 🚀 端到端总吞吐率 (E2E Total):   {d_e2e_tot_tps:.1f} token/s  (含大上下文摄入与缓存全流程综合吞吐)")

        print("   [-] 实际路由模型细分与双维度速率对比:")
        for (m_date, m_slug), m_stat in sorted(models.items()):
            if m_date == d:
                tot_str = format_tokens(m_stat["total_tokens"])
                m_in = m_stat["input_tokens"]
                m_cache = m_stat["cached_input_tokens"]
                m_hit_rate = (m_cache / m_in * 100.0) if m_in > 0 else 0.0

                m_gen_dur = models_gen_durations[(m_date, m_slug)]
                m_gen_tps = (m_stat["output_tokens"] / m_gen_dur) if m_gen_dur > 0 else 0.0

                m_e2e_dur = models_e2e_durations[(m_date, m_slug)]
                m_e2e_tps = (m_stat["output_tokens"] / m_e2e_dur) if m_e2e_dur > 0 else 0.0

                disp_name = model_meta.get(m_slug, {}).get("display_name", m_slug)
                label = f"{disp_name} ({m_slug})" if disp_name != m_slug else m_slug

                # 采用宽度安全填充，保证各字段在同一垂直线上
                col_lbl = pad_cell(f"* {label}", 40, "left")
                col_trn = pad_cell(f"轮次: {m_stat['turns']:>4}", 12, "left")
                col_tot = pad_cell(f"总消耗: {tot_str}", 26, "left")
                col_hit = pad_cell(f"缓存率: {m_hit_rate:>5.1f}%", 15, "left")
                col_gen = pad_cell(f"纯吐率: {m_gen_tps:>4.1f} tok/s", 18, "left")
                col_e2e = pad_cell(f"端到端: {m_e2e_tps:>4.1f} tok/s", 18, "left")

                print(f"       {col_lbl} | {col_trn} | {col_tot} | {col_hit} | {col_gen} | {col_e2e}")

    # 全局总计
    grand_total = collections.Counter()
    for s in daily.values():
        grand_total.update(s)

    g_in = grand_total["input_tokens"]
    g_cache = grand_total["cached_input_tokens"]
    g_hit_rate = (g_cache / g_in * 100.0) if g_in > 0 else 0.0

    g_gen_dur = sum(daily_gen_durations.values())
    g_gen_tps = (grand_total["output_tokens"] / g_gen_dur) if g_gen_dur > 0 else 0.0
    g_e2e_dur = sum(daily_e2e_durations.values())
    g_e2e_tps = (grand_total["output_tokens"] / g_e2e_dur) if g_e2e_dur > 0 else 0.0
    g_tot_tps = (grand_total["total_tokens"] / g_e2e_dur) if g_e2e_dur > 0 else 0.0

    print("\n" + "=" * banner_width)
    print("[*] 总体汇总 (Grand Total):")
    print(f"   * 累计对话轮次:       {grand_total['turns']} 轮")
    print(f"   * 累计总 Token:       {format_tokens(grand_total['total_tokens'])}")
    print(f"   * 累计输入 Token:     {format_tokens(g_in)}")
    print(f"   * 累计缓存加速:       {format_tokens(g_cache)} | 🚀 总体缓存命中率: {g_hit_rate:.2f}%")
    print(f"   * 累计模型输出:       {format_tokens(grand_total['output_tokens'])} (深度思考推理消耗: {format_tokens(grand_total['reasoning_output_tokens'])})")
    print(f"   * ⚡ 全程纯生成吐字速率 (Gen TPS):     {g_gen_tps:.1f} token/s")
    print(f"   * ⏱️ 全程端到端输出吐率 (E2E Out TPS): {g_e2e_tps:.1f} token/s")
    print(f"   * 🚀 全程端到端总吞吐率 (E2E Total):   {g_tot_tps:.1f} token/s")
    print("=" * banner_width)

    # 最近会话路由流实时审计 (网格表格与 CJK 绝对对齐)
    if show_recent_routes > 0 and session_route_history:
        print(f"\n[*] 最近 {min(show_recent_routes, len(session_route_history))} 次交互会话实际路由与吐率追踪 (Session Route & Speed Audit):")

        # 严格定义每一列的标题、真实字符宽度、以及对齐方向
        cols_cfg = [
            ("时间 (UTC+8)", 14, "center"),
            ("Session ID", 12, "center"),
            ("客户端请求模型", 18, "left"),
            ("服务端实际路由模型", 24, "left"),
            ("状态", 10, "center"),
            ("总Token消耗", 23, "right"),
            ("缓存率", 8, "right"),
            ("纯吐率", 11, "right"),
            ("端到端吐率", 11, "right"),
        ]

        # 组装表头与分割线
        header_str = " | ".join(pad_cell(title, w, align) for title, w, align in cols_cfg)
        sep_str = "-+-".join("-" * w for _, w, _ in cols_cfg)

        print(sep_str)
        print(header_str)
        print(sep_str)

        recent_sessions = session_route_history[-show_recent_routes:]
        for r in reversed(recent_sessions):
            req_m = r["req_model"]
            act_m = r["actual_model"]
            act_disp = model_meta.get(act_m, {}).get("display_name", act_m)

            # 路由判定
            if req_m in ("(Auto/默认)", "None", None):
                route_status = "[ROUTED]"
            elif req_m == act_m or req_m == act_disp:
                route_status = "[MATCH]"
            else:
                route_status = "[REDIRECT]"

            tot_s = format_tokens(r["total_tokens"])
            in_s = r["in_tokens"]
            c_s = r["cached_tokens"]
            rate = (c_s / in_s * 100.0) if in_s > 0 else 0.0
            gen_str = f"{r['gen_tps']:.1f} tok/s" if r['gen_tps'] > 0 else "--"
            e2e_str = f"{r['e2e_tps']:.1f} tok/s" if r['e2e_tps'] > 0 else "--"

            act_str = f"{act_disp} ({r['efforts']})" if r['efforts'] != "default" else act_disp

            row_vals = [
                r["time"],
                r["session_id"],
                req_m,
                act_str,
                route_status,
                tot_s,
                f"{rate:.1f}%",
                gen_str,
                e2e_str
            ]

            row_line = " | ".join(pad_cell(val, w, align) for val, (_, w, align) in zip(row_vals, cols_cfg))
            print(row_line)

        print(sep_str)
        print("💡 指标物理定义说明:")
        print("   • [纯生成吐率 (Gen TPS)]   : 扣除工具执行与等待后，模型纯输出推理吐字速率 (Output Tokens / Generation Latency)。")
        print("   • [端到端输出吐率 (E2E Out)]: 包含多轮思考、工具执行（命令/文件读写）挂钟时间的实际交付吐率。")
        print("   • [端到端总吞吐 (E2E Total)]: 包含庞大上下文摄入(几十万Prompt)与缓存加速的系统综合吞吐能力。")
        print("=" * banner_width)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="统计本地 Codex 运行模型与 Token 消耗，追踪实际路由模型及端到端/生成吞吐率")
    parser.add_argument("--days", type=int, default=7, help="查看最近几天的数据 (默认 7 天)")
    parser.add_argument("--routes", type=int, default=10, help="展示最近 N 次会话的路由追踪明细 (默认 10)")
    args = parser.parse_args()
    get_codex_stats(args.days, args.routes)
