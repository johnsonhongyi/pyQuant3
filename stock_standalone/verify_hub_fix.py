import sys
import os
import sqlite3
from datetime import datetime

# Add the project directory to sys.path
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')

from trading_hub import get_trading_hub

def test_fix():
    hub = get_trading_hub()
    code = "TEST_CODE_FIX"
    
    print(f"Using DB: {hub.signal_db}")
    
    # 0. Setup test data
    conn = sqlite3.connect(hub.signal_db)
    conn.execute("DELETE FROM follow_queue WHERE code=?", (code,))
    conn.execute("INSERT INTO follow_queue (code, status, detected_date) VALUES (?, ?, ?)", 
                 (code, "TRACKING", "2026-01-26"))
    conn.commit()
    conn.close()

    print("\nTest 1: Updating only notes (the scenario causing the error)...")
    try:
        success = hub.update_follow_status(code, notes="New Test Note Only")
        print(f"Success: {success}")
        # Verify in DB
        conn = sqlite3.connect(hub.signal_db)
        res = conn.execute("SELECT status, notes FROM follow_queue WHERE code=?", (code,)).fetchone()
        conn.close()
        print(f"DB Result: status={res[0]}, notes={res[1]}")
        assert res[0] == "TRACKING"
        assert res[1] == "New Test Note Only"
        print("Test 1 PASSED")
    except Exception as e:
        print(f"Test 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\nTest 2: Updating both status and notes (backward compatibility)...")
    try:
        success = hub.update_follow_status(code, "READY", notes="Ready to buy now")
        print(f"Success: {success}")
        # Verify in DB
        conn = sqlite3.connect(hub.signal_db)
        res = conn.execute("SELECT status, notes FROM follow_queue WHERE code=?", (code,)).fetchone()
        conn.close()
        print(f"DB Result: status={res[0]}, notes={res[1]}")
        assert res[0] == "READY"
        assert res[1] == "Ready to buy now"
        print("Test 2 PASSED")
    except Exception as e:
        print(f"Test 2 FAILED: {e}")
        return

    print("\nTest 3: Updating only status...")
    try:
        success = hub.update_follow_status(code, "ENTERED")
        print(f"Success: {success}")
        # Verify in DB
        conn = sqlite3.connect(hub.signal_db)
        res = conn.execute("SELECT status, notes FROM follow_queue WHERE code=?", (code,)).fetchone()
        conn.close()
        print(f"DB Result: status={res[0]}, notes={res[1]}")
        assert res[0] == "ENTERED"
        assert res[1] == "Ready to buy now" # notes should remain
        print("Test 3 PASSED")
    except Exception as e:
        print(f"Test 3 FAILED: {e}")
        return

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_fix()
