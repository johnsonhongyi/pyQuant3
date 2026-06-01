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

def get_branch_cn(branch_name: str) -> str:
    """策略分支英文类名向直观中文名称的映射"""
    name_map = {
        "SuperTrendMA5Branch": "5日线主升浪",
        "SuperTrendMA10Branch": "10日线趋势",
        "SwsPullbackBranch": "SWS盈利线低吸",
        "TrendMA60Branch": "60日线生死防守",
        "OscillatingBreakdownBranch": "破位高位防震"
    }
    return name_map.get(branch_name, branch_name)


def update_premarket_diagnose_json(code_clean: str, name: str, close_val: float, predicted_ma5: float, upper_val: float, sws_support: float, stop_price: float, action: str, action_cn: str, branch: str, branch_cn: str, reason: str, has_position: bool, entry_price: float = 0.0):
    """
    将手动回测个股当前的的操作机会与战术交易计划更新或追加到 logs/premarket_diagnose.json 中。
    """
    import os
    import json
    try:
        from sys_utils import get_base_path
        base_dir = get_base_path()
    except Exception:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if not name or str(name).startswith("个股_"):
        # Look up from top_all.h5 to get the real stock name
        try:
            import pandas as pd
            for path in [r'g:\top_all.h5', os.path.join(base_dir, 'top_all.h5'), os.path.join(os.getcwd(), 'top_all.h5')]:
                if os.path.exists(path):
                    df_top = pd.read_hdf(path, 'top_all')
                    if not df_top.empty:
                        code_zfill = code_clean.zfill(6)
                        if df_top.index.name == 'code' and code_zfill in df_top.index:
                            name = df_top.loc[code_zfill, 'name']
                            break
                        elif 'code' in df_top.columns:
                            matched = df_top[df_top['code'].astype(str).str.zfill(6) == code_zfill]
                            if not matched.empty:
                                name = matched.iloc[0]['name']
                                break
                        else:
                            idx_str = df_top.index.astype(str).str.zfill(6)
                            if code_zfill in idx_str.values:
                                name = df_top.loc[df_top.index.astype(str).str.zfill(6) == code_zfill, 'name'].iloc[0]
                                break
        except Exception:
            pass

    filepath = os.path.join(base_dir, "logs", "premarket_diagnose.json")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    diagnostics = []
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                diagnostics = json.load(f)
                if not isinstance(diagnostics, list):
                    diagnostics = []
        except Exception as e:
            print(f"📡 Error loading premarket_diagnose.json: {e}")
            diagnostics = []
            
    # 构建新的战术作战计划
    advice = {
        "code": code_clean,
        "name": name,
        "entry_price": round(entry_price, 2),
        "volume": 0.0,
        "close": round(close_val, 2),
        "predicted_ma5": round(predicted_ma5, 2),
        "upper_boll": round(upper_val, 2),
        "sws_support": round(sws_support, 2),
        "hard_stop": round(stop_price, 2),
        "suggest_action": action,
        "action_cn": action_cn,
        "size_pct": 0.70 if action in ["BUY", "ADD"] else 0.0,
        "active_branch": branch,
        "branch_cn": branch_cn,
        "reason": reason
    }
    
    # 查找并更新
    updated = False
    for idx, d in enumerate(diagnostics):
        d_code = d.get("code", "")
        # Clean emoji just in case
        for icon in ['🔴', '🟢', '📊', '⚠️']:
            d_code = d_code.replace(icon, '').strip()
        if d_code == code_clean:
            diagnostics[idx] = advice
            updated = True
            break
            
    if not updated:
        diagnostics.append(advice)
        
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(diagnostics, f, indent=4, ensure_ascii=False)
        print(f"📡 [BACKTEST-GUIDANCE] Successfully added/updated {name} ({code_clean}) plan in {filepath}")
    except Exception as e:
        print(f"📡 [BACKTEST-GUIDANCE] Failed to save premarket_diagnose.json: {e}")


_is_router_loaded = False

