import pandas as pd
import sys
import os

# Add current directory to sys.path to import local modules
sys.path.append(os.getcwd())

from realtime_data_service import MinuteKlineCache, KLineItem

def simulate_volume():
    hdf_path = r'g:\sina_MultiIndex_data.h5'
    print(f"Loading data from {hdf_path}...")
    
    try:
        # Read the 'all_30' key from HDF5
        df = pd.read_hdf(hdf_path, key='all_30')
        print(f"Data loaded. Shape: {df.shape}")
        
        # Sort by time just in case, though it should be sorted
        # The index is likely MultiIndex (code, ticktime) or similar
        # Let's inspect index
        print(f"Index names: {df.index.names}")
        
        # We need to iterate chronologically. 
        # If it's MultiIndex, we might want to sort by ticktime.
        # Check if 'ticktime' is in index or columns
        if 'ticktime' in df.index.names:
             df_sorted = df.sort_index(level='ticktime')
        else:
             print("Warning: 'ticktime' not found in index. Assuming data is time-sorted or 'ticktime' is a column.")
             df_sorted = df # Assuming it's already sorted or we iterate as is
             
        # Initialize Cache
        cache = MinuteKlineCache(max_len=240)
        
        # Pick a test stock. '000001' was used in debug logs, let's see if it exists
        test_code = '000001'
        # Or pick the first code from data if 000001 is not there
        unique_codes = df.index.get_level_values('code').unique()
        if test_code not in unique_codes:
            print(f"Stock {test_code} not found in data. Using {unique_codes[0]} instead.")
            test_code = unique_codes[0]
            
        print(f"Simulating for stock: {test_code}")
        
        # Filter for test stock
        # Assuming MultiIndex (code, ticktime)
        stock_data = df.xs(test_code, level='code')
        
        # Iterate and update
        print("Starting playback...")
        for time_idx, row in stock_data.iterrows():
            # time_idx should be the timestamp
            # row contains columns
            
            # Map column names if necessary (HDF5 might have 'vol' or 'volume')
            vol = row.get('volume', row.get('vol', 0.0))
            price = row.get('close', 0.0)
            
            # Timestamp handling: Ensure it's int/float timestamp or convert
            # The previous 'read_hdf' showed ticktime as string '2026-01-23 09:26:13'
            # MinuteKlineCache expects YYYYMMDDHHMM int usually?
            # Let's check _update_internal usage of minute_ts.
            # It compares minute_ts. If string, comparison works but formatting matters.
            # In update_batch: 
            # minute_ts = int(row.name[1].strftime('%Y%m%d%H%M')) if isinstance(row.name[1], pd.Timestamp) ...
            
            # Let's verify what time_idx is
            if isinstance(time_idx, str):
                 # Convert "2026-01-23 09:26:13" to 202601230926
                 # Simple parsing
                 ts_str = time_idx.replace('-', '').replace(' ', '').replace(':', '')[:12]
                 minute_ts = int(ts_str)
            elif isinstance(time_idx, pd.Timestamp):
                 minute_ts = int(time_idx.strftime('%Y%m%d%H%M'))
            else:
                 minute_ts = time_idx # Assess what it is
                 
            # print(f"Processing {minute_ts}, Vol: {vol}")
            
            # Call _update_internal
            # Note: _update_internal logic wraps print with if code == '000001'
            # If we changed test_code, we might verify logs manually or change the hardcoded check in future.
            # But the logic fix applies to all.
            
            cache._update_internal(test_code, price, float(vol), minute_ts)
            
        print("Simulation finished.")
        
        # Inspect results
        klines = cache.get_klines(test_code)
        print(f"Generated {len(klines)} K-lines.")
        if len(klines) > 0:
            print("Sample K-lines:")
            for k in klines[:5]:
                print(k)
            print("...")
            for k in klines[-5:]:
                print(k)
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    simulate_volume()
