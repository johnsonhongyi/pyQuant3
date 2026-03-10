import pandas as pd
import os

df = pd.DataFrame({'a': [1, 2, 3]})
test_file = "test_infer.pkl"

# Save with zstd
df.to_pickle(test_file, compression='zstd')

try:
    # Try to read without specifying compression
    df2 = pd.read_pickle(test_file)
    print("✅ Read successful without compression argument")
except Exception as e:
    print(f"❌ Read failed: {e}")

try:
    # Try to read with explicit compression
    df3 = pd.read_pickle(test_file, compression='zstd')
    print("✅ Read successful with explicit compression='zstd'")
except Exception as e:
    print(f"❌ Read failed with explicit: {e}")

if os.path.exists(test_file): os.remove(test_file)
