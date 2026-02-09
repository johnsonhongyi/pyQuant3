# 数据库修复功能使用说明

## 功能说明

数据库修复功能已集成到主程序的命令行参数中,可以通过命令行参数直接运行数据库修复工具,无需单独运行 `db_repair_tool.py`。

## 使用方法

### 1. 修复默认数据库 (signal_strategy.db)

```bash
# 开发环境
python instock_MonitorTK.py --repair-db

# 或使用短参数
python instock_MonitorTK.py -repair_db
```

### 2. 修复指定数据库

```bash
# 修复指定的数据库文件
python instock_MonitorTK.py --repair-db path/to/your/database.db

# 使用绝对路径
python instock_MonitorTK.py --repair-db D:\Data\signal_strategy.db
```

### 3. 打包后的 EXE 使用

打包成 EXE 后,同样可以通过命令行参数使用:

```bash
# 修复默认数据库
instock_MonitorTK.exe --repair-db

# 修复指定数据库
instock_MonitorTK.exe --repair-db path/to/database.db
```

## 修复流程

修复工具会按以下步骤执行:

1. **完整性检查** - 检查数据库是否损坏
2. **自动备份** - 创建数据库备份文件 (包含时间戳)
3. **WAL Checkpoint** - 尝试合并 WAL 日志
4. **数据恢复** - 使用 SQLite .recover 命令恢复数据
5. **重建数据库** - 导出可读数据并重建数据库

## 输出说明

- 修复成功: 程序返回 0,日志显示 "数据库修复完成!"
- 修复失败: 程序返回 1,日志显示 "数据库修复失败!"
- 备份文件: 自动创建在原数据库同目录,文件名格式: `database.db.backup_YYYYMMDD_HHMMSS`

## 注意事项

1. 修复过程会自动创建备份,请确保有足够的磁盘空间
2. 如果数据库正在被其他程序使用,修复可能会失败
3. 修复后的数据库可能会丢失部分约束信息,但数据完整性得到保证
4. 建议在非交易时间进行数据库修复操作

## 示例

```bash
# Windows 开发环境
python instock_MonitorTK.py --repair-db

# Windows EXE
instock_MonitorTK.exe --repair-db signal_strategy.db

# 查看帮助
python instock_MonitorTK.py --help
```

## 相关文件

- `db_repair_tool.py` - 数据库修复工具核心代码
- `instock_MonitorTK.py` - 主程序,集成了修复功能
- `signal_strategy.db` - 默认的信号策略数据库

## 技术细节

修复工具使用的技术:
- SQLite PRAGMA integrity_check - 完整性检查
- SQLite WAL checkpoint - 日志合并
- SQLite .recover 命令 - 数据恢复
- Python sqlite3 模块 - 数据库操作
