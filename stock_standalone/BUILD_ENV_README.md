# PyInstall 打包环境配置指南

## 概述

本指南帮助你创建一个专用于 `instock_MonitorTK.py` 的精简 PyInstall 打包环境，可以将可执行文件大小从 300MB+ 减少到 150-200MB。

## 为什么需要专用环境？

原因包括：
- ❌ 当前环境包含多个不必要的大包（bokeh、scipy、plotly、statsmodels、astropy等）
- ❌ 这些包占用 280+ MB 空间
- ✅ 新环境只安装必需的包，节省大量空间

## 快速开始

### 方法 1：使用批处理脚本（推荐）

#### 第一步：创建环境
```batch
setup_build_env.bat
```
这个脚本会：
1. 检查 conda 是否安装
2. 删除旧的 `py_stock_build` 环境（如果存在）
3. 创建新的 Python 3.9 环境
4. 安装所有必需的包
5. 验证环装

**预期耗时：** 5-10 分钟

#### 第二步：验证环境
```batch
verify_build_env.bat verify
```

#### 第三步：打包应用
激活环境后打包：
```batch
conda activate py_stock_build
pyinstaller --onefile instock_MonitorTK.py
```

### 方法 2：使用 environment.yml

```bash
# 创建环境
conda env create -f environment.yml

# 激活环境
conda activate py_stock_build

# 打包
pyinstaller --onefile instock_MonitorTK.py
```

## 环境包含的包

### 核心数据处理 (必需)
- **numpy** - 数值计算库
- **pandas** - 数据处理框架

### GUI 框架 (必需)
- **PyQt5** - GUI 框架
- **pyqtgraph** - 高性能图形库

### 金融数据 (必需)
- **talib** - 技术分析库
- **tushare** - 股票数据接口
- **pandas-ta** - 技术指标计算

### 工具库 (必需)
- **requests** - HTTP 请求
- **configobj** - 配置文件处理
- **tqdm** - 进度条
- **chardet** - 字符编码检测
- **a-trade-calendar** - 交易日历

### 系统库 (必需)
- **pywin32** - Windows API
- **pyperclip** - 剪贴板操作

### 打包工具 (打包时需要)
- **pyinstaller** - 可执行文件打包

## 不包含的包 (已移除)

以下包已从环境中移除，以节省空间：

| 包名 | 大小 | 原因 |
|------|------|------|
| bokeh | 78.4 MB | 不使用的可视化库 |
| scipy | 64.1 MB | 不使用的科学计算库 |
| plotly | 60.9 MB | 不使用的图表库 |
| statsmodels | 38.9 MB | 不使用的统计库 |
| astropy | 32.0 MB | 不使用的天文库 |
| IPython | 4.1 MB | 不使用的交互式shell |
| matplotlib | 20.0 MB | 用 pyqtgraph 替代 |

**总节省空间：278.4 MB**

## 环境管理命令

### 查看所有环境
```bash
conda env list
```

### 激活环境
```bash
conda activate py_stock_build
```

### 停用环境
```bash
conda deactivate
```

### 删除环境
```bash
conda remove -y -n py_stock_build --all
```

### 检查环境大小
```batch
verify_build_env.bat size
```

### 列出已安装的包
```batch
verify_build_env.bat list
```

## 打包命令详解

### 基本打包（推荐）
```bash
# 激活环境
conda activate py_stock_build

# 打包为单个EXE文件
pyinstaller --onefile instock_MonitorTK.py
```

### 带控制台的打包
```bash
pyinstaller --onefile --console instock_MonitorTK.py
```

### 自定义输出目录
```bash
pyinstaller --onefile -d build instock_MonitorTK.py
```

### 添加图标
```bash
pyinstaller --onefile --icon=app.ico instock_MonitorTK.py
```

### 查看打包结果
打包完成后，可执行文件位于：
```
dist/instock_MonitorTK.exe
```

## 常见问题

### Q: 打包失败，提示缺少模块
**A:** 检查所有导入的模块是否都在环境中安装
```bash
pip list | grep <module_name>
```

### Q: EXE 文件运行后出现错误
**A:** 查看日志文件 `appTk.log`，或运行控制台版本查看错误信息
```bash
pyinstaller --onefile --console instock_MonitorTK.py
```

### Q: 如何减小 EXE 文件大小
**A:** 使用 UPX 压缩
```bash
pyinstaller --onefile --upx-dir=C:/path/to/upx instock_MonitorTK.py
```

### Q: 需要修改源代码后重新打包
**A:** 只需重新运行 pyinstaller 命令
```bash
conda activate py_stock_build
pyinstaller --onefile instock_MonitorTK.py
```

## 性能对比

| 指标 | 旧环境 | 新环境 | 节省 |
|------|--------|--------|------|
| 环境大小 | ~650 MB | ~370 MB | 280 MB |
| EXE 文件 | 300+ MB | 150-200 MB | 100+ MB |
| 打包时间 | 3-5 分钟 | 2-3 分钟 | 更快 |

## 故障排除

### 环境创建失败
1. 确保 conda 已正确安装
2. 清理 conda 缓存：`conda clean --all`
3. 检查磁盘空间是否充足（至少需要 5GB）

### 包安装失败
1. 检查网络连接
2. 尝试更换源：
   ```bash
   conda config --add channels conda-forge
   ```
3. 手动安装失败的包：
   ```bash
   pip install --no-cache-dir <package_name>
   ```

## 后续步骤

1. ✅ 创建环境：运行 `setup_build_env.bat`
2. ✅ 验证环境：运行 `verify_build_env.bat verify`
3. ✅ 激活环境：`conda activate py_stock_build`
4. ✅ 打包应用：`pyinstaller --onefile instock_MonitorTK.py`
5. ✅ 测试 EXE：运行 `dist/instock_MonitorTK.exe`

## 相关文件

- `environment.yml` - conda 环境配置文件
- `setup_build_env.bat` - 环境创建脚本
- `verify_build_env.bat` - 环境验证脚本
- `optimize_build_env.py` - 环境优化工具

---

**版本:** 1.0  
**最后更新:** 2025-11-29
