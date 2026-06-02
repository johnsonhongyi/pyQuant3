import os
import sys
import json
import pandas as pd
from datetime import datetime

# Add base path to import project modules
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from sys_utils import get_base_path, get_app_root, resolve_stock_name
    pkg_dir = get_base_path()
except Exception:
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
if pkg_dir not in sys.path:
    sys.path.append(pkg_dir)

from logger_utils import LoggerFactory
logger = LoggerFactory.getLogger("PremarketAnalyzer")

from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df
from trading_kernel.engine.decision_engine import decide
from trading_kernel.core.signal import StrategySignal

def get_branch_cn(branch_name: str) -> str:
    """Map strategy branch names to intuitive Chinese names."""
    name_map = {
        "SuperTrendMA5Branch": "5日线主升浪",
        "SuperTrendMA10Branch": "10日线趋势",
        "SwsPullbackBranch": "SWS盈利线低吸",
        "TrendMA60Branch": "60日线生死防守",
        "OscillatingBreakdownBranch": "破位高位防震"
    }
    return name_map.get(branch_name, branch_name)

def run_premarket_diagnose() -> list:
    """
    Run pre-market diagnostics for all current holdings in paper_account_state.json.
    Computes support, resistance, predicted MA5 (today's recommended price), and active strategy decisions.
    Saves results to logs/premarket_diagnose.json.
    """
    logger.info("Starting pre-market diagnostics...")
    
    # 1. Load holdings from paper_account_state.json
    state_file = os.path.join(get_app_root(), "logs", "paper_account_state.json")
    if not os.path.exists(state_file):
        logger.warning(f"Account state file not found: {state_file}. Generating mock diagnostics...")
        # fallback to an empty or default structure
        positions = {}
    else:
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                positions = state_data.get("positions", {})
        except Exception as e:
            logger.error(f"Failed to load paper_account_state.json: {e}")
            positions = {}

    diagnostics = []
    
    if not positions:
        logger.warning("No positions found to diagnose. Using a watchlist or fallback sample stock list.")
        # Fallback list of typical watchlist stocks to avoid empty view
        fallback_codes = {
            "300058": "蓝色光标",
            "002156": "通富微电",
            "603823": "百合花",
            "301071": "力量钻石",
            "603533": "掌阅科技"
        }
        for code, name in fallback_codes.items():
            positions[code] = {
                "code": code,
                "entry_price": 0.0,
                "volume": 0.0,
                "current_price": 0.0,
                "entry_time": "N/A",
                "is_fallback": True
            }

    # 2. Iterate and analyze each stock
    for code, pos in positions.items():
        # Strip any emojis from code just in case
        code_clean = str(code).strip()
        for icon in ['🔴', '🟢', '📊', '⚠️', '👑']:
            code_clean = code_clean.replace(icon, '').strip()
        code_clean = code_clean.zfill(6)

        name = pos.get("name")
        name_clean = ""
        if name:
            name_clean = str(name).strip()
            for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠', '👑']:
                name_clean = name_clean.replace(icon, '').strip()
            if name_clean.startswith("回测_"):
                name_clean = name_clean[3:].strip()

        if not name_clean or name_clean.isdigit() or name_clean == code_clean or name_clean.startswith("个股_"):
            name = resolve_stock_name(code_clean)

        logger.debug(f"Analyzing {name} ({code_clean})...")
        
        df = get_tdx_Exp_day_to_df(code_clean)
        if df is None or df.empty:
            logger.warning(f"No historical K-line data for {code_clean}. Skipping...")
            continue
            
        if len(df) < 5:
            logger.warning(f"Insufficient historical data ({len(df)} days) for {code_clean}. Skipping...")
            continue

        # Extract latest metrics as of yesterday's close
        close = float(df['close'].iloc[-1])
        low_price = float(df['low'].iloc[-1])
        high_price = float(df['high'].iloc[-1])
        vol_curr = float(df['vol'].iloc[-1])
        
        # Bollinger Bands (ma20 + 2 * std20)
        if len(df) >= 20:
            ma20 = df['close'].iloc[-20:].mean()
            std20 = df['close'].iloc[-20:].std()
            upper = ma20 + 2 * std20
        else:
            upper = close * 1.08
            
        dff = close - df['close'].iloc[-2] if len(df) >= 2 else 0.0
        
        high4 = df['high'].iloc[-4:].max()
        hmax = df['high'].iloc[-10:].max()
        low60 = df['low'].iloc[-60:].min() if len(df) >= 60 else df['low'].min()
        ptop = df['close'].iloc[-5:].max()
        pbreak = (close >= ptop * 0.995)
        
        vol_ma5 = df['vol'].iloc[-5:].mean()
        vol_ratio = vol_curr / vol_ma5 if vol_ma5 > 0 else 1.0
        
        vol_shrink_3d = False
        if len(df) >= 3:
            vol_shrink_3d = (float(df['vol'].iloc[-1]) < float(df['vol'].iloc[-2]) < float(df['vol'].iloc[-3]))
            
        sws = df['close'].iloc[-10:].mean()
        sws_prev5 = df['close'].iloc[-14:-4].mean() if len(df) >= 14 else sws
        
        swl = df['close'].iloc[-60:].mean() if len(df) >= 60 else df['close'].mean()
        swl_prev5 = df['close'].iloc[-64:-4].mean() if len(df) >= 64 else swl
        
        ma10d = df['close'].iloc[-10:].mean()
        ma10d_prev5 = df['close'].iloc[-14:-4].mean() if len(df) >= 14 else ma10d
        
        ma5d = df['close'].iloc[-5:].mean()
        ma5d_prev1 = df['close'].rolling(5).mean().iloc[-2] if len(df) >= 6 else ma5d
        ma5d_prev5 = df['close'].iloc[-9:-4].mean() if len(df) >= 9 else ma5d
        
        ma60d = df['close'].iloc[-60:].mean() if len(df) >= 60 else df['close'].mean()
        ma60d_prev5 = df['close'].iloc[-64:-4].mean() if len(df) >= 64 else ma60d
        
        low_prev1 = float(df['low'].iloc[-2]) if len(df) >= 2 else low_price
        
        is_pullback_support = (low_price <= sws * 1.015 and close >= sws * 0.985)
        is_collecting_stage = (sws >= sws_prev5 * 0.995)
        is_consolidation_stage = (abs(close - sws) / sws <= 0.04)
        
        open_curr = float(df['open'].iloc[-1])
        is_doji = (abs(close - open_curr) / open_curr <= 0.008) if open_curr > 0 else False
        
        # Today's predicted MA5 support using slope extrapolation
        ma5_slope = ma5d - ma5d_prev1
        predicted_ma5 = ma5d + ma5_slope
        
        # Position holdings information
        entry_price = float(pos.get("entry_price", 0.0))
        volume = float(pos.get("volume", 0.0))
        pnl_pct = ((close - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
        days_held = 1.0 # default diagnostic step
        
        # Construct yesterday's features signal
        sig = StrategySignal(
            code=code_clean,
            name=name,
            ts=datetime.now().strftime("%Y-%m-%d 09:10:00"),
            source="PREMARKET_DIAGNOSE",
            signal_type="HOLDING" if entry_price > 0 else "PULLBACK",
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
                "days_held": days_held,
                "pnl_pct": pnl_pct,
                "vol_shrink_3d": vol_shrink_3d,
                "is_pullback_support": is_pullback_support,
                "is_collecting_stage": is_collecting_stage,
                "is_consolidation_stage": is_consolidation_stage,
                "is_doji": is_doji,
                "upper": upper,
                "max_pnl_since_entry": pnl_pct if pnl_pct > 0 else 0.0,
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
                "tp_triggered": False,
                "is_swing_low_mode": False,
                "raw_reason": "盘前持仓个股体检",
                "open": open_curr,
            }
        )
        
        # Decide tactical guidance
        state = "IN_TRADE" if entry_price > 0 else "FLAT"
        intent = decide(sig, state)
        
        active_branch = getattr(intent.reason, "routed_branch", "SuperTrendMA5Branch")
        branch_cn = get_branch_cn(active_branch)
        action = intent.action
        
        action_map = {
            "BUY": "买入建仓",
            "SELL": "分批大止盈",
            "ADD": "做T回补",
            "FLAT": "保持观察"
        }
        action_cn = action_map.get(action, "保持观察")
        
        # Support & Defensive values
        stop_price = intent.stop_price if intent.stop_price else (sws * 0.985)
        
        # Construct summary advice
        advice = {
            "code": code_clean,
            "name": name,
            "timestamp": datetime.now().strftime("%Y-%m-%d"),
            "entry_price": round(entry_price, 2),
            "volume": round(volume, 0),
            "close": round(close, 2),
            "predicted_ma5": round(predicted_ma5, 2),
            "upper_boll": round(upper, 2),
            "sws_support": round(sws, 2),
            "hard_stop": round(stop_price, 2),
            "suggest_action": action,
            "action_cn": action_cn,
            "size_pct": round(intent.size_pct or 0.0, 2),
            "active_branch": active_branch,
            "branch_cn": branch_cn,
            "reason": getattr(intent.reason, "raw_reason", "策略条件诊断中...")
        }
        diagnostics.append(advice)

    # 3. Persistent save
    output_file = os.path.join(get_app_root(), "logs", "premarket_diagnose.json")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(diagnostics, f, indent=4, ensure_ascii=False)
        logger.info(f"Premarket diagnostics successfully saved to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save premarket_diagnose.json: {e}")

    return diagnostics

if __name__ == "__main__":
    run_premarket_diagnose()
