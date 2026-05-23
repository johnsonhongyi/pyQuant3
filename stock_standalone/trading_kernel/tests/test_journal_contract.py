# -*- coding: utf-8 -*-
import os
import json
import pytest
from datetime import datetime
from trading_kernel.observability.journal import JsonlJournal


def test_journal_payload_and_ui_unpacking(tmp_path):
    """验证 JsonlJournal 的数据持久化契约以及 UI 解析解包的健壮性"""
    log_file = tmp_path / "test_kernel_trace.jsonl"
    journal = JsonlJournal(path=str(log_file))

    # 1. 模拟一个完整的交易内核决策记录 (包括 nested dict 结构)
    test_record = {
        "trace": {
            "trace_id": "8a604516-a57d-4d96-b540-d0ab7dc98bf9",
            "timestamp": datetime.now().isoformat(),
            "state": "FLAT"
        },
        "signal": {
            "code": "600519",
            "name": "贵州茅台",
            "signal_type": "BREAKOUT",
            "features": {
                "is_leader": True,
                "priority": 8.5,
                "raw_reason": "突破年线"
            }
        },
        "intent": {
            "confidence": 0.95,
            "stop_price": 1650.50,
            "reason": "突破阻力位"
        },
        "risk": {
            "final_action": "BUY",
            "final_size_pct": 15.0,
            "allowed": True,
            "reject_context": {}
        },
        "kernel_reason": {
            "is_breakout": True,
            "simulation": False
        }
    }

    # 2. 写入日志
    journal.append(test_record)

    # 3. 核验物理文件写入与字段对齐
    assert log_file.exists()
    
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        written_data = json.loads(lines[0])
        
        # 核验字段注入
        assert "trade_date" in written_data
        assert "journal_ts" in written_data
        assert written_data["signal"]["code"] == "600519"
        assert written_data["risk"]["final_action"] == "BUY"

    # 4. 模拟 UI 扁平化数据解包提取算法 (对齐 decision_flow_panel.py 中的 _append_record_to_table)
    rec = written_data
    
    # 模拟时间解析
    ts_str = rec.get("journal_ts", "")
    assert ts_str != ""
    time_part = ts_str.split("T")[1] if "T" in ts_str else ts_str
    timestamp = time_part[:8]
    assert len(timestamp) == 8

    # 模拟字段提取
    sig = rec.get("signal", {})
    trace = rec.get("trace", {})
    intent = rec.get("intent", {})
    risk = rec.get("risk", {})

    code = sig.get("code", "")
    name = sig.get("name", "")
    state = rec.get("kernel_state", "") or trace.get("state", "FLAT")
    action = rec.get("kernel_action", "") or risk.get("final_action", "")
    size_val = rec.get("kernel_size_pct", 0.0) or risk.get("final_size_pct", 0.0)
    size_pct = f"{float(size_val):.1f}%"
    confidence = str(rec.get("kernel_confidence", "") or intent.get("confidence", ""))
    allowed_val = risk.get("allowed", True)
    risk_allowed = "Allowed" if allowed_val else "Blocked"
    stop_price_val = rec.get("kernel_stop_price", 0.0) or intent.get("stop_price", 0.0)
    stop_price = f"{float(stop_price_val):.2f}"
    trace_id = trace.get("trace_id", "")
    short_trace_id = trace_id[:8]

    # 核验数据契约提取的准确性
    assert code == "600519"
    assert name == "贵州茅台"
    assert state == "FLAT"
    assert action == "BUY"
    assert size_pct == "15.0%"
    assert confidence == "0.95"
    assert risk_allowed == "Allowed"
    assert stop_price == "1650.50"
    assert short_trace_id == "8a604516"

    # 模拟理由摘要构建
    features = sig.get("features", {})
    is_leader = features.get("is_leader", False)
    priority = features.get("priority", 0.0)
    raw_reason = features.get("raw_reason", "")
    
    reason_parts = []
    if is_leader:
        reason_parts.append("⭐龙头领涨")
    if priority and priority > 0:
        reason_parts.append(f"强度:{priority}")
        
    kernel_reason = rec.get("kernel_reason", {})
    for r_k, r_v in kernel_reason.items():
        if r_v and str(r_v).strip().lower() != "false":
            reason_parts.append(f"{r_k}={r_v}")
            
    if raw_reason:
        reason_parts.append(raw_reason)
        
    reason_summary = " | ".join(reason_parts)
    
    assert "⭐龙头领涨" in reason_summary
    assert "强度:8.5" in reason_summary
    assert "突破年线" in reason_summary
    assert "is_breakout=True" in reason_summary
