
import tkinter as tk
import pandas as pd
from market_pulse_viewer import MarketPulseViewer
import logging

# Mock StockSelector
class MockSelector:
    def __init__(self):
        self.resample = 'd'
        self.df_all_realtime = pd.DataFrame({
            'code': ['000001', '000002'],
            'Rank': [1, 2],
            'topR': [5.5, 2.1], # Gap
            # 'win': [3, 1] 
        }).set_index('code')

# Mock MonitorApp
class MockApp:
    def __init__(self):
        self.stock_selector = MockSelector()
        self.live_strategy = None # Mock if needed

def verify_ui():
    root = tk.Tk()
    app = MockApp()
    
    print("Launching MarketPulseViewer...")
    viewer = MarketPulseViewer(root, app)
    
    # Verify Columns
    cols = viewer.tree['columns']
    print(f"Columns: {cols}")
    expected = ('index', 'code', 'name', 'score', 'rank', 'gap', 'price', 'add_price', 'profit', 'win', 'win_rate', 'period', 'sector', 'reason', 'auto_reason', 'action_plan')
    
    if tuple(cols) == expected:
        print("PASS: Columns match expected structure.")
    else:
        print(f"FAIL: Columns mismatch.\nExpected: {expected}\nGot: {tuple(cols)}")
        
    # Verify Tree Font
    style = viewer.style = tk.ttk.Style()
    font = style.lookup("Pulse.Treeview", "font")
    print(f"Tree Font (configured in code): {font}") 
    # Note: lookup might return default if style config isn't applied globally or correctly queried in this mock context, but visual check is key.
    
    # Verify WindowMixin load called
    # (Implicitly checked if window opens without error)
    
    print("UI Open. Please check visually. Closing in 3 seconds...")
    root.after(3000, root.destroy)
    root.mainloop()

if __name__ == "__main__":
    verify_ui()
