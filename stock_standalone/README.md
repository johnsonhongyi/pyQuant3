# instock_MonitorTK 独立打包指南

本目录包含 `instock_MonitorTK.py` 及其所有项目内部依赖模块，可用 PyInstaller 打包成单文件 exe。

## 目录结构

```
stock_standalone/
├── instock_MonitorTK.py          # 主应用文件
├── instock_MonitorTK.spec        # PyInstaller spec 文件
├── README.md                      # 本文件
├── alerts_manager.py              # 警报管理模块
├── concept_db.py                  # 概念数据库模块
├── customGraphics.py              # 自定义图形模块
├── JohnsonUtil/                   # 内部工具库
│   ├── __init__.py
│   ├── johnson_cons.py            # 常量定义
│   ├── commonTips.py              # 通用工具函数
│   ├── LoggerFactory.py           # 日志工厂
│   ├── stock_sender.py            # 股票发送模块
│   └── ... (其他模块)
└── JSONData/                      # JSON 数据处理库
    ├── __init__.py
    ├── stockFilter.py             # 股票筛选
    ├── tdx_data_Day.py            # TDX 日数据
    └── ... (其他模块)
```

## 打包步骤

### 前置条件

确保已安装 PyInstaller：
```bash
pip install pyinstaller
```

### 方法 1：使用 spec 文件（推荐）

```bash
cd d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone

# 构建单文件 exe（在 dist/ 目录中生成）
pyinstaller instock_MonitorTK.spec
```

### 方法 2：直接命令行构建

```bash
cd d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone

pyinstaller ^
  --onefile ^
  --windowed ^
  --name instock_MonitorTK ^
  --hidden-import=JohnsonUtil ^
  --hidden-import=JohnsonUtil.stock_sender ^
  --hidden-import=JohnsonUtil.johnson_cons ^
  --hidden-import=JohnsonUtil.LoggerFactory ^
  --hidden-import=JohnsonUtil.commonTips ^
  --hidden-import=JSONData ^
  --hidden-import=JSONData.stockFilter ^
  --hidden-import=JSONData.tdx_data_Day ^
  --hidden-import=alerts_manager ^
  --hidden-import=concept_db ^
  --hidden-import=customGraphics ^
  instock_MonitorTK.py
```

### 输出

打包完成后，exe 文件将位于：
```
stock_standalone/dist/instock_MonitorTK.exe
```

## 打包配置说明

### spec 文件中的关键参数

- **`onefile`**：生成单个可执行文件（而不是目录）
- **`windowed`**（注：spec 中设置为 `console=True`）：
  - `True`：无控制台窗口（GUI 应用）
  - `False`：显示控制台窗口（便于调试）
  
- **`hiddenimports`**：显式指定所有自定义模块，确保 PyInstaller 能找到它们

- **`pathex`**：搜索路径，指向 `stock_standalone` 目录

## 常见问题

### Q1：打包后 exe 启动很慢
**解决**：这是正常现象。第一次启动时，PyInstaller 需要解压资源。可以：
- 使用 UPX 压缩（见 spec 中的 `upx=True`）
- 或接受首次启动延迟

### Q2：某个模块找不到
**解决**：
1. 确认模块文件在本目录中存在
2. 在 spec 的 `hiddenimports` 中添加模块名
3. 重新运行 pyinstaller

### Q3：运行 exe 报权限错误
**解决**：
- 以管理员权限运行 exe
- 或将 exe 放在无需管理员权限的目录（如用户桌面）

### Q4：exe 体积过大
**解决**：
- spec 中设置 `console=False` 减少约 5MB
- 使用 UPX 压缩（需另外安装）
- 移除不必要的第三方库依赖

## 依赖检查

本打包包含的第三方库依赖（需在环境中安装）：
```
pandas
numpy
PyQt5
pyqtgraph
pyperclip
screeninfo
win32api (pywin32)
```

确保你的 Python 环境已安装这些库：
```bash
pip install pandas numpy PyQt5 pyqtgraph pyperclip screeninfo pywin32
```

## 联系与反馈

如在打包过程中遇到问题，请检查：
1. PyInstaller 版本（建议 >=5.0）
2. Python 版本（推荐 3.8-3.9.13）
3. 所有依赖库已安装

---

**生成日期**：2025-11-28  
**用途**：instock_MonitorTK 单文件 exe 打包
