"""Short, consistent Chinese labels for stable machine-readable states."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


LRRM_STATE_CN_MAP: Mapping[str, str] = MappingProxyType({
    "LOOSE": "充裕宽松 🟢",
    "NORMAL": "平稳中性 ⚪",
    "TIGHT": "流动紧缩 🟡",
    "SHOCK": "休克熔断 🔴",
    "UNKNOWN": "数据未就绪 ⚠️",
})

IPO_REGIME_CN_MAP: Mapping[str, str] = MappingProxyType({
    "REPAIR": "修复蓄势 🟡",
    "CONTINUATION": "主升共振 🟢",
    "MANIA": "高潮过热 🟣",
    "EXHAUSTION": "动能衰竭 🟠",
    "DISTRIBUTION": "退潮派发 🔴",
    "UNKNOWN": "样本未就绪 ⚠️",
})

T1_CARRY_STATE_CN_MAP: Mapping[str, str] = MappingProxyType({
    "ALLOW": "允许隔夜 🟢",
    "CAUTION": "谨慎待命 🟡",
    "BLOCK": "严禁隔夜 🔴",
    "UNKNOWN": "待评估 ⚠️",
})

GATE_DECISION_CN_MAP: Mapping[str, str] = MappingProxyType({
    "ENTRY": "准入开仓 🟢",
    "WATCH": "重点观察 🟡",
    "BLOCK": "一票否决 🔴",
})

VETO_REASON_CN_MAP: Mapping[str, str] = MappingProxyType({
    "LRRM_MISSING": "宏观数据缺失",
    "LRRM_SHOCK": "全市场流动性休克",
    "LRRM_TIGHT": "全市场流动性紧缩",
    "REGIME_MISSING": "板块周期未就绪",
    "REGIME_DISTRIBUTION": "次新板块处于退潮期",
    "REGIME_EXHAUSTION": "次新板块动能衰竭",
    "T1_CARRY_PSEUDO_STRENGTH": "命中华大海天伪强派发",
    "T1_CARRY_EXTREME": "动能极端过热",
    "T1_CARRY_SCORE_LOW": "隔夜兑现评分不足",
    "ANCHOR_LOW_BREACHED": "跌破首日最低价双锚",
    "ANCHOR_OPEN_BREACHED": "跌破首日开盘价双锚",
    "ANCHOR_D0_BREAK": "跌破首日开盘或发行价",
    "ANCHOR_MISSING": "首日封存锚点缺失",
    "VWAP_STALE": "VWAP 行情过期未同步",
    "VWAP_BREACHED": "跌破当日均线超 1.5%",
    "VWAP_INCOMPLETE": "VWAP 多日结构不完整",
    "TDE_NO_PLAN": "缺少通道突破交易计划",
    "TDE_PRICE_TOO_HIGH": "现价超出买入上限防追高",
    "TDE_PRICE_TOO_LOW": "现价低于买入区间下限",
    "TDE_RR_TOO_LOW": "盈亏比不足 2.5:1",
    "TDE_NOT_LEADER": "非领头羊排位待命",
    "RISK_OVER_EXPOSURE": "超出个股/板块风控限额",
    "RISK_DRAWDOWN_CUT": "回撤超限风控拒绝",
})

LIFE_CYCLE_CN_MAP: Mapping[str, str] = MappingProxyType({
    "OBSERVE": "盘前观察 🔭",
    "ARMED": "就绪待命 🎯",
    "ENTRY_READY": "准入开仓 ⚡",
    "ENTERED": "持仓确认 💼",
    "HOLD_T1": "隔夜锁仓 🔒",
    "EXIT_READY": "待平仓 🚨",
    "BLOCKED": "硬阻断 ⛔",
})

ANCHOR_STATUS_CN_MAP: Mapping[str, str] = MappingProxyType({
    "SAFE": "守住双锚 🛡️",
    "BREACHED": "双锚失守 ⚠️",
    "D0_SUPPORT": "首日支撑有效 🟢",
    "D0_BROKEN": "首日破发/破开 🔴",
    "RECLAIMED": "快速回收 (待次日观察)",
})


def display_label(
    mapping: Mapping[str, str],
    code: Any,
    fallback: str = "未知",
) -> str:
    """Map known codes to labels while leaving the raw code to the caller."""
    if not isinstance(code, str) or not code:
        return fallback
    return mapping.get(code, fallback)
