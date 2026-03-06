import sqlite3
from trading_hub import get_trading_hub
from datetime import datetime, timedelta

def setup_test_data():
    hub = get_trading_hub()
    conn = sqlite3.connect(hub.signal_db)
    c = conn.cursor()
    
    # 清空当前队列以进行干净的测试
    c.execute("DELETE FROM follow_queue WHERE status NOT IN ('EXITED', 'CANCELLED')")
    
    now = datetime.now()
    # 插入 150 条记录
    # 50条 STALE (最先被清理)
    for i in range(50):
        code = f"STALE_{i:04d}"
        c.execute("INSERT INTO follow_queue (code, name, status, priority, detected_date) VALUES (?, ?, ?, ?, ?)",
                 (code, f"S_{i}", 'STALE', 1, (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')))
        
    # 100条 TRACKING
    for i in range(100):
        code = f"TRACK_{i:04d}"
        c.execute("INSERT INTO follow_queue (code, name, status, priority, detected_date) VALUES (?, ?, ?, ?, ?)",
                 (code, f"T_{i}", 'TRACKING', 5, now.strftime('%Y-%m-%d %H:%M:%S')))
    
    conn.commit()
    conn.close()
    print("Test data setup done: 50 STALE, 100 TRACKING (Total 150 active)")

def run_cleanup():
    hub = get_trading_hub()
    results = hub.cleanup_stale_signals(max_days=2)
    print(f"Cleanup results: CANCELLED={len(results['CANCEL_SIGNAL'])}, STALE={len(results['STALE_SIGNAL'])}")
    
    conn = sqlite3.connect(hub.signal_db)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM follow_queue WHERE status NOT IN ('EXITED', 'CANCELLED')")
    count = c.fetchone()[0]
    conn.close()
    print(f"Final active count: {count}")
    return count

if __name__ == "__main__":
    setup_test_data()
    final_count = run_cleanup()
    if final_count == 100:
        print("✅ VERIFICATION SUCCESS: Queue limited to 100.")
    else:
        print(f"❌ VERIFICATION FAILED: Queue size is {final_count}, expected 100.")
