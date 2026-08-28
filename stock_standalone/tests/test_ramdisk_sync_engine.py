# -*- coding: utf-8 -*-
"""
RamDisk 实时数据自动同步与备份守护引擎单元测试套件
测试覆盖：
1. 配置管理持久化与默认路径探测
2. 交易日与交易时段约束逻辑
3. 数据变更指纹比对（新建、修改、未变动 0 I/O 跳过）
4. Windows 安全原子替换与时间戳元数据保持
5. 日期归档与镜像覆盖模式
"""

import os
import sys
import time
import json
import shutil
import tempfile
import datetime
import pytest

# 动态将项目根目录和 webTools 加入路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
webtools_dir = os.path.join(parent_dir, "webTools")
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if webtools_dir not in sys.path:
    sys.path.insert(0, webtools_dir)

from window_manager.sync_engine import (
    RamDiskSyncConfig,
    RamDiskSyncEngine,
    RamDiskSyncWorker,
    detect_default_ramdisk_dir,
    detect_default_backup_dir
)


@pytest.fixture
def temp_dirs():
    """提供干净隔离的临时源目录与备份目录"""
    tmp_root = tempfile.mkdtemp(prefix="test_ramdisk_sync_")
    src_dir = os.path.join(tmp_root, "ramdisk_src")
    tgt_dir = os.path.join(tmp_root, "backup_tgt")
    cfg_file = os.path.join(tmp_root, "sync_cfg.json")
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(tgt_dir, exist_ok=True)

    yield {
        "root": tmp_root,
        "src": src_dir,
        "tgt": tgt_dir,
        "cfg": cfg_file
    }

    try:
        shutil.rmtree(tmp_root)
    except Exception:
        pass


def test_config_load_and_save(temp_dirs):
    """测试配置文件的加载、序列化与反序列化"""
    cfg_path = temp_dirs["cfg"]
    cfg = RamDiskSyncConfig(config_path=cfg_path)
    
    # 初始默认值
    assert cfg.enabled is True
    assert cfg.sync_interval_sec >= 5
    assert cfg.backup_mode == "mirror"
    assert cfg.atomic_swap is True
    assert cfg.log_enabled is False  # 默认关闭，避免刷屏
    assert len(cfg.trading_hours) > 0

    # 修改并保存
    cfg.enabled = False
    cfg.sync_interval_sec = 45
    cfg.source_dir = temp_dirs["src"]
    cfg.target_dir = temp_dirs["tgt"]
    cfg.backup_mode = "date_folder"
    cfg.log_enabled = True  # 开启日志开关
    cfg.save()

    # 重新加载断言
    cfg2 = RamDiskSyncConfig(config_path=cfg_path)
    assert cfg2.enabled is False
    assert cfg2.sync_interval_sec == 45
    assert cfg2.source_dir == temp_dirs["src"]
    assert cfg2.target_dir == temp_dirs["tgt"]
    assert cfg2.backup_mode == "date_folder"
    assert cfg2.log_enabled is True  # 验证持久化成功


def test_trading_hours_and_workdays_filter(temp_dirs):
    """测试交易日与时段判定"""
    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.only_workdays = True
    cfg.only_trading_hours = True
    cfg.trading_hours = [["09:15", "11:35"], ["13:00", "15:10"]]
    
    engine = RamDiskSyncEngine(cfg)

    # 1. 模拟周一 09:30 (盘中) -> 应该放行
    monday_morning = datetime.datetime(2026, 8, 24, 9, 30, 0) # 2026-08-24 是周一
    in_slot, reason = engine.is_in_trading_time(monday_morning)
    assert in_slot is True

    # 2. 模拟周一 14:30 (午后盘中) -> 应该放行
    monday_afternoon = datetime.datetime(2026, 8, 24, 14, 30, 0)
    in_slot, reason = engine.is_in_trading_time(monday_afternoon)
    assert in_slot is True

    # 3. 模拟周一 12:00 (午休非交易时段) -> 应该拦截
    monday_noon = datetime.datetime(2026, 8, 24, 12, 0, 0)
    in_slot, reason = engine.is_in_trading_time(monday_noon)
    assert in_slot is False
    assert "非交易时段" in reason

    # 4. 模拟周日 10:00 (周末) -> 应该拦截
    sunday = datetime.datetime(2026, 8, 23, 10, 0, 0) # 2026-08-23 是周日
    in_slot, reason = engine.is_in_trading_time(sunday)
    assert in_slot is False
    assert "非工作日" in reason

    # 5. 关闭时段与工作日限制 -> 全天候放行
    cfg.only_workdays = False
    cfg.only_trading_hours = False
    in_slot, reason = engine.is_in_trading_time(sunday)
    assert in_slot is True


