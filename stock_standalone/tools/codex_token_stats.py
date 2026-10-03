# -*- coding: utf-8 -*-
"""
本地 AI 编程助手运行模型与 Token 消耗统计审计工具
支持多源接入:
1. OpenAI Codex CLI: 读取 ~/.codex/sessions/**/*.jsonl 本地会话归档
2. Google Antigravity / Gemini: 读取 ~/.gemini/antigravity/conversations/*.db (Protobuf) 与 logs/transcript.jsonl

核心能力:
- 真实模型路由审计 ([MATCH] / [ROUTED] / [REDIRECT])
- 输入/输出/思考Token核算及提示词缓存命中率透出 (Context Caching ~92%)
- 工业级【纯生成吐率 (Gen TPS)】与【端到端吞吐率 (E2E TPS)】双维度性能分析
- 终端 CJK 中文字符宽度感知与绝对数据网格对齐
- 智能日期简写解析 (支持 20260930, 0930, 9-30, 30 等)
- 100% 对齐 X 社区评测同款高保真输出卡片渲染 (包含首token等待与近似流式双重速率、样本覆盖率)
"""
import os
import sys
import glob
import json
import sqlite3
import collections
import datetime
from datetime import timezone, timedelta
import argparse
import unicodedata

# 确保在 Windows 控制台（GBK）下安全输出 UTF-8
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

def decode_protobuf(b):
    """
    轻量原生二进制 Protobuf 解码器 (无外部第三方库依赖)
    返回字段列表: [(field_number, wire_type_name, value)]
    """
    if not isinstance(b, (bytes, bytearray)):
        return []
    pos = 0
    fields = []
    b_len = len(b)
    while pos < b_len:
        key = 0
        shift = 0
        while pos < b_len:
            byte = b[pos]
            pos += 1
            key |= (byte & 0x7f) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
        field_num = key >> 3
        wire_type = key & 0x7

        if wire_type == 0:  # varint
            val = 0
            shift = 0
            while pos < b_len:
                byte = b[pos]
                pos += 1
                val |= (byte & 0x7f) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            fields.append((field_num, 'varint', val))
        elif wire_type == 2:  # length-delimited (string, bytes, embedded message)
            length = 0
            shift = 0
            while pos < b_len:
                byte = b[pos]
                pos += 1
                length |= (byte & 0x7f) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            if pos + length > b_len:
                break
            chunk = b[pos:pos+length]
            pos += length
            fields.append((field_num, 'bytes', chunk))
        elif wire_type == 1:  # 64-bit
            pos += 8
        elif wire_type == 5:  # 32-bit
            pos += 4
        else:
            break
    return fields

def load_codex_model_metadata():
    """从本地 ~/.codex/models_cache.json 加载官方 Codex 模型映射字典"""
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

# Google Antigravity / Gemini 模型官方友好显示名定义 (严格实事求是，底层写什么输出什么，绝不硬凑任何级别)
AGY_MODEL_META = {
    "gemini-3.8-flash": {"display_name": "Gemini 3.8 Flash"},
    "gemini-3.8-flash-tiered": {"display_name": "Gemini 3.8 Flash (Tiered)"},
    "gemini-3.8-flash-n": {"display_name": "Gemini 3.8 Flash (Preview)"},
    "gemini-3.7-flash": {"display_name": "Gemini 3.7 Flash"},
    "gemini-3.6-flash": {"display_name": "Gemini 3.6 Flash"},
    "gemini-3.6-flash-tiered": {"display_name": "Gemini 3.6 Flash (Tiered)"},
    "gemini-3-flash-a": {"display_name": "Gemini 3 Flash (Alpha)"},
    "gemini-3.1-pro-low": {"display_name": "Gemini 3.1 Pro (Low)"},
    "gemini-2.5-pro": {"display_name": "Gemini 2.5 Pro"},
    "gemini-pro-default": {"display_name": "Gemini Pro (Default)"},
    "gemini-default": {"display_name": "Gemini (Default)"},
    "claude-opus-4-6-thinking": {"display_name": "Claude Opus 4.6 (Thinking)"},
    "claude-sonnet-4-6": {"display_name": "Claude Sonnet 4.6"},
}

def load_antigravity_client_model():
    """实事求是读取用户在 ~/.gemini/antigravity-cli/settings.json 中配置的真实请求模型"""
    p = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                d = json.load(f)
                m = d.get("model")
                if m:
                    return str(m).strip()
        except Exception:
            pass
    return "Auto/默认"

# =========================================================================
# 权威模型官方与市场参考阶梯定价体系 (单位: 美元 / 100万 Tokens, 即 USD per 1M Tokens)
# 计费公式: Cost = (Input * input_price + Cache_Read * cache_read_price + Cache_Create * cache_create_price + Output * output_price) / 1,000,000
# =========================================================================
MODEL_PRICING = {
    # --- OpenAI Codex / GPT-6 / GPT-5.6 系列 ---
    "gpt-6.1-sol": {"input": 2.00, "cache_read": 0.10, "cache_create": 2.00, "output": 10.00},
    "gpt-6-sol": {"input": 2.00, "cache_read": 0.10, "cache_create": 2.00, "output": 10.00},
    "gpt-6.1-luna": {"input": 0.10, "cache_read": 0.01, "cache_create": 0.10, "output": 0.50},
    "gpt-6-luna": {"input": 0.10, "cache_read": 0.01, "cache_create": 0.10, "output": 0.50},
    "gpt-5.6-luna": {"input": 0.20, "cache_read": 0.02, "cache_create": 0.20, "output": 1.20},
    "gpt-5.6-sol": {"input": 1.00, "cache_read": 0.10, "cache_create": 1.00, "output": 5.00},
    "gpt-6-astra": {"input": 10.00, "cache_read": 1.00, "cache_create": 10.00, "output": 50.00},
    "gpt-6.1-astra": {"input": 10.00, "cache_read": 1.00, "cache_create": 10.00, "output": 50.00},
    "codex-auto-review": {"input": 0.15, "cache_read": 0.075, "cache_create": 0.15, "output": 0.60},
    "o3-mini": {"input": 1.10, "cache_read": 0.55, "cache_create": 1.10, "output": 4.40},
    "o1": {"input": 15.00, "cache_read": 7.50, "cache_create": 15.00, "output": 60.00},
    "gpt-4o": {"input": 2.50, "cache_read": 1.25, "cache_create": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "cache_read": 0.075, "cache_create": 0.15, "output": 0.60},

    # --- Google Antigravity / Gemini 系列 ---
    "gemini-3.8-flash": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},
    "gemini-3.8-flash-tiered": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},
    "gemini-3.8-flash-n": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},
    "gemini-3.7-flash": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},
    "gemini-3.6-flash": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},
    "gemini-3-flash-a": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},
    "gemini-3.1-pro-low": {"input": 1.25, "cache_read": 0.3125, "cache_create": 1.25, "output": 5.00},
    "gemini-2.5-pro": {"input": 1.25, "cache_read": 0.3125, "cache_create": 1.25, "output": 5.00},
    "gemini-pro-default": {"input": 1.25, "cache_read": 0.3125, "cache_create": 1.25, "output": 5.00},
    "gemini-default": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},
    "gemini-model": {"input": 0.15, "cache_read": 0.0375, "cache_create": 0.15, "output": 0.60},

    # --- Anthropic Claude 系列 (Antigravity 路由支持) ---
    "claude-sonnet-4-6": {"input": 3.00, "cache_read": 0.30, "cache_create": 3.75, "output": 15.00},
    "claude-3-7-sonnet": {"input": 3.00, "cache_read": 0.30, "cache_create": 3.75, "output": 15.00},
    "claude-3-5-sonnet": {"input": 3.00, "cache_read": 0.30, "cache_create": 3.75, "output": 15.00},
    "claude-opus-4-6-thinking": {"input": 15.00, "cache_read": 1.50, "cache_create": 18.75, "output": 75.00},
    "claude-3-opus": {"input": 15.00, "cache_read": 1.50, "cache_create": 18.75, "output": 75.00},
}

DEFAULT_PRICING = {"input": 1.00, "cache_read": 0.10, "cache_create": 1.00, "output": 5.00}

def load_custom_pricing():
    """动态加载用户本地自定义定价表 (如 ~/.codex/pricing.json 或 ~/.gemini/pricing.json)"""
    for p in [os.path.expanduser("~/.codex/pricing.json"), os.path.expanduser("~/.gemini/pricing.json")]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    custom = json.load(f)
                    if isinstance(custom, dict):
                        for k, v in custom.items():
                            if isinstance(v, dict):
                                MODEL_PRICING[k.lower().strip()] = v
            except Exception:
                pass

load_custom_pricing()

