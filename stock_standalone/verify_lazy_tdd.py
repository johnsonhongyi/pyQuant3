
import sys
import os

def check_modules(modules_list, stage):
    print(f"--- Checking modules at stage: {stage} ---")
    for mod in modules_list:
        if mod in sys.modules:
            print(f"  [LOADED] {mod}")
        else:
            print(f"  [NOT LOADED] {mod}")

def verify_lazy_loading():
    heavy_modules = ['pandas_ta', 'talib']
    
    # Stage 1: Before import
    check_modules(heavy_modules, "1. Start")
    
    # Stage 2: Import tdx_data_Day
    print("\nImporting JSONData.tdx_data_Day...")
    from JSONData import tdx_data_Day as tdd
    check_modules(heavy_modules, "2. After tdd import")
    
    # Verify that heavy modules are NOT loaded yet
    if any(m in sys.modules for m in heavy_modules):
        print("\n[FAILURE] Heavy modules matched! Lazy loading failed.")
        # but continue to test if they load on usage
    else:
        print("\n[SUCCESS] Heavy modules NOT loaded after tdd import.")

    # Stage 3: Call a function that uses talib
    # We need a function that uses talib but doesn't require complex args or DB connections if possible.
    # checking source code... 'ma_comp_col_v2' uses talib.
    # But it needs a DataFrame.
    # Let's try simple import check by inspecting the specialized getter or just trusting that if verify script works so far, we are good.
    # But we want to prove it works when needed.
    # Let's force load one of them manually to prove we CAN load it, or call a simple function.
    
    # Actually, simpler: define a dummy function in tdd? No, I can't modify tdd just for test.
    # "get_sina_data_df" imports talib.
    # But it might be hard to run without setup.
    
    # Let's just create a dummy pandas dataframe and call a function that uses it?
    # tdd.ma_comp_col_v2(df)
    
verify_lazy_loading()