def test_change_detection_and_incremental_sync(temp_dirs):
    """测试核心变更指纹检测：仅在文件新增或修改时同步，无变化时 0 I/O"""
    src_dir = temp_dirs["src"]
    tgt_dir = temp_dirs["tgt"]
    
    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.enabled = True
    cfg.source_dir = src_dir
    cfg.target_dir = tgt_dir
    cfg.sync_scope = "all_directory"
    cfg.file_patterns = ["*.h5", "*.json", "*.pkl"]
    cfg.backup_mode = "mirror"

    engine = RamDiskSyncEngine(cfg)

    # 步骤 1：源目录初始写入两个文件
    file1 = os.path.join(src_dir, "sina_MultiIndex_data.h5")
    file2 = os.path.join(src_dir, "market_alerts_history.json")
    with open(file1, "wb") as f:
        f.write(b"HDF5_MOCK_DATA_VERSION_1")
    with open(file2, "w", encoding="utf-8") as f:
        f.write('{"alerts": [1, 2, 3]}')

    # 执行首次同步
    res1 = engine.sync_once(force=False, ignore_time_filter=True)
    assert res1["status"] == "ok"
    assert len(res1["synced_files"]) == 2
    assert "sina_MultiIndex_data.h5" in res1["synced_files"]
    assert "market_alerts_history.json" in res1["synced_files"]
    assert os.path.exists(os.path.join(tgt_dir, "sina_MultiIndex_data.h5"))
    assert os.path.exists(os.path.join(tgt_dir, "market_alerts_history.json"))

    # 步骤 2：数据未发生任何变化，执行第二次同步
    res2 = engine.sync_once(force=False, ignore_time_filter=True)
    assert res2["status"] == "ok"
    assert len(res2["synced_files"]) == 0
    assert res2["skipped_count"] == 2
    assert "无变化" in res2["message"]

    # 步骤 3：仅修改其中 1 个文件 (market_alerts_history.json)
    time.sleep(1.1)  # 跨过 1s 确保 mtime 发生严格变动
    with open(file2, "w", encoding="utf-8") as f:
        f.write('{"alerts": [1, 2, 3, 4, 5], "new_alert": true}')

    res3 = engine.sync_once(force=False, ignore_time_filter=True)
    assert res3["status"] == "ok"
    assert len(res3["synced_files"]) == 1
    assert "market_alerts_history.json" in res3["synced_files"]
    assert res3["skipped_count"] == 1

    # 验证目标文件内容已更新
    with open(os.path.join(tgt_dir, "market_alerts_history.json"), "r", encoding="utf-8") as f:
        content = f.read()
    assert "new_alert" in content

    # 步骤 4：在源目录新增第 3 个文件 (minute_kline_cache.pkl)
    file3 = os.path.join(src_dir, "minute_kline_cache.pkl")
    with open(file3, "wb") as f:
        f.write(b"PKL_CACHE_BINARY_BYTES")

    res4 = engine.sync_once(force=False, ignore_time_filter=True)
    assert res4["status"] == "ok"
    assert len(res4["synced_files"]) == 1
    assert "minute_kline_cache.pkl" in res4["synced_files"]
    assert res4["skipped_count"] == 2


def test_atomic_swap_and_timestamp_preservation(temp_dirs):
    """测试原子安全写入与 mtime 元数据保持"""
    src_dir = temp_dirs["src"]
    tgt_dir = temp_dirs["tgt"]
    
    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.source_dir = src_dir
    cfg.target_dir = tgt_dir
    cfg.sync_scope = "all_directory"
    cfg.atomic_swap = True

    engine = RamDiskSyncEngine(cfg)

    src_file = os.path.join(src_dir, "test_atomic.h5")
    with open(src_file, "wb") as f:
        f.write(b"SAMPLE_BIG_DATA_STREAM" * 1024)

    # 人为设置一个特定的过去时间戳
    past_mtime = time.time() - 3600
    os.utime(src_file, (past_mtime, past_mtime))

    res = engine.sync_once(force=False, ignore_time_filter=True)
    assert res["status"] == "ok"
    assert "test_atomic.h5" in res["synced_files"]

    dst_file = os.path.join(tgt_dir, "test_atomic.h5")
    assert os.path.exists(dst_file)
    assert os.path.getsize(dst_file) == os.path.getsize(src_file)
    
    # 时间戳保持一致（允许 1s 文件系统转换误差）
    assert abs(os.path.getmtime(dst_file) - past_mtime) < 1.5