def get_model_pricing(model_name):
    """
    智能解析模型名称并匹配其权威单价字典 (USD per 1M tokens)
    支持前缀与关键词容错
    """
    if not model_name:
        return DEFAULT_PRICING
    m_clean = str(model_name).lower().strip()
    if m_clean in MODEL_PRICING:
        return MODEL_PRICING[m_clean]

    # 关键词模糊匹配
    if "6.1-sol" in m_clean or "6.1_sol" in m_clean or "gpt-6.1-sol" in m_clean:
        return MODEL_PRICING["gpt-6.1-sol"]
    elif "sol" in m_clean:
        if "5.6" in m_clean:
            return MODEL_PRICING["gpt-5.6-sol"]
        return MODEL_PRICING["gpt-6.1-sol"]
    elif "luna" in m_clean:
        if "5.6" in m_clean:
            return MODEL_PRICING["gpt-5.6-luna"]
        return MODEL_PRICING["gpt-6-luna"]
    elif "astra" in m_clean:
        return MODEL_PRICING["gpt-6-astra"]
    elif "auto-review" in m_clean or "auto_review" in m_clean:
        return MODEL_PRICING["codex-auto-review"]
    elif "flash" in m_clean:
        return MODEL_PRICING["gemini-3.8-flash"]
    elif "pro" in m_clean and ("gemini" in m_clean or "2.5" in m_clean or "3.1" in m_clean):
        return MODEL_PRICING["gemini-2.5-pro"]
    elif "opus" in m_clean:
        return MODEL_PRICING["claude-opus-4-6-thinking"]
    elif "sonnet" in m_clean:
        return MODEL_PRICING["claude-sonnet-4-6"]
    elif "o3" in m_clean:
        return MODEL_PRICING["o3-mini"]
    elif "o1" in m_clean:
        return MODEL_PRICING["o1"]
    elif "4o-mini" in m_clean:
        return MODEL_PRICING["gpt-4o-mini"]
    elif "4o" in m_clean:
        return MODEL_PRICING["gpt-4o"]
    elif "gemini" in m_clean:
        return MODEL_PRICING["gemini-default"]

    return DEFAULT_PRICING

def calc_token_cost(model_name, uncached_input, cached_input, output_tokens, cache_create=0):
    """
    计算特定模型调用的预估费用 (单位: USD)
    uncached_input: 未缓存的提示词输入 tokens
    cached_input: 命中缓存的输入 tokens
    output_tokens: 输出 tokens (包含 reasoning 思考 tokens)
    cache_create: 写入缓存的 tokens (若有，默认 0)
    """
    p = get_model_pricing(model_name)
    cost = (
        uncached_input * p.get("input", 1.0) +
        cached_input * p.get("cache_read", 0.1) +
        cache_create * p.get("cache_create", 1.0) +
        output_tokens * p.get("output", 5.0)
    ) / 1_000_000.0
    return max(0.0, cost)

def format_cost_cell(val):
    """格式化消费金额，兼顾美分与微美分精度"""
    if val >= 0.005:
        return f"${val:.2f}"
    elif val > 0:
        return f"${val:.3f}"
    return "$0.00"

def render_cost_table(daily, models, daily_costs, models_costs, model_meta, vendor_title="OpenAI Codex"):
    """
    渲染与用户/社区评测同款高保真 Unicode 边框格式的:
    [日级与模型细分 Token 消耗与消费成本审计表 (Daily Usage & Cost Table)]
    """
    all_models = [m for (_, m) in models.keys()]
    max_m_len = max([len(str(m)) for m in all_models] + [11])
    w_date = max(17, max_m_len + 5)
    w_model = max(14, max_m_len + 2)

    cols_w = [w_date, w_model, 9, 9, 10, 13, 11, 13, 11]
    top_border = "┌" + "┬".join("─" * (w + 2) for w in cols_w) + "┐"
    mid_border = "├" + "┼".join("─" * (w + 2) for w in cols_w) + "┤"
    bot_border = "└" + "┴".join("─" * (w + 2) for w in cols_w) + "┘"

    header_cols = [
        pad_cell("Date", w_date, "left"),
        pad_cell("Models", w_model, "left"),
        pad_cell("Input", 9, "right"),
        pad_cell("Output", 9, "right"),
        pad_cell("Reasoning", 10, "right"),
        pad_cell("Cache Create", 13, "right"),
        pad_cell("Cache Read", 11, "right"),
        pad_cell("Total Tokens", 13, "right"),
        pad_cell("Cost (USD)", 11, "right"),
    ]
    header_row = "│ " + " │ ".join(header_cols) + " │"

    print("\n" + "=" * 118)
    print(f"[*] 💰 日级模型 Token 消耗与预估消费审计表 [{vendor_title}] (Daily Usage & Cost Table):")
    print(top_border)
    print(header_row)
    print(mid_border)

    sorted_dates = sorted(daily.keys())
    grand_uncached = 0
    grand_out = 0
    grand_reasoning = 0
    grand_cache_create = 0
    grand_cache_read = 0
    grand_total_tokens = 0
    grand_cost = 0.0

    for d_idx, d in enumerate(sorted_dates):
        m_list = [m for (m_date, m) in sorted(models.keys()) if m_date == d]
        if not m_list:
            continue

        d_uncached = sum(models[(d, m)]["uncached_tokens"] for m in m_list)
        d_out = sum(models[(d, m)]["output_tokens"] for m in m_list)
        d_reasoning = sum(models[(d, m)]["reasoning_output_tokens"] for m in m_list)
        d_cache_create = sum(models[(d, m)]["cache_create_tokens"] for m in m_list)
        d_cache_read = sum(models[(d, m)]["cached_input_tokens"] for m in m_list)
        d_total = sum(models[(d, m)]["total_tokens"] for m in m_list)
        d_cost = daily_costs[d]

        grand_uncached += d_uncached
        grand_out += d_out
        grand_reasoning += d_reasoning
        grand_cache_create += d_cache_create
        grand_cache_read += d_cache_read
        grand_total_tokens += d_total
        grand_cost += d_cost

        if len(m_list) > 1:
            first_m = m_list[0]
            r1 = [
                pad_cell(d, w_date, "left"),
                pad_cell(f"- {first_m}", w_model, "left"),
                pad_cell(f"{d_uncached:,}", 9, "right"),
                pad_cell(f"{d_out:,}", 9, "right"),
                pad_cell(f"{d_reasoning:,}", 10, "right"),
                pad_cell(f"{d_cache_create:,}", 13, "right"),
                pad_cell(f"{d_cache_read:,}", 11, "right"),
                pad_cell(f"{d_total:,}", 13, "right"),
                pad_cell(format_cost_cell(d_cost), 11, "right"),
            ]
            print("│ " + " │ ".join(r1) + " │")

            for m in m_list[1:]:
                rx = [
                    pad_cell("", w_date, "left"),
                    pad_cell(f"- {m}", w_model, "left"),
                    pad_cell("", 9, "right"),
                    pad_cell("", 9, "right"),
                    pad_cell("", 10, "right"),
                    pad_cell("", 13, "right"),
                    pad_cell("", 11, "right"),
                    pad_cell("", 13, "right"),
                    pad_cell("", 11, "right"),
                ]
                print("│ " + " │ ".join(rx) + " │")

            for m in m_list:
                print(mid_border)
                m_st = models[(d, m)]
                m_cst = models_costs[(d, m)]
                sub_r = [
                    pad_cell(f"  └─ {m}", w_date, "left"),
                    pad_cell("", w_model, "left"),
                    pad_cell(f"{m_st['uncached_tokens']:,}", 9, "right"),
                    pad_cell(f"{m_st['output_tokens']:,}", 9, "right"),
                    pad_cell(f"{m_st['reasoning_output_tokens']:,}", 10, "right"),
                    pad_cell(f"{m_st['cache_create_tokens']:,}", 13, "right"),
                    pad_cell(f"{m_st['cached_input_tokens']:,}", 11, "right"),
                    pad_cell(f"{m_st['total_tokens']:,}", 13, "right"),
                    pad_cell(format_cost_cell(m_cst), 11, "right"),
                ]
                print("│ " + " │ ".join(sub_r) + " │")
        else:
            m = m_list[0]
            r1 = [
                pad_cell(d, w_date, "left"),
                pad_cell(f"- {m}", w_model, "left"),
                pad_cell(f"{d_uncached:,}", 9, "right"),
                pad_cell(f"{d_out:,}", 9, "right"),
                pad_cell(f"{d_reasoning:,}", 10, "right"),
                pad_cell(f"{d_cache_create:,}", 13, "right"),
                pad_cell(f"{d_cache_read:,}", 11, "right"),
                pad_cell(f"{d_total:,}", 13, "right"),
                pad_cell(format_cost_cell(d_cost), 11, "right"),
            ]
            print("│ " + " │ ".join(r1) + " │")

        if d_idx < len(sorted_dates) - 1:
            print(mid_border)

    if len(sorted_dates) > 1:
        print(mid_border)
        grand_r = [
            pad_cell("Total (Grand)", w_date, "left"),
            pad_cell(f"{len(set(all_models))} models", w_model, "left"),
            pad_cell(f"{grand_uncached:,}", 9, "right"),
            pad_cell(f"{grand_out:,}", 9, "right"),
            pad_cell(f"{grand_reasoning:,}", 10, "right"),
            pad_cell(f"{grand_cache_create:,}", 13, "right"),
            pad_cell(f"{grand_cache_read:,}", 11, "right"),
            pad_cell(f"{grand_total_tokens:,}", 13, "right"),
            pad_cell(format_cost_cell(grand_cost), 11, "right"),
        ]
        print("│ " + " │ ".join(grand_r) + " │")

    print(bot_border)


