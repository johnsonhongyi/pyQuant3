# PyInstall 打包环境 - 最终使用指南

## 📌 快速开始（3步）

### 第 1 步: 创建 Python 3.9.13 环境

```bash
conda create -n py_stock_build python=3.9.13
conda activate py_stock_build
```

### 第 2 步: 快速安装所有包

选择以下任一方法：

#### 方法 A: 自动化脚本（推荐）
```batch
quick_install_fix.bat
```

#### 方法 B: 使用 requirements 文件
```bash
pip install -r requirements_build.txt -i https://mirrors.aliyun.com/pypi/simple/
```

#### 方法 C: 完整自动化（包括环境创建）
```batch
setup_build_env.bat
```

### 第 3 步: 打包应用

```bash
pyinstaller --onefile instock_MonitorTK.py
```

完成！EXE文件在 `dist/instock_MonitorTK.exe`

---

## 🔍 验证环境

```bash
# 验证核心包
python -c "import warnings; warnings.filterwarnings('ignore'); import numpy, pandas, PyQt5, pyqtgraph, tushare; print('OK')"

# 或使用脚本
verify_build_env_fixed.bat verify
```

---

## 📁 关键文件说明

| 文件 | 用途 | 何时使用 |
|------|------|--------|
| **setup_build_env.bat** | 创建环境 + 安装包 | 第一次完整设置 |
| **quick_install_fix.bat** | 快速安装包 | 已有环境时 |
| **quick_build_fixed.bat** | 交互式菜单 | 日常使用 |
| **verify_build_env_fixed.bat** | 验证和管理 | 环境维护 |
| **requirements_build.txt** | pip 包列表 | 手动安装 |
| **environment.yml** | conda 配置 | conda 创建 |

---

## 🐛 常见问题快速解决

### Q: 安装失败 - 网络问题
```bash
# 使用国内源
pip install -r requirements_build.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### Q: talib 安装失败
**原因:** 需要编译，或 Python 版本不兼容

**解决:**
1. 确保使用 Python 3.9.13
2. 手动下载轮子文件: https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib
3. 安装轮子: `pip install TA_Lib-0.4.21-cp310-cp310-win_amd64.whl`

### Q: 验证失败 - 包未安装
```bash
# 列出已安装包
pip list

# 重新安装缺失的包
pip install numpy pandas PyQt5 pyqtgraph
```

### Q: PyQt5 版本警告
这是警告，不是错误，不影响功能。

### Q: EXE 文件太大
```bash
# 删除不需要的包
pip uninstall bokeh scipy plotly -y

# 或使用 UPX 压缩
pyinstaller --onefile --upx-dir=C:/path/to/upx instock_MonitorTK.py
```

---

## 📊 预期效果

| 指标 | 值 |
|------|-----|
| 环境大小 | ~370 MB |
| EXE 大小 | 150-200 MB |
| 打包时间 | 2-3 分钟 |
| Python 版本 | 3.9.13 |

---

## 🎯 选择正确的脚本

### 对于新用户 (第一次)
```batch
setup_build_env.bat
```
优点: 完全自动化，包括环境创建

### 对于有环境的用户 (只需安装包)
```batch
quick_install_fix.bat
```
优点: 快速，只安装包

### 对于日常使用 (打包、验证等)
```batch
quick_build_fixed.bat
```
优点: 交互式菜单，易于使用

---

## 🔧 手动安装步骤 (如果脚本不工作)

```bash
# 1. 创建环境
conda create -n py_stock_build python=3.9.13

# 2. 激活环境
conda activate py_stock_build

# 3. 升级 pip
python -m pip install --upgrade pip

# 4. 安装基础包
pip install numpy==1.21.0 pandas PyQt5 pywin32

# 5. 安装金融包
pip install talib==0.4.21 tushare pandas-ta

# 6. 安装工具包
pip install pyperclip pyqtgraph requests configobj tqdm chardet a-trade-calendar

# 7. 安装打包工具
pip install pyinstaller

# 8. 验证
python -c "import numpy, pandas, PyQt5, pyqtgraph, tushare; print('OK')"

# 9. 打包
pyinstaller --onefile instock_MonitorTK.py
```

---

## 📚 相关文档

- **BUILD_ENV_README.md** - 详细的环境配置指南
- **TROUBLESHOOTING.md** - 问题排查和解决方案
- **PACKAGES_SUMMARY.md** - 包的快速参考
- **PACKAGES_GUIDE.txt** - 完整的包安装指南

---

## ✅ 完成检查表

- [ ] Python 3.9.13 已安装
- [ ] 虚拟环境已创建 (py_stock_build)
- [ ] 虚拟环境已激活
- [ ] 所有包已安装 (运行快速安装脚本)
- [ ] 验证通过 (运行 verify_build_env_fixed.bat verify)
- [ ] 打包完成 (运行 pyinstaller 命令)
- [ ] EXE 文件可以运行 (dist/instock_MonitorTK.exe)

---

## 🚀 开始使用

**最简单的方法:**
1. 打开命令行
2. 进入项目目录
3. 运行: `setup_build_env.bat`
4. 等待完成
5. 运行: `pyinstaller --onefile instock_MonitorTK.py`

**完成！** 🎉

---

**更新时间:** 2025-11-29  
**推荐版本:** 最新
