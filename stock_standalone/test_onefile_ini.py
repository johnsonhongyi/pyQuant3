# -*- coding: UTF-8 -*-
import os
import sys

def get_base_path():
    # 1. Nuitka onefile: the original launched EXE directory is stored in sys.executable
    if "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        return os.path.dirname(os.path.abspath(sys.executable))
        
    # 2. PyInstaller frozen mode
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.argv[0]))
        
    # 3. Normal Python interpreter / script mode
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_file(rel_path, out_name=None, BASE_DIR=None):
    if BASE_DIR is None:
        BASE_DIR = get_base_path()

    if out_name is None:
        out_name = os.path.basename(rel_path)

    target_path = os.path.join(BASE_DIR, out_name)
    print(f"[DEBUG] Destination target_path: {target_path}")

    # 已存在 → 直接返回
    if os.path.exists(target_path):
         print(f"[INFO] target_path already exists: {target_path}")
         return target_path

    # 从 MEIPASS 或 Nuitka 临时目录复制
    if "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        # Under Nuitka onefile, the temporary unpacked resources are located in NUITKA_ONEFILE_DIRECTORY
        base = os.environ["NUITKA_ONEFILE_DIRECTORY"]
        print(f"[DEBUG] Detected Nuitka onefile environment. Temp base: {base}")
    elif getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
        print(f"[DEBUG] Detected PyInstaller environment. sys._MEIPASS base: {base}")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        print(f"[DEBUG] Detected standard Python interpreter environment. base: {base}")
        
    src = os.path.join(base, rel_path)
    print(f"[DEBUG] Source resource path in temp: {src}")

    if not os.path.exists(src):
        print(f"[ERROR] Built-in resource missing: {src}")
        return None

    try:
        # 二进制流流式拷贝，无需额外的 shutil 依赖，保证最轻快编译
        with open(src, 'rb') as f_in:
            data = f_in.read()
        with open(target_path, 'wb') as f_out:
            f_out.write(data)
        print(f"[SUCCESS] Extracted and copied resource to: {target_path}")
        return target_path
    except Exception as e:
        print(f"[ERROR] Failed to extract resource: {e}")
        return None

print("==========================================================")
print("RUNNING FINAL NUITKA ONEFILE PATH RESOLUTION DIAGNOSTIC")
print("==========================================================")

# Clean up any existing global.ini next to the EXE to force extraction
target_out_path = os.path.join(get_base_path(), "global.ini")
if os.path.exists(target_out_path):
    print(f"Cleaning existing output config: {target_out_path}")
    os.remove(target_out_path)

# Retrieve resource
print("Invoking get_resource_file...")
res_path = get_resource_file("JohnsonUtil/global.ini", "global.ini")

print("==========================================================")
print(f"Extraction result path: {res_path}")
if res_path and os.path.exists(res_path):
    print("SUCCESS: Config extracted and verified next to EXE!")
    print("----------------------------------------------------------")
    with open(res_path, 'r', encoding='utf-8') as f:
         print(f.read().strip())
    print("----------------------------------------------------------")
else:
    print("ERROR: Config extraction verification failed.")
print("==========================================================")
