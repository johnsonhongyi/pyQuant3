#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PyInstall 环境优化脚本
用于删除不需要的包和优化打包大小
"""

import subprocess
import sys

# 不需要的大包
UNUSED_PACKAGES = [
    'bokeh',        # 78.4 MB
    'scipy',        # 64.1 MB
    'plotly',       # 60.9 MB
    'statsmodels',  # 38.9 MB
    'astropy',      # 32.0 MB
    'ipython',      # 4.1 MB
    'jupyter',      # 常见但不需要
    'notebook',     # 常见但不需要
    'matplotlib',   # 20.0 MB (如果有 pyqtgraph 则不需要)
]

# 必需的核心包
REQUIRED_PACKAGES = [
    'numpy',
    'pandas',
    'PyQt5',
    'pyperclip',
    'pyqtgraph',
    'talib',
    'tushare',
    'pandas-ta',
    'requests',
    'configobj',
    'tqdm',
    'chardet',
    'a-trade-calendar',
    'pywin32',
]

def run_command(cmd, verbose=True):
    """运行命令"""
    if verbose:
        print(f"\n执行: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0 and verbose:
        print(f"警告: {result.stderr}")
    return result.returncode == 0

def cleanup_unused_packages():
    """清理不需要的包"""
    print("=" * 70)
    print("PyInstall 环境清理")
    print("=" * 70)
    
    print(f"\n要删除的包 ({len(UNUSED_PACKAGES)} 个):")
    for pkg in UNUSED_PACKAGES:
        print(f"  - {pkg}")
    
    # 卸载不需要的包
    for pkg in UNUSED_PACKAGES:
        run_command(f"pip uninstall -y {pkg}", verbose=False)
        print(f"  ✓ 卸载 {pkg}")
    
    print("\n✓ 清理完成")

def verify_environment():
    """验证环境"""
    print("\n" + "=" * 70)
    print("验证环境")
    print("=" * 70)
    
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg.replace('-', '_'))
            print(f"  ✓ {pkg}")
        except ImportError:
            missing.append(pkg)
            print(f"  ✗ {pkg} [缺失]")
    
    if missing:
        print(f"\n缺失的包: {', '.join(missing)}")
        print("请运行: pip install " + " ".join(missing))
        return False
    
    print("\n✓ 所有必需包都已安装")
    return True

def get_env_size():
    """获取环境大小"""
    import os
    import subprocess
    
    # 获取当前conda环境路径
    result = subprocess.run("python -c \"import sys; print(sys.prefix)\"", 
                          shell=True, capture_output=True, text=True)
    env_path = result.stdout.strip()
    
    if not os.path.exists(env_path):
        print("无法获取环境路径")
        return
    
    # 计算大小
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(os.path.join(env_path, 'lib', 'site-packages')):
            for filename in filenames:
                try:
                    total_size += os.path.getsize(os.path.join(dirpath, filename))
                except:
                    pass
    except:
        pass
    
    size_mb = total_size / (1024 * 1024)
    print(f"\n环境大小: {size_mb:.1f} MB (site-packages)")
    return size_mb

def main():
    """主函数"""
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd == 'cleanup':
            cleanup_unused_packages()
        elif cmd == 'verify':
            verify_environment()
        elif cmd == 'size':
            get_env_size()
        else:
            print("用法:")
            print("  python optimize_build_env.py cleanup   - 清理不需要的包")
            print("  python optimize_build_env.py verify    - 验证环境")
            print("  python optimize_build_env.py size      - 显示环境大小")
    else:
        print("PyInstall 环境优化工具")
        print("=" * 70)
        print("\n用法:")
        print("  1. 清理环境:   python optimize_build_env.py cleanup")
        print("  2. 验证包:     python optimize_build_env.py verify")
        print("  3. 查看大小:   python optimize_build_env.py size")
        print("\n默认删除的包 (可节省 ~280MB):")
        for pkg in UNUSED_PACKAGES[:5]:
            print(f"  - {pkg}")
        print(f"  ... 共 {len(UNUSED_PACKAGES)} 个")

if __name__ == '__main__':
    main()
