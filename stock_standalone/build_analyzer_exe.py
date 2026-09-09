# -*- coding: utf-8 -*-
"""
build_analyzer_exe.py — 极小体积 exe 一键构建脚本
--------------------------------------------------
用法:
    python build_analyzer_exe.py [--no-clean]
"""

import sys
import os
import shutil
import time
import subprocess
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def build(clean=True):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    spec_file = os.path.join(base_dir, "delivery_order_analyzer.spec")
    if not os.path.exists(spec_file):
        print(f"❌ 未找到 spec 文件: {spec_file}")
        return False

    dist_dir = os.path.join(base_dir, "dist")
    build_dir = os.path.join(base_dir, "build")
    target_exe = os.path.join(dist_dir, "DeliveryOrderAnalyzer.exe")

    if clean:
        print("🧹 清理历史构建缓存...")
        for p in [build_dir, dist_dir]:
            if os.path.exists(p):
                try:
                    shutil.rmtree(p)
                except Exception as e:
                    print(f"  警告: 清理 {p} 失败: {e}")

    start_time = time.time()
    print("🚀 开始执行 PyInstaller 极小模式打包 (纯原生+零依赖)...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        spec_file
    ]

    res = subprocess.run(cmd, cwd=base_dir)
    elapsed = time.time() - start_time

    if res.returncode != 0:
        print(f"❌ 构建失败！返回码: {res.returncode}")
        return False

    if os.path.exists(target_exe):
        size_bytes = os.path.getsize(target_exe)
        size_mb = size_bytes / (1024 * 1024)
        print("\n==================================================")
        print("🎉 极小体积独立运行程序构建成功！")
        print(f"📁 产物路径: {target_exe}")
        print(f"📦 单文件大小: {size_mb:.2f} MB")
        print(f"⏱️ 打包耗时: {elapsed:.1f} 秒")
        print("==================================================")
        return True
    else:
        print(f"❌ 未能找到生成产物: {target_exe}")
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="一键构建极小体积 DeliveryOrderAnalyzer.exe")
    parser.add_argument("--no-clean", action="store_true", help="不清理历史 build 目录")
    args = parser.parse_args()

    success = build(clean=not args.no_clean)
    sys.exit(0 if success else 1)
