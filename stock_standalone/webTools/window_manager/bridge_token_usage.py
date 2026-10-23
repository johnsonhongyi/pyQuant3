"""Shared, compact token display and read-only AGV bridge accounting."""
from contextlib import closing
from datetime import datetime, timedelta
import sqlite3


def format_token_count(value):
    if type(value) is not int or value < 0:
        return "未采集"
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} 百万"
    if value >= 10_000:
        return f"{value / 10_000:.2f} 万"
    return f"{value:,}"


def token_usage_text(tokens):
    if not tokens or not tokens.get("available"):
        return "暂无已采集的真实 Token 用量记录。"
    lines = []
    for key, label in (("today", "今日"), ("week", "近 7 日")):
        bucket = tokens.get(key) or {}
        fields = " / ".join(f"{name} {format_token_count(bucket.get(field))}"
            for field, name in (("input", "输入"), ("cached", "缓存"), ("output", "输出")))
        text = f"{label}：{format_token_count(bucket.get('total'))} tokens（{fields}，{bucket.get('turns', 0)} 轮）"
        if bucket.get("input") and type(bucket.get("cached")) is int:
            text += f" · 缓存占输入 {bucket['cached'] / bucket['input'] * 100:.1f}%"
        lines.append(text)
    return "\n".join(lines)


def agv_token_counts(path, now=None):
    now = now or datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    week = (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)).timestamp()
    empty = lambda: {"input": None, "cached": None, "output": None, "total": None, "turns": 0}
    result = {"available": False, "today": empty(), "week": empty()}
    if not path.is_file():
        return result
    try:
        try:
            db_uri = path.resolve().as_uri() + "?mode=ro"
        except (OSError, RuntimeError):
            db_uri = path.absolute().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(db_uri, uri=True, timeout=1)) as db:
            for table in ("chat_results", "results"):
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                if not {"result", "created_at"}.issubset(columns):
                    continue
                # Project only counters: never load prompts or full reports into the UI.
                rows = db.execute(f"""SELECT created_at,
                    json_extract(result, '$.token_usage.inputTokens'),
                    json_extract(result, '$.token_usage.cachedInputTokens'),
                    json_extract(result, '$.token_usage.outputTokens'),
                    json_extract(result, '$.token_usage.totalTokens')
                    FROM {table} WHERE created_at>=? AND json_valid(result)""", (week,))
                for stamp, *values in rows:
                    if not any(type(v) is int and v >= 0 for v in values):
                        continue
                    result["available"] = True
                    for key in ("week", "today") if stamp >= today else ("week",):
                        bucket = result[key]
                        bucket["turns"] += 1
                        for field, value in zip(("input", "cached", "output", "total"), values):
                            if type(value) is int and value >= 0:
                                bucket[field] = (bucket[field] or 0) + value
        return result
    except (sqlite3.Error, OSError, ValueError):
        return {"available": False, "error": "用量账本暂不可读"}
