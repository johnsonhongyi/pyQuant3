from __future__ import annotations

import math

from trading_kernel.core.intent import DecisionIntent, DecisionReason
from trading_kernel.core.signal import StrategySignal


def _num(signal: StrategySignal, key: str, default: float = 0.0) -> float:
    try:
        return float(signal.features.get(key, default))
    except Exception:
        return default


def _confidence(priority: float, sector_heat: float, pct_diff: float, dff: float) -> float:
    score = 0.0
    score += min(max(priority, 0.0), 100.0) * 0.004
    score += min(max(sector_heat, 0.0), 100.0) * 0.003
    score += min(max(pct_diff, 0.0), 8.0) * 0.025
    score += min(max(dff, 0.0), 8.0) * 0.0125
    return round(min(max(score, 0.0), 0.95), 4)


def decide(signal: StrategySignal, state: str) -> DecisionIntent:
    # ── 手工干预或强制平仓与买入逻辑，直接走绿色通道无条件执行 ──
    raw_action = str(signal.features.get("action", "")).upper()
    is_manual_sell = (raw_action == "SELL" or signal.signal_type == "手工平仓" or "手工平仓" in str(signal.features.get("raw_reason", "")))
    is_manual_buy = (raw_action in {"BUY", "ADD"} and (signal.signal_type == "手动买入" or "手动买入" in str(signal.features.get("raw_reason", "")) or "Confirm:" in str(signal.features.get("raw_reason", ""))))
    
    if is_manual_sell or is_manual_buy:
        action = "BUY" if is_manual_buy else "SELL"
        reason = DecisionReason(
            regime="MANUAL_OVERRIDE",
            setup="手动交易" if is_manual_buy else "手工平仓",
            sector_heat=0.0,
            sector_rank=None,
            is_leader=False,
            breakout=False,
            volume_ratio=1.0,
            dff=0.0,
            dff_positive=False,
            price_above_vwap=True,
            confidence_inputs=(),
        )
        return DecisionIntent(
            code=signal.code,
            action=action,
            size_pct=0.30 if action == "BUY" else 1.0,  # 手工买入默认为30%仓位，卖出100%全平
            stop_price=round(signal.price * 0.98, 3) if action == "BUY" and signal.price > 0 else None,
            confidence=1.0,
            reason=reason,
            expires_at=signal.ts,
        )

    priority = _num(signal, "priority")
    sector_heat = _num(signal, "sector_heat")
    pct_diff = _num(signal, "pct_diff")
    dff = _num(signal, "dff")
    price = signal.price
    suggest_price = _num(signal, "suggest_price", price)
    volume_ratio = max(1.0, _num(signal, "hits", 1.0))
    breakout = pct_diff > 0.3 or "BREAKOUT" in signal.signal_type.upper()
    dff_positive = dff > 0
    is_leader = bool(signal.features.get("is_leader", False))
    regime = "BREAKOUT_ALLOWED" if sector_heat >= 20 and priority >= 50 else "WATCH_ONLY"
    # ── 如果是持仓状态，允许从 features 继承当前的持仓类型 (如 SWING_LOW_BUY) ──
    if state == "IN_TRADE":
        inherited_regime = signal.features.get("regime")
        if inherited_regime:
            regime = inherited_regime
    setup = signal.signal_type or "UNKNOWN"
    
    # ── [NEW] 多周期枢轴右侧自愈 Re-entry 激活判定 ──
    is_reentry = False
    reentry_reason_str = ""
    reentry_boost = 1.0
    try:
        from trading_kernel.engine.reentry_tracker import reentry_tracker
        # 组装用于判定特征字典
        feat_dict = {
            "close": price,
            "high4": _num(signal, "high4"),
            "hmax": _num(signal, "hmax"),
            "low60": _num(signal, "low60"),
            "pbreak": int(_num(signal, "pbreak", 0)),
            "ptop": _num(signal, "ptop"),
            "dff": dff,
            "vol_ratio_5d": volume_ratio
        }
        activated, r_reason, r_boost = reentry_tracker.check_activation(signal.code, feat_dict, current_time_str=signal.ts)
        if activated:
            is_reentry = True
            reentry_reason_str = r_reason
            reentry_boost = r_boost
            regime = "BREAKOUT_ALLOWED" # 强行升级为允许买入状态
            setup = f"RE_ENTRY:{setup}"
    except Exception:
        pass

    confidence = _confidence(priority, sector_heat, pct_diff, dff)
    if is_reentry:
        confidence = min(0.95, round(confidence * reentry_boost, 4))

    action = "HOLD"
    size_pct = 0.0

    # ── [NEW] 龙头回踩低吸与大格局突破分批止盈/T+2时间风控特征提取 ──
    vol_shrink_3d = bool(signal.features.get("vol_shrink_3d", False))
    is_pullback_support = bool(signal.features.get("is_pullback_support", False))
    is_collecting_stage = bool(signal.features.get("is_collecting_stage", False))
    is_consolidation_stage = bool(signal.features.get("is_consolidation_stage", False))
    is_doji = bool(signal.features.get("is_doji", False))
    upper = float(_num(signal, "upper", 0.0))
    max_pnl_since_entry = float(_num(signal, "max_pnl_since_entry", 0.0))
    days_held = int(_num(signal, "days_held", 0.0))
    pnl_pct = float(_num(signal, "pnl_pct", 0.0))
    pbreak = int(_num(signal, "pbreak", 0))
    ptop = _num(signal, "ptop", 0.0)
    sws = float(_num(signal, "sws", 0.0))
    sws_prev5 = float(_num(signal, "sws_prev5", 0.0))
    swl = float(_num(signal, "swl", 0.0))
    low_price = float(_num(signal, "low", 0.0))
    ma10d = float(_num(signal, "ma10d", 0.0))
    ma10d_prev5 = float(_num(signal, "ma10d_prev5", 0.0))

    # 提取爆量换手特征
    vol_val = float(_num(signal, "volume", 0.0))
    vol_ma5_val = float(_num(signal, "vol_ma5", 0.0))
    vol_ratio = vol_val / vol_ma5_val if vol_ma5_val > 0 else 1.0

    # 1. 开仓/加仓买入逻辑
    if state in {"FLAT", "ARMED"}:
        if vol_shrink_3d and is_pullback_support and is_doji:
            # 必须满足筹码收集期触摸 Upper 回踩 SWS，或者大涨派发后的回落洗盘 SWS 整固
            if is_collecting_stage or is_consolidation_stage:
                action = "BUY"
                size_pct = 0.30
                regime = "SWING_LOW_BUY"
                setup = "SWS_COLLECT_PULLBACK" if is_collecting_stage else "SWS_CONSOLIDATE_PULLBACK"
                confidence = 0.88
                suggest_price = price
        
        # 👑 新增：主升浪沿 MA10 爬升企稳低吸买入规则 (TREND_FOLLOW_BUY)
        # 爬升趋势：MA10 每一天都比前几天高，或者 5 天前的 MA10 增长明显；MA5 > SWS 支撑；资金流 dff > 0 配合。
        # 沿线整理回踩：最低价踩在 MA10 附近，但收盘价稳立 MA10 之上，且今日并未大爆量出货。
        if action == "HOLD":
            ma10_val = ma10d if ma10d > 0.0 else sws
            ma10_prev5_val = ma10d_prev5 if ma10d_prev5 > 0.0 else sws_prev5
            
            is_ma10_climbing = (ma10_prev5_val > 0.0 and ma10_val >= ma10_prev5_val * 1.005)
            is_ma10_pullback = (low_price > 0.0 and ma10_val > 0.0 and low_price <= ma10_val * 1.015) and (price >= ma10_val * 0.99)
            is_vol_ok = (vol_val > 0.0 and vol_val < vol_ma5_val * 1.05)
            # 趋势判定：真正的 SWL/ma10d 在 SWS 之上有趋势情况，或者经典 5日均线 > 10日均线多头排列
            ma5_val = float(_num(signal, "ma5d", 0.0))
            if ma5_val <= 0.0:
                ma5_val = swl if swl > 0.0 else price
            
            is_trend_ok = (swl > sws) or (ma10_val > sws) or (ma5_val > ma10_val)
            
            if is_ma10_climbing and is_ma10_pullback and is_vol_ok and is_trend_ok and (is_doji or vol_shrink_3d):
                action = "BUY"
                size_pct = 0.30
                regime = "SWING_LOW_BUY"
                setup = "MA10_TREND_FOLLOW"
                confidence = 0.85
                suggest_price = price

        if action == "HOLD" and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
            action = "BUY"
            if is_reentry:
                size_pct = 0.40 if confidence < 0.75 else 0.50
            else:
                size_pct = 0.30 if confidence < 0.75 else 0.40

    # 2. 持仓/平仓减仓风控逻辑
    elif state == "IN_TRADE":
        # 👑 爆量大涨派发止盈：向上强力突破通道天花板或大平台顶，已实现 5% 以上浮盈，且必须爆量（vol_ratio >= 1.4代表筹码高位剧烈换手主力派发）
        is_breakout_tp = (pbreak == 1 or (ptop > 0 and price >= ptop * 1.01)) and pnl_pct >= 5.0 and vol_ratio >= 1.4
        
        # 👑 放量在 upper 附近不冲关止盈判定
        is_upper_vol_tp = False
        if upper > 0.0:
            if price >= upper * 0.97 and vol_ratio >= 1.2 and pbreak == 0 and pnl_pct >= 2.0:
                is_upper_vol_tp = True

        # T+2 时间保护锁风控：若持仓满 2 个交易日且账面浮盈不及预期 (< 3%)，冲高出局
        is_time_failsafe = (days_held >= 2 and pnl_pct < 3.0)

        # 👑 企稳不加速就逢高出局 (低吸持仓，T+2，最高浮盈从未超过 6.0%)
        is_weak_no_accelerate = False
        tp_triggered = bool(signal.features.get("tp_triggered", False))
        is_swing_low_mode = bool(signal.features.get("is_swing_low_mode", False))
        if (is_swing_low_mode or regime == "SWING_LOW_BUY") and days_held >= 2 and max_pnl_since_entry < 6.0:
            is_weak_no_accelerate = True

        # 👑 爆量大跌崩溃平仓：高位大跌且伴随爆量（回吐大于 3.0% 且 vol_ratio >= 1.4），强制 100% 物理清仓
        is_volume_breakdown = (pct_diff < -3.0) and vol_ratio >= 1.4

        # 💡 黄金低吸回补仓位 (Re-entry Add Back 70%) 判定：
        # 如果已经大止盈减仓过 (tp_triggered)，且当前属于低吸持仓模式 (is_swing_low_mode)
        # 并且股价多日回落到 SWS 附近 (low_price <= sws * 1.015 且 close >= sws * 0.985 守稳不破)
        # 且成交量明显萎缩 (vol_ratio < 0.95)
        low_val = _num(signal, "low", price)
        sws_val = _num(signal, "sws", 0.0)
        is_add_back = False
        if tp_triggered and (is_swing_low_mode or regime == "SWING_LOW_BUY") and sws_val > 0:
            if low_val <= sws_val * 1.015 and price >= sws_val * 0.985 and vol_ratio < 0.95:
                is_add_back = True

        if is_breakout_tp or is_upper_vol_tp:
            action = "SELL"  # 用 SELL 配合 size_pct=0.70 代表分批止盈 70% 仓位
            size_pct = 0.70
            regime = "TAKE_PROFIT_TRIGGERED"
            setup = "UPPER_VOL_TP" if is_upper_vol_tp else "BREAKOUT_TAKE_PROFIT"
            confidence = 0.90
        elif is_weak_no_accelerate:
            action = "SELL"
            size_pct = 1.00
            regime = "WEAK_NO_ACCELERATE"
            setup = "不加速_平仓避险"
            confidence = 0.95
        elif is_add_back:
            action = "ADD"
            size_pct = 0.70
            regime = "SWING_LOW_BUY"
            setup = "SWS_ADD_BACK"
            confidence = 0.88
        elif is_time_failsafe:
            action = "SELL"
            size_pct = 1.00
            regime = "TIME_FAILSAFE"
            setup = "T+2_EXPECTATION_FAIL"
            confidence = 0.95
        elif is_volume_breakdown:
            action = "SELL"
            size_pct = 1.00
            regime = "VOLUME_BREAKDOWN"
            setup = "VOL_COLLAPSE_平仓"
            confidence = 0.95
        elif regime != "SWING_LOW_BUY" and (pct_diff < -1.5 or dff < -1.0):
            # 对于低吸建仓的龙头个股，彻底豁免无爆量的普通敏感止损或 DFF 指标破位，把防守交由 SWS 支撑线！
            action = "SELL"
            size_pct = 1.0
        elif confidence >= 0.80:
            action = "ADD"
            size_pct = 0.20

    elif state == "EXITING":
        action = "SELL"
        size_pct = 1.0

    stop_price = None
    if action in {"BUY", "ADD"} and suggest_price > 0:
        if regime == "SWING_LOW_BUY":
            # 👑 四两拨千斤：有真实的 SWS 支撑位时，止损线死死钉在 SWS 工作支撑线下方的 1.5%，最大程度控制试错成本！
            sws_val = float(_num(signal, "sws", 0.0))
            if sws_val > 0:
                stop_price = round(sws_val * 0.985, 3)
            else:
                stop_price = round(suggest_price * 0.965, 3)
        else:
            stop_price = round(suggest_price * 0.98, 3)

    reason = DecisionReason(
        regime=regime,
        setup=setup,
        sector_heat=round(sector_heat, 4),
        sector_rank=None,
        is_leader=is_leader,
        breakout=breakout,
        volume_ratio=round(volume_ratio, 4),
        dff=round(dff, 4),
        dff_positive=dff_positive,
        price_above_vwap=not math.isnan(price) and price > 0,
        confidence_inputs=(
            ("priority", round(priority, 4)),
            ("sector_heat", round(sector_heat, 4)),
            ("pct_diff", round(pct_diff, 4)),
            ("dff", round(dff, 4)),
        ),
    )
    # 动态植入 Re-entry 标记与原因，使用 object.__setattr__ 完美绕开 dataclass(frozen=True) 物理阻断
    object.__setattr__(reason, "is_reentry_signal", is_reentry)
    object.__setattr__(reason, "reentry_reason", reentry_reason_str)

    intent = DecisionIntent(
        code=signal.code,
        action=action,
        size_pct=round(size_pct, 4),
        stop_price=stop_price,
        confidence=confidence,
        reason=reason,
        expires_at=signal.ts,
    )
    object.__setattr__(intent, "is_reentry_signal", is_reentry)
    return intent

