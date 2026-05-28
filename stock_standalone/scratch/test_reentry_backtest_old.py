import os
import sys
import pandas as pd
from datetime import datetime
import io

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

_last_backtest_signals = {}
_last_backtest_best_branch = {}

def get_last_backtest_signals(code: str) -> list:
    code_clean = code.strip()
    for icon in ['🔴', '🟢', '📊', '⚠️']:
        code_clean = code_clean.replace(icon, '').strip()
    return _last_backtest_signals.get(code_clean, [])

def get_last_backtest_best_branch(code: str) -> str:
    code_clean = code.strip()
    for icon in ['🔴', '🟢', '📊', '⚠️']:
        code_clean = code_clean.replace(icon, '').strip()
    return _last_backtest_best_branch.get(code_clean, "SuperTrendMA5Branch")

def run_backtest_and_get_report(code: str, name: str, only_report: bool = False) -> str:
    """运行指定个股 of Re-entry 历史回测，并以字符串形式返回完整的日志及整体总结报告。"""
    code_clean = code.strip()
    for icon in ['🔴', '🟢', '📊', '⚠️']:
        code_clean = code_clean.replace(icon, '').strip()
    _last_backtest_signals[code_clean] = []
    _last_backtest_best_branch[code_clean] = "SuperTrendMA5Branch"
    # ── 从 global.ini 动态灌入 StrategyRouter 静态路由表 ──
    try:
        import configparser
        from trading_kernel.engine.decision_engine import StrategyRouter
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(base_dir, "global.ini")
        if os.path.exists(ini_path):
            config = configparser.ConfigParser()
            config.read(ini_path, encoding="utf-8")
            if "strategy_routing" in config.sections():
                rmap = {}
                for key in config["strategy_routing"]:
                    val = config["strategy_routing"][key]
                    rmap[key] = [c.strip() for c in val.split(",") if c.strip()]
                StrategyRouter.register_static_routes(rmap)
    except Exception:
        pass

    output = io.StringIO()
    def log(msg="", is_detail=True):
        if only_report and is_detail:
            return
        output.write(str(msg) + "\n")
        
    log("=" * 80)
    log(f"[RE-ENTRY TEST] 开始对标的 【{name} ({code})】 进行多周期枢轴右侧 Re-entry 逐日回溯测试")
    log("=" * 80)

    # 1. 抓取完整的交易数据（拉取足够长 1200 天以防均线前置依赖缺失）
    df_all = get_tdx_Exp_day_to_df(code, dl=1200)
    if df_all is None or df_all.empty:
        log(f"[ERROR] 无法加载个股 {code} 的通达信历史日线数据，请检查本地 Vipdoc 目录是否同步！", is_detail=False)
        return output.getvalue()

    # 按日期排序
    df_all = df_all.sort_index()
    df_calendar = df_all.tail(250)
    total_days = len(df_calendar)
    log(f"[INFO] 成功加载 {len(df_all)} 天的历史数据，测试日历区间 (250天): {df_calendar.index[0]} 至 {df_calendar.index[-1]}")

    # 选择倒数第 30 个交易日作为被洗盘止损点
    stop_idx = total_days - 30
    if stop_idx < 40:
        stop_idx = 40

    stop_date = df_calendar.index[stop_idx]
    
    # 模拟止损当天的真实收盘价 (不带未来数据)
    df_stop = df_all.loc[:stop_date]
    if df_stop.empty:
        log(f"[ERROR] 无法加载 {stop_date} 截止的数据", is_detail=False)
        return output.getvalue()
        
    stop_price = float(df_stop.iloc[-1]["close"])
    log(f"[STOP-LOSS EVENT] 模拟历史事件：在 {stop_date} 标的遭遇窄幅洗盘，触发止损清仓，止损价格: {stop_price:.2f} 元")

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
    tp_count = 0
    locked_pnl = 0.0
    is_swing_low_mode = False
    
    # 用于收集整理最后“整体报告”的关键事件
    trade_events = []
    prev_predict_ma5 = None
    current_setup = ""

    # 2. 逐日推进 enddate
    activated_date = None
    for i in range(stop_idx + 1, total_days):
        current_date = df_calendar.index[i]
        
        # 核心漏洞修复：使用局部视口切片计算，杜绝未来数据泄露，且极大提升运行速度
        row_idx = df_all.index.get_loc(current_date)
        close = float(df_all['close'].iloc[row_idx])
        high_p = float(df_all['high'].iloc[row_idx])
        low_price = float(df_all['low'].iloc[row_idx])
        vol_curr = float(df_all['vol'].iloc[row_idx])
        open_p = float(df_all['open'].iloc[row_idx])
        
        # 计算 high4, hmax, low60, ptop, dff, pbreak
        high4 = df_all['high'].iloc[max(0, row_idx-3) : row_idx+1].max()
        hmax = df_all['high'].iloc[max(0, row_idx-9) : row_idx+1].max()
        low60 = df_all['low'].iloc[max(0, row_idx-59) : row_idx+1].min()
        ptop = df_all['close'].iloc[max(0, row_idx-4) : row_idx+1].max()
        pbreak = 1 if close >= ptop * 0.995 else 0
        dff = close - df_all['close'].iloc[row_idx - 1] if row_idx >= 1 else 0.0
        vol_ratio = 1.3
        
        if row_idx >= 9:
            ma10d = df_all['close'].iloc[max(0, row_idx-9) : row_idx+1].mean()
            ma5d = df_all['close'].iloc[max(0, row_idx-4) : row_idx+1].mean()
            vol_ma5 = df_all['vol'].iloc[max(0, row_idx-4) : row_idx+1].mean()
            
            ma60d = df_all['close'].iloc[max(0, row_idx-59) : row_idx+1].mean()
            ma60d_prev5 = df_all['close'].iloc[max(0, row_idx-63) : row_idx-3].mean() if row_idx >= 59 else close
            low_prev1 = float(df_all['low'].iloc[row_idx - 1]) if row_idx >= 1 else close
            
            sws = ma10d
            swl = ma5d
            
            if row_idx >= 14:
                sws_prev5 = df_all['close'].iloc[max(0, row_idx-14) : row_idx-4].mean()
                ma10d_prev5 = sws_prev5
                swl_prev5 = df_all['close'].iloc[max(0, row_idx-9) : row_idx-4].mean()
                ma5d_prev5 = swl_prev5
            else:
                sws_prev5 = sws
                ma10d_prev5 = ma10d
                swl_prev5 = swl
                ma5d_prev5 = ma5d
                
            today_order_target = prev_predict_ma5
            ma5_slope = (ma5d - ma5d_prev5) / 5.0 if ma5d_prev5 > 0.0 else 0.0
            prev_predict_ma5 = round(ma5d + ma5_slope, 3)
            
            if row_idx >= 24:
                ma20 = df_all['close'].iloc[row_idx-19 : row_idx+1].mean()
                ma20_prev5 = df_all['close'].iloc[row_idx-24 : row_idx-4].mean()
            else:
                ma20 = close
                ma20_prev5 = close
                
            if row_idx >= 19:
                sws_prev12 = df_all['close'].iloc[row_idx-21 : row_idx-11].mean()
                sws_max12 = sws_prev12
                for r in range(row_idx - 11, row_idx + 1):
                    sws_r = df_all['close'].iloc[r-9 : r+1].mean()
                    sws_max12 = max(sws_max12, sws_r)
                profit_band_growth = (sws_max12 - sws_prev12) / sws_prev12
            else:
                profit_band_growth = 0.0
                
            is_active_profit_band = (profit_band_growth >= 0.04)
            
            has_big_surge = False
            if row_idx >= 15:
                for r in range(row_idx - 14, row_idx + 1):
                    s_close = float(df_all['close'].iloc[r])
                    s_prev = float(df_all['close'].iloc[r-1])
                    s_pct = (s_close - s_prev) / s_prev * 100
                    if s_pct >= 6.8:
                        has_big_surge = True
                        break
            else:
                has_big_surge = True
                
            has_breakout_touch = False
            if row_idx >= 15:
                for r in range(row_idx - 14, row_idx + 1):
                    r_close = float(df_all['close'].iloc[r])
                    r_ptop = df_all['close'].iloc[max(0, r-4) : r+1].max()
                    if r_close >= r_ptop * 0.995:
                        has_breakout_touch = True
                        break
            else:
                has_breakout_touch = True
                
            is_profit_band = (sws >= sws_prev5 * 1.002) and (ma20 >= ma20_prev5 * 1.001) and is_active_profit_band and (close >= ma20 * 0.995) and has_big_surge and has_breakout_touch
            
            ma20_val = df_all['close'].iloc[max(0, row_idx-19) : row_idx+1].mean()
            std20 = df_all['close'].iloc[max(0, row_idx-19) : row_idx+1].std()
            upper = ma20_val + 2.0 * std20 if row_idx >= 19 else close * 1.10
            
            vol_shrink_3d = (vol_curr < vol_ma5 * 0.90)
            
            body_len = abs(close - open_p)
            shadow_len = high_p - low_price
            is_doji = False
            if shadow_len > 0:
                if (body_len / shadow_len <= 0.3) or (body_len / close <= 0.01):
                    is_doji = True
            else:
                is_doji = True
                
            is_pullback_support = (low_price <= sws * 1.015) and (close >= sws * 0.985)
            
            touch_upper_days = 0
            for r in range(row_idx - 7, row_idx + 1):
                if r >= 19:
                    r_close = float(df_all['close'].iloc[r])
                    r_high = float(df_all['high'].iloc[r])
                    r_ma20 = df_all['close'].iloc[r-19 : r+1].mean()
                    r_std20 = df_all['close'].iloc[r-19 : r+1].std()
                    r_upper = r_ma20 + 2.0 * r_std20
                else:
                    r_upper = float(df_all['close'].iloc[r]) * 1.10
                    r_close = float(df_all['close'].iloc[r])
                    r_high = float(df_all['high'].iloc[r])
                if r_close >= r_upper * 0.99 or r_high >= r_upper * 0.99:
                    touch_upper_days += 1
            is_collecting_stage = (touch_upper_days >= 2)
            
            min_close_15 = float(df_all['close'].iloc[max(0, row_idx-14) : row_idx+1].min())
            max_close_15 = float(df_all['close'].iloc[max(0, row_idx-14) : row_idx+1].max())
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
            ma5d = close
            ma5d_prev5 = close
            ma60d = close
            ma60d_prev5 = close
            low_prev1 = close
            today_order_target = None
            prev_predict_ma5 = close

        reentry_tracker.update_price(code, close)

        if has_position:
            days_held += 1
            max_high_since_entry = max(max_high_since_entry, close)
            pnl_pct = (close - entry_price) / entry_price * 100
            high_prev1 = float(df_all['high'].iloc[row_idx - 1]) if row_idx >= 1 else close
            high_prev2 = float(df_all['high'].iloc[row_idx - 2]) if row_idx >= 2 else close
            high_prev3 = float(df_all['high'].iloc[row_idx - 3]) if row_idx >= 3 else close
            close_prev1 = float(df_all['close'].iloc[row_idx - 1]) if row_idx >= 1 else close
            open_prev1 = float(df_all['open'].iloc[row_idx - 1]) if row_idx >= 1 else close

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
                    "sws_prev5": sws_prev5,
                    "swl": swl,
                    "swl_prev5": swl_prev5,
                    "vol_ma5": vol_ma5,
                    "ma10d": ma10d,
                    "ma10d_prev5": ma10d_prev5,
                    "ma5d": ma5d,
                    "ma5d_prev5": ma5d_prev5,
                    "ma60d": ma60d,
                    "ma60d_prev5": ma60d_prev5,
                    "low_prev1": low_prev1,
                    "setup": current_setup,
                    "regime": "SWING_LOW_BUY" if is_swing_low_mode else "BREAKOUT_ALLOWED",
                    "tp_triggered": tp_triggered,
                    "is_swing_low_mode": is_swing_low_mode,
                    "raw_reason": "持仓状态动态决策",
                    "high_prev1": high_prev1,
                    "high_prev2": high_prev2,
                    "high_prev3": high_prev3,
                    "close_prev1": close_prev1,
                    "open_prev1": open_prev1,
                    "open": open_p,
                }
            )

            intent = decide(sig, "IN_TRADE")
            if intent.reason and intent.reason.setup:
                current_setup = intent.reason.setup
            
            # 👑 策略分支自适应动态路由流转检测
            active_branch_name = getattr(intent.reason, "routed_branch", "UnknownBranch")
            if 'last_branch_name' not in locals() or last_branch_name is None:
                last_branch_name = active_branch_name
            
            if active_branch_name != last_branch_name:
                log(f"   -> 🔄 [BRANCH ROTATE] 策略分支自适应轮转：{last_branch_name} -> {active_branch_name}")
                trade_events.append(f"分支轮转：{current_date} 策略分支自适应轮转：{last_branch_name} -> {active_branch_name}。")
                last_branch_name = active_branch_name
            
            # 👑 动态自适应防守线同步更新：如果决策大脑传回了最新的动态止损线价格，回测沙盒同步更新防线！
            if intent.stop_price and intent.stop_price > 0:
                trailing_stop = intent.stop_price
            
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
                    tp_count += 1
                    locked_pnl += pnl_pct * 0.70
                    log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 👑 [TAKE-PROFIT EVENT] 满足大周期/平台顶向上强力突破，触发逆向分批大止盈！")
                    log(f"   -> 锁定 70% 仓位高位浮盈: +{pnl_pct:.2f}% | 剩余 30% 仓位轻仓留守大格局奔跑...")
                    
                    if tp_count == 1:
                        trade_events.append(
                            f"减仓：{current_date} 大涨且伴随成交量急剧放大（大于 5 日均量 {vol_curr/vol_ma5:.1f} 倍），精准触发 [TAKE-PROFIT EVENT] 大止盈 70% 锁定利润，价格 {close:.2f} 元。 [分支策略: {active_branch_name}]"
                        )
                    else:
                        trade_events.append(
                            f"二次大止盈：{current_date} 暴拉至 {close:.2f} 元最高位时再次触发 70% 大止盈锁定超级利润。 [分支策略: {active_branch_name}]"
                        )
                    
                    _last_backtest_signals[code_clean].append({
                        "date": str(current_date),
                        "action": "SELL",
                        "price": float(close),
                        "branch": str(active_branch_name),
                        "desc": "大止盈减仓"
                    })
                continue

            # 💡 黄金低吸与主升浪回补仓位判定 (Re-entry Add Back 70%)：
            if intent.action == "ADD" and intent.size_pct == 0.70:
                old_entry_price = entry_price
                setup_name = intent.reason.setup if intent.reason else "SWS_ADD_BACK"
                
                # 挂单成交逻辑：主升浪 5 日线回补优先采用前一日计算出的理论支撑挂单价
                fill_price = close
                is_limit_order_filled = False
                if setup_name == "MA5_TREND_ADD_BACK" and today_order_target is not None:
                    if low_price <= today_order_target:
                        # 盘中向下探底回踩，挂单完美以昨日预估的今日理论支撑位置买入成交！
                        fill_price = today_order_target
                        is_limit_order_filled = True
                entry_price = (old_entry_price * 0.30 + fill_price * 0.70)
                tp_triggered = False
                trailing_stop = intent.stop_price if intent.stop_price else (sws * 0.985)
                current_stop = trailing_stop
                max_high_since_entry = max(max_high_since_entry, close)
                
                if setup_name == "MA5_TREND_ADD_BACK":
                    if is_limit_order_filled:
                        log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 🌟 [MA5-ADD-BACK EVENT] 盘中跌破预计算 5日均线 挂单价 {fill_price:.2f} 元，黄金挂单自动买入补回 70% 满仓！早低尾高吃饱！")
                        log(f"   -> 原持仓均价: {old_entry_price:.2f} 元 | 挂单补回价格: {fill_price:.2f} 元 | 加权新持仓均价: {entry_price:.2f} 元 | 新 MA5 防线: {current_stop:.2f} 元")
                        trade_events.append(
                            f"回补：{current_date} 盘前预计算理论 MA5 挂单，盘中成功以挂单价 {fill_price:.2f} 元自动补回大止盈 70% 仓位，加权拉平成本至 {entry_price:.2f} 元。 [分支策略: {active_branch_name}]"
                        )
                    else:
                        log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 🌟 [MA5-ADD-BACK EVENT] 未跌破理论挂单价，尾盘强制补回 70% 筹码！重新满仓运行！")
                        log(f"   -> 原持仓均价: {old_entry_price:.2f} 元 | 补回价格: {fill_price:.2f} 元 | 加权新持仓均价: {entry_price:.2f} 元 | 新 MA5 防线: {current_stop:.2f} 元")
                        trade_events.append(
                            f"回补：{current_date} 主升回踩 5日线尾盘补仓 {fill_price:.2f} 元，精准触发 [ADD-BACK] 补回 70% 筹码，加权拉平成本至 {entry_price:.2f} 元。 [分支策略: {active_branch_name}]"
                        )
                else:
                    log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 🌟 [ADD-BACK EVENT] 满足龙头回踩 SWS 支撑且缩量洗盘，大止盈的 70% 仓位补回！重新满仓运行！")
                    log(f"   -> 原持仓均价: {old_entry_price:.2f} 元 | 补回价格: {fill_price:.2f} 元 | 加权新持仓均价: {entry_price:.2f} 元 | 新 SWS 防线: {current_stop:.2f} 元")
                    trade_events.append(
                        f"回补：{current_date} 回踩洗盘 {fill_price:.2f} 元且成交量量缩，精准触发 [ADD-BACK] 补回 70% 筹码，加权拉平成本至 {entry_price:.2f} 元。 [分支策略: {active_branch_name}]"
                    )
                
                _last_backtest_signals[code_clean].append({
                    "date": str(current_date),
                    "action": "BUY",
                    "price": float(fill_price),
                    "branch": str(active_branch_name),
                    "desc": f"黄金加仓回补({setup_name})"
                })
                continue

            # B. T+2时间不及预期风控出局 ── 100% 平仓
            elif intent.action == "SELL" and intent.reason.setup == "T+2_EXPECTATION_FAIL":
                final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else (locked_pnl + pnl_pct)
                log(f"[DATE: {current_date}] 收盘价: {close:.2f} | ⏰ [TIME-LIMIT FAILSAFE] 买入满 2 日不及预期冲高就走！触发平仓退场。")
                log("=" * 80)
                log(f"[RE-ENTRY POSITIONS TRANSACTION COMPLETED]")
                log(f"-> 交易个股: {name} ({code})")
                log(f"-> 出局日期: {current_date} (T+{days_held})")
                log(f"-> 重新买入价格: {entry_price:.2f} 元 | 平仓价格: {close:.2f} 元")
                log(f"-> 🎯 逆向大师策略斩获最终综合盈亏率: {final_pnl:+.2f}% (大止盈已锁定)")
                log("=" * 80 + "\n")
                
                trade_events.append(
                    f"清仓平仓：{current_date} 触发 T+2 时间保护，不及预期冲高就走平仓退场，平仓价 {close:.2f} 元，综合盈亏率: {final_pnl:+.2f}%。 [分支策略: {active_branch_name}]"
                )
                
                _last_backtest_signals[code_clean].append({
                    "date": str(current_date),
                    "action": "SELL",
                    "price": float(close),
                    "branch": str(active_branch_name),
                    "desc": "T+2时间平仓"
                })
                
                has_position = False
                tp_triggered = False
                locked_pnl = 0.0
                is_swing_low_mode = False
                reentry_tracker.register_exit(code, close, exit_time=f"{current_date} 15:00:00")
                continue

            # C. 跌破弹性止损线或者 DFF 指标破位 ── 100% 物理清仓
            elif close < current_stop or (intent.action == "SELL" and intent.size_pct == 1.00):
                final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else (locked_pnl + pnl_pct)
                trigger_stop_val = current_stop if close < current_stop else close
                log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 🚨 跌破防守线 {trigger_stop_val:.2f} 元或触发破位！触发物理平仓出局。")
                log("=" * 80)
                log(f"[RE-ENTRY POSITIONS TRANSACTION COMPLETED]")
                log(f"-> 交易个股: {name} ({code})")
                log(f"-> 出局日期: {current_date}")
                log(f"-> 重新买入价格: {entry_price:.2f} 元 | 平仓价格: {close:.2f} 元")
                log(f"-> 🎯 逆向大师策略斩获最终综合盈亏率: {final_pnl:+.2f}%")
                log("=" * 80 + "\n")
                
                trade_events.append(
                    f"止损平仓：{current_date} 跌破防守线 {trigger_stop_val:.2f} 元，触发物理清仓出局，平仓价 {close:.2f} 元，最终盈亏率: {final_pnl:+.2f}%。 [分支策略: {active_branch_name}]"
                )
                
                _last_backtest_signals[code_clean].append({
                    "date": str(current_date),
                    "action": "SELL",
                    "price": float(close),
                    "branch": str(active_branch_name),
                    "desc": "防守止损平仓"
                })
                
                has_position = False
                tp_triggered = False
                locked_pnl = 0.0
                is_swing_low_mode = False
                reentry_tracker.register_exit(code, close, exit_time=f"{current_date} 15:00:00")
            else:
                current_held_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else (locked_pnl + pnl_pct)
                log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 💼 持续持仓中，综合收益: {current_held_pnl:+.2f}% | 弹性动态止损线: {current_stop:.2f} 元")
            continue

        # 组装模拟盘中行情信号，进行开仓判定
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
                "sws_prev5": sws_prev5,
                "swl": swl,
                "swl_prev5": swl_prev5,
                "vol_ma5": vol_ma5,
                "ma10d": ma10d,
                "ma10d_prev5": ma10d_prev5,
                "ma5d": ma5d,
                "ma5d_prev5": ma5d_prev5,
                "ma60d": ma60d,
                "ma60d_prev5": ma60d_prev5,
                "low_prev1": low_prev1,
                "setup": "",
                "tp_triggered": tp_triggered,
                "is_swing_low_mode": is_swing_low_mode,
                "raw_reason": "逐日回溯模拟信号"
            }
        )

        intent = decide(sig, "FLAT")

        is_reentry_triggered = getattr(intent, "is_reentry_signal", False)
        reentry_reason_str = getattr(intent.reason, "reentry_reason", "")
        is_swing_low_triggered = (intent.action == "BUY" and intent.reason.regime == "SWING_LOW_BUY")

        if is_reentry_triggered or is_swing_low_triggered:
            current_setup = intent.reason.setup if intent.reason else ""
            active_branch_name = getattr(intent.reason, "routed_branch", "UnknownBranch")
            last_branch_name = active_branch_name
            
            activated_date = current_date
            entry_price = close
            trailing_stop = intent.stop_price
            max_high_since_entry = close
            days_held = 0
            tp_triggered = False
            locked_pnl = 0.0
            is_swing_low_mode = is_swing_low_triggered
            has_position = True

            log("\n" + "*" * 80)
            if is_swing_low_triggered:
                log(f"[SWING-LOW BUY TRIGGERED SUCCESS!] | 👑 激活分支策略: {active_branch_name}")
                log(f"-> 触发个股: {name} ({code})")
                log(f"-> 触发日期: {current_date}")
                log(f"-> 激活原因: 👑 支撑低吸：{intent.reason.setup}")
                
                trade_events.append(
                    f"建仓：{current_date} 识别到缩量踩工作线，触发买入 {close:.2f} 元。 [分支策略: {active_branch_name}]"
                )
                
                _last_backtest_signals[code_clean].append({
                    "date": str(current_date),
                    "action": "BUY",
                    "price": float(close),
                    "branch": str(active_branch_name),
                    "desc": "支撑低吸建仓"
                })
            else:
                log(f"[RE-ENTRY ALERT TRIGGERED SUCCESS!] | 👑 激活分支策略: {active_branch_name}")
                log(f"-> 触发个股: {name} ({code})")
                log(f"-> 触发日期: {current_date} (距离止损平仓仅 {i - stop_idx} 个交易日)")
                log(f"-> 激活原因: {reentry_reason_str}")
                
                trade_events.append(
                    f"建仓：{current_date} 满足 Re-entry 右侧突破信号，触发买入 {close:.2f} 元。 [分支策略: {active_branch_name}]"
                )
                
                _last_backtest_signals[code_clean].append({
                    "date": str(current_date),
                    "action": "BUY",
                    "price": float(close),
                    "branch": str(active_branch_name),
                    "desc": "Re-entry突破开仓"
                })
            log(f"-> 决策动作: {intent.action} | 阶梯底仓仓位分配: {intent.size_pct * 100:.1f}%")
            log(f"-> 动态止损价设定: {intent.stop_price:.2f} 元")
            log(f"-> 最终共振置信度: {intent.confidence:.4f}")
            log("*" * 80 + "\n")
        else:
            log(f"[DATE: {current_date}] 收盘价: {close:.2f} | high4: {high4:.2f} | hmax: {hmax:.2f} | low60: {low60:.2f} | pbreak: {pbreak} | Re-entry 触发: [KEEP OBSERVING] 保持观察")

    if has_position:
        pnl_pct = (close - entry_price) / entry_price * 100
        final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else (locked_pnl + pnl_pct)
        log("=" * 80)
        log(f"[RE-ENTRY HELD UNTIL TODAY - STATUS]")
        log(f"-> 交易个股: {name} ({code})")
        log(f"-> 截止今天: {df_calendar.index[-1]}")
        log(f"-> 重新买入价格: {entry_price:.2f} 元 | 今日最新收盘: {close:.2f} 元")
        log(f"-> 🎯 依然持仓躺赢中！综合已实现+账面浮盈盈亏: {final_pnl:+.2f}%")
        log("=" * 80 + "\n")
        
        trade_events.append(
            f"持仓至今：{df_calendar.index[-1]} 最新价 {close:.2f} 元，综合已实现+账面盈亏: {final_pnl:+.2f}%。"
        )

    if not activated_date:
        log(f"\nℹ️ 标的 {code} 在观察期内行情尚未确立，继续在池中保持观察洗盘深度。\n")
        trade_events.append(f"观察：在观察期内行情尚未确立，继续在池中保持观察洗盘深度。")

    # 👑 根治主图与回测活跃分支显示漂移：在回测结束后，使用最后一天的真实行情特征与持仓状态，重新进行一次最新的策略路由寻址
    try:
        from trading_kernel.engine.decision_engine import StrategyRouter
        last_state = "IN_TRADE" if has_position else "FLAT"
        last_active_branch = StrategyRouter.route(sig, last_state, sig.features)
        _last_backtest_best_branch[code_clean] = last_active_branch.name
    except Exception as e:
        if 'active_branch_name' in locals() and active_branch_name and active_branch_name != "UnknownBranch":
            _last_backtest_best_branch[code_clean] = active_branch_name
        else:
            _last_backtest_best_branch[code_clean] = "SuperTrendMA5Branch"

    # 👑 识别倒数第一个确实属于买卖交易动作的行（建仓/回补/减仓/平仓/止损），进行极度显眼的标识
    last_trade_idx = -1
    for idx in range(len(trade_events) - 1, -1, -1):
        ev = trade_events[idx]
        if any(keyword in ev for keyword in ["建仓", "回补", "减仓", "二次大止盈", "平仓", "止损"]):
            last_trade_idx = idx
            break

    if last_trade_idx != -1:
        ev = trade_events[last_trade_idx]
        if any(kw in ev for kw in ["建仓", "回补"]):
            trade_events[last_trade_idx] = "🟢【最新买卖点决策】 " + ev
        else:
            trade_events[last_trade_idx] = "🔴【最新买卖点决策】 " + ev

    # 👑 生成最后的“整体报告”
    log("\n" + "=" * 80, is_detail=False)
    log(f"👑 【Re-entry 历史回测整体报告】 - {name} ({code})", is_detail=False)
    log("=" * 80, is_detail=False)
    if trade_events:
        for idx, ev in enumerate(trade_events, 1):
            log(f"{idx}. {ev}", is_detail=False)
    else:
        log("（未触发任何实质交易动作）", is_detail=False)
    log("=" * 80, is_detail=False)

    # 👑 动态增加当前战术状态与活跃分支策略的极速透传展示区块
    current_branch = _last_backtest_best_branch.get(code_clean, "SuperTrendMA5Branch")
    log("👑 【当前战术状态与活跃分支策略】", is_detail=False)
    log("-" * 80, is_detail=False)
    if has_position:
        log(f"▶ 战术状态: 💼 正在持仓中 (筹码做T滚动持股中)", is_detail=False)
        log(f"▶ 活跃分支: 🧡 {current_branch} (当前主图策略推荐分支)", is_detail=False)
    else:
        log(f"▶ 战术状态: 📊 保持空仓观察 (KEEP OBSERVING)", is_detail=False)
        log(f"▶ 观察队列: ⏳ 正在对齐主力 12日防踏空右侧抢回防线", is_detail=False)
    log("=" * 80 + "\n", is_detail=False)

    return output.getvalue()

def run_backtest_for_code(code: str, name: str):
    """供命令行直接执行输出"""
    from JohnsonUtil.commonTips import timed_ctx
    with timed_ctx(f"Re-entry Backtest {code}", warn_ms=300):
        report = run_backtest_and_get_report(code, name, only_report=True)
    print(report)

if __name__ == "__main__":
    # 执行测试用户指定的个股：蓝色光标 (300058)
    run_backtest_for_code("300058", "蓝色光标")
    run_backtest_for_code("603533", "掌阅科技")
    run_backtest_for_code("301071", "力量钻石")
    
    # 👑 同时测试通富微电 (002156)，展示筹码收集期回踩与大涨回落 SWS 整固两段大师低吸策略的极致效果
    run_backtest_for_code("002156", "通富微电")
    
    # 👑 百合花 (603823) 的超强 5日均线主升浪行情
    run_backtest_for_code("603823", "百合花")
