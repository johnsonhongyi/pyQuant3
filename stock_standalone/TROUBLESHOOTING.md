# PyInstall 环境配置问题排查

## 问题诊断

### 错误 1: numpy 版本不兼容
```
ERROR: Ignored the following versions that require a different python version: 
1.21.2 Requires-Python >=3.7,<3.11
```

**原因:** 
- numpy 1.21.x 不支持 Python 3.12+
- 需要使用 Python 3.9.13 或更低版本

**解决方案:**
```bash
# 使用 Python 3.9.13 创建环境
conda create -n py_stock_build python=3.9.13
conda activate py_stock_build
```

---

### 错误 2: talib 找不到
```
ERROR: Could not find a version that satisfies the requirement talib>=0.4.21
ERROR: No matching distribution found for talib>=0.4.21
```

**原因:**
- talib 是编译型库，需要预编译的二进制文件
- 默认源可能没有你的 Python 版本的预编译文件
- talib 对 Python 版本有严格要求

**解决方案:**

#### 方案 1: 使用兼容的 Python 版本（推荐）
```bash
# Python 3.9.13 通常有 talib 的轮子文件
conda create -n py_stock_build python=3.9.13
conda activate py_stock_build
pip install talib==0.4.21
```

#### 方案 2: 手动编译安装
```bash
# 需要 Visual Studio C++ Build Tools
pip install talib --upgrade --no-cache-dir

# 或从轮子文件安装
# 下载: https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib
pip install TA_Lib‑0.4.21‑cp310‑cp310‑win_amd64.whl
```

#### 方案 3: 跳过 talib（应用仍可运行）
```bash
# talib 是可选的，应用可以不需要它
pip install -r requirements_build.txt --ignore-installed talib
```

---

## 推荐配置

### Python 版本
✅ **推荐**: Python 3.9.13
- numpy 1.21.x 兼容
- talib 有预编译文件
- PyQt5 5.12+ 支持

❌ **不推荐**: 
- Python 3.12+ (numpy 1.21 不支持)
- Python 3.7 (太旧，缺少依赖)

### 安装步骤

#### 步骤 1: 创建 Python 3.9.13 环境
```bash
# Conda 方式
conda create -n py_stock_build python=3.9.13
conda activate py_stock_build

# 或 venv 方式
python3.9.13 -m venv py_stock_build
call py_stock_build\Scripts\activate.bat
```

#### 步骤 2: 升级 pip
```bash
python -m pip install --upgrade pip
```

#### 步骤 3: 安装包
```bash
# 使用国内源加快速度
pip install -r requirements_build.txt -i https://mirrors.aliyun.com/pypi/simple/

# 或使用官方源
pip install -r requirements_build.txt
```

#### 步骤 4: 验证安装
```bash
python -c "import warnings; warnings.filterwarnings('ignore'); import numpy, pandas, PyQt5, pyqtgraph, tushare; print('OK')"
```

#### 步骤 5: 打包
```bash
pyinstaller --onefile instock_MonitorTK.py
```

---

## 快速修复脚本

使用新的 `quick_install_fix.bat` 脚本，它包括：
- 自动检测 Python 版本
- 正确处理 numpy 版本
- 处理 talib 安装失败的备用方案
- 详细的错误提示

运行方式:
```batch
# 先创建 Python 3.9.13 环境
conda create -n py_stock_build python=3.9.13
conda activate py_stock_build

# 然后运行快速安装脚本
quick_install_fix.bat
```

---

## 故障排除表

| 错误 | 原因 | 解决方案 |
|------|------|--------|
| numpy 版本不兼容 | Python 版本过新 | 使用 Python 3.9.13 |
| talib 找不到 | 没有预编译文件 | 使用 Python 3.9.13 或手动下载轮子 |
| PyQt5 版本警告 | Qt 版本低 | 忽略（不影响功能） |
| 安装超时 | 网络问题 | 使用国内源 (-i 参数) |
| 磁盘空间不足 | 包太大 | 删除不需要的包或扩展磁盘 |

---

## 国内源加速

```bash
# 阿里源
pip install -r requirements_build.txt -i https://mirrors.aliyun.com/pypi/simple/

# 清华源
pip install -r requirements_build.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 豆瓣源
pip install -r requirements_build.txt -i http://pypi.douban.com/simple/
```

---

## 环境配置总结

### 最小化配置 (仅核心包)
```
Python 3.9.13
numpy==1.21.0
pandas
PyQt5
pyqtgraph
tushare
pandas-ta
requests, configobj, tqdm, chardet, a-trade-calendar
pywin32
pyinstaller
```

### 完整配置 (包括可选包)
```
上述所有包 + talib==0.4.21
```

---

## 后续步骤

1. ✅ 删除或更新旧的 `py_stock_build` 环境
   ```bash
   conda remove -n py_stock_build --all -y
   ```

2. ✅ 创建 Python 3.9.13 环境
   ```bash
   conda create -n py_stock_build python=3.9.13
   ```

3. ✅ 激活环境
   ```bash
   conda activate py_stock_build
   ```

4. ✅ 运行快速安装
   ```batch
   quick_install_fix.bat
   ```

5. ✅ 打包应用
   ```bash
   pyinstaller --onefile instock_MonitorTK.py
   ```

---

**更新时间:** 2025-11-29
**版本:** 3.0 (修复版)
