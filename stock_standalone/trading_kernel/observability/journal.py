from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    if hasattr(obj, "keys") and hasattr(obj, "__getitem__"):
        try:
            return obj[key]
        except Exception:
            pass
    return default


class JsonlJournal:
    def __init__(self, path: str = "logs/trading_kernel_trace.jsonl"):
        self.path = path
        self._lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
            
        # 维护一个当天已记录特征集合，用于精准去重
        self._written_records = set()
        if os.path.exists(self.path) and os.path.getsize(self.path) > 0:
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                with open(self.path, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-5000:]  # 快速读取最后 5000 行，提取今日信号防重
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            # 同时检查 journal_ts 或新增的 trade_date
                            ts = data.get("trade_date", "") or data.get("journal_ts", "")
                            if ts and ts.startswith(today_str):
                                sig = data.get("signal", {})
                                code = _safe_get(sig, "code")
                                sig_type = _safe_get(sig, "signal_type")
                                action = data.get("kernel_result", {}).get("kernel_action", "")
                                if code:
                                    is_sim = data.get("is_simulation", False)
                                    if is_sim:
                                        self._written_records.add((code, "SIMULATION"))
                                    elif sig_type:
                                        self._written_records.add((code, sig_type, action))
                        except Exception:
                            continue
            except Exception:
                pass

    def append(self, record: dict[str, Any]) -> None:
        payload = dict(record)
        
        # 支持审计类日志（如 HUMAN_CONFIRMATION_AUDIT, POSITION_SYNC_AUDIT）直接写入而不受 code 过滤与去重限制
        jtype = payload.get("journal_type")
        if jtype is not None and "AUDIT" in str(jtype):
            now_dt = datetime.now()
            payload["trade_date"] = now_dt.strftime("%Y-%m-%d")
            payload.setdefault("journal_ts", now_dt.isoformat(timespec="seconds"))
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(_to_plain(payload), ensure_ascii=False, sort_keys=True) + "\n")
            return

        sig = payload.get("signal", {})
        code = _safe_get(sig, "code")
        sig_type = _safe_get(sig, "signal_type")
        action = _safe_get(payload.get("kernel_result", {}), "kernel_action", "")

        if not code:
            # 没有股票代码，直接过滤忽略
            return

        # 引入标准交易时间工具 (支持打包及各种环境的 Fallback 级联导入)
        try:
            from JohnsonUtil import commonTips as cct
        except ImportError:
            try:
                import commonTips as cct
            except ImportError:
                import common as cct

        # 计算当前是否在交易活跃期 (交易日且 09:15-11:30 或 13:00-15:05)
        is_trade_day = cct.get_trade_date_status()
        now_dt = datetime.now()
        now_time = now_dt.hour * 100 + now_dt.minute
        is_active_trading = is_trade_day and ((915 <= now_time <= 1130) or (1300 <= now_time <= 1505))
        today_str = now_dt.strftime("%Y-%m-%d")

        if not is_active_trading:
            # 其余时间执行都是模拟信号，标注 simulation 属性
            payload["is_simulation"] = True
            if "kernel_result" in payload and payload["kernel_result"] is not None:
                if isinstance(payload["kernel_result"], dict):
                    payload["kernel_result"]["is_simulation"] = True
                    if "kernel_reason" in payload["kernel_result"] and isinstance(payload["kernel_result"]["kernel_reason"], dict):
                        payload["kernel_result"]["kernel_reason"]["simulation"] = True

            # 模拟时段去重：同一个 code，只允许记录一次模拟信号
            key = (code, "SIMULATION")
            with self._lock:
                if key in self._written_records:
                    return
                self._written_records.add(key)
        else:
            # 交易活跃期去重：同一个 code，同一个信号类型，同一种动作，只允许记录一次
            if not sig_type:
                return
            key = (code, sig_type, action)
            with self._lock:
                if key in self._written_records:
                    return
                self._written_records.add(key)

        # 显式加入交易日 trade_date 字段和 journal_ts 字段，保障数据一致性与可追溯性
        payload["trade_date"] = today_str
        payload.setdefault("journal_ts", now_dt.isoformat(timespec="seconds"))
        
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(_to_plain(payload), ensure_ascii=False, sort_keys=True) + "\n")


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