def parse_date_input(date_str, tz=None):
    """
    智能解析用户输入的日期简写格式，自动对齐最近的年份和最近的月份:
    - 标准格式: '2026-09-30', '2026/09/30', '2026.09.30' -> '2026-09-30'
    - 8位纯数字: '20260930' -> '2026-09-30'
    - 4位纯数字 (MMDD): '0930' -> '2026-09-30' (自动补齐当前年份，若月日超前则推导至最近年份)
    - 短横线月日 (M-D/MM-DD): '9-30', '09-30' -> '2026-09-30'
    - 纯日期 (D/DD): '30', '1' -> 自动推导至最近发生该日期的月份 (如今天是10-01，输入30自动识别为上月09-30)
    """
    if not date_str:
        return None
    now = datetime.datetime.now(tz) if tz else datetime.datetime.now()
    cur_year = now.year
    cur_month = now.month
    cur_day = now.day

    s = date_str.strip().replace("/", "-").replace(".", "-")

    # 1. 已经是 YYYY-MM-DD
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            datetime.datetime.strptime(s, "%Y-%m-%d")
            return s
        except ValueError:
            pass

    # 2. 8 位纯数字 YYYYMMDD, 如 20260930
    if len(s) == 8 and s.isdigit():
        try:
            d = datetime.datetime.strptime(s, "%Y%m%d")
            return d.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 3. 4 位纯数字 MMDD, 如 0930
    if len(s) == 4 and s.isdigit():
        month = int(s[:2])
        day = int(s[2:])
        cand_year = cur_year
        if month > cur_month + 1:
            cand_year = cur_year - 1
        try:
            d = datetime.date(cand_year, month, day)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 4. 包含短横线的 M-D 或 MM-DD, 如 9-30 或 09-30
    if "-" in s and len(s) in (3, 4, 5):
        parts = s.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            month = int(parts[0])
            day = int(parts[1])
            cand_year = cur_year
            if month > cur_month + 1:
                cand_year = cur_year - 1
            try:
                d = datetime.date(cand_year, month, day)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # 5. 纯 1~2 位数字 (DD), 如 30, 代表当月或最近一月的 30 号
    if s.isdigit() and len(s) in (1, 2):
        day = int(s)
        if day > cur_day:
            tgt_month = cur_month - 1 if cur_month > 1 else 12
            tgt_year = cur_year if cur_month > 1 else cur_year - 1
        else:
            tgt_month = cur_month
            tgt_year = cur_year
        try:
            d = datetime.date(tgt_year, tgt_month, day)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 兜底尝试标准格式解析
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m%d", "%m-%d"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            if "%Y" not in fmt:
                d = d.replace(year=cur_year)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str

# =========================================================================
# 对齐 X 社区评测同款样式的核心速度与样本可靠性评估卡片渲染器 (通用复用)
# =========================================================================
def render_community_speed_card(daily, model_sample_stats, model_meta, tz, target_date_override=None, target_model_override=None, default_keyword=None, vendor_title=None):
    """
    对齐 X 社区评测样式的标准输出卡片:
    今天 X 月 X 日截至北京时间 HH:MM, [Model Display] 的输出速度估算为:
    • XX.XX tokens/秒: 包含首 token 等待，剔除工具执行和用户空闲。
    • 约 XX.XX tokens/秒: 从首个输出记录起算的近似流式速度。

    核查了 XX 个会话、X,XXX 次请求，其中 X,XXX 次计时可靠，覆盖 XX.X% 的请求、XX.X% 的输出。输出包含推理 tokens；因此不能把它称为全部请求的精确纯解码速度。
    """
    now = datetime.datetime.now(tz)
    today_str = now.date().isoformat()
    latest_date = max(daily.keys()) if daily else today_str

    target_date = target_date_override if target_date_override else latest_date
    all_pairs = list(model_sample_stats.keys())
    if not all_pairs:
        return

    def pick_target_model(date_key):
        cand = [m for (d, m) in all_pairs if d == date_key]
        if not cand:
            return None
        if target_model_override:
            m_matches = [m for m in cand if target_model_override.lower() in m.lower()]
            if m_matches:
                return m_matches[0]
        if default_keyword:
            kw_matches = [m for m in cand if default_keyword.lower() in m.lower()]
            if kw_matches:
                return kw_matches[0]
        return max(cand, key=lambda m: model_sample_stats[(date_key, m)]["total_requests"])

    target_model = pick_target_model(target_date)
    if not target_model:
        avail_dates = sorted(list(set(d for (d, m) in all_pairs)), reverse=True)
        for ad in avail_dates:
            target_model = pick_target_model(ad)
            if target_model:
                target_date = ad
                break

    if not target_model:
        return

    def print_single_card(title_prefix, stats, model_name):
        tot_req = stats["total_requests"]
        rel_req = stats["reliable_requests"]
        tot_out = stats["total_output_tokens"]
        rel_out = stats["reliable_output_tokens"]
        sess_cnt = len(stats["sessions"])

        if tot_req == 0:
            return

        req_cov = (rel_req / tot_req * 100.0) if tot_req > 0 else 0.0
        out_cov = (rel_out / tot_out * 100.0) if tot_out > 0 else 0.0

        sum_ttft = stats["sum_ttft_dur"]
        sum_stream = stats["sum_stream_dur"]

        rate_ttft = (rel_out / sum_ttft) if sum_ttft > 0 else 0.0
        rate_stream = (rel_out / sum_stream) if sum_stream > 0 else 0.0

        disp = model_meta.get(model_name, {}).get("display_name", model_name)
        clean = (disp.replace("-Sol", " Sol")
                     .replace("-Luna", " Luna")
                     .replace("-Astra", " Astra")
                     .replace("-n", " (Preview)")
                     .replace("-tiered", " (Tiered)")
                     .replace("-thinking", " (Thinking)"))

        print(f"\n{title_prefix}, {clean} 的输出速度估算为:\n")
        print(f"  • {rate_ttft:.2f} tokens/秒: 包含首 token 等待，剔除工具执行和用户空闲。")
        print(f"  • 约 {rate_stream:.2f} tokens/秒: 从首个输出记录起算的近似流式速度。\n")
        print(f"核查了 {sess_cnt} 个会话、{tot_req:,} 次请求，其中 {rel_req:,} 次计时可靠，覆盖 {req_cov:.1f}% 的请求、{out_cov:.1f}% 的输出。输出包含推理 tokens；因此不能把它称为全部请求的精确纯解码速度。\n")

    print("\n" + "-" * 118)
    banner_extra = f" [{vendor_title}]" if vendor_title else ""
    print(f"[*] 🌟 社区评测标准速度与样本审计卡片{banner_extra} (Community Benchmark Style Summary):")
    print("-" * 118)

    # 1. 输出指定日期或今日的卡片
    t_dt = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    if t_dt == now.date():
        time_heading = f"今天 {now.month} 月 {now.day:02d} 日截至北京时间 {now.strftime('%H:%M')}"
    else:
        time_heading = f"{t_dt.year} 年 {t_dt.month:02d} 月 {t_dt.day:02d} 日截至北京时间 24:00"

    today_stats = model_sample_stats[(target_date, target_model)]
    print_single_card(time_heading, today_stats, target_model)

    # 2. 如果统计的天数大于 1 天，追加一个多日大样本综合卡片，方便比对统计学均值
    distinct_dates = list(daily.keys())
    if len(distinct_dates) > 1 and not target_date_override:
        agg_stats = {
            "total_requests": 0,
            "reliable_requests": 0,
            "total_output_tokens": 0,
            "reliable_output_tokens": 0,
            "sum_ttft_dur": 0.0,
            "sum_stream_dur": 0.0,
            "sessions": set(),
        }
        for (d, m), s in model_sample_stats.items():
            if m == target_model:
                agg_stats["total_requests"] += s["total_requests"]
                agg_stats["reliable_requests"] += s["reliable_requests"]
                agg_stats["total_output_tokens"] += s["total_output_tokens"]
                agg_stats["reliable_output_tokens"] += s["reliable_output_tokens"]
                agg_stats["sum_ttft_dur"] += s["sum_ttft_dur"]
                agg_stats["sum_stream_dur"] += s["sum_stream_dur"]
                agg_stats["sessions"].update(s["sessions"])

        if agg_stats["total_requests"] > 0:
            agg_heading = f"近 {len(distinct_dates)} 天综合全量样本 (截至北京时间 {now.strftime('%H:%M')})"
            print("-" * 118)
            print_single_card(agg_heading, agg_stats, target_model)

    print("-" * 118)