def run_backtest_and_get_report(code: str, name: str, only_report: bool = True, resample: str = "d") -> str:
    """运行指定个股 of Re-entry 历史回测，并以字符串形式返回完整的日志及整体总结报告。"""
    global _is_router_loaded
    code_clean = code.strip()
    for icon in ['🔴', '🟢', '📊', '⚠️']:
        code_clean = code_clean.replace(icon, '').strip()
    _last_backtest_signals[code_clean] = []
    _last_backtest_best_branch[code_clean] = "SuperTrendMA5Branch"
    
    # ── 从 global.ini 动态灌入 StrategyRouter 静态路由表 (全局仅载入一次) ──
    if not _is_router_loaded:
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
            _is_router_loaded = True
        except Exception:
            pass

    output = io.StringIO()
    def log(msg="", is_detail=True):
        if only_report and is_detail:
            return
        output.write(str(msg) + "\n")
        
    log("=" * 80)
    log(f"Re-entry 策略历史回溯模拟盘开始：个股 {name} ({code}) | 周期: {resample}")
    log("=" * 80)

    # 1. 物理加载 TDX 历史日线数据
    df = get_tdx_Exp_day_to_df(code_clean, resample=resample)
    if df is None or df.empty:
        log("【ERROR】未能在系统数据库或 TDX 本地缓存中检索到该个股的历史日线数据。")
        return output.getvalue()
    
    # 过滤 2026 年以来的数据作为历史回测观察区间
    df_calendar = df[df.index >= '2026-04-01']
    if df_calendar.empty:
        log("【ERROR】筛选 2026-04-01 之后的交易历史数据为空，无法执行回测。")
        return output.getvalue()

    log(f"-> 成功加载历史数据，回测区间: {df_calendar.index[0]} 至 {df_calendar.index[-1]} | 共 {len(df_calendar)} 个交易日")

    # 2. 初始化回测沙盒与状态追踪器
    has_position = False
    entry_price = 0.0
    trailing_stop = 0.0
    current_stop = 0.0
    max_high_since_entry = 0.0
    days_held = 0
    tp_triggered = False
    tp_count = 0
    locked_pnl = 0.0
    is_swing_low_mode = False
    current_setup = ""
    last_branch_name = None
    
    # 挂单参数缓存：预测明日挂单价
    prev_predict_ma5 = None
    today_order_target = None
    
    trade_events = []
    activated_date = None
    stop_idx = 0
 
    reentry_tracker.clear()
 
    # 3. 逐日滚动模拟行情演进
    start_idx = df.index.get_loc(df_calendar.index[0])
    
    for i in range(1, len(df_calendar)):
        current_date = df_calendar.index[i]
        row_idx = start_idx + i
        
        # 提取当前交易日的量价及技术指标特征 (局部视口切片计算，绝无未来数据，且比重新截取 df_curr 性能高出数倍)
        close = float(df['close'].iloc[row_idx])
        low_price = float(df['low'].iloc[row_idx])
        high_price = float(df['high'].iloc[row_idx])
        vol_curr = float(df['vol'].iloc[row_idx])
        
        # 计算布林带、主力工作线（SWS）及均线斜率特征
        if row_idx >= 19:
            ma20 = df['close'].iloc[row_idx-19 : row_idx+1].mean()
            std20 = df['close'].iloc[row_idx-19 : row_idx+1].std()
            upper = ma20 + 2 * std20
        else:
            upper = close * 1.08
            
        dff = close - df['close'].iloc[row_idx - 1] if row_idx >= 1 else 0.0
        
        high4 = df['high'].iloc[max(0, row_idx-3) : row_idx+1].max()
        hmax = df['high'].iloc[max(0, row_idx-9) : row_idx+1].max()
        low60 = df['low'].iloc[max(0, row_idx-59) : row_idx+1].min()
        ptop = df['close'].iloc[max(0, row_idx-4) : row_idx+1].max()
        pbreak = (close >= ptop * 0.995)
        
        vol_ma5 = df['vol'].iloc[max(0, row_idx-4) : row_idx+1].mean()
        vol_ratio = vol_curr / vol_ma5 if vol_ma5 > 0 else 1.0
        
        # 近3日是否缩量
        if row_idx >= 2:
            vol_shrink_3d = (float(df['vol'].iloc[row_idx]) < float(df['vol'].iloc[row_idx - 1]) < float(df['vol'].iloc[row_idx - 2]))
        else:
            vol_shrink_3d = False
            
        sws = df['close'].iloc[max(0, row_idx-9) : row_idx+1].mean()
        sws_prev5 = df['close'].iloc[max(0, row_idx-13) : row_idx-3].mean() if row_idx >= 9 else sws
        
        swl = df['close'].iloc[max(0, row_idx-59) : row_idx+1].mean()
        swl_prev5 = df['close'].iloc[max(0, row_idx-63) : row_idx-3].mean() if row_idx >= 9 else swl
        
        ma10d = df['close'].iloc[max(0, row_idx-9) : row_idx+1].mean()
        ma10d_prev5 = df['close'].iloc[max(0, row_idx-13) : row_idx-3].mean() if row_idx >= 9 else ma10d
        
        ma5d = df['close'].iloc[max(0, row_idx-4) : row_idx+1].mean()
        ma5d_prev5 = df['close'].iloc[max(0, row_idx-8) : row_idx-3].mean() if row_idx >= 4 else ma5d
        
        ma60d = df['close'].iloc[max(0, row_idx-59) : row_idx+1].mean()
        ma60d_prev5 = df['close'].iloc[max(0, row_idx-63) : row_idx-3].mean() if row_idx >= 59 else ma60d
        
        low_prev1 = float(df['low'].iloc[row_idx - 1]) if row_idx >= 1 else low_price
        
        is_pullback_support = (low_price <= sws * 1.015 and close >= sws * 0.985)
        is_collecting_stage = (sws >= sws_prev5 * 0.995)
        is_consolidation_stage = (abs(close - sws) / sws <= 0.04)
        
        open_curr = float(df['open'].iloc[row_idx])
        is_doji = (abs(close - open_curr) / open_curr <= 0.008) if open_curr > 0 else False

        # 👑 在循环最顶部：注入盘前预计算理论支撑价逻辑，防止 continue 导致预测脱节
        today_order_target = prev_predict_ma5
        
        # 斜率外推算法：根据今日的 ma5 以及斜率预测明天的 ma5 理论支撑位
        if row_idx >= 4:
            ma5_today = ma5d
            ma5_prev1 = float(df['ma5d'].iloc[row_idx - 1])
            ma5_slope = ma5_today - ma5_prev1
            prev_predict_ma5 = ma5_today + ma5_slope
        else:
            prev_predict_ma5 = close

        if has_position:
            days_held += 1
            max_high_since_entry = max(max_high_since_entry, close)
            pnl_pct = (close - entry_price) / entry_price * 100
            high_prev1 = float(df['high'].iloc[row_idx - 1]) if row_idx >= 1 else close
            high_prev2 = float(df['high'].iloc[row_idx - 2]) if row_idx >= 2 else close
            high_prev3 = float(df['high'].iloc[row_idx - 3]) if row_idx >= 3 else close
            close_prev1 = float(df['close'].iloc[row_idx - 1]) if row_idx >= 1 else close
            open_prev1 = float(df['open'].iloc[row_idx - 1]) if row_idx >= 1 else close

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
                    "open": float(df['open'].iloc[row_idx]),
                }
            )

            intent = decide(sig, "IN_TRADE")
            if intent.reason and intent.reason.setup:
                current_setup = intent.reason.setup
            
            # 👑 策略分支自适应动态路由流转检测
            active_branch_name = getattr(intent.reason, "routed_branch", "UnknownBranch")
            _last_backtest_best_branch[code_clean] = active_branch_name
            if last_branch_name is None:
                last_branch_name = active_branch_name
            
            if active_branch_name != last_branch_name:
                log(f"   -> 🔄 [BRANCH ROTATE] 策略轮转：{get_branch_cn(last_branch_name)} -> {get_branch_cn(active_branch_name)}")
                trade_events.append(f"分支轮转：{current_date} 策略轮转：{get_branch_cn(active_branch_name)}")
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
                    log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 👑 [TAKE-PROFIT EVENT] 满足大周期突破，触发逆向分批大止盈！")
                    
                    if tp_count == 1:
                        trade_events.append(
                            f"减仓：{current_date} 满足平台顶大止盈 70% 锁定利润，价格 {close:.2f} 元 [分支策略: {get_branch_cn(active_branch_name)}]"
                        )
                    else:
                        trade_events.append(
                            f"二次大止盈：{current_date} 暴拉至 {close:.2f} 元再次触发 70% 大止盈 [分支策略: {get_branch_cn(active_branch_name)}]"
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
                        fill_price = today_order_target
                        is_limit_order_filled = True
                entry_price = (old_entry_price * 0.30 + fill_price * 0.70)
                tp_triggered = False
                trailing_stop = intent.stop_price if intent.stop_price else (sws * 0.985)
                current_stop = trailing_stop
                max_high_since_entry = max(max_high_since_entry, close)
                
                if setup_name == "MA5_TREND_ADD_BACK":
                    if is_limit_order_filled:
                        log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 👑 [MA5-ADD-BACK EVENT] 盘中跌破预计算理论5日线挂单价 {fill_price:.2f} 元，自动买入回补 70% 满仓！")
                        trade_events.append(
                            f"回补：{current_date} 盘中自动按 5日线 挂单价 {fill_price:.2f} 元回补 70% 仓位，加权成本 {entry_price:.2f} 元 [分支策略: {get_branch_cn(active_branch_name)}]"
                        )
                    else:
                        log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 👑 [MA5-ADD-BACK EVENT] 未跌破理论挂单价，尾盘强制补仓 70%！")
                        trade_events.append(
                            f"回补：{current_date} 尾盘踩 5日线 回补 70% 仓位，加权成本 {entry_price:.2f} 元 [分支策略: {get_branch_cn(active_branch_name)}]"
                        )
                else:
                    log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 👑 [ADD-BACK EVENT] 满足龙头回踩支撑，大止盈 70% 仓位回补！")
                    trade_events.append(
                        f"回补：{current_date} 缩量回踩工作线回补 70% 仓位，加权成本 {entry_price:.2f} 元 [分支策略: {get_branch_cn(active_branch_name)}]"
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
                log(f"[DATE: {current_date}] 收盘价: {close:.2f} | ⚠️ [TIME-LIMIT FAILSAFE] 买入满 2 日不及预期，触发平仓退场。")
                
                trade_events.append(
                    f"清仓平仓：{current_date} 触发 T+2 冲高不及预期平仓退场，平仓价 {close:.2f} 元，盈亏 {final_pnl:+.2f}% [分支策略: {get_branch_cn(active_branch_name)}]"
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

            # C. 跌破弹性止损线或 DFF 指标破位 ── 100% 物理清仓
            elif close < current_stop or (intent.action == "SELL" and intent.size_pct == 1.00):
                final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else (locked_pnl + pnl_pct)
                trigger_stop_val = current_stop if close < current_stop else close
                log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 🚨 跌破防守线 {trigger_stop_val:.2f} 元，触发物理清仓。")
                
                trade_events.append(
                    f"止损平仓：{current_date} 跌破防守线 {trigger_stop_val:.2f} 元物理清仓，平仓价 {close:.2f} 元，盈亏 {final_pnl:+.2f}% [分支策略: {get_branch_cn(active_branch_name)}]"
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
                continue
            else:
                current_held_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else (locked_pnl + pnl_pct)
                log(f"[DATE: {current_date}] 收盘价: {close:.2f} | 持续持仓中，综合收益: {current_held_pnl:+.2f}%")
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
        active_branch_name = getattr(intent.reason, "routed_branch", "UnknownBranch")
        _last_backtest_best_branch[code_clean] = active_branch_name

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
                log(f"[SWING-LOW BUY TRIGGERED SUCCESS!] | 激活分支策略: {active_branch_name}")
                trade_events.append(
                    f"建仓：{current_date} 缩量回踩工作线买入建仓，价格 {close:.2f} 元 [分支策略: {get_branch_cn(active_branch_name)}]"
                )
                
                _last_backtest_signals[code_clean].append({
                    "date": str(current_date),
                    "action": "BUY",
                    "price": float(close),
                    "branch": str(active_branch_name),
                    "desc": "支撑低吸建仓"
                })
            else:
                log(f"[RE-ENTRY ALERT TRIGGERED SUCCESS!] | 激活分支策略: {active_branch_name}")
                trade_events.append(
                    f"建仓：{current_date} 满足右侧突破信号建仓买入，价格 {close:.2f} 元 [分支策略: {get_branch_cn(active_branch_name)}]"
                )
                
                _last_backtest_signals[code_clean].append({
                    "date": str(current_date),
                    "action": "BUY",
                    "price": float(close),
                    "branch": str(active_branch_name),
                    "desc": "Re-entry突破建仓"
                })
            log("*" * 80 + "\n")
        else:
            log(f"[DATE: {current_date}] 收盘价: {close:.2f} | Re-entry 触发: [KEEP OBSERVING] 保持观察")

    if has_position:
        pnl_pct = (close - entry_price) / entry_price * 100
        final_pnl = (locked_pnl + pnl_pct * 0.30) if tp_triggered else (locked_pnl + pnl_pct)
        
        trade_events.append(
            f"持仓至今：{df_calendar.index[-1]} 最新价 {close:.2f} 元，综合盈亏: {final_pnl:+.2f}%"
        )

    if not activated_date:
        trade_events.append(f"观察：在观察期内行情尚未确立，继续在池中保持观察洗盘深度。")

    # 动态记录当前最推荐的超级策略分支
    if 'active_branch_name' in locals() and active_branch_name and active_branch_name != "UnknownBranch":
        _last_backtest_best_branch[code_clean] = active_branch_name

    # 识别倒数第一个确实属于买卖交易动作的行，进行高亮度加持标示
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

    # 生成最后的“整体报告”
    log("\n" + "=" * 80, is_detail=False)
    log(f"👑 【Re-entry 历史回测整体报告】 - {name} ({code})", is_detail=False)
    log("=" * 80, is_detail=False)
    if trade_events:
        for idx, ev in enumerate(trade_events, 1):
            log(f"{idx}. {ev}", is_detail=False)
    else:
        log("（未触发任何实质交易动作）", is_detail=False)
    log("=" * 80, is_detail=False)

    # 动态增加当前战术状态与活跃分支策略的独立展示区块
    current_branch = _last_backtest_best_branch.get(code_clean, "SuperTrendMA5Branch")
    log("👑 【当前战术状态与活跃分支策略】", is_detail=False)
    log("-" * 80, is_detail=False)
    if has_position:
        log(f"▶ 战术状态: 💼 正在持仓中 (筹码做T滚动持股中)", is_detail=False)
        log(f"▶ 活跃分支: 🧡 {get_branch_cn(current_branch)} (当前主图策略推荐分支)", is_detail=False)
    else:
        log(f"▶ 战术状态: 📊 保持空仓观察 (KEEP OBSERVING)", is_detail=False)
        log(f"▶ 观察队列: ⏳ 正在对齐主力 12日防踏空右侧抢回防线", is_detail=False)
    
    # 动态追加展示回测的重采样周期
    resample_labels = {'d': '日线','2d': '2日线', '3d': '3日线', 'w': '周线', 'm': '月线'}
    resample_cn = resample_labels.get(resample, resample)
    log(f"▶ 回测周期Resample: 🗓️ {resample_cn} ({resample})", is_detail=False)
    log("=" * 80 + "\n", is_detail=False)

    # 👑 联动添加/更新到每日操作指南 (open_guidance_window) 中
    try:
        latest_action = intent.action if intent else "KEEP_OBSERVING"
        # 只要当前模拟持仓中，或者有买入、回补、持股决策（即有参与价值），则追加到每日指南中
        has_value = has_position or (latest_action in ["BUY", "ADD", "HOLD"])
        if has_value:
            latest_close = float(close)
            latest_predicted_ma5 = float(prev_predict_ma5) if prev_predict_ma5 else latest_close
            latest_upper = float(upper)
            latest_sws = float(sws)
            latest_stop = float(current_stop if current_stop > 0 else (sws * 0.985))
            
            action_map = {
                "BUY": "买入建仓",
                "SELL": "分批大止盈" if (tp_triggered or (intent and intent.size_pct == 0.70)) else "清仓平仓",
                "ADD": "做T回补",
                "HOLD": "持股滚动"
            }
            action_cn = action_map.get(latest_action, "保持观察")
            if latest_action == "SELL" and intent and intent.size_pct == 1.00:
                action_cn = "清仓平仓"
                
            latest_branch = _last_backtest_best_branch.get(code_clean, "SuperTrendMA5Branch")
            branch_cn = get_branch_cn(latest_branch)
            
            latest_reason = getattr(intent.reason, "raw_reason", "手动回测智能战术决策计划") if intent and intent.reason else "手动回测智能战术决策计划"
            if has_position:
                latest_reason = f"💼 正在模拟持仓中(滚动做T)。{latest_reason}"
            else:
                latest_reason = f"📊 回测最新决策: {action_cn}。{latest_reason}"
                
            update_premarket_diagnose_json(
                code_clean=code_clean,
                name=name,
                close_val=latest_close,
                predicted_ma5=latest_predicted_ma5,
                upper_val=latest_upper,
                sws_support=latest_sws,
                stop_price=latest_stop,
                action=latest_action,
                action_cn=action_cn,
                branch=latest_branch,
                branch_cn=branch_cn,
                reason=latest_reason,
                has_position=has_position,
                entry_price=float(entry_price)
            )
    except Exception as ex:
        log(f"⚠️ [GUIDANCE-INTEGRATION] Failed to export trading plan to guidance list: {ex}", is_detail=False)

    return output.getvalue()

def run_backtest_for_code(code: str, name: str):
    """子供命令行直接执行输出"""
    from JohnsonUtil.commonTips import timed_ctx
    with timed_ctx(f"Re-entry Backtest {code}", warn_ms=300):
        report = run_backtest_and_get_report(code, name, only_report=True)
    print(report)

if __name__ == "__main__":
    # 执行测试用户指定的个股：蓝色光标 (300058)
    run_backtest_for_code("300058", "蓝色光标")
    run_backtest_for_code("603533", "掌阅科技")
    run_backtest_for_code("301071", "力量钻石")
    
    # 同时测试通富微电 (002156)
    run_backtest_for_code("002156", "通富微电")
    
    # 百合花 (603823) 的超强 5日线主升浪
    run_backtest_for_code("603823", "百合花")
