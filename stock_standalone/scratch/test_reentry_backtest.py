import os
import sys
import pandas as pd
from datetime import datetime

# 保证控制台流以 UTF-8 输出，防止 Emoji 或中文字符在 Windows 环境下发生 gbk 物理编码报错
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 注入项目根目录以确保模块可导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df
from trading_kernel.engine.reentry_tracker import reentry_tracker
from trading_kernel.engine.decision_engine import decide
from trading_kernel.core.signal import StrategySignal

def run_backtest_for_code(code: str, name: str):
    print("=" * 80)
    print(f"[RE-ENTRY TEST] 开始对标的 【{name} ({code})】 进行多周期枢轴右侧 Re-entry 逐日回溯测试")
    print("=" * 80)

    # 1. 抓取完整的交易日历（拉取足够长 250 天）
    df_calendar = get_tdx_Exp_day_to_df(code, dl=250)
    if df_calendar is None or df_calendar.empty:
        print(f"[ERROR] 无法加载个股 {code} 的通达信历史日线数据，请检查本地 Vipdoc 目录是否同步！")
        return

    # 按日期排序
    df_calendar = df_calendar.sort_index()
    total_days = len(df_calendar)
    print(f"[INFO] 成功加载 {total_days} 个交易日的历史数据，日期区间: {df_calendar.index[0]} 至 {df_calendar.index[-1]}")

    # 选择倒数第 30 个交易日作为被洗盘止损点
    stop_idx = total_days - 30
    if stop_idx < 40:
        stop_idx = 40

    stop_date = df_calendar.index[stop_idx]
    
    # 模拟止损当天的真实收盘价 (不带未来数据)
    df_stop = get_tdx_Exp_day_to_df(code, end=stop_date, dl=1000)
    if df_stop.empty:
        print(f"[ERROR] 无法加载 {stop_date} 截止的数据")
        return
        
    stop_price = float(df_stop.iloc[-1]["close"])
    print(f"[STOP-LOSS EVENT] 模拟历史事件：在 {stop_date} 标的遭遇窄幅洗盘，触发止损清仓，止损价格: {stop_price:.2f} 元")

    # 重置并注册进 reentry 观察池
    reentry_tracker.clear()
    reentry_tracker.register_exit(code, stop_price, exit_time=f"{stop_date} 15:00:00")

    # 模拟持仓状态变量
    has_position = False
    entry_price = 0.0
    trailing_stop = 0.0
    max_high_since_entry = 0.0
    days_held = 0
    tp_triggered = False
    locked_pnl = 0.0
    is_swing_low_mode = False

    # 2. 逐日推进 enddate 切换测试策略效率 (从止损后的第一天开始模拟，每日重新加载防止未来数据泄露)
    activated_date = None
    for i in range(stop_idx + 1, total_days):
        current_date = df_calendar.index[i]
        
        # 核心漏洞修复：每次都以 current_date 为截止点，重新计算当日绝对真实的指标特征，使用足够长(1000天)的深度
        df_curr = get_tdx_Exp_day_to_df(code, end=current_date, dl=1000)
        if df_curr.empty:
            continue
            
        row = df_curr.iloc[-1]
        close = float(row.get("close", 0.0))
        high4 = float(row.get("high4", 0.0))
        hmax = float(row.get("hmax", 0.0))
        low60 = float(row.get("low60", 0.0))
        pbreak = int(row.get("pbreak", 0))
        ptop = float(row.get("ptop", 0.0))
        dff = float(row.get("dff", 0.0))
        vol_ratio = 1.3 # 模拟主力温和放量突破的盘中量比

        # 1. 动态自愈计算 10日均线、5日均线和成交量特征 (无未来数据)
        if len(df_curr) >= 10:
            ma10_series = df_curr['close'].rolling(10).mean()
            ma5_series = df_curr['close'].rolling(5).mean()
            vol_ma5_series = df_curr['vol'].rolling(5).mean()
            
            ma10 = float(ma10_series.iloc[-1])
            ma5 = float(ma5_series.iloc[-1])
            vol_ma5 = float(vol_ma5_series.iloc[-1])
            
            # SWS & SWL & Upper 高精度提取与 100% 物理 Fallback 机制
            sws = float(row.get("SWS", 0.0))
            swl = float(row.get("SWL", 0.0))
            if sws <= 0 or sws < close * 0.85 or sws > close * 1.15:
                sws = ma10
            if swl <= 0 or swl < close * 0.85 or swl > close * 1.15:
                swl = ma5
                
            # 提取 5 天前的 SWS 支撑线值，进行趋势校验
            if len(df_curr) >= 15:
                row_prev5 = df_curr.iloc[-6]
                sws_prev5 = float(row_prev5.get("SWS", 0.0))
                close_prev5 = float(row_prev5['close'])
                if sws_prev5 <= 0 or sws_prev5 < close_prev5 * 0.85 or sws_prev5 > close_prev5 * 1.15:
                    sws_prev5 = float(df_curr['close'].rolling(10).mean().iloc[-6])
            else:
                sws_prev5 = sws
                
            # 提取 20日主力生命均线倾角特征，过滤中期趋势走平走弱的个股
            if len(df_curr) >= 25:
                ma20_series = df_curr['close'].rolling(20).mean()
                ma20 = float(ma20_series.iloc[-1])
                ma20_prev5 = float(ma20_series.iloc[-6])
            else:
                ma20 = close
                ma20_prev5 = close
                
            # 提取 12 天前及过去 12 天内最大 SWS，判断是否有强拉升盈利带
            if len(df_curr) >= 20:
                row_prev12 = df_curr.iloc[-13]
                sws_prev12 = float(row_prev12.get("SWS", 0.0))
                close_prev12 = float(row_prev12['close'])
                if sws_prev12 <= 0 or sws_prev12 < close_prev12 * 0.85 or sws_prev12 > close_prev12 * 1.15:
                    sws_prev12 = float(df_curr['close'].rolling(10).mean().iloc[-13])
                
                # 计算过去 12 天内的最大 SWS
                recent_12 = df_curr.tail(12)
                sws_max12 = sws_prev12
                for r_idx in range(len(recent_12)):
                    r_row = recent_12.iloc[r_idx]
                    r_sws = float(r_row.get("SWS", 0.0))
                    r_close = float(r_row['close'])
                    if r_sws <= 0 or r_sws < r_close * 0.85 or r_sws > r_close * 1.15:
                        r_sws = float(r_row['close'])
                    sws_max12 = max(sws_max12, r_sws)
                
                profit_band_growth = (sws_max12 - sws_prev12) / sws_prev12
            else:
                profit_band_growth = 0.0
                
            # 👑 黄金盈利上升带活性校验：主力支撑 SWS 必须有至少 4.0% 以上的上扬斜率增长，才证明有强势主力资金的盈利带！
            is_active_profit_band = (profit_band_growth >= 0.04)
            
            # 计算过去 15 天内单日最大涨幅，过滤无大阳线脉冲的缓慢蠕动阴跌品种
            has_big_surge = False
            if len(df_curr) >= 16:
                recent_15_df = df_curr.tail(15)
                for s_idx in range(len(recent_15_df)):
                    sub_len_s = len(df_curr) - len(recent_15_df) + s_idx + 1
                    if sub_len_s >= 2:
                        s_close = float(df_curr['close'].iloc[sub_len_s - 1])
                        s_prev = float(df_curr['close'].iloc[sub_len_s - 2])
                        s_pct = (s_close - s_prev) / s_prev * 100
                        if s_pct >= 6.8:  # 包含大涨 7% 左右的大阳线
                            has_big_surge = True
                            break
            else:
                has_big_surge = True
                
            # 计算前期 15 天内是否有过真金白银的突破 pbreak == 1 信号
            has_breakout_touch = False
            if len(df_curr) >= 15:
                recent_15_df = df_curr.tail(15)
                # 检查过去 15 天内是否有任意一天的 pbreak == 1 或者是超过前期大平台顶
                for s_idx in range(len(recent_15_df)):
                    r_row = recent_15_df.iloc[s_idx]
                    if int(r_row.get("pbreak", 0)) == 1:
                        has_breakout_touch = True
                        break
            else:
                has_breakout_touch = True
                
            if code == "603533" and current_date == "2026-04-24":
                print(f"[DEBUG SURGE DETAIL 603533]")
                recent_15_df = df_curr.tail(15)
                for s_idx in range(len(recent_15_df)):
                    sub_len_s = len(df_curr) - len(recent_15_df) + s_idx + 1
                    if sub_len_s >= 2:
                        date_s = df_curr.index[sub_len_s - 1]
                        s_close = float(df_curr['close'].iloc[sub_len_s - 1])
                        s_prev = float(df_curr['close'].iloc[sub_len_s - 2])
                        s_pct = (s_close - s_prev) / s_prev * 100
                        print(f"   Date: {date_s}, Close: {s_close}, PrevClose: {s_prev}, Pct: {s_pct:.2f}%")
                print(f"has_big_surge calculated as: {has_big_surge}, has_breakout_touch (pbreak_15d): {has_breakout_touch}")
                
            # 👑 SWS 黄金盈利上升带 + MA20 主力昂头 + 盈利带活性 + 主力线尊严 + 强庄大阳线拉升 + 前期大突破门禁：
            # 1. SWS 支撑重心上移
            # 2. MA20 主力生命线必须保持向上倾斜
            # 3. 过去 12 天内有过 4.0% 以上的明确资金拉升盈利带
            # 4. 收盘价必须死守在 20日中期主力生命线之上（close >= ma20 * 0.995）
            # 5. 过去 15 天内必须有过至少一根大阳线（>= 6.8%）的强庄建仓启动信号
            # 6. 过去 15 天内必须触碰或突破过 30日最高点 hmax，彻底排除无突围多头基因的阴跌品种！
            is_profit_band = (sws >= sws_prev5 * 1.002) and (ma20 >= ma20_prev5 * 1.001) and is_active_profit_band and (close >= ma20 * 0.995) and has_big_surge and has_breakout_touch
                
            upper = float(row.get("upper", 0.0))
            if upper <= 0:
                ma20_val = df_curr['close'].rolling(20).mean()
                std20 = df_curr['close'].rolling(20).std()
                if len(df_curr) >= 20:
                    upper = float(ma20_val.iloc[-1] + 2.0 * std20.iloc[-1])
                else:
                    upper = close * 1.10
            
            # 缩量判定：当日量低于 5 日均量的 90%
            vol_curr = float(df_curr['vol'].iloc[-1])
            vol_prev1 = float(df_curr['vol'].iloc[-2]) if len(df_curr) >= 2 else vol_curr
            vol_prev2 = float(df_curr['vol'].iloc[-3]) if len(df_curr) >= 3 else vol_prev1
            
            vol_shrink_3d = (vol_curr < vol_ma5 * 0.90)
            
            # 计算十字星/均线企稳K线特征
            open_p = float(row.get("open", close))
            high_p = float(row.get("high", close))
            low_p = float(row.get("low", close))
            body_len = abs(close - open_p)
            shadow_len = high_p - low_p
            is_doji = False
            if shadow_len > 0:
                if (body_len / shadow_len <= 0.3) or (body_len / close <= 0.01):
                    is_doji = True
            else:
                is_doji = True
            
            # 👑 SWS 支撑回踩判定：最低价踩在 SWS 支撑线附近，且收盘稳定在 SWS 之上，并具备黄金上扬盈利带
            low_price = float(df_curr['low'].iloc[-1])
            is_pullback_support = (low_price <= sws * 1.015) and (close >= sws * 0.985)
            
            if code == "603533" and current_date in ["2026-04-24", "2026-05-12"]:
                print(f"[DEBUG SWS CHECK FOR 603533 on {current_date}] close={close:.2f} sws={sws:.2f}, sws_prev5={sws_prev5:.2f}, is_profit_band={is_profit_band}")
            
            # 👑 筹码收集期判定 (第一买点特征)：过去 8 天内，至少有 2 天的收盘价或最高价非常贴近或突破布林上轨
            recent_8 = df_curr.tail(8)
            touch_upper_days = 0
            for idx in range(len(recent_8)):
                sub_len = len(df_curr) - len(recent_8) + idx + 1
                sub_df = df_curr.iloc[:sub_len]
                r_row = recent_8.iloc[idx]
                r_close = float(r_row['close'])
                r_high = float(r_row['high'])
                r_upper = float(r_row.get("upper", 0.0))
                if r_upper <= 0:
                    if len(sub_df) >= 20:
                        r_ma20 = sub_df['close'].rolling(20).mean().iloc[-1]
                        r_std20 = sub_df['close'].rolling(20).std().iloc[-1]
                        r_upper = float(r_ma20 + 2.0 * r_std20)
                    else:
                        r_upper = r_close * 1.10
                if r_close >= r_upper * 0.99 or r_high >= r_upper * 0.99:
                    touch_upper_days += 1
            is_collecting_stage = (touch_upper_days >= 2)
            
            # 👑 洗盘整固期判定 (第二买点特征)：过去 15 天内有过快速上涨（最大涨幅曾 >= 12%），随后股价回落，且并未跌破 SWS
            recent_15 = df_curr.tail(15)
            min_close_15 = float(recent_15['close'].min())
            max_close_15 = float(recent_15['close'].max())
            has_prior_surge = (max_close_15 - min_close_15) / min_close_15 >= 0.12
            is_consolidation_stage = has_prior_surge and (close < max_close_15 * 0.97) and (close >= sws * 0.985)
            
        else:
            sws = close
            swl = close
            upper = close * 1.10
            vol_shrink_3d = False
            is_pullback_support = False
            is_collecting_stage = False
            is_consolidation_stage = False
            is_doji = False
            vol_curr = 200000.0

        # 实时更新 tracker 的洗盘最低价以进行低位企稳判定
        reentry_tracker.update_price(code, close)

        if has_position:
            days_held += 1
            max_high_since_entry = max(max_high_since_entry, close)
            pnl_pct = (close - entry_price) / entry_price * 100
            low_price = float(df_curr['low'].iloc[-1])

            # 组装模拟持仓决策行情信号，用于触发大止盈或 T+2 时间保护出局
            sig = StrategySignal(
                code=code,
                name=name,
                ts=f"{current_date} 10:00:00",
                source="BACKTEST",
                signal_type="HOLDING",
                price=close,
                features={
                    "priority": 75.0,
                    "sector_heat": 45.0,
                    "pct_diff": pnl_pct,
                    "dff": dff,
                    "volume": vol_curr,
                    "low": low_price,
                    "high4": high4,
                    "hmax": hmax,
                    "low60": low60,
                    "pbreak": pbreak,
                    "ptop": ptop,
                    "vol_ratio_5d": vol_ratio,
                    "days_held": float(days_held),
                    "pnl_pct": pnl_pct,
                    "vol_shrink_3d": vol_shrink_3d,
                    "is_pullback_support": is_pullback_support,
                    "is_collecting_stage": is_collecting_stage,
                    "is_consolidation_stage": is_consolidation_stage,
                    "is_doji": is_doji,
                    "upper": upper,
                    "max_pnl_since_entry": (max_high_since_entry - entry_price) / entry_price * 100.0 if entry_price > 0.0 else 0.0,
                    "sws": sws,
                    "vol_ma5": vol_ma5,
                    "regime": "SWING_LOW_BUY" if is_swing_low_mode else "BREAKOUT_ALLOWED",
                    "tp_triggered": tp_triggered,
                    "is_swing_low_mode": is_swing_low_mode,
                    "raw_reason": "持仓状态动态决策"
                }
            )

            intent = decide(sig, "IN_TRADE")
            
            # 💡 弹性大格局防守判定：
            # 1. 👑 如果是低吸持仓，死守 SWS 支撑线防线不变，绝对不主动上提移动止损，避免假摔洗盘！
            # 2. 浮盈未拉开身位 (未超 8.0%) 时，保持初始止损 trailing_stop 不变；
            # 3. 浮盈拉开身位 (>= 8.0%) 后，开启 10% 黄金洗盘宽垫防护 (max_high * 0.90)；
            if is_swing_low_mode:
                current_stop = trailing_stop
            elif pnl_pct < 8.0:
                current_stop = trailing_stop
            else:
                current_stop = max(trailing_stop, max_high_since_entry * 0.90)

            # A. 向上平台顶/大周期物理突破 ── 触发大止盈减仓 70%
            if intent.action == "SELL" and intent.size_pct == 0.70:
                if not tp_triggered:
                    tp_triggered = True
                    locked_pnl += pnl_pct * 0.70
                    print(f"[DATE: {current_date}] 收盘价: {close:.2f} | 👑 [TAKE-PROFIT EVENT] 满足大周期/平台顶向上强力突破，触发逆向分批大止盈！")
                    print(f"   -> 锁定 70% 仓位高位浮盈: +{pnl_pct:.2f}% | 剩余 30% 仓位轻仓留守大格局奔跑...")
                else:
                    # 已止盈过，剩余仓位只受移动止损保护
                    pass
                continue

            # 💡 黄金低吸回补仓位判定 (Re-entry Add Back 70%)：
            if intent.action == "ADD" and intent.size_pct == 0.70:
                old_entry_price = entry_price
                entry_price = (old_entry_price * 0.30 + close * 0.70)
                tp_triggered = False  # 标志重置，持仓满仓运行！
                locked_pnl = 0.0      # 已经重新满仓，重置锁定利润以新成本重新计算
                trailing_stop = intent.stop_price if intent.stop_price else (sws * 0.985)
                current_stop = trailing_stop
                max_high_since_entry = max(max_high_since_entry, close)
                print(f"[DATE: {current_date}] 收盘价: {close:.2f} | 🌟 [ADD-BACK EVENT] 满足龙头回踩 SWS 支撑且缩量洗盘，大止盈的 70% 仓位补回！重新满仓运行！")
                print(f"   -> 原持仓均价: {old_entry_price:.2f} 元 | 补回价格: {close:.2f} 元 | 加权新持仓均价: {entry_price:.2f} 元 | 新 SWS 防线: {current_stop:.2f} 元")
                continue

            # B. T+2时间不及预期风控出局 ── 100% 平仓
            elif intent.action == "SELL" and intent.reason.setup == "T+2_EXPECTATION_FAIL":
                final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else pnl_pct
                print(f"[DATE: {current_date}] 收盘价: {close:.2f} | ⏰ [TIME-LIMIT FAILSAFE] 买入满 2 日不及预期冲高就走！触发平仓退场。")
                print("=" * 80)
                print(f"[RE-ENTRY POSITIONS TRANSACTION COMPLETED]")
                print(f"-> 交易个股: {name} ({code})")
                print(f"-> 出局日期: {current_date} (T+{days_held})")
                print(f"-> 重新买入价格: {entry_price:.2f} 元 | 平仓价格: {close:.2f} 元")
                print(f"-> 🎯 逆向大师策略斩获最终综合盈亏率: {final_pnl:+.2f}% (大止盈已锁定)")
                print("=" * 80 + "\n")
                has_position = False
                tp_triggered = False
                locked_pnl = 0.0
                is_swing_low_mode = False
                reentry_tracker.register_exit(code, close, exit_time=f"{current_date} 15:00:00")
                continue

            # C. 跌破弹性止损线或者 DFF 指标破位 ── 100% 物理清仓
            elif close < current_stop or (intent.action == "SELL" and intent.size_pct == 1.00):
                final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else pnl_pct
                trigger_stop_val = current_stop if close < current_stop else close
                print(f"[DATE: {current_date}] 收盘价: {close:.2f} | 🚨 跌破防守线 {trigger_stop_val:.2f} 元或触发破位！触发物理平仓出局。")
                print("=" * 80)
                print(f"[RE-ENTRY POSITIONS TRANSACTION COMPLETED]")
                print(f"-> 交易个股: {name} ({code})")
                print(f"-> 出局日期: {current_date}")
                print(f"-> 重新买入价格: {entry_price:.2f} 元 | 平仓价格: {close:.2f} 元")
                print(f"-> 🎯 逆向大师策略斩获最终综合盈亏率: {final_pnl:+.2f}%")
                print("=" * 80 + "\n")
                has_position = False
                tp_triggered = False
                locked_pnl = 0.0
                is_swing_low_mode = False
                reentry_tracker.register_exit(code, close, exit_time=f"{current_date} 15:00:00")
            else:
                current_held_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else pnl_pct
                print(f"[DATE: {current_date}] 收盘价: {close:.2f} | 💼 持续持仓中，综合收益: {current_held_pnl:+.2f}% | 弹性动态止损线: {current_stop:.2f} 元")
            continue

        # 组装模拟盘中行情信号，进行开仓判定
        low_price = float(df_curr['low'].iloc[-1])
        sig = StrategySignal(
            code=code,
            name=name,
            ts=f"{current_date} 10:00:00",
            source="BACKTEST",
            signal_type="PULLBACK",
            price=close,
            features={
                "priority": 75.0,
                "sector_heat": 45.0,
                "pct_diff": 1.2,
                "dff": dff,
                "volume": vol_curr,
                "low": low_price,
                "high4": high4,
                "hmax": hmax,
                "low60": low60,
                "pbreak": pbreak,
                "ptop": ptop,
                "vol_ratio_5d": vol_ratio,
                "vol_shrink_3d": vol_shrink_3d,
                "is_pullback_support": is_pullback_support,
                "is_collecting_stage": is_collecting_stage,
                "is_consolidation_stage": is_consolidation_stage,
                "is_doji": is_doji,
                "upper": upper,
                "max_pnl_since_entry": 0.0,
                "sws": sws,
                "vol_ma5": vol_ma5,
                "tp_triggered": tp_triggered,
                "is_swing_low_mode": is_swing_low_mode,
                "raw_reason": "逐日回溯模拟信号"
            }
        )

        # 决策引擎进行判定
        intent = decide(sig, "FLAT")

        is_reentry_triggered = getattr(intent, "is_reentry_signal", False)
        reentry_reason_str = getattr(intent.reason, "reentry_reason", "")
        
        # 判断是右侧 Re-entry 激活还是左侧缩量回踩均线低吸建仓
        is_swing_low_triggered = (intent.action == "BUY" and intent.reason.regime == "SWING_LOW_BUY")

        if code == "002156" and current_date in ["2026-04-27", "2026-04-28", "2026-04-29", "2026-05-06", "2026-05-18"]:
            print(f"--- [DIAGNOSTIC 002156 on {current_date}] ---")
            print(f"    close={close:.2f}, low={low_price:.2f}, sws={sws:.2f}, sws_prev5={sws_prev5:.2f}")
            print(f"    vol_shrink_3d={vol_shrink_3d}, is_pullback_support={is_pullback_support}")
            print(f"    is_profit_band={is_profit_band} (sws_up={sws >= sws_prev5 * 1.002}, ma20_up={ma20 >= ma20_prev5 * 1.001}, active_band={is_active_profit_band}, close_above_ma20={close >= ma20 * 0.995}, has_big_surge={has_big_surge}, has_breakout_touch={has_breakout_touch})")
            print(f"    is_collecting_stage={is_collecting_stage}, is_consolidation_stage={is_consolidation_stage}")
            print(f"    intent.action={intent.action}, intent.reason.regime={intent.reason.regime}")

        if is_reentry_triggered or is_swing_low_triggered:
            activated_date = current_date
            entry_price = close
            trailing_stop = intent.stop_price
            max_high_since_entry = close
            days_held = 0
            tp_triggered = False
            locked_pnl = 0.0
            is_swing_low_mode = is_swing_low_triggered
            has_position = True

            print("\n" + "*" * 80)
            if is_swing_low_triggered:
                print(f"[SWING-LOW BUY TRIGGERED SUCCESS!]")
                print(f"-> 触发个股: {name} ({code})")
                print(f"-> 触发日期: {current_date}")
                print(f"-> 激活原因: 👑 支撑低吸：{intent.reason.setup}")
            else:
                print(f"[RE-ENTRY ALERT TRIGGERED SUCCESS!]")
                print(f"-> 触发个股: {name} ({code})")
                print(f"-> 触发日期: {current_date} (距离止损平仓仅 {i - stop_idx} 个交易日)")
                print(f"-> 激活原因: {reentry_reason_str}")
            print(f"-> 决策动作: {intent.action} | 阶梯底仓仓位分配: {intent.size_pct * 100:.1f}%")
            print(f"-> 动态止损价设定: {intent.stop_price:.2f} 元")
            print(f"-> 最终共振置信度: {intent.confidence:.4f}")
            print("*" * 80 + "\n")
        else:
            print(f"[DATE: {current_date}] 收盘价: {close:.2f} | high4: {high4:.2f} | hmax: {hmax:.2f} | low60: {low60:.2f} | pbreak: {pbreak} | Re-entry 触发: [KEEP OBSERVING] 保持观察")

    if has_position:
        # 如果直到回测最后一天仍在持仓
        pnl_pct = (close - entry_price) / entry_price * 100
        final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else pnl_pct
        print("=" * 80)
        print(f"[RE-ENTRY HELD UNTIL TODAY - STATUS]")
        print(f"-> 交易个股: {name} ({code})")
        print(f"-> 截止今天: {df_calendar.index[-1]}")
        print(f"-> 重新买入价格: {entry_price:.2f} 元 | 今日最新收盘: {close:.2f} 元")
        print(f"-> 🎯 依然持仓躺赢中！综合已实现+账面浮盈盈亏: {final_pnl:+.2f}%")
        print("=" * 80 + "\n")

    if not activated_date:
        print(f"\nℹ️ 标的 {code} 在观察期内行情尚未确立，继续在池中保持观察洗盘深度。\n")

if __name__ == "__main__":
    # 执行测试用户指定的个股：蓝色光标 (300058)
    run_backtest_for_code("300058", "蓝色光标")
    
    # 👑 同时测试通富微电 (002156)，展示筹码收集期回踩与大涨回落 SWS 整固两段大师低吸策略的极致效果
    run_backtest_for_code("002156", "通富微电")