# =========================================================================
# 适配器 1: OpenAI Codex 本地会话统计
# =========================================================================
def get_codex_stats(days_back=7, show_recent_routes=10, target_date_arg=None, target_model_arg=None, time_mode="active"):
    root = os.path.expanduser("~/.codex/sessions")
    if not os.path.exists(root):
        print(f"未找到 Codex 会话目录: {root}")
        return None

    model_meta = load_codex_model_metadata()
    tz = timezone(timedelta(hours=8))

    target_date_clean = parse_date_input(target_date_arg, tz)
    if target_date_clean and target_date_clean != target_date_arg:
        print(f"[*] 智能日期简写识别: '{target_date_arg}' -> '{target_date_clean}'")

    if target_date_clean:
        try:
            tgt_dt = datetime.datetime.strptime(target_date_clean, "%Y-%m-%d").date()
            now_dt = datetime.datetime.now(tz).date()
            diff_days = (now_dt - tgt_dt).days
            if diff_days >= days_back:
                days_back = diff_days + 1
        except Exception:
            pass

    cutoff_date = (datetime.datetime.now(tz) - timedelta(days=days_back)).date().isoformat()

    daily = collections.defaultdict(collections.Counter)
    models = collections.defaultdict(collections.Counter)
    daily_costs = collections.defaultdict(float)
    models_costs = collections.defaultdict(float)
    daily_gen_durations = collections.defaultdict(float)
    models_gen_durations = collections.defaultdict(float)
    daily_e2e_durations = collections.defaultdict(float)
    models_e2e_durations = collections.defaultdict(float)

    model_sample_stats = collections.defaultdict(lambda: {
        "total_requests": 0,
        "reliable_requests": 0,
        "total_output_tokens": 0,
        "reliable_output_tokens": 0,
        "sum_ttft_dur": 0.0,
        "sum_stream_dur": 0.0,
        "sessions": set(),
    })

    seen_responses = set()
    session_route_history = []

    all_files = glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
    all_files.sort(key=os.path.getmtime)

    for fn in all_files:
        turn_models = {}
        client_requested_model = None
        session_first_time = None
        session_last_time = None
        session_total_tokens = 0
        session_in_tokens = 0
        session_cached_tokens = 0
        session_out_tokens = 0
        session_cost = 0.0
        session_gen_dur = 0.0
        session_e2e_dur = 0.0
        session_actual_models = collections.Counter()
        session_efforts = set()

        call_start_time = None
        turn_start_time = None
        first_output_time = None
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

                    if cur_dt:
                        if not session_first_time:
                            session_first_time = cur_dt
                        session_last_time = cur_dt

                    if "thread_settings" in p and not client_requested_model:
                        client_requested_model = p["thread_settings"].get("model")

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
                            first_output_time = None
                        continue

                    if event_type == "response_item" and p.get("type") in ("custom_tool_call_output", "tool_output"):
                        if cur_dt:
                            call_start_time = cur_dt
                            first_output_time = None
                        continue

                    if event_type == "response_item" and p.get("type") in ("reasoning", "message", "custom_tool_call"):
                        if call_start_time and not first_output_time and cur_dt:
                            first_output_time = cur_dt
                        continue

                    if event_type == "token_usage_record":
                        rid = p.get("response_id")
                        if rid and rid in seen_responses:
                            continue
                        if rid:
                            seen_responses.add(rid)

                        u = p.get("usage") or p.get("turn_token_usage") or {}
                        d = cur_dt.date().isoformat() if cur_dt else "未知日期"

                        out_tok = int(u.get("output_tokens", 0) or 0)
                        in_tok_raw = int(u.get("input_tokens", 0) or 0)
                        cached_tok = int(u.get("cached_input_tokens", 0) or 0)
                        cache_create_tok = int(u.get("cache_write_input_tokens", 0) or 0)
                        reasoning_tok = int(u.get("reasoning_output_tokens", 0) or 0)
                        total_tok = int(u.get("total_tokens", 0) or 0)

                        if total_tok > 0 and (in_tok_raw + cached_tok + out_tok) == total_tok:
                            uncached_tok = in_tok_raw
                            total_in_tok = in_tok_raw + cached_tok
                        else:
                            uncached_tok = max(0, in_tok_raw - cached_tok)
                            total_in_tok = in_tok_raw

                        turn_id = p.get("turn_id")
                        m = turn_models.get(turn_id, cur_model)
                        turn_cost = calc_token_cost(m, uncached_tok, cached_tok, out_tok, cache_create_tok)

                        vals = {
                            "input_tokens": total_in_tok,
                            "uncached_tokens": uncached_tok,
                            "cached_input_tokens": cached_tok,
                            "cache_create_tokens": cache_create_tok,
                            "output_tokens": out_tok,
                            "reasoning_output_tokens": reasoning_tok,
                            "total_tokens": total_tok if total_tok > 0 else (total_in_tok + out_tok),
                        }

                        ttft_dur = 0.0
                        stream_dur = 0.0
                        if call_start_time and cur_dt and out_tok > 0:
                            elapsed_ttft = (cur_dt - call_start_time).total_seconds()
                            if 0.5 <= elapsed_ttft <= 300.0:
                                ttft_dur = elapsed_ttft
                                if first_output_time and cur_dt >= first_output_time:
                                    s_elapsed = (cur_dt - first_output_time).total_seconds()
                                    stream_dur = s_elapsed if s_elapsed > 0.2 else (elapsed_ttft * 0.85)
                                else:
                                    stream_dur = elapsed_ttft * 0.85

                        gen_dur = stream_dur if stream_dur > 0 else (ttft_dur if ttft_dur > 0 else 0.0)
                        call_start_time = None
                        first_output_time = None

                        e2e_dur = 0.0
                        if turn_start_time and cur_dt:
                            elapsed_e2e = (cur_dt - turn_start_time).total_seconds()
                            if 0.5 <= elapsed_e2e <= 600.0:
                                e2e_dur = elapsed_e2e

                        session_total_tokens += vals["total_tokens"]
                        session_in_tokens += total_in_tok
                        session_cached_tokens += cached_tok
                        session_out_tokens += out_tok
                        session_cost += turn_cost
                        session_gen_dur += gen_dur
                        session_e2e_dur += e2e_dur

                        if d >= cutoff_date or d == "未知日期":
                            daily[d].update(vals)
                            daily[d]["turns"] += 1
                            daily_costs[d] += turn_cost
                            daily_gen_durations[d] += gen_dur
                            if e2e_dur > 0:
                                daily_e2e_durations[d] += e2e_dur

                            models[(d, m)].update(vals)
                            models[(d, m)]["turns"] += 1
                            models_costs[(d, m)] += turn_cost
                            models_gen_durations[(d, m)] += gen_dur
                            if e2e_dur > 0:
                                models_e2e_durations[(d, m)] += e2e_dur

                            card_key = (d, m)
                            model_sample_stats[card_key]["total_requests"] += 1
                            model_sample_stats[card_key]["total_output_tokens"] += out_tok
                            model_sample_stats[card_key]["sessions"].add(fn)
                            if ttft_dur > 0:
                                model_sample_stats[card_key]["reliable_requests"] += 1
                                model_sample_stats[card_key]["reliable_output_tokens"] += out_tok
                                model_sample_stats[card_key]["sum_ttft_dur"] += ttft_dur
                                model_sample_stats[card_key]["sum_stream_dur"] += stream_dur

            if session_total_tokens > 0:
                sid = os.path.basename(fn).replace(".jsonl", "")
                if sid.startswith("rollout-"):
                    sid = sid.split("-")[-1]

                if not session_last_time:
                    mtime = os.path.getmtime(fn)
                    session_last_time = datetime.datetime.fromtimestamp(mtime, tz)
                if not session_first_time:
                    session_first_time = session_last_time

                created_time_str = session_first_time.strftime("%m-%d %H:%M:%S")
                active_time_str = session_last_time.strftime("%m-%d %H:%M:%S")
                active_ts = session_last_time.timestamp()

                top_actual = session_actual_models.most_common(1)[0][0] if session_actual_models else "unknown"
                sess_gen_tps = (session_out_tokens / session_gen_dur) if session_gen_dur > 0 else 0.0
                sess_e2e_tps = (session_out_tokens / session_e2e_dur) if session_e2e_dur > 0 else 0.0

                session_route_history.append({
                    "time": active_time_str if time_mode == "active" else created_time_str,
                    "active_time": active_time_str,
                    "created_time": created_time_str,
                    "active_ts": active_ts,
                    "session_id": sid[:12],
                    "req_model": client_requested_model or "(Auto/默认)",
                    "actual_model": top_actual,
                    "efforts": "/".join(session_efforts) if session_efforts else "default",
                    "total_tokens": session_total_tokens,
                    "in_tokens": session_in_tokens,
                    "cached_tokens": session_cached_tokens,
                    "cost": session_cost,
                    "gen_tps": sess_gen_tps,
                    "e2e_tps": sess_e2e_tps,
                })
        except Exception:
            continue

    if not daily:
        print(f"近 {days_back} 天内未发现 OpenAI Codex 本地会话记录。")
        return None

    banner_width = 118
    print("=" * banner_width)
    print(f"[*] 本地 OpenAI Codex 运行模型路由、Token 消耗与【纯生成吐率 vs 端到端吞吐】双维度审计报告 (近 {days_back} 天)")
    print("=" * banner_width)

    for d in sorted(daily.keys()):
        stat = daily[d]
        d_cost = daily_costs[d]
        in_tok = stat["input_tokens"]
        cached_tok = stat["cached_input_tokens"]
        hit_rate = (cached_tok / in_tok * 100.0) if in_tok > 0 else 0.0

        d_gen_dur = daily_gen_durations[d]
        d_gen_tps = (stat["output_tokens"] / d_gen_dur) if d_gen_dur > 0 else 0.0
        d_e2e_dur = daily_e2e_durations[d]
        d_e2e_out_tps = (stat["output_tokens"] / d_e2e_dur) if d_e2e_dur > 0 else 0.0
        d_e2e_tot_tps = (stat["total_tokens"] / d_e2e_dur) if d_e2e_dur > 0 else 0.0

        print(f"\n[+] 日期 【{d}】 交互轮次: {stat['turns']} 轮 | 💰 预估费用: ${d_cost:.2f}")
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
                m_cst = models_costs[(m_date, m_slug)]
                m_in = m_stat["input_tokens"]
                m_cache = m_stat["cached_input_tokens"]
                m_hit_rate = (m_cache / m_in * 100.0) if m_in > 0 else 0.0

                m_gen_dur = models_gen_durations[(m_date, m_slug)]
                m_gen_tps = (m_stat["output_tokens"] / m_gen_dur) if m_gen_dur > 0 else 0.0

                m_e2e_dur = models_e2e_durations[(m_date, m_slug)]
                m_e2e_tps = (m_stat["output_tokens"] / m_e2e_dur) if m_e2e_dur > 0 else 0.0

                disp_name = model_meta.get(m_slug, {}).get("display_name", m_slug)
                label = f"{disp_name} ({m_slug})" if disp_name != m_slug else m_slug

                col_lbl = pad_cell(f"* {label}", 40, "left")
                col_trn = pad_cell(f"轮次: {m_stat['turns']:>4}", 12, "left")
                col_tot = pad_cell(f"总消耗: {tot_str}", 26, "left")
                col_cst = pad_cell(f"费用: {format_cost_cell(m_cst)}", 13, "left")
                col_hit = pad_cell(f"缓存率: {m_hit_rate:>5.1f}%", 15, "left")
                col_gen = pad_cell(f"纯吐率: {m_gen_tps:>4.1f} tok/s", 18, "left")
                col_e2e = pad_cell(f"端到端: {m_e2e_tps:>4.1f} tok/s", 18, "left")

                print(f"       {col_lbl} | {col_trn} | {col_tot} | {col_cst} | {col_hit} | {col_gen} | {col_e2e}")

    grand_total = collections.Counter()
    for s in daily.values():
        grand_total.update(s)

    grand_cost = sum(daily_costs.values())
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
    print(f"   * 💰 累计预估消费:     ${grand_cost:.2f} USD (折合约 ￥{grand_cost * 7.2:.2f} RMB)")
    print(f"   * 累计输入 Token:     {format_tokens(g_in)}")
    print(f"   * 累计缓存加速:       {format_tokens(g_cache)} | 🚀 总体缓存命中率: {g_hit_rate:.2f}%")
    print(f"   * 累计模型输出:       {format_tokens(grand_total['output_tokens'])} (深度思考推理消耗: {format_tokens(grand_total['reasoning_output_tokens'])})")
    print(f"   * ⚡ 全程纯生成吐字速率 (Gen TPS):     {g_gen_tps:.1f} token/s")
    print(f"   * ⏱️ 全程端到端输出吐率 (E2E Out TPS): {g_e2e_tps:.1f} token/s")
    print(f"   * 🚀 全程端到端总吞吐率 (E2E Total):   {g_tot_tps:.1f} token/s")
    print("=" * banner_width)

    # 渲染高保真日级模型消耗与消费成本审计表 (对齐用户专属格式)
    render_cost_table(daily, models, daily_costs, models_costs, model_meta, vendor_title="OpenAI Codex")

    if show_recent_routes > 0 and session_route_history:
        time_col_title = "活跃时间 (UTC+8)" if time_mode == "active" else "创建时间 (UTC+8)"
        print(f"\n[*] 最近 {min(show_recent_routes, len(session_route_history))} 次交互会话实际路由与吐率追踪 (Session Route & Speed Audit):")
        cols_cfg = [
            (time_col_title, 14, "center"),
            ("Session ID", 12, "center"),
            ("客户端请求模型", 18, "left"),
            ("服务端实际路由模型", 24, "left"),
            ("状态", 10, "center"),
            ("总Token消耗", 21, "right"),
            ("预估费用", 10, "right"),
            ("缓存率", 8, "right"),
            ("纯吐率", 11, "right"),
            ("端到端吐率", 11, "right"),
        ]

        header_str = " | ".join(pad_cell(title, w, align) for title, w, align in cols_cfg)
        sep_str = "-+-".join("-" * w for _, w, _ in cols_cfg)

        print(sep_str)
        print(header_str)
        print(sep_str)

        # 严格按最后活跃时间排序 (从旧到新)
        session_route_history.sort(key=lambda x: x["active_ts"])
        recent_sessions = session_route_history[-show_recent_routes:]
        for r in reversed(recent_sessions):
            req_m = r["req_model"]
            act_m = r["actual_model"]
            act_disp = model_meta.get(act_m, {}).get("display_name", act_m)

            if req_m in ("(Auto/默认)", "None", None):
                route_status = "[ROUTED]"
            elif req_m == act_m or req_m == act_disp:
                route_status = "[MATCH]"
            else:
                route_status = "[REDIRECT]"

            tot_s = format_tokens(r["total_tokens"])
            cost_s = format_cost_cell(r.get("cost", 0.0))
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
                cost_s,
                f"{rate:.1f}%",
                gen_str,
                e2e_str
            ]
            row_line = " | ".join(pad_cell(val, w, align) for val, (_, w, align) in zip(row_vals, cols_cfg))
            print(row_line)

        print(sep_str)
        time_meaning = (
            "会话最后一次响应输出的最新活跃时间 (默认方案A，时间严格递减；可用 --created 切换查看创建起源)"
            if time_mode == "active"
            else "会话首次创建并产生首个Token的时间 (当前样式，按活跃倒序展示创建起源)"
        )
        print("💡 指标物理定义说明:")
        print(f"   • [{time_col_title}]: {time_meaning}。")
        print("   • [纯生成吐率 (Gen TPS)]   : 扣除工具执行与等待后，模型纯输出推理吐字速率 (Output Tokens / Generation Latency)。")
        print("   • [端到端输出吐率 (E2E Out)]: 包含多轮思考、工具执行（命令/文件读写）挂钟时间的实际交付吐率。")
        print("   • [端到端总吞吐 (E2E Total)]: 包含庞大上下文摄入(几十万Prompt)与缓存加速的系统综合吞吐能力。")
        print("   • [预估费用 (Cost)]        : 基于 OpenAI / Google / Anthropic 官方阶梯定价与缓存折扣自动核算折算。")

    render_community_speed_card(daily, model_sample_stats, model_meta, tz, target_date_clean, target_model_arg, default_keyword="sol", vendor_title="OpenAI Codex")
    print("=" * banner_width)
    grand_total["cost_usd"] = grand_cost
    return grand_total