def test_backup_mode_date_folder(temp_dirs):
    """测试按日期创建子文件夹备份模式"""
    src_dir = temp_dirs["src"]
    tgt_dir = temp_dirs["tgt"]
    
    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.source_dir = src_dir
    cfg.target_dir = tgt_dir
    cfg.sync_scope = "all_directory"
    cfg.backup_mode = "date_folder"

    engine = RamDiskSyncEngine(cfg)

    src_file = os.path.join(src_dir, "daily_report.json")
    with open(src_file, "w", encoding="utf-8") as f:
        f.write('{"report": "ok"}')

    res = engine.sync_once(force=False, ignore_time_filter=True)
    assert res["status"] == "ok"

    today_str = datetime.datetime.now().strftime("%Y%m%d")
    date_subfolder = os.path.join(tgt_dir, today_str)
    assert os.path.exists(date_subfolder)
    assert os.path.exists(os.path.join(date_subfolder, "daily_report.json"))


def test_specific_files_multi_selection_mode(temp_dirs):
    """测试多选指定文件模式：精准只同步选中的文件，绝不同步多余文件"""
    src_dir = temp_dirs["src"]
    tgt_dir = temp_dirs["tgt"]
    
    # 创建 5 个不同文件
    for name in ["f1_multiindex.h5", "f2_alerts.json", "f3_cache.pkl", "f4_unused.csv", "f5_other.h5"]:
        with open(os.path.join(src_dir, name), "w", encoding="utf-8") as f:
            f.write(f"content of {name}")

    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.source_dir = src_dir
    cfg.target_dir = tgt_dir
    cfg.sync_scope = "specific_files"
    # 模拟用户多选指定了 2 个关键文件
    cfg.specific_files = ["f1_multiindex.h5", "f3_cache.pkl"]

    engine = RamDiskSyncEngine(cfg)

    # 首次同步
    res1 = engine.sync_once(force=False, ignore_time_filter=True)
    assert res1["status"] == "ok"
    assert len(res1["synced_files"]) == 2
    assert "f1_multiindex.h5" in res1["synced_files"]
    assert "f3_cache.pkl" in res1["synced_files"]
    
    # 确认未选中的文件绝不被同步到目标目录
    assert os.path.exists(os.path.join(tgt_dir, "f1_multiindex.h5"))
    assert os.path.exists(os.path.join(tgt_dir, "f3_cache.pkl"))
    assert not os.path.exists(os.path.join(tgt_dir, "f2_alerts.json"))
    assert not os.path.exists(os.path.join(tgt_dir, "f4_unused.csv"))
    assert not os.path.exists(os.path.join(tgt_dir, "f5_other.h5"))

    # 修改未被选中的文件 f2_alerts.json，再次同步 -> 应该仍然跳过
    with open(os.path.join(src_dir, "f2_alerts.json"), "w", encoding="utf-8") as f:
        f.write("modified f2")
    res2 = engine.sync_once(force=False, ignore_time_filter=True)
    assert len(res2["synced_files"]) == 0
    assert not os.path.exists(os.path.join(tgt_dir, "f2_alerts.json"))

    # 修改被选中的文件 f1_multiindex.h5，再次同步 -> 仅同步该文件
    time.sleep(1.1)
    with open(os.path.join(src_dir, "f1_multiindex.h5"), "w", encoding="utf-8") as f:
        f.write("modified f1 with new ticks")
    res3 = engine.sync_once(force=False, ignore_time_filter=True)
    assert len(res3["synced_files"]) == 1
    assert "f1_multiindex.h5" in res3["synced_files"]


