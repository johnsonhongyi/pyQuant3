# PyInstall 打包必需包总结

## 📦 完整包列表

### 数据处理 (必需，约100 MB)
```
numpy>=1.21.0        # 56.2 MB - 数值计算
pandas>=1.3.0        # 44.7 MB - 数据处理框架
```

### GUI框架 (必需，约22 MB)
```
PyQt5>=5.12          # 17.1 MB - GUI框架
pyqtgraph>=0.12.4    # 4.8 MB - 高性能图形库
pyperclip>=1.8.2     # < 1 MB - 剪贴板操作
```

### 金融数据 (必需，约3 MB)
```
talib>=0.4.21        # 1.4 MB - 技术分析
pandas-ta>=0.3.14b0  # 1.0 MB - 技术指标
tushare>=1.2.70      # 0.8 MB - 股票数据接口
```

### 工具库 (必需，< 1 MB)
```
requests>=2.26.0     # HTTP请求
configobj>=5.0.6     # 配置管理
tqdm>=4.62.0         # 进度条
chardet>=4.0.0       # 编码检测
a-trade-calendar     # 交易日历
pywin32>=300         # Windows API
```

### 打包工具 (必需)
```
pyinstaller>=4.7     # EXE生成工具
```

---

## 📊 环境大小

| 组件 | 大小 | 用途 |
|------|------|------|
| numpy + pandas | 100 MB | 数据处理 |
| PyQt5 + pyqtgraph | 22 MB | GUI图形 |
| talib等 | 3 MB | 技术分析 |
| 其他工具 | < 1 MB | 辅助功能 |
| **总计** | **~125 MB** | **应用运行** |
| 打包开销 | ~50 MB | 依赖库 |
| **EXE文件** | **150-200 MB** | **最终输出** |

---

## 🚀 安装方式

### 方式 1: 自动化脚本（最简单）
```batch
setup_build_env.bat      # 自动创建虚拟环境 + 安装所有包
```

### 方式 2: 快速安装（需要先创建虚拟环境）
```batch
REM 创建虚拟环境
conda create -n py_stock_build python=3.9
conda activate py_stock_build

REM 快速安装所有包
quick_install.bat
```

### 方式 3: 使用 requirements.txt
```batch
pip install -r requirements_build.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 方式 4: 手动逐个安装
```batch
pip install numpy pandas PyQt5 pyperclip pyqtgraph talib tushare pandas-ta requests configobj tqdm chardet a-trade-calendar pywin32 pyinstaller -i https://mirrors.aliyun.com/pypi/simple/
```

---

## 📝 必需包详解

### 核心包 (无法替代)
- **numpy** - 数值计算，pandas 的基础
- **pandas** - 数据处理，股票数据的核心
- **PyQt5** - GUI 框架，主窗口
- **pyqtgraph** - K线图、技术指标图表

### 金融包 (业务相关)
- **talib** - 技术分析指标 (MA, RSI, MACD等)
- **tushare** - 股票数据接口
- **pandas-ta** - 补充的技术指标

### 系统包 (功能支持)
- **pywin32** - Windows API (需要)
- **requests** - HTTP 请求 (数据获取)
- **pyperclip** - 剪贴板 (复制功能)

### 工具包 (非关键但推荐)
- **configobj** - 配置文件
- **tqdm** - 进度条
- **chardet** - 编码检测
- **a-trade-calendar** - 交易日历

### 打包包 (生成EXE需要)
- **pyinstaller** - 打包工具

---

## ❌ 已移除的包

下列包已移除以节省空间 (总计 280+ MB):

| 包 | 大小 | 原因 |
|----|------|------|
| bokeh | 78.4 MB | ❌ 不使用的可视化库 |
| scipy | 64.1 MB | ❌ 不使用的科学计算库 |
| plotly | 60.9 MB | ❌ 不使用的交互图表 |
| statsmodels | 38.9 MB | ❌ 不使用的统计库 |
| astropy | 32.0 MB | ❌ 不使用的天文库 |
| matplotlib | 20.0 MB | ⚠️ 用 pyqtgraph 替代 |
| IPython | 4.1 MB | ❌ 不使用的交互shell |
| jupyter | 10+ MB | ❌ 不使用的笔记本 |

---

## 📈 打包效果

### 优化前
- 环境大小: ~650 MB
- EXE 文件: 300+ MB
- 打包时间: 3-5 分钟

### 优化后
- 环境大小: ~370 MB ⬇️ -43%
- EXE 文件: 150-200 MB ⬇️ -50%
- 打包时间: 2-3 分钟 ⬆️ +25% 快

---

## 🛠️ 打包命令

```bash
# 基本打包
pyinstaller --onefile instock_MonitorTK.py

# 输出信息详细
pyinstaller --onefile --console instock_MonitorTK.py

# 自定义输出位置
pyinstaller --onefile -d build instock_MonitorTK.py

# 添加图标
pyinstaller --onefile --icon=app.ico instock_MonitorTK.py

# UPX压缩 (需要先安装upx)
pyinstaller --onefile --upx-dir=C:/path/to/upx instock_MonitorTK.py
```

---

## ✅ 验证清单

- [ ] Python 3.9+ 已安装
- [ ] 虚拟环境已创建 (conda 或 venv)
- [ ] 虚拟环境已激活
- [ ] 所有包已安装
  ```bash
  python -c "import numpy, pandas, PyQt5, pyqtgraph, talib, tushare; print('OK')"
  ```
- [ ] 打包完成 `dist/instock_MonitorTK.exe`
- [ ] EXE 文件可以运行

---

## 🐛 常见问题

### Q: 安装很慢
**A:** 使用国内镜像源
```bash
pip install -r requirements_build.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### Q: 某个包安装失败
**A:** 检查是否依赖其他包，单独安装
```bash
pip install --no-cache-dir <package_name>
```

### Q: EXE 文件太大
**A:** 移除不必要的包或使用 UPX 压缩
```bash
pip uninstall bokeh scipy plotly -y
```

### Q: 如何删除环境重新创建
**A:** 
```bash
# Conda
conda remove -y -n py_stock_build --all

# venv
rmdir /s /q py_stock_build
```

---

**更新时间:** 2025-11-29  
**版本:** 2.0