# =========================================================================
# 适配器 2: Google Antigravity / Gemini 本地会话统计 (支持桌面端、IDE端与全量合并)
# =========================================================================
def get_antigravity_stats(days_back=7, show_recent_routes=10, target_date_arg=None, target_model_arg=None, app_type="standalone", time_mode="active"):
    """
    解析本地 Google Antigravity / Gemini 会话记录与 Token 吞吐审计
    - app_type:
        'standalone': 扫描 ~/.gemini/antigravity (桌面独立端)
        'ide':        扫描 ~/.gemini/antigravity-ide (VS Code IDE端)
        'merged':     扫描并合并独立端与 IDE 端全部记录
    """
    base_agy = os.path.expanduser("~/.gemini/antigravity")
    base_ide = os.path.expanduser("~/.gemini/antigravity-ide")

    scan_targets = []  # list of (db_dir, brain_dir, app_tag)
    if app_type == "standalone":
        scan_targets = [(os.path.join(base_agy, "conversations"), os.path.join(base_agy, "brain"), "[APP]")]
        audit_title = f"[*] 本地 Google Antigravity (桌面独立端) 运行模型路由、Token 消耗与【纯生成吐率 vs 端到端吞吐】审计报告 (近 {days_back} 天)"
        card_vendor = "Google Antigravity"
    elif app_type == "ide":
        scan_targets = [(os.path.join(base_ide, "conversations"), os.path.join(base_ide, "brain"), "[IDE]")]
        audit_title = f"[*] 本地 Google Antigravity IDE (VS Code) 运行模型路由、Token 消耗与【纯生成吐率 vs 端到端吞吐】审计报告 (近 {days_back} 天)"
        card_vendor = "Google Antigravity IDE"
    else:  # merged / gemini
        if os.path.exists(os.path.join(base_agy, "conversations")):
            scan_targets.append((os.path.join(base_agy, "conversations"), os.path.join(base_agy, "brain"), "[APP]"))
        if os.path.exists(os.path.join(base_ide, "conversations")):
            scan_targets.append((os.path.join(base_ide, "conversations"), os.path.join(base_ide, "brain"), "[IDE]"))
        audit_title = f"[*] 本地 Google Antigravity & IDE (Gemini 全量) 运行模型路由与综合吞吐审计报告 (近 {days_back} 天)"
        card_vendor = "Google Antigravity (All)"

    # 检查是否有可用目录
    existing_targets = [t for t in scan_targets if os.path.exists(t[0])]
    if not existing_targets:
        print(f"未找到 Antigravity 会话目录: {[t[0] for t in scan_targets]}")
        return None

    tz = timezone(timedelta(hours=8))
    target_date_clean = parse_date_input(target_date_arg, tz)
    if target_date_clean and target_date_clean != target_date_arg:
        print(f"[*] 智能日期简写识别: '{target_date_arg}' -> '{target_date_clean}'")

    if target_date_clean:
        try:
            tgt_dt = datetime.datetime.strptime(target_date_clean, "%Y-%m-%d").date()
            now_dt = datetime.datetime.now(tz).date()
            diff_days = (now_dt - tgt_dt).days
            if diff_days >= days_back:
                days_back = diff_days + 1
        except Exception:
            pass

    now = datetime.datetime.now(tz)
    cutoff_dt = now - timedelta(days=days_back)
    cutoff_ts = cutoff_dt.timestamp()
    cutoff_date = cutoff_dt.date().isoformat()

    # 聚合所有会话 DB，并去重
    candidate_dbs = {}  # conv_id -> (db_path, brain_dir, app_tag, mtime)
    for db_dir, brain_dir, app_tag in existing_targets:
        for f in glob.glob(os.path.join(db_dir, "*.db")):
            mtime = os.path.getmtime(f)
            if mtime >= (cutoff_ts - 86400):
                conv_id = os.path.basename(f).replace(".db", "")
                if conv_id not in candidate_dbs or mtime > candidate_dbs[conv_id][3]:
                    candidate_dbs[conv_id] = (f, brain_dir, app_tag, mtime)

    active_items = sorted(candidate_dbs.values(), key=lambda x: x[3])

    daily = collections.defaultdict(collections.Counter)
    models = collections.defaultdict(collections.Counter)
    daily_costs = collections.defaultdict(float)
    models_costs = collections.defaultdict(float)
    daily_gen_durations = collections.defaultdict(float)
    models_gen_durations = collections.defaultdict(float)
    daily_e2e_durations = collections.defaultdict(float)
    models_e2e_durations = collections.defaultdict(float)

    model_sample_stats = collections.defaultdict(lambda: {
        "total_requests": 0,
        "reliable_requests": 0,
        "total_output_tokens": 0,
        "reliable_output_tokens": 0,
        "sum_ttft_dur": 0.0,
        "sum_stream_dur": 0.0,
        "sessions": set(),
    })

    session_route_history = []
    client_req_model = load_antigravity_client_model()

    for db_path, brain_dir, app_tag, _ in active_items:
        conv_id = os.path.basename(db_path).replace(".db", "")
        tr_path = os.path.join(brain_dir, conv_id, ".system_generated", "logs", "transcript.jsonl")

        step_times = {}
        step_e2e_durs = {}
        if os.path.exists(tr_path):
            try:
                with open(tr_path, "r", encoding="utf-8", errors="ignore") as f:
                    last_user_time = None
                    planner_idx = 0
                    for line in f:
                        try:
                            o = json.loads(line)
                            t = o.get("type")
                            ts = o.get("created_at")
                            if ts:
                                dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz)
                                if t == "USER_INPUT":
                                    last_user_time = dt
                                elif t == "PLANNER_RESPONSE":
                                    step_times[planner_idx] = dt
                                    if last_user_time:
                                        e_dur = (dt - last_user_time).total_seconds()
                                        if 0.5 <= e_dur <= 600.0:
                                            step_e2e_durs[planner_idx] = e_dur
                                        last_user_time = None
                                    planner_idx += 1
                        except Exception:
                            pass
            except Exception:
                pass

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT idx, data FROM gen_metadata ORDER BY idx ASC;")
            rows = cur.fetchall()

            sess_total_tokens = 0
            sess_in_tokens = 0
            sess_uncached_tokens = 0
            sess_cached_tokens = 0
            sess_out_tokens = 0
            sess_cost = 0.0
            sess_gen_dur = 0.0
            sess_e2e_dur = 0.0
            sess_models = collections.Counter()
            models_timeline = []
            cur_step_model = None
            sess_first_dt = None
            sess_last_dt = None

            for idx, data in rows:
                cur_dt = step_times.get(idx)
                if not cur_dt:
                    mtime = os.path.getmtime(db_path)
                    cur_dt = datetime.datetime.fromtimestamp(mtime, tz)

                if sess_first_dt is None or cur_dt < sess_first_dt:
                    sess_first_dt = cur_dt
                if sess_last_dt is None or cur_dt > sess_last_dt:
                    sess_last_dt = cur_dt

                d = cur_dt.date().isoformat()

                fields = decode_protobuf(data)
                for fnum, wtype, val in fields:
                    if fnum == 1 and wtype == 'bytes':
                        sub = decode_protobuf(val)
                        m_name = None
                        uncached_in = 0
                        cached_in = 0
                        out_tok = 0
                        reasoning_tok = 0
                        dur_sec = 0.0
                        stream_sec = 0.0

                        for sf_num, sf_type, sf_val in sub:
                            if sf_num == 19 and sf_type == 'bytes':
                                try:
                                    m_name = sf_val.decode('utf-8', errors='ignore')
                                except Exception:
                                    pass
                            elif sf_num == 4 and sf_type == 'bytes':
                                metrics = decode_protobuf(sf_val)
                                for mk, mt, mv in metrics:
                                    if mk == 2: uncached_in = mv
                                    elif mk == 3: out_tok = mv
                                    elif mk == 5: cached_in = mv
                                    elif mk == 9: reasoning_tok = mv
                            elif sf_num == 11 and sf_type == 'bytes':
                                d_arr = decode_protobuf(sf_val)
                                s, ns = 0, 0
                                for dk, dt, dv in d_arr:
                                    if dk == 1: s = dv
                                    elif dk == 2: ns = dv
                                dur_sec = s + ns / 1e9
                            elif sf_num == 12 and sf_type == 'bytes':
                                d_arr = decode_protobuf(sf_val)
                                s, ns = 0, 0
                                for dk, dt, dv in d_arr:
                                    if dk == 1: s = dv
                                    elif dk == 2: ns = dv
                                stream_sec = s + ns / 1e9

                        if not m_name:
                            m_name = "gemini-model"

                        in_tok = uncached_in + cached_in
                        tot_tok = in_tok + out_tok

                        # 计算该步预估费用
                        step_cost = calc_token_cost(m_name, uncached_in, cached_in, out_tok, 0)

                        # 流式阶段耗时计算: 若有原生流式记录则用之，否则依经验折扣 TTFT 首字等待
                        s_dur = stream_sec if stream_sec > 0.2 else (dur_sec * 0.85)

                        e2e_dur = step_e2e_durs.get(idx, 0.0)
                        if e2e_dur == 0.0 and dur_sec > 0:
                            e2e_dur = dur_sec

                        sess_total_tokens += tot_tok
                        sess_in_tokens += in_tok
                        sess_uncached_tokens += uncached_in
                        sess_cached_tokens += cached_in
                        sess_out_tokens += out_tok
                        sess_cost += step_cost
                        sess_gen_dur += dur_sec
                        sess_e2e_dur += e2e_dur
                        if m_name and m_name != "gemini-model":
                            sess_models[m_name] += 1
                            if m_name != cur_step_model:
                                models_timeline.append(m_name)
                                cur_step_model = m_name
                        elif m_name == "gemini-model":
                            sess_models[m_name] += 1

                        if d >= cutoff_date:
                            vals = {
                                "input_tokens": in_tok,
                                "uncached_tokens": uncached_in,
                                "cached_input_tokens": cached_in,
                                "cache_create_tokens": 0,
                                "output_tokens": out_tok,
                                "reasoning_output_tokens": reasoning_tok,
                                "total_tokens": tot_tok,
                            }
                            daily[d].update(vals)
                            daily[d]["turns"] += 1
                            daily_costs[d] += step_cost
                            daily_gen_durations[d] += dur_sec
                            if e2e_dur > 0:
                                daily_e2e_durations[d] += e2e_dur

                            models[(d, m_name)].update(vals)
                            models[(d, m_name)]["turns"] += 1
                            models_costs[(d, m_name)] += step_cost
                            models_gen_durations[(d, m_name)] += dur_sec
                            if e2e_dur > 0:
                                models_e2e_durations[(d, m_name)] += e2e_dur

                            card_key = (d, m_name)
                            model_sample_stats[card_key]["total_requests"] += 1
                            model_sample_stats[card_key]["total_output_tokens"] += out_tok
                            model_sample_stats[card_key]["sessions"].add(db_path)

                            if dur_sec > 0.2 and out_tok > 0:
                                model_sample_stats[card_key]["reliable_requests"] += 1
                                model_sample_stats[card_key]["reliable_output_tokens"] += out_tok
                                model_sample_stats[card_key]["sum_ttft_dur"] += dur_sec
                                model_sample_stats[card_key]["sum_stream_dur"] += s_dur

            if sess_total_tokens > 0:
                unique_models = []
                for m in models_timeline:
                    if m not in unique_models:
                        unique_models.append(m)

                disp_names = [AGY_MODEL_META.get(m, {}).get("display_name", m) for m in unique_models]

                if len(unique_models) == 0:
                    act_disp = "Unknown"
                    route_status = "[MATCH]"
                elif len(unique_models) == 1:
                    act_disp = disp_names[0]
                    m0 = unique_models[0].lower()
                    req_lower = client_req_model.lower()
                    if ("3.8" in req_lower and "3.8" in m0) or (m0 in req_lower) or req_lower.startswith("auto"):
                        route_status = "[MATCH]"
                    else:
                        route_status = "[REDIRECT]"
                else:
                    act_disp = " ➔ ".join(disp_names)
                    route_status = "[SWITCH]"

                tps = (sess_out_tokens / sess_gen_dur) if sess_gen_dur > 0 else 0.0
                e2e_tps = (sess_out_tokens / sess_e2e_dur) if sess_e2e_dur > 0 else 0.0

                mtime = os.path.getmtime(db_path)
                mtime_dt = datetime.datetime.fromtimestamp(mtime, tz)
                if not sess_last_dt or mtime_dt > sess_last_dt:
                    sess_last_dt = mtime_dt
                if not sess_first_dt:
                    sess_first_dt = sess_last_dt

                created_time_str = sess_first_dt.strftime("%m-%d %H:%M:%S")
                active_time_str = sess_last_dt.strftime("%m-%d %H:%M:%S")
                active_ts = sess_last_dt.timestamp()

                session_route_history.append({
                    "time": active_time_str if time_mode == "active" else created_time_str,
                    "active_time": active_time_str,
                    "created_time": created_time_str,
                    "active_ts": active_ts,
                    "session_id": (f"{app_tag} " if app_type == "merged" else "") + conv_id[:12],
                    "req_model": client_req_model,
                    "actual_model": act_disp,
                    "status": route_status,
                    "total_tokens": sess_total_tokens,
                    "in_tokens": sess_in_tokens,
                    "cached_tokens": sess_cached_tokens,
                    "cost": sess_cost,
                    "gen_tps": tps,
                    "e2e_tps": e2e_tps,
                })
        except Exception:
            pass
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    if not daily:
        print(f"近 {days_back} 天内未发现 Antigravity (Gemini) 本地会话记录。")
        return None

    banner_width = 118
    print("=" * banner_width)
    print(audit_title)
    print("=" * banner_width)

    for d in sorted(daily.keys()):
        stat = daily[d]
        d_cost = daily_costs[d]
        in_tok = stat["input_tokens"]
        cached_tok = stat["cached_input_tokens"]
        hit_rate = (cached_tok / in_tok * 100.0) if in_tok > 0 else 0.0

        d_gen_dur = daily_gen_durations[d]
        d_gen_tps = (stat["output_tokens"] / d_gen_dur) if d_gen_dur > 0 else 0.0
        d_e2e_dur = daily_e2e_durations[d]
        d_e2e_out_tps = (stat["output_tokens"] / d_e2e_dur) if d_e2e_dur > 0 else 0.0
        d_e2e_tot_tps = (stat["total_tokens"] / d_e2e_dur) if d_e2e_dur > 0 else 0.0

        print(f"\n[+] 日期 【{d}】 交互轮次: {stat['turns']} 轮 | 💰 预估费用: ${d_cost:.2f}")
        print(f"   |-- 总 Token 消耗:     {format_tokens(stat['total_tokens'])}")
        print(f"   |-- 提示词输入 (Prompt): {format_tokens(in_tok)}")
        print(f"   |   \\-- 缓存命中 Token:  {format_tokens(cached_tok)} | 🎯 上下文缓存命中率: {hit_rate:.2f}%")
        print(f"   \\-- 模型回答 (Output):   {format_tokens(stat['output_tokens'])} (其中思考消耗: {format_tokens(stat['reasoning_output_tokens'])})")
        print(f"       ├─ ⚡ 纯生成吐字速率 (Gen TPS):     {d_gen_tps:.1f} token/s  (模型纯推理吐字速度，对应社区实测)")
        print(f"       ├─ ⏱️ 端到端输出吐率 (E2E Out TPS): {d_e2e_out_tps:.1f} token/s  (含多轮交互、工具执行挂钟输出速度)")
        print(f"       └─ 🚀 端到端总吞吐率 (E2E Total):   {d_e2e_tot_tps:.1f} token/s  (含大上下文摄入与缓存全流程综合吞吐)")

        print("   [-] 实际路由模型细分与双维度速率对比:")
        for (m_date, m_slug), m_stat in sorted(models.items()):
            if m_date == d and m_stat["total_tokens"] > 0:
                tot_str = format_tokens(m_stat["total_tokens"])
                m_cst = models_costs[(m_date, m_slug)]
                m_in = m_stat["input_tokens"]
                m_cache = m_stat["cached_input_tokens"]
                m_hit_rate = (m_cache / m_in * 100.0) if m_in > 0 else 0.0

                m_gen_dur = models_gen_durations[(m_date, m_slug)]
                m_gen_tps = (m_stat["output_tokens"] / m_gen_dur) if m_gen_dur > 0 else 0.0

                m_e2e_dur = models_e2e_durations[(m_date, m_slug)]
                m_e2e_tps = (m_stat["output_tokens"] / m_e2e_dur) if m_e2e_dur > 0 else 0.0

                disp_name = AGY_MODEL_META.get(m_slug, {}).get("display_name", m_slug)
                label = f"{disp_name} ({m_slug})" if disp_name != m_slug else m_slug

                col_lbl = pad_cell(f"* {label}", 42, "left")
                col_trn = pad_cell(f"轮次: {m_stat['turns']:>4}", 12, "left")
                col_tot = pad_cell(f"总消耗: {tot_str}", 26, "left")
                col_cst = pad_cell(f"费用: {format_cost_cell(m_cst)}", 13, "left")
                col_hit = pad_cell(f"缓存率: {m_hit_rate:>5.1f}%", 15, "left")
                col_gen = pad_cell(f"纯吐率: {m_gen_tps:>5.1f} tok/s", 18, "left")
                col_e2e = pad_cell(f"端到端: {m_e2e_tps:>4.1f} tok/s", 18, "left")

                print(f"       {col_lbl} | {col_trn} | {col_tot} | {col_cst} | {col_hit} | {col_gen} | {col_e2e}")

    grand_total = collections.Counter()
    for s in daily.values():
        grand_total.update(s)

    grand_cost = sum(daily_costs.values())
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
    print(f"   * 💰 累计预估消费:     ${grand_cost:.2f} USD (折合约 ￥{grand_cost * 7.2:.2f} RMB)")
    print(f"   * 累计输入 Token:     {format_tokens(g_in)}")
    print(f"   * 累计缓存加速:       {format_tokens(g_cache)} | 🚀 总体缓存命中率: {g_hit_rate:.2f}%")
    print(f"   * 累计模型输出:       {format_tokens(grand_total['output_tokens'])} (深度思考推理消耗: {format_tokens(grand_total['reasoning_output_tokens'])})")
    print(f"   * ⚡ 全程纯生成吐字速率 (Gen TPS):     {g_gen_tps:.1f} token/s")
    print(f"   * ⏱️ 全程端到端输出吐率 (E2E Out TPS): {g_e2e_tps:.1f} token/s")
    print(f"   * 🚀 全程端到端总吞吐率 (E2E Total):   {g_tot_tps:.1f} token/s")
    print("=" * banner_width)

    # 渲染高保真日级模型消耗与消费成本审计表 (对齐用户专属格式)
    render_cost_table(daily, models, daily_costs, models_costs, AGY_MODEL_META, vendor_title=card_vendor)

    if show_recent_routes > 0 and session_route_history:
        time_col_title = "活跃时间 (UTC+8)" if time_mode == "active" else "创建时间 (UTC+8)"
        print(f"\n[*] 最近 {min(show_recent_routes, len(session_route_history))} 次交互会话实际路由与吐率追踪 (Session Route & Speed Audit):")
        cols_cfg = [
            (time_col_title, 14, "center"),
            ("Session ID", 18 if app_type == "merged" else 12, "center"),
            ("客户端请求模型", 26, "left"),
            ("服务端实际路由模型", 38, "left"),
            ("状态", 10, "center"),
            ("总Token消耗", 21, "right"),
            ("预估费用", 10, "right"),
            ("缓存率", 8, "right"),
            ("纯吐率", 11, "right"),
            ("端到端吐率", 11, "right"),
        ]

        header_str = " | ".join(pad_cell(title, w, align) for title, w, align in cols_cfg)
        sep_str = "-+-".join("-" * w for _, w, _ in cols_cfg)

        print(sep_str)
        print(header_str)
        print(sep_str)

        # 严格按最后活跃时间排序 (从旧到新)
        session_route_history.sort(key=lambda x: x["active_ts"])
        recent_sessions = session_route_history[-show_recent_routes:]
        for r in reversed(recent_sessions):
            tot_s = format_tokens(r["total_tokens"])
            cost_s = format_cost_cell(r.get("cost", 0.0))
            in_s = r["in_tokens"]
            c_s = r["cached_tokens"]
            rate = (c_s / in_s * 100.0) if in_s > 0 else 0.0
            gen_str = f"{r['gen_tps']:.1f} tok/s" if r['gen_tps'] > 0 else "--"
            e2e_str = f"{r['e2e_tps']:.1f} tok/s" if r['e2e_tps'] > 0 else "--"

            row_vals = [
                r["time"],
                r["session_id"],
                r["req_model"],
                r["actual_model"],
                r["status"],
                tot_s,
                cost_s,
                f"{rate:.1f}%",
                gen_str,
                e2e_str
            ]
            row_line = " | ".join(pad_cell(val, w, align) for val, (_, w, align) in zip(row_vals, cols_cfg))
            print(row_line)

        print(sep_str)
        time_meaning = (
            "会话最后一次响应输出的最新活跃时间 (默认方案A，时间严格递减；可用 --created 切换查看创建起源)"
            if time_mode == "active"
            else "会话首次创建与首次发起请求的时间 (当前通过 --created 参数指定展示)"
        )
        print("💡 指标物理定义说明:")
        print(f"   • [{time_col_title}]: {time_meaning}。")
        print("   • [纯生成吐率 (Gen TPS)]   : 扣除工具执行与等待后，模型纯输出推理吐字速率 (Output Tokens / API Latency)。")
        print("   • [端到端输出吐率 (E2E Out)]: 包含多轮思考、工具执行（命令/文件读写）挂钟时间的实际交付吐率。")
        print("   • [端到端总吞吐 (E2E Total)]: 包含庞大上下文摄入(几十万Prompt)与缓存加速的系统综合吞吐能力。")
        print("   • [预估费用 (Cost)]        : 基于 OpenAI / Google / Anthropic 官方阶梯定价与缓存折扣自动核算折算。")

    render_community_speed_card(daily, model_sample_stats, AGY_MODEL_META, tz, target_date_clean, target_model_arg, default_keyword="flash", vendor_title=card_vendor)
    print("=" * banner_width)
    grand_total["cost_usd"] = grand_cost
    return grand_total

