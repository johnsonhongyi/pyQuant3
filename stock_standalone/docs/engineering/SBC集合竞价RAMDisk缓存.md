# SBC 集合竞价 RAMDisk 缓存

- `ats/auction_cache.py` 使用 configured_ramdisk_root() 下的 sbc_auction.sqlite3；无可用RAMDisk时仅保留进程内存并记录一次警告，不回退SSD。
- 主键为股票/交易日/分钟，SQLite短事务及100ms锁等待处理多进程写入；较旧observed_at不能覆盖更新采样。读取只恢复指定股票的当日有效样本，不补造未采集历史。
- 快照获取路径保存竞价轨迹，最多每5秒普通落盘，auction_open切换立即保存；09:30后仍可附带当日轨迹供新窗口恢复。撮合轨迹不写分钟成交/VWAP历史。
- C键及右键菜单切换叠图，绘制仅使用内存，不发网络/磁盘请求；Ctrl+C保留，文本编辑状态不切图。默认显示沿用原行为。
- 定向验证：tests/test_sbc_auction_cache.py共5项，覆盖缓存隔离、旧写者、盘后重开、未成交/最终成交、RAMDisk缺失及显示切换；未跑全量测试。源码需重开SBC加载；冻结程序需重新打包。
