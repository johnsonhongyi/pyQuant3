
import sys
import os
import importlib

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'JohnsonUtil'))

modules_to_check = [
    'tqdm',
    'tqdm.contrib.concurrent',
    'configobj',
    'requests',
    'JohnsonUtil.commonTips',
    'JohnsonUtil.johnson_cons',
    'JSONData.realdatajson',
    'JSONData.sina_data',
    'JSONData.tdxbk',
    'JSONData.tdx_data_Day'
]

results = []

for mod_name in modules_to_check:
    pid = os.spawnv(os.P_WAIT, sys.executable, [sys.executable, "-c", 
        f"import sys; sys.path.append(r'{os.getcwd()}'); " + 
        f"sys.path.append(r'{os.path.join(os.getcwd(), 'JohnsonUtil')}'); " +
        f"import {mod_name}; " + 
        f"print('{mod_name}:', 'pandas' in sys.modules)"
    ])
    # Note: spawnv output goes to stdout/stderr.
    # To capture, we might need subprocess.run but run_command handles that.
    # However, running them in SAME process contaminates sys.modules.
    # So we must run separate processes.

# Let's try a simpler approach script that just runs one check based on arg
if len(sys.argv) > 1:
    mod_name = sys.argv[1]
    try:
        importlib.import_module(mod_name)
        if 'pandas' in sys.modules:
            print(f"{mod_name}: TRUE")
        else:
            print(f"{mod_name}: FALSE")
    except Exception as e:
        print(f"{mod_name}: ERROR {e}")
