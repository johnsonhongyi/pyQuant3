# -*- coding: utf-8 -*-
"""Versioned, fixed prompts approved for outbound IPO Agent requests."""

from __future__ import annotations

from typing import Any

from ats.llm.remote_sanitizer import RemoteEgressError


MARKET_REGIME_PROMPT_VERSION = "r9.market-regime.v2"
MARKET_REGIME_PROMPT = (
    "你是只读的新股情绪分析 Agent。只依据所附截止时点的已验证快照做辅助归纳；"
    "不得引入截止时间之后的信息，不得给出交易指令，也不得修改规则、标签或模型。"
    "必须输出 sentiment_score、stage_hint、catalysts、risk_warnings 四个字段；"
    "stage_hint 只能是 NEUTRAL/PANIC/REPAIR/REVERSAL/FOMO/COOLDOWN。"
    "每个 catalyst/risk_warnings 条目包含 summary 与 evidence_ids，引用 context.snapshot_hash。"
    "若规则结论为 BLOCK 或宏观指标缺失，不得编造催化；score=50、stage_hint=NEUTRAL、"
    "catalysts=[]，并在 risk_warnings 写明数据不足/门禁阻断及证据哈希。"
    "只输出一个 JSON 对象，禁止 Markdown 代码围栏、说明文字或额外字段；"
    "所有必需字段都必须出现，输出必须严格符合给定 JSON Schema。"
)

_APPROVED_PROMPTS = {
    ("MARKET_REGIME", MARKET_REGIME_PROMPT_VERSION): MARKET_REGIME_PROMPT,
}


def build_approved_remote_prompt(
    agent_type: Any,
    prompt_version: Any,
    supplied_prompt: Any,
    safe_context_json: Any,
) -> str:
    """Reject caller-controlled prompt text and compose only approved inputs."""
    if not isinstance(agent_type, str) or not isinstance(prompt_version, str):
        raise RemoteEgressError("remote prompt identity is invalid")
    template = _APPROVED_PROMPTS.get((agent_type, prompt_version))
    if template is None or supplied_prompt != template:
        raise RemoteEgressError("remote prompt is not an approved versioned template")
    if not isinstance(safe_context_json, str) or not safe_context_json:
        raise RemoteEgressError("remote prompt context is not a sanitized projection")
    return (
        template
        + "\n\n仅使用本次获准投影的上下文(JSON)：\n"
        + safe_context_json
    )