def test_startup_baseline_check_bypasses_trading_hours(temp_dirs):
    """测试启动初检逻辑：即使处于非交易时段，目标位没有备份或缺失时也能初始化完成底包同步"""
    src_dir = temp_dirs["src"]
    tgt_dir = temp_dirs["tgt"]

    # 1. 创建源文件
    src_file = os.path.join(src_dir, "sina_MultiIndex_data.h5")
    with open(src_file, "wb") as f:
        f.write(b"SAMPLE_BIG_DATA_INIT")

    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.source_dir = src_dir
    cfg.target_dir = tgt_dir
    cfg.sync_scope = "specific_files"
    cfg.specific_files = ["sina_MultiIndex_data.h5"]
    
    # 严格开启交易日与交易时段限制（且设置一个不可能在当前匹配的虚构时段）
    cfg.only_workdays = True
    cfg.only_trading_hours = True
    cfg.trading_hours = [["03:00", "03:05"]]  # 凌晨3点才算交易时间

    engine = RamDiskSyncEngine(cfg)

    # 2. 验证常规周期性同步会被“非交易时段”拦截跳过
    normal_res = engine.sync_once(force=False, ignore_time_filter=False)
    assert normal_res["status"] == "skipped"
    assert "非交易时段" in normal_res["message"]
    assert not os.path.exists(os.path.join(tgt_dir, "sina_MultiIndex_data.h5"))

    # 3. 验证启动初检（check_and_sync_startup_baseline）不受交易时段限制，能自动补齐缺失底包
    init_res = engine.check_and_sync_startup_baseline()
    assert init_res["status"] == "ok"
    assert "sina_MultiIndex_data.h5" in init_res["synced_files"]
    assert os.path.exists(os.path.join(tgt_dir, "sina_MultiIndex_data.h5"))
    assert "启动初检初始化完成" in init_res["message"]

    # 4. 再次执行启动初检（目标目录与源目录一致无变化时），输出一致性完成报告
    init_res2 = engine.check_and_sync_startup_baseline()
    assert init_res2["status"] == "ok"
    assert len(init_res2["synced_files"]) == 0
    assert "目标备份位置数据完整且与源目录一致" in init_res2["message"]


def test_verbose_log_and_worker_wake_event(temp_dirs):
    """测试详细日志模式下的非交易时段消息结构与 Worker 主动唤醒标志"""
    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.source_dir = temp_dirs["src"]
    cfg.target_dir = temp_dirs["tgt"]
    cfg.only_workdays = True
    cfg.only_trading_hours = True
    cfg.trading_hours = [["09:15", "11:35"], ["13:00", "15:10"]]
    cfg.log_enabled = True

    engine = RamDiskSyncEngine(cfg)
    worker = RamDiskSyncWorker(engine)

    # 1. 模拟非交易时间执行常规同步
    night_time = datetime.datetime(2026, 8, 27, 22, 1, 0)
    res = engine.sync_once(force=False, ignore_time_filter=False)
    assert res["status"] == "skipped"
    assert "巡检待命跳过" in res["message"]
    assert "09:15-11:35" in res["message"]

    # 2. 测试 trigger_sync_now 设置唤醒标志
    worker._trigger_event = False
    worker.trigger_sync_now(force=False)
    assert worker._trigger_event is True


def test_backup_mode_diff_snapshot_and_rotation(temp_dirs):
    """测试差异快照版本归档模式：变动保留历史时间戳版本，并自动轮转超额旧快照"""
    src_dir = temp_dirs["src"]
    tgt_dir = temp_dirs["tgt"]

    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.source_dir = src_dir
    cfg.target_dir = tgt_dir
    cfg.sync_scope = "specific_files"
    cfg.specific_files = ["sina_MultiIndex_data.h5"]
    cfg.backup_mode = "diff_snapshot"
    cfg.max_snapshots_per_file = 3  # 最多保留 3 个快照版本

    engine = RamDiskSyncEngine(cfg)

    src_file = os.path.join(src_dir, "sina_MultiIndex_data.h5")
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    date_subfolder = os.path.join(tgt_dir, today_str)

    # 版本 1
    with open(src_file, "w", encoding="utf-8") as f:
        f.write("v1_data")
    res1 = engine.sync_once(force=False, ignore_time_filter=True)
    assert res1["status"] == "ok"
    assert len(res1["synced_files"]) == 1
    assert os.path.exists(os.path.join(date_subfolder, "sina_MultiIndex_data.h5"))

    # 版本 2
    time.sleep(1.1)
    with open(src_file, "w", encoding="utf-8") as f:
        f.write("v2_data_ticks")
    res2 = engine.sync_once(force=False, ignore_time_filter=True)
    assert len(res2["synced_files"]) == 1

    # 版本 3
    time.sleep(1.1)
    with open(src_file, "w", encoding="utf-8") as f:
        f.write("v3_data_ticks_more")
    res3 = engine.sync_once(force=False, ignore_time_filter=True)
    assert len(res3["synced_files"]) == 1

    # 版本 4（触发轮转删除）
    time.sleep(1.1)
    with open(src_file, "w", encoding="utf-8") as f:
        f.write("v4_data_ticks_final")
    res4 = engine.sync_once(force=False, ignore_time_filter=True)
    assert len(res4["synced_files"]) == 1

    # 验证目录中：包含 1 个基准文件 + 最多 3 个快照文件
    all_files = os.listdir(date_subfolder)
    snapshots = [f for f in all_files if f.startswith("sina_MultiIndex_data_") and f.endswith(".h5")]
    assert len(snapshots) <= 3
    assert "sina_MultiIndex_data.h5" in all_files


