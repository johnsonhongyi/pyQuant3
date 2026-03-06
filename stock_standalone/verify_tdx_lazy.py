
import sys
import os

# Ensure we can import from current directory
sys.path.append(os.getcwd())
# Also append parent just in case
sys.path.append(os.path.dirname(os.getcwd()))

print(f"Initial: 'pandas' in sys.modules: {'pandas' in sys.modules}")

try:
    from JSONData import tdx_data_Day
except ImportError:
    # Try importing as if we are in the package
    try:
        import JSONData.tdx_data_Day as tdx_data_Day
    except ImportError:
         print("Could not import tdx_data_Day")
         sys.exit(1)

print(f"After import: 'pandas' in sys.modules: {'pandas' in sys.modules}")

if 'pandas' in sys.modules:
    print("Result: FAIL - pandas loaded early")
else:
    print("Result: SUCCESS - pandas lazy loaded")

# Test attribute access
try:
    print("Accessing tdx_data_Day.pd...")
    p = tdx_data_Day.pd
    print(f"Got: {p}")
    print(f"After access: 'pandas' in sys.modules: {'pandas' in sys.modules}")
except Exception as e:
    print(f"Error accessing pd: {e}")
