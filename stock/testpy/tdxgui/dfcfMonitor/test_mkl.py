import numpy as np
import sys
import os
import ctypes
import ctypes.util

def detect_numpy_blas():
    backend = "Unknown"
    detected_libs = []

    # 1️⃣ 先检查 numpy.__config__
    for attr in dir(np.__config__):
        if attr.endswith("_info"):
            try:
                info = getattr(np.__config__, attr)
                if isinstance(info, dict) and info.get("libraries"):
                    for lib in info["libraries"]:
                        detected_libs.append(lib.lower())
            except Exception:
                pass

    if any("mkl" in lib for lib in detected_libs):
        backend = "MKL"
    elif any("openblas" in lib for lib in detected_libs):
        backend = "OpenBLAS"
    elif any("blis" in lib for lib in detected_libs):
        backend = "BLIS"

    # 2️⃣ 尝试检查已加载的 DLL（Windows 特有）
    if sys.platform.startswith("win"):
        try:
            mkl_dll = ctypes.util.find_library("mkl_rt")
            openblas_dll = ctypes.util.find_library("libopenblas") or ctypes.util.find_library("openblas")
            if mkl_dll:
                backend = "MKL"
            elif openblas_dll:
                backend = "OpenBLAS"
        except Exception:
            pass

    # 3️⃣ 检查 np.__mkl_version__ 或 mkl-service
    try:
        if hasattr(np, "__mkl_version__") and np.__mkl_version__ is not None:
            backend = "MKL"
    except Exception:
        pass

    return backend, detected_libs

if __name__ == "__main__":
    backend, libs = detect_numpy_blas()
    print("Detected BLAS backend:", backend)
    print("Libraries found:", libs)