def test_normalize_dir_path():
    """测试 Windows 盘符与路径规范化"""
    from window_manager.sync_engine import normalize_dir_path
    assert normalize_dir_path("G:") == "G:\\"
    assert normalize_dir_path("g:") == "G:\\"
    assert normalize_dir_path("D:\\Ramdisk_Backup") == os.path.abspath("D:\\Ramdisk_Backup")


def test_clean_expired_backup_folders(temp_dirs):
    """测试过期历史日期归档目录清理机制"""
    tgt_dir = temp_dirs["tgt"]
    today = datetime.date.today()

    # 创建 4 个日期目录：今天、昨天、7天前、10天前(超期)
    dir_today = today.strftime("%Y%m%d")
    dir_yesterday = (today - datetime.timedelta(days=1)).strftime("%Y%m%d")
    dir_7d = (today - datetime.timedelta(days=7)).strftime("%Y%m%d")
    dir_15d = (today - datetime.timedelta(days=15)).strftime("%Y%m%d")
    dir_custom = "custom_non_date_folder"  # 非日期目录，绝不应被误删

    for d in [dir_today, dir_yesterday, dir_7d, dir_15d, dir_custom]:
        os.makedirs(os.path.join(tgt_dir, d), exist_ok=True)

    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.target_dir = tgt_dir
    cfg.backup_mode = "date_folder"
    cfg.keep_backup_days = 7  # 保留 7 天

    engine = RamDiskSyncEngine(cfg)

    # 执行清理
    cleaned = engine.clean_expired_backup_folders()
    assert dir_15d in cleaned
    assert not os.path.exists(os.path.join(tgt_dir, dir_15d))

    # 验证 7 天内的目录及自定义目录未被删除
    assert os.path.exists(os.path.join(tgt_dir, dir_today))
    assert os.path.exists(os.path.join(tgt_dir, dir_yesterday))
    assert os.path.exists(os.path.join(tgt_dir, dir_7d))
    assert os.path.exists(os.path.join(tgt_dir, dir_custom))

    # 验证 keep_backup_days = 0 时永久保留
    cfg.keep_backup_days = 0
    os.makedirs(os.path.join(tgt_dir, dir_15d), exist_ok=True)
    cleaned_zero = engine.clean_expired_backup_folders()
    assert len(cleaned_zero) == 0
    assert os.path.exists(os.path.join(tgt_dir, dir_15d))


def test_ramdisk_sync_dialog_ui_instantiation(temp_dirs):
    """测试 RamDiskSyncDialog 界面控件的完整实例化与符号绑定（防范 NameError）"""
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
    except Exception:
        pytest.skip("非 GUI / PyQt6 环境，跳过 UI 渲染测试")

    from window_manager.ui import RamDiskSyncDialog

    cfg = RamDiskSyncConfig(config_path=temp_dirs["cfg"])
    cfg.source_dir = temp_dirs["src"]
    cfg.target_dir = temp_dirs["tgt"]
    cfg.backup_mode = "diff_snapshot"
    cfg.keep_backup_days = 15

    engine = RamDiskSyncEngine(cfg)
    dlg = RamDiskSyncDialog(cfg, engine)

    # 验证所有控件实例正确生成
    assert dlg.spn_keep_days is not None
    assert dlg.spn_keep_days.value() == 15
    assert dlg.cb_backup_mode.currentData() == "diff_snapshot"
    assert dlg.spn_keep_days.isEnabled() is True

    # 模拟切换模式为 mirror，验证联动禁用
    dlg.cb_backup_mode.setCurrentIndex(2)  # mirror
    assert dlg.spn_keep_days.isEnabled() is False

    # 模拟切换回 date_folder，验证联动启用
    dlg.cb_backup_mode.setCurrentIndex(0)  # date_folder
    assert dlg.spn_keep_days.isEnabled() is True




