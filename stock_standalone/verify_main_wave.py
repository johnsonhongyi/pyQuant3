
from intraday_decision_engine import IntradayDecisionEngine
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)

def verify_main_wave():
    print("Verifying Main Wave Logic...")
    engine = IntradayDecisionEngine()
    
    # Test Case 1: Mode 4 Acceleration (Price > Upper)
    row_acc = {
        "code": "000001", "trade": 10.5, "open": 10.0, "high": 10.6, "low": 10.0,
        "nclose": 10.2, "amount": 1000000, "volume": 100000, "ratio": 3.0,
        "percent": 5.0, "ma5d": 10.0, "ma10d": 9.8, "ma20d": 9.5, "ma60d": 9.0
    }
    snapshot_acc = {
        "upper": 10.4, # Price 10.5 > Upper 10.4
        "last_close": 10.0,
        "win": 3,
        "red": 5,
        "sum_perc": 15,
        "cost_price": 0
    }
    debug_acc = {}
    
    print("\n--- Test Case 1: Consolidating Acceleration ---")
    # Using private method for direct test, or evaluate for full flow
    # Testing _check_acceleration_pattern directly
    if hasattr(engine, "_check_acceleration_pattern"):
        res = engine._check_acceleration_pattern(row_acc, snapshot_acc, debug_acc)
        print(f"Acceleration Result: {res}")
        if res.get("is_acc") and "站上Upper加速" in res.get("reason", ""):
            print("PASS: Mode 4 Acceleration detected.")
        else:
            print(f"FAIL: Mode 4 Acceleration NOT detected. Reason: {res.get('reason')}")
            
    # Test Case 2: Main Wave Structure Score
    # Construct data with Higher Highs and Higher Lows
    # Today: High=11, Low=10.5
    # Prev: High=10.8, Low=10.2
    # Prev2: High=10.5, Low=10.0
    row_struct = {
        "trade": 10.8, "high": 11.0, "low": 10.5, "open": 10.6,
        "lastp1d": 10.7, "lastp2d": 10.4, "lastp3d": 10.1,
        "lasth1d": 10.8, "lasth2d": 10.5, "lasth3d": 10.2,
        "lastl1d": 10.2, "lastl2d": 10.0, "lastl3d": 9.8,
        "win": 3, "red": 5, "sum_perc": 10
    }
    debug_struct = {}
    print("\n--- Test Case 2: Main Wave Structure Score ---")
    score = engine._multiday_trend_score(row_struct, debug_struct)
    print(f"Trend Score: {score}")
    print(f"Reasons: {debug_struct.get('multiday_trend_reasons')}")
    
    reasons = debug_struct.get('multiday_trend_reasons', [])
    if "主升结构(新高无新低)" in reasons:
        print("PASS: Main Wave Structure detected.")
    else:
        print("FAIL: Main Wave Structure NOT detected.")

    # Test Case 3: Verify UnboundLocalError Fix
    # Calling evaluate with minimal data to ensure it doesn't crash on 'win' check
    print("\n--- Test Case 3: Regression Test for UnboundLocalError ---")
    try:
        row_reg = {"code": "000002", "trade": 10, "ma5d": 9, "ma10d": 8, "open": 9.9, "low": 9.8, "high": 10.1}
        snap_reg = {"win": 1, "red": 1} # Not enough for acceleration, but should run
        engine.evaluate(row_reg, snap_reg, mode="full")
        print("PASS: evaluate() ran without UnboundLocalError.")
    except Exception as e:
        print(f"FAIL: evaluate() crashed: {e}")

if __name__ == "__main__":
    verify_main_wave()
