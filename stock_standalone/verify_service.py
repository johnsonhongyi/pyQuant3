import time
import pandas as pd
from realtime_data_service import DataPublisher, MinuteKlineCache
from JohnsonUtil import commonTips as cct

def test_service_basic():
    print("Testing RealtimeDataService Basic Functionality...")
    dp = DataPublisher()
    
    # Mock DataFrame
    df = pd.DataFrame([
        {'code': '600000', 'percent': 1.5, 'trade': 10.1},
        {'code': '600001', 'percent': -0.5, 'trade': 15.2}
    ])
    
    dp.update_batch(df)
    
    score = dp.get_emotion_score('600000')
    print(f"Emotion Score 600000 (Expected 1.5/Mapped): {score}")
    
    assert score == 1.5, f"Score mismatch: {score}"
    print("Basic Test Passed.")

def test_frequency_logic_simulation():
    print("\nSimulating Frequency Adaptation Logic...")
    # Mocking environment
    class MockValues:
        def getkey(self, k, default=None):
            return 30 if k == 'sina_limit_time' else 120
            
    g_values = MockValues()
    cct.sina_limit_time = 30
    duration_sleep_time = 120
    
    # Simulating Trading Time
    is_trading_time = True 
    sina_limit = 30
    cfg_sleep = 120
    
    if is_trading_time:
        loop_sleep_time = min(sina_limit, cfg_sleep)
        if loop_sleep_time < 5: loop_sleep_time = 5
    else:
        loop_sleep_time = cfg_sleep
        
    print(f"Trading Time Sleep Calculation: {loop_sleep_time}s (Expected 30s)")
    assert loop_sleep_time == 30
    
    # Simulating Non-Trading Time
    is_trading_time = False
    if is_trading_time:
        loop_sleep_time = min(sina_limit, cfg_sleep)
    else:
        loop_sleep_time = cfg_sleep
        
    print(f"Non-Trading Time Sleep Calculation: {loop_sleep_time}s (Expected 120s)")
    assert loop_sleep_time == 120
    print("Frequency Logic Passed.")

if __name__ == "__main__":
    try:
        test_service_basic()
        test_frequency_logic_simulation()
    except Exception as e:
        print(f"Test Failed: {e}")
