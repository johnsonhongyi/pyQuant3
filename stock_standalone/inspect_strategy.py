
import inspect
import sys
import os

try:
    from stock_live_strategy import StockLiveStrategy
    print("StockLiveStrategy imported successfully.")
    
    if hasattr(StockLiveStrategy, '_process_follow_queue'):
        print("Found _process_follow_queue!")
        # Get source lines
        lines, start_line = inspect.getsourcelines(StockLiveStrategy._process_follow_queue)
        print(f"Defined at line: {start_line}")
        print("First 5 lines:")
        for l in lines[:5]:
            print(l, end='')
    else:
        print("ERROR: _process_follow_queue NOT FOUND in StockLiveStrategy class.")

except Exception as e:
    print(f"Error: {e}")
