import time
import pandas as pd
import numpy as np
import logging
from realtime_data_service import DataPublisher
from stock_live_strategy import StockLiveStrategy
from JohnsonUtil import LoggerFactory, commonTips as cct
import threading

# Mock trading time to force execution
def mock_get_work_time():
    return True
cct.get_work_time_duration = mock_get_work_time
cct.get_now_time_int = lambda: 930 # Mock 9:30 AM

# Setup logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestSimulation")

def simulate_market_data(codes, step):
    """Generate mock data with sine wave pattern for price"""
    data = []
    for code in codes:
        # Create a price that moves
        base_price = 10.0
        # Sine wave + noise
        noise = np.random.normal(0, 0.05)
        price_change = np.sin(step / 10.0) * 0.5 + noise
        price = base_price + price_change
        
        # Calculate percent change from base
        percent = (price - base_price) / base_price * 100
        
        data.append({
            'code': code,
            'name': f"Stock_{code}",
            'trade': round(price, 2),
            'price': round(price, 2), # Compatibility
            'percent': round(percent, 2),
            'high': round(price + 0.1, 2),
            'low': round(price - 0.1, 2),
            'open': base_price,
            'nclose': base_price, # Previous close
            'volume': 1000 + step * 10,
            'amount': 10000 + step * 100,
            'ratio': 0.1, # Turnover rate
            'ma5d': base_price,
            'ma10d': base_price, 
            'ma20d': base_price,
            'ma60d': base_price,
            'turnover': 0.1,
            # Add emotion score source column if needed, or let RDS calculate it
            # RDS calculates emotion from 'percent'
        })
    return pd.DataFrame(data)

def run_simulation():
    print(">>> Starting StockLiveStrategy Integration Test (Simulation) <<<")
    
    # 1. Initialize RealtimeDataService
    realtime_service = DataPublisher()
    print("[1] RealtimeDataService initialized.")
    
    # 2. Initialize Strategy with Service Injection
    # voice_enabled=False to avoid noise during test
    strategy = StockLiveStrategy(
        voice_enabled=False, 
        realtime_service=realtime_service,
        alert_cooldown=5 # Short cooldown for testing
    )
    strategy.enabled = True
    print("[2] StockLiveStrategy initialized with RealtimeDataService injected.")
    
    # 3. Add Monitor manually
    test_code = "600000"
    strategy.add_monitor(test_code, "TestStock", "price_up", 10.4) # Target price
    print(f"[3] Added monitor for {test_code} with price_up target > 10.4")
    
    # 4. Simulation Loop
    codes = [test_code, "600001"]
    
    print("\n>>> Running Simulation Loop (Press Ctrl+C to stop early) <<<")
    print("Simulating 60 steps (approx 10 minutes of data accelerated)...")
    
    try:
        for step in range(60):
            # Generate Data
            df = simulate_market_data(codes, step)
            
            # Update Service (Simulating background process)
            realtime_service.update_batch(df)
            
            # Manually trigger strategy process (Simulating main thread timer)
            # In actual app, this is called via `self.after`
            strategy.process_data(df)
            
            # Check Internal State Verification
            score = realtime_service.get_emotion_score(test_code)
            
            # Accessing private attribute for verification (strictly for testing)
            monitor_data = strategy._monitored_stocks.get(test_code, {})
            snap = monitor_data.get('snapshot', {})
            rt_emotion_in_strat = snap.get('rt_emotion')
            
            print(f"Step {step:02d}: {test_code} Price={df.loc[0, 'trade']} | RDS Score={score} | Strat.Snap.Emotion={rt_emotion_in_strat}")
            
            if rt_emotion_in_strat == score and score != 0:
                 # Verification success on non-zero score
                 pass
            
            time.sleep(0.5) # Fast forward
            
    except KeyboardInterrupt:
        print("Simulation stopped.")
    except Exception as e:
        logger.error(f"Simulation Error: {e}", exc_info=True)

    print("\n>>> Test Complete <<<")

if __name__ == "__main__":
    run_simulation()
