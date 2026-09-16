# -*- coding: utf-8 -*-
"""
ats/proactive_exit_engine.py
----------------------------
ProactiveExitEngine — 8层递进式主动出局引擎（防守端核心）
核心理念：绝不在破位后被动割肉，在出现弱势特征时主动减仓、清仓。

8 层递进防御阵列：
  Layer 1: 时间衰减止损 (Time Decay Stop)
  Layer 2: 无量不涨止损 (Volume Absence Stop)
  Layer 3: 反弹前高不过止损 (Failed Rally Stop) — 专克 600733 红色箭头假反弹
  Layer 4: 冲高派发识别 (Distribution Detection)
  Layer 5: 震荡不创高 (Oscillation Lower Highs)
  Layer 6: 量价背离出局 (Volume-Price Divergence)
  Layer 7: 大级别 MA5d 拐头 (Multi-Timeframe Rollover)
  Layer 8: VWAP 破位最后防线 (Final Safety Net)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from ats.vwap_rule_model import VWAPRuleModel

logger = logging.getLogger("ProactiveExitEngine")


@dataclass
class PositionWatchItem:
    """被守护的标的持仓状态快照"""
    code: str
    entry_time: float                     # 买入时间戳
    entry_price: float                    # 开仓均价
    shares: int = 1000                    # 持仓数量
    highest_price: float = 0.0            # 开仓后的最高价
    lowest_price: float = 999999.0        # 开仓后的最低价
    prev_day_high: float = 0.0            # 前日高点
    prev_day_close: float = 0.0           # 前日收盘价
    vwap_yesterday: float = 0.0           # 昨日 VWAP
    intraday_high_before: float = 0.0     # 开仓前的日内最高点
    
    # 状态计数
    minutes_below_vwap: int = 0           # 跌破今日VWAP持续分钟数
    reduce_count: int = 0                 # 已执行减仓次数
    last_reduce_time: Optional[float] = None
    
    # 窗口历史记录 (最近30个Tick/分钟数据)
    price_history: List[float] = field(default_factory=list)
    volume_history: List[float] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    
    # 前高阻力徘徊记录
    rally_dwell_seconds: float = 0.0      # 接近阻力位停留时间(秒)
    rally_peak_price: float = 0.0         # 本轮反弹摸到的最高价

    # 💥 [NEW] 底抬高企稳与VWAP向上位移反转保护特征
    is_reversal_protected: bool = False   # 是否处于底抬高企稳+VWAP位移反转结构保护中
    higher_low_stop: float = 0.0          # 底抬高关键防守线 (Higher Low 次低点)


@dataclass
class ExitAction:
    """主动出局指令"""
    code: str
    rule_id: str                          # 规则 ID
    rule_name: str                        # 规则中文名称
    layer: int                            # 防御层级 (1~8)
    action_type: str                      # "REDUCE_30" | "REDUCE_HALF" | "EXIT_ALL"
    size_pct: float                       # 建议减仓比例 (0.3, 0.5, 1.0)
    trigger_price: float                  # 触发价格
    reason: str                           # 详尽中文说明（行为可解释）
    timestamp: float                      # 触发时间戳


class ProactiveExitEngine:
    """
    8层递进式主动出局守护引擎
    """

    def __init__(self, rule_model: Optional[VWAPRuleModel] = None):
        self.rule_model = rule_model or VWAPRuleModel()
        self._positions: Dict[str, PositionWatchItem] = {}

    def register_position(
        self,
        code: str,
        entry_price: float,
        shares: int = 1000,
        entry_time: Optional[float] = None,
        prev_day_high: float = 0.0,
        vwap_yesterday: float = 0.0,
        intraday_high_before: float = 0.0,
    ) -> PositionWatchItem:
        """注册持仓进入 8 层主动出局守护池"""
        t = entry_time if entry_time is not None else time.time()
        item = PositionWatchItem(
            code=code,
            entry_time=t,
            entry_price=entry_price,
            shares=shares,
            highest_price=entry_price,
            lowest_price=entry_price,
            prev_day_high=prev_day_high,
            vwap_yesterday=vwap_yesterday,
            intraday_high_before=intraday_high_before,
            price_history=[entry_price],
            volume_history=[],
            timestamps=[t],
        )
        self._positions[code] = item
        logger.info(f"[{code}] 成功注册进 ProactiveExitEngine 8层守护池 (成本价: ¥{entry_price:.2f})")
        return item

    def unregister_position(self, code: str) -> Optional[PositionWatchItem]:
        """移除已清仓标的"""
        return self._positions.pop(code, None)

    def get_position(self, code: str) -> Optional[PositionWatchItem]:
        """获取持仓状态"""
        return self._positions.get(code)

    def evaluate_tick(
        self,
        code: str,
        price: float,
        vwap_today: float,
        volume: float,
        volume_ratio: float = 1.0,
        current_time: Optional[float] = None,
        extra_ctx: Optional[Dict[str, Any]] = None,
    ) -> Optional[ExitAction]:
        """
        每 Tick 评估持仓是否满足 8 层主动离场中的任意一层。
        优先级严格遵循：L1(时间) > L2(无量) > L3(反弹前高不过) > L4(冲高派发) > L5(震荡不创高) > L6(背离) > L7(MA5d) > L8(VWAP兜底)
        """
        pos = self._positions.get(code)
        if not pos:
            return None

        now = current_time if current_time is not None else time.time()
        ctx = extra_ctx or {}

        # 💥 [NEW] 反转结构持仓保护上下文注入与次低点止损更新
        if ctx.get("is_reversal_structure", False):
            pos.is_reversal_protected = True
        hl_ctx = float(ctx.get("higher_low", 0.0))
        if hl_ctx > 0:
            pos.higher_low_stop = max(pos.higher_low_stop, hl_ctx)

        try:
            # 1. 更新持仓极值与分时历史
            if price > pos.highest_price:
                pos.highest_price = price
            if price < pos.lowest_price:
                pos.lowest_price = price

            pos.price_history.append(price)
            pos.volume_history.append(volume)
            pos.timestamps.append(now)
            if len(pos.price_history) > 60:
                pos.price_history.pop(0)
                pos.volume_history.pop(0)
                pos.timestamps.pop(0)

            # 更新跌破 VWAP 计数
            if price < vwap_today:
                pos.minutes_below_vwap += 1
            else:
                pos.minutes_below_vwap = 0

            # 💥 [NEW] 阶梯次低点硬止损保护：若跌破关键底抬高防守线，直接全清离场
            if pos.higher_low_stop > 0 and price < pos.higher_low_stop * 0.99:
                return self._record_action(pos, ExitAction(
                    code=pos.code,
                    rule_id="exit_higher_low_broken",
                    rule_name="跌破次低点防守线(企稳结构破坏)",
                    layer=8,
                    action_type="EXIT_ALL",
                    size_pct=1.0,
                    trigger_price=price,
                    reason=f"价格跌破底抬高关键防守线 {pos.higher_low_stop:.2f}元 (现价 {price:.2f}元)，反转企稳结构失效，执行清仓止损",
                    timestamp=now,
                ))

            # 2. 依次按优先级评估 8 层守护
            # Layer 1: 时间衰减
            action = self._eval_layer1_time_decay(pos, price, now)
            if action:
                return self._record_action(pos, action)

            # Layer 2: 无量不涨
            action = self._eval_layer2_no_volume_no_rise(pos, price, volume, volume_ratio, now)
            if action:
                return self._record_action(pos, action)

            # Layer 3: 反弹前高不过 (600733 关键守护)
            action = self._eval_layer3_failed_rally(pos, price, volume_ratio, now)
            if action:
                return self._record_action(pos, action)

            # Layer 4: 冲高派发
            action = self._eval_layer4_distribution(pos, price, volume_ratio, ctx, now)
            if action:
                return self._record_action(pos, action)

            # Layer 5: 震荡不创高
            action = self._eval_layer5_oscillation(pos, price, vwap_today, now)
            if action:
                return self._record_action(pos, action)

            # Layer 6: 量价背离
            action = self._eval_layer6_volume_divergence(pos, price, ctx, now)
            if action:
                return self._record_action(pos, action)

            # Layer 7: 大级别 MA5d 拐头
            action = self._eval_layer7_ma5d_rollover(pos, price, vwap_today, ctx, now)
            if action:
                return self._record_action(pos, action)

            # Layer 8: VWAP 破位最后防线
            action = self._eval_layer8_vwap_breakdown(pos, price, vwap_today, now)
            if action:
                return self._record_action(pos, action)

        except Exception as exc:
            logger.error(f"[{code}] ProactiveExitEngine 评估异常: {exc}", exc_info=True)

        return None

    def _record_action(self, pos: PositionWatchItem, action: ExitAction) -> ExitAction:
        """记录动作并更新内部减仓状态"""
        if action.action_type in ("REDUCE_HALF", "REDUCE_30"):
            pos.reduce_count += 1
            pos.last_reduce_time = action.timestamp
        elif action.action_type == "EXIT_ALL":
            # 清仓后由调度器或外层调用 unregister_position
            pass
        return action

    # -------------------------------------------------------------------------
    # Layer 1: 时间衰减止损
    # -------------------------------------------------------------------------
    def _eval_layer1_time_decay(
        self, pos: PositionWatchItem, current_price: float, now: float
    ) -> Optional[ExitAction]:
        # 💥 [NEW] 底抬高企稳与VWAP位移反转结构生效时，若价格在次低点或成本线上方，豁免时间衰减止损
        if pos.is_reversal_protected and current_price >= pos.entry_price * 0.992:
            return None

        minutes_held = (now - pos.entry_time) / 60.0
        if minutes_held < 10.0:
            return None

        gain_pct = (current_price - pos.entry_price) / pos.entry_price * 100.0
        min_gain = self.rule_model.get_exit_layer_param("exit_time_decay", "min_gain_pct", 0.3)
        reduce_min = self.rule_model.get_exit_layer_param("exit_time_decay", "reduce_minutes", 20)
        exit_min = self.rule_model.get_exit_layer_param("exit_time_decay", "exit_minutes", 30)

        # 20分钟内涨幅不足0.3%且未曾减仓 -> 主动减半仓
        if minutes_held >= reduce_min and pos.reduce_count == 0 and gain_pct < min_gain:
            return ExitAction(
                code=pos.code,
                rule_id="exit_time_decay",
                rule_name="时间衰减止损(不及预期减半)",
                layer=1,
                action_type="REDUCE_HALF",
                size_pct=0.5,
                trigger_price=current_price,
                reason=f"买入持仓已达 {minutes_held:.1f} 分钟，涨幅仅为 {gain_pct:.2f}% (低于阈值 {min_gain}%)，机械执行主动减半仓防守",
                timestamp=now,
            )

        # 30分钟内仍处于成本线以下或浮亏 -> 100%清仓
        if minutes_held >= exit_min and gain_pct <= 0.0:
            return ExitAction(
                code=pos.code,
                rule_id="exit_time_decay",
                rule_name="时间衰减止损(超时浮亏清仓)",
                layer=1,
                action_type="EXIT_ALL",
                size_pct=1.0,
                trigger_price=current_price,
                reason=f"买入持仓超过 {exit_min} 分钟仍未能脱离成本区(浮亏: {gain_pct:.2f}%)，杜绝'介入十字星不及预期死扛'，强制清仓离场",
                timestamp=now,
            )

        return None

    # -------------------------------------------------------------------------
    # Layer 2: 无量不涨止损
    # -------------------------------------------------------------------------
    def _eval_layer2_no_volume_no_rise(
        self, pos: PositionWatchItem, current_price: float, volume: float, volume_ratio: float, now: float
    ) -> Optional[ExitAction]:
        minutes_held = (now - pos.entry_time) / 60.0
        if minutes_held < 5.0 or len(pos.volume_history) < 5:
            return None

        gain_pct = (current_price - pos.entry_price) / pos.entry_price * 100.0
        # 如果最近5根K线成交量萎缩严重且涨幅迟滞
        shrink_threshold = self.rule_model.get_exit_layer_param("exit_no_volume_no_rise", "volume_shrink_ratio", 0.5)
        price_thresh = self.rule_model.get_exit_layer_param("exit_no_volume_no_rise", "price_threshold_pct", 0.2)

        recent_v = pos.volume_history[-3:]
        avg_v = sum(pos.volume_history) / len(pos.volume_history) if pos.volume_history else 1.0
        is_shrinking = all(v < avg_v * shrink_threshold for v in recent_v) if avg_v > 0 else False

        if is_shrinking and gain_pct < price_thresh and volume_ratio < 0.7:
            if pos.reduce_count == 0:
                return ExitAction(
                    code=pos.code,
                    rule_id="exit_no_volume_no_rise",
                    rule_name="无量不涨止损(主动减半)",
                    layer=2,
                    action_type="REDUCE_HALF",
                    size_pct=0.5,
                    trigger_price=current_price,
                    reason=f"买入后量能持续萎缩(量比 {volume_ratio:.2f})，价格停滞不前(涨幅 {gain_pct:.2f}%)，无主力资金做多迹象，主动减半仓",
                    timestamp=now,
                )
            elif minutes_held >= 15.0 and gain_pct < 0.0:
                return ExitAction(
                    code=pos.code,
                    rule_id="exit_no_volume_no_rise",
                    rule_name="无量不涨止损(持续缩量清仓)",
                    layer=2,
                    action_type="EXIT_ALL",
                    size_pct=1.0,
                    trigger_price=current_price,
                    reason=f"持仓持续缩量阴跌超过 15 分钟，多头衰竭，清仓出局",
                    timestamp=now,
                )

        return None

    # -------------------------------------------------------------------------
    # Layer 3: 反弹前高不过止损 (600733 关键守护)
    # -------------------------------------------------------------------------
    def _eval_layer3_failed_rally(
        self, pos: PositionWatchItem, current_price: float, volume_ratio: float, now: float
    ) -> Optional[ExitAction]:
        # 💥 [NEW] 底抬高企稳与VWAP位移反转结构生效时，突破/逼近前高属于反转主升确立，绝非反弹力竭，彻底豁免 Layer 3 出局
        if pos.is_reversal_protected:
            return None

        # 寻找前高参考阻力位：依次比较 prev_day_high, vwap_yesterday, intraday_high_before
        candidates = [c for c in [pos.prev_day_high, pos.vwap_yesterday, pos.intraday_high_before] if c > pos.entry_price * 0.98]
        if not candidates:
            return None

        # 选取最接近当前价格的上方阻力位
        ref_high = min(candidates, key=lambda x: abs(x - current_price))
        if ref_high <= 0:
            return None

        near_pct = self.rule_model.get_exit_layer_param("exit_failed_rally", "near_prev_high_pct", 0.5) / 100.0
        breakout_pct = self.rule_model.get_exit_layer_param("exit_failed_rally", "breakout_threshold_pct", 0.5) / 100.0
        retreat_pct = self.rule_model.get_exit_layer_param("exit_failed_rally", "retreat_exit_pct", 1.5) / 100.0

        lower_bound = ref_high * (1.0 - near_pct)
        upper_bound = ref_high * (1.0 + breakout_pct)

        # 价格处于前高阻力观察区
        if lower_bound <= current_price <= upper_bound:
            if current_price > pos.rally_peak_price:
                pos.rally_peak_price = current_price

            pos.rally_dwell_seconds += 3.0  # 假设 tick 间隔约 3 秒
            # 如果在阻力位徘徊超过 120 秒 (约2分钟) 且量能萎缩无法带量突破
            if pos.rally_dwell_seconds >= 120.0 and volume_ratio < 1.0:
                return ExitAction(
                    code=pos.code,
                    rule_id="exit_failed_rally",
                    rule_name="反弹前高不过(阻力遇阻出局)",
                    layer=3,
                    action_type="REDUCE_HALF" if pos.reduce_count == 0 else "EXIT_ALL",
                    size_pct=0.5 if pos.reduce_count == 0 else 1.0,
                    trigger_price=current_price,
                    reason=f"价格反弹逼近前高阻力位 ¥{ref_high:.2f} (当前 ¥{current_price:.2f})，停留已久但量比萎缩(量比 {volume_ratio:.2f})无法突破，判定反弹力竭主动离场",
                    timestamp=now,
                )
        else:
            # 曾经接近过前高（摸到过阻力附近），但随后跌落回撤超过 retreat_pct
            if pos.rally_peak_price >= lower_bound:
                drop_from_peak = (pos.rally_peak_price - current_price) / pos.rally_peak_price
                if drop_from_peak >= retreat_pct:
                    return ExitAction(
                        code=pos.code,
                        rule_id="exit_failed_rally",
                        rule_name="反弹前高不过(遇阻回落清仓)",
                        layer=3,
                        action_type="EXIT_ALL",
                        size_pct=1.0,
                        trigger_price=current_price,
                        reason=f"价格冲击前高 ¥{ref_high:.2f} 失败，从反弹高点 ¥{pos.rally_peak_price:.2f} 回落已达 {drop_from_peak*100:.2f}% (超过清仓线 {retreat_pct*100:.1f}%)，确认为诱多派发，立即全清",
                        timestamp=now,
                    )

        return None

    # -------------------------------------------------------------------------
    # Layer 4: 冲高派发识别
    # -------------------------------------------------------------------------
    def _eval_layer4_distribution(
        self, pos: PositionWatchItem, current_price: float, volume_ratio: float, ctx: Dict[str, Any], now: float
    ) -> Optional[ExitAction]:
        # 💥 [NEW] 底抬高企稳与VWAP位移反转结构生效时，突破冲高回踩属于健康洗盘，豁免 Layer 4 派发出局
        if pos.is_reversal_protected:
            return None

        open_price = ctx.get("open", pos.entry_price)
        intraday_high = ctx.get("high", pos.highest_price)
        high_drop_event = bool(ctx.get("pattern_high_drop", False))

        rise_from_open = (intraday_high - open_price) / open_price * 100.0 if open_price > 0 else 0.0
        drop_from_high = (intraday_high - current_price) / intraday_high * 100.0 if intraday_high > 0 else 0.0

        # 满足冲高放量回落
        if high_drop_event or (rise_from_open >= 3.0 and drop_from_high >= 2.0 and volume_ratio >= 1.5):
            gain_pct = (current_price - pos.entry_price) / pos.entry_price * 100.0
            if gain_pct > 1.5:
                # 浮盈状态锁定利润
                return ExitAction(
                    code=pos.code,
                    rule_id="exit_distribution",
                    rule_name="冲高派发识别(锁盈出局)",
                    layer=4,
                    action_type="REDUCE_HALF",
                    size_pct=0.5,
                    trigger_price=current_price,
                    reason=f"分时冲高 +{rise_from_open:.1f}% 后放量回落 {drop_from_high:.1f}%，呈现主力派发特征，减半仓锁定利润",
                    timestamp=now,
                )
            else:
                # 浮亏或微利直接清仓
                return ExitAction(
                    code=pos.code,
                    rule_id="exit_distribution",
                    rule_name="冲高派发识别(回落清仓)",
                    layer=4,
                    action_type="EXIT_ALL",
                    size_pct=1.0,
                    trigger_price=current_price,
                    reason=f"分时冲高后快速放量下砸(自最高点回撤 {drop_from_high:.1f}%)，警惕主力诱多假突破，全仓撤出",
                    timestamp=now,
                )

        return None

    # -------------------------------------------------------------------------
    # Layer 5: 震荡不创新高
    # -------------------------------------------------------------------------
    def _eval_layer5_oscillation(
        self, pos: PositionWatchItem, current_price: float, vwap_today: float, now: float
    ) -> Optional[ExitAction]:
        if len(pos.price_history) < 15:
            return None

        # 简单波峰检测：寻找局部高点
        p = pos.price_history
        peaks = []
        for i in range(1, len(p) - 1):
            if p[i] > p[i - 1] and p[i] >= p[i + 1]:
                peaks.append(p[i])

        if len(peaks) >= 3:
            # 最近3个局部高点依次下降 (Lower Highs)
            if peaks[-1] < peaks[-2] < peaks[-3] and current_price < vwap_today:
                return ExitAction(
                    code=pos.code,
                    rule_id="exit_oscillation",
                    rule_name="震荡不创新高(高点下移减仓)",
                    layer=5,
                    action_type="REDUCE_30",
                    size_pct=0.3,
                    trigger_price=current_price,
                    reason=f"分时波峰序列连续 3 次下移 (¥{peaks[-3]:.2f} -> ¥{peaks[-2]:.2f} -> ¥{peaks[-1]:.2f}) 且位于均价线下方，结构性转弱，减仓 30%",
                    timestamp=now,
                )

        return None

    # -------------------------------------------------------------------------
    # Layer 6: 量价背离出局
    # -------------------------------------------------------------------------
    def _eval_layer6_volume_divergence(
        self, pos: PositionWatchItem, current_price: float, ctx: Dict[str, Any], now: float
    ) -> Optional[ExitAction]:
        dff = ctx.get("dff", 0.0)
        has_divergence = bool(ctx.get("volume_divergence", False))

        # 价格接近买入后最高点但资金流向差加速出逃
        if current_price >= pos.highest_price * 0.995 and (has_divergence or dff < -0.5):
            return ExitAction(
                code=pos.code,
                rule_id="exit_volume_divergence",
                rule_name="量价背离出局(资金出逃避险)",
                layer=6,
                action_type="REDUCE_HALF",
                size_pct=0.5,
                trigger_price=current_price,
                reason=f"价格运行在近期高位 ¥{current_price:.2f}，但资金流向差 DFF 出现严重负流向 ({dff:.2f})，呈现顶背离，减半仓防范跳水",
                timestamp=now,
            )

        return None

    # -------------------------------------------------------------------------
    # Layer 7: 大级别 MA5d 拐头 (跨周期大势守护)
    # -------------------------------------------------------------------------
    def _eval_layer7_ma5d_rollover(
        self, pos: PositionWatchItem, current_price: float, vwap_today: float, ctx: Dict[str, Any], now: float
    ) -> Optional[ExitAction]:
        ma5d = ctx.get("ma5d", 0.0)
        ma5d_prev5 = ctx.get("ma5d_prev5", 0.0)
        channel_slope_60m = ctx.get("channel_slope_60m", 0.0)

        if ma5d > 0 and ma5d_prev5 > 0:
            # 日线MA5拐头向下
            ma5_declining = ma5d < ma5d_prev5 * 0.998
            # 跌破日线5日均线且60分通道加速下行
            if ma5_declining and current_price < ma5d and channel_slope_60m < -5.0:
                # 当分时价格反抽到均价线附近时，分时反弹直接出清！
                if abs(current_price - vwap_today) / vwap_today <= 0.005:
                    return ExitAction(
                        code=pos.code,
                        rule_id="exit_ma5d_rollover",
                        rule_name="大级别MA5d拐头(分时反抽清仓)",
                        layer=7,
                        action_type="EXIT_ALL",
                        size_pct=1.0,
                        trigger_price=current_price,
                        reason=f"日线 MA5 均线已拐头向下 (¥{ma5d:.2f} < ¥{ma5d_prev5:.2f}) 且 60 分通道斜率 ({channel_slope_60m:.1f}°) 下行，大级别破位，分时反抽 VWAP 均价即刻出清，严防大级别深套",
                        timestamp=now,
                    )

        return None

    # -------------------------------------------------------------------------
    # Layer 8: VWAP 破位兜底 (最后防线)
    # -------------------------------------------------------------------------
    def _eval_layer8_vwap_breakdown(
        self, pos: PositionWatchItem, current_price: float, vwap_today: float, now: float
    ) -> Optional[ExitAction]:
        threshold_mins = self.rule_model.get_exit_layer_param("exit_vwap_breakdown", "below_vwap_minutes", 5)

        # 跌破今日均价连续达到 5 分钟 (约 100 个 Tick)
        if pos.minutes_below_vwap >= (threshold_mins * 20):
            return ExitAction(
                code=pos.code,
                rule_id="exit_vwap_breakdown",
                rule_name="VWAP破位兜底(最后防线强平)",
                layer=8,
                action_type="EXIT_ALL",
                size_pct=1.0,
                trigger_price=current_price,
                reason=f"价格跌破今日分时均线 VWAP (¥{vwap_today:.2f}) 持续超过 {threshold_mins} 分钟且未能站回，最后防线触发，强制 100% 清仓",
                timestamp=now,
            )

        return None
