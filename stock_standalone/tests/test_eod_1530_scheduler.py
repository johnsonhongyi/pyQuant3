# -*- coding: utf-8 -*-
import datetime
from unittest.mock import MagicMock, patch
import pytest

import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from instock_MonitorTK import StockMonitorApp


class DummyApp:
    """轻量级 Mock 类，仅复用 schedule_15_30_job 与 run_15_30_task 的逻辑"""
    def __init__(self):
        self.scheduled_jobs = []
        self.threads_started = []
        self.df_all = None
        self._task_running = False

    def _schedule_after(self, delay_ms, func):
        self.scheduled_jobs.append((delay_ms, func))

    # 绑定待测函数
    schedule_15_30_job = StockMonitorApp.schedule_15_30_job
    run_15_30_task = StockMonitorApp.run_15_30_task


def test_schedule_15_30_job_far_before_1530():
    """测试距离 15:30 较远（>60秒）时，每 60 秒轮询一次"""
    app = DummyApp()
    # 模拟当前时间 14:00:00
    mock_now = datetime.datetime(2026, 9, 15, 14, 0, 0)
    with patch("instock_MonitorTK.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.datetime.combine
        
        app.schedule_15_30_job()
        
        assert len(app.scheduled_jobs) == 1
        delay_ms, func = app.scheduled_jobs[0]
        assert delay_ms == 60 * 1000  # 60秒
        assert func == app.schedule_15_30_job
        assert not hasattr(app, "_last_run_date") or app._last_run_date is None


def test_schedule_15_30_job_near_1530():
    """测试临近 15:30（<=60秒）时，自适应精确毫秒唤醒"""
    app = DummyApp()
    # 模拟当前时间 15:29:45 (距离 15:30 还有 15 秒)
    mock_now = datetime.datetime(2026, 9, 15, 15, 29, 45)
    with patch("instock_MonitorTK.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.datetime.combine
        
        app.schedule_15_30_job()
        
        assert len(app.scheduled_jobs) == 1
        delay_ms, func = app.scheduled_jobs[0]
        assert delay_ms == 15 * 1000  # 精确 15 秒
        assert func == app.schedule_15_30_job


def test_schedule_15_30_job_trigger_and_post_throttle():
    """测试到达 15:30 触发后台线程，并将后续调度间隔拉长至 30 分钟"""
    app = DummyApp()
    mock_now = datetime.datetime(2026, 9, 15, 15, 30, 2)
    with patch("instock_MonitorTK.datetime") as mock_dt, \
         patch("instock_MonitorTK.threading.Thread") as mock_thread_cls:
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.datetime.combine
        mock_thread_inst = MagicMock()
        mock_thread_cls.return_value = mock_thread_inst

        app.schedule_15_30_job()

        # 验证线程启动
        mock_thread_cls.assert_called_once_with(
            target=app.run_15_30_task,
            name="EOD_15_30_Task",
            daemon=True
        )
        mock_thread_inst.start.assert_called_once()
        assert app._last_run_date == mock_now.date()

        # 验证下次调度间隔为 30 分钟 (1800000 ms)
        assert len(app.scheduled_jobs) == 1
        delay_ms, _ = app.scheduled_jobs[0]
        assert delay_ms == 30 * 60 * 1000

        # 当天再次调用时，不重复启动线程，保持 30 分钟轮询
        mock_thread_cls.reset_mock()
        app.scheduled_jobs.clear()
        app.schedule_15_30_job()
        mock_thread_cls.assert_not_called()
        assert app.scheduled_jobs[0][0] == 30 * 60 * 1000


def test_run_15_30_task_decoupled_guards():
    """测试 write_all_day_date == today 时，不阻断 STEP 1~3，仅跳过 STEP 4"""
    app = DummyApp()
    today_str = "2026-09-15"

    with patch("instock_MonitorTK.cct.get_today", return_value=today_str), \
         patch("instock_MonitorTK.cct.get_trade_date_status", return_value=True), \
         patch("instock_MonitorTK.tdd.Write_market_all_day_mp") as mock_write_mp, \
         patch("instock_MonitorTK.logger") as mock_logger:

        # 外部进程已提前写入 write_all_day_date = today_str
        import instock_MonitorTK
        instock_MonitorTK.write_all_day_date = today_str

        # 首次调用：入口守卫不应拦截
        app.run_15_30_task()

        # 验证 STEP 4 未执行 tdd.Write_market_all_day_mp (因为外部已写)
        mock_write_mp.assert_not_called()

        # 验证记录了本进程完成标记
        assert getattr(app, "_eod_completed_date", None) == today_str

        # 第二次调用：入口守卫根据 _eod_completed_date 正常早退
        mock_logger.reset_mock()
        app.run_15_30_task()
        mock_logger.warning.assert_any_call(
            f"[15:30 Task] skip: all EOD tasks already completed for {today_str}"
        )
