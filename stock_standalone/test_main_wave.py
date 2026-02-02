import pandas as pd
import numpy as np
from td_sequence import calculate_td_sequence
from daily_top_detector import detect_top_signals

def test():
    # Create dummy data: 20 bars of uptrend
    data = {
        'open': np.linspace(10, 20, 20),
        'high': np.linspace(10.5, 21, 20),
        'low': np.linspace(9.5, 19.5, 20),
        'close': np.linspace(10.2, 20.5, 20),
        'volume': np.linspace(1000, 5000, 20)
    }
    df = pd.DataFrame(data)
    
    # Add TD Sequence
    df = calculate_td_sequence(df)
    
    print("TD Sequence Results (Last 10 bars):")
    print(df[['close', 'td_setup', 'td_sell_setup', 'td_buy_setup']].tail(10))
    
    # Test Top Detector
    current_tick = df.iloc[-1].to_dict()
    current_tick['trade'] = current_tick['close']
    current_tick['ma5d'] = df['close'].rolling(5).mean().iloc[-1]
    
    top_info = detect_top_signals(df, current_tick)
    print("\nDaily Top Detector Results:")
    print(top_info)

if __name__ == "__main__":
    test()