# =========================================================================
# 命令行主入口
# =========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="统计本地 Codex / Antigravity (Gemini) 运行模型与 Token 消耗，追踪实际路由及纯生成/端到端吞吐率"
    )
    # 模式与数据源控制
    parser.add_argument(
        "--source",
        choices=["codex", "agy", "gemini", "antigravity", "ide", "antigravity-ide", "all"],
        default="codex",
        help="指定数据源: codex (默认), agy/antigravity (桌面独立端), ide/antigravity-ide (IDE端), gemini (全量合并), all (全量对比)"
    )
    parser.add_argument("--agy", action="store_true", help="快捷参数: 独立分析 Google Antigravity (桌面独立端) 会话")
    parser.add_argument("--antigravity", action="store_true", help="快捷参数: 独立分析 Google Antigravity (桌面独立端) 会话")
    parser.add_argument("--ide", action="store_true", help="快捷参数: 独立分析 Antigravity IDE (VS Code) 会话")
    parser.add_argument("--antigravity-ide", action="store_true", help="快捷参数: 独立分析 Antigravity IDE (VS Code) 会话")
    parser.add_argument("--agy-ide", action="store_true", help="快捷参数: 独立分析 Antigravity IDE (VS Code) 会话")
    parser.add_argument("--gemini", action="store_true", help="快捷参数: 汇总分析本地全部 Google Gemini / Antigravity 会话 (含独立端与IDE端)")
    parser.add_argument("--codex", action="store_true", help="快捷参数: 独立分析 OpenAI Codex 会话")
    parser.add_argument("--all", action="store_true", help="快捷参数: 同时分析并对比 Codex、Antigravity 独立端与 IDE 端")

    # 过滤与展示参数
    parser.add_argument("--days", type=int, default=7, help="查看最近几天的数据 (默认 7 天)")
    parser.add_argument("--routes", type=int, default=10, help="展示最近 N 次会话的路由追踪明细 (默认 10)")
    parser.add_argument("--date", type=str, default=None, help="指定卡片生成的特定日期 (支持 2026-09-30, 20260930, 0930, 30)")
    parser.add_argument("--model", type=str, default=None, help="指定卡片展示的目标模型 (如 gemini-3.8-flash 或 gpt-6.1-sol)")
    parser.add_argument(
        "--created", "--show-created",
        action="store_true",
        help="切换会话追踪表时间列为【会话首次创建时间】(默认方案A为【最新活跃时间】，时间严格单调递减)"
    )
    parser.add_argument(
        "--time-mode",
        choices=["active", "created"],
        default="active",
        help="指定会话追踪表的时间展示维度: active (默认，显示最后活跃时间，单调递减) 或 created (显示首次创建时间)"
    )

    args = parser.parse_args()

    time_mode = "created" if (args.created or args.time_mode == "created") else "active"

    # 判定最终数据源 (显式指定参数 > 全量模式 > 默认 codex)
    if args.all or args.source == "all":
        chosen_source = "all"
    elif args.ide or args.antigravity_ide or args.agy_ide or args.source in ("ide", "antigravity-ide"):
        chosen_source = "ide"
    elif args.agy or args.antigravity or args.source in ("agy", "antigravity"):
        chosen_source = "agy"
    elif args.gemini or args.source == "gemini":
        chosen_source = "gemini"
    elif args.codex:
        chosen_source = "codex"
    else:
        chosen_source = args.source

    if chosen_source == "ide":
        get_antigravity_stats(
            days_back=args.days,
            show_recent_routes=args.routes,
            target_date_arg=args.date,
            target_model_arg=args.model,
            app_type="ide",
            time_mode=time_mode
        )
    elif chosen_source == "agy":
        get_antigravity_stats(
            days_back=args.days,
            show_recent_routes=args.routes,
            target_date_arg=args.date,
            target_model_arg=args.model,
            app_type="standalone",
            time_mode=time_mode
        )
    elif chosen_source == "gemini":
        get_antigravity_stats(
            days_back=args.days,
            show_recent_routes=args.routes,
            target_date_arg=args.date,
            target_model_arg=args.model,
            app_type="merged",
            time_mode=time_mode
        )
    elif chosen_source == "codex":
        get_codex_stats(
            days_back=args.days,
            show_recent_routes=args.routes,
            target_date_arg=args.date,
            target_model_arg=args.model,
            time_mode=time_mode
        )
    elif chosen_source == "all":
        print("\n" + "#" * 118)
        print("# [1/3] 正在分析 OpenAI Codex 本地运行审计...")
        print("#" * 118)
        codex_tot = get_codex_stats(
            days_back=args.days,
            show_recent_routes=args.routes,
            target_date_arg=args.date,
            target_model_arg=args.model,
            time_mode=time_mode
        )

        print("\n" + "#" * 118)
        print("# [2/3] 正在分析 Google Antigravity (桌面独立端) 本地运行审计...")
        print("#" * 118)
        agy_tot = get_antigravity_stats(
            days_back=args.days,
            show_recent_routes=args.routes,
            target_date_arg=args.date,
            target_model_arg=args.model,
            app_type="standalone",
            time_mode=time_mode
        )

        print("\n" + "#" * 118)
        print("# [3/3] 正在分析 Google Antigravity IDE (VS Code) 本地运行审计...")
        print("#" * 118)
        ide_tot = get_antigravity_stats(
            days_back=args.days,
            show_recent_routes=args.routes,
            target_date_arg=args.date,
            target_model_arg=args.model,
            app_type="ide",
            time_mode=time_mode
        )

        print("\n" + "=" * 118)
        print("[*] 📊 多助手全量横向综合对比 (OpenAI Codex vs Antigravity Standalone vs Antigravity IDE):")
        print("=" * 118)
        c_tot = codex_tot["total_tokens"] if codex_tot else 0
        c_trn = codex_tot["turns"] if codex_tot else 0
        c_cst = codex_tot.get("cost_usd", 0.0) if codex_tot else 0.0
        a_tot = agy_tot["total_tokens"] if agy_tot else 0
        a_trn = agy_tot["turns"] if agy_tot else 0
        a_cst = agy_tot.get("cost_usd", 0.0) if agy_tot else 0.0
        i_tot = ide_tot["total_tokens"] if ide_tot else 0
        i_trn = ide_tot["turns"] if ide_tot else 0
        i_cst = ide_tot.get("cost_usd", 0.0) if ide_tot else 0.0

        print(f"  * 总 Token 吞吐:   Codex: {format_tokens(c_tot)} | AGY桌面端: {format_tokens(a_tot)} | AGY-IDE端: {format_tokens(i_tot)}")
        print(f"  * 预估费用折算:   Codex: ${c_cst:.2f} | AGY桌面端: ${a_cst:.2f} | AGY-IDE端: ${i_cst:.2f}")
        print(f"  * 对话总轮次:     Codex: {c_trn:,} 轮 | AGY桌面端: {a_trn:,} 轮 | AGY-IDE端: {i_trn:,} 轮")
        print("=" * 118)
