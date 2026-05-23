from __future__ import annotations

import os
import tempfile
import time
from multiprocessing import Process
from trading_kernel.engine.state_manager import StateManager, IN_TRADE, COOLDOWN, FLAT


def _writer_worker(code: str, state: str) -> None:
    """独立的子进程写入辅助函数"""
    sm = StateManager()
    sm.set(code, state)


def test_state_manager_multiprocess_concurrency():
    # 物理清空已有的状态文件，确保纯净测试
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, "trading_kernel_shared_state.json")
    lockpath = os.path.join(temp_dir, "trading_kernel_shared_state.lock")
    for p in (filepath, lockpath):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    sm_parent = StateManager()
    
    # 场景 A: 启动 3 个独立子进程，分别并发写入不同的个股行为状态
    p1 = Process(target=_writer_worker, args=("600519", IN_TRADE))
    p2 = Process(target=_writer_worker, args=("000001", COOLDOWN))
    p3 = Process(target=_writer_worker, args=("601318", IN_TRADE))

    p1.start()
    p2.start()
    p3.start()

    p1.join()
    p2.join()
    p3.join()

    # 场景 B: 父进程进行状态同步与核验，确保跨进程合并成功
    assert sm_parent.get("600519") == IN_TRADE
    assert sm_parent.get("000001") == COOLDOWN
    assert sm_parent.get("601318") == IN_TRADE
    assert sm_parent.get("999999") == FLAT  # 默认值正确


def test_state_manager_deadlock_self_healing():
    temp_dir = tempfile.gettempdir()
    lockpath = os.path.join(temp_dir, "trading_kernel_shared_state.lock")
    
    # 模拟遗留死锁文件，修改修改时间为 5 秒前 (过期)
    with open(lockpath, "w") as f:
        f.write("DEADLOCK")
    past_time = time.time() - 5.0
    os.utime(lockpath, (past_time, past_time))

    # 初始化 StateManager 并进行状态设置，应当在 0.3s 内自愈物理清除死锁锁并顺利完成写入
    sm = StateManager()
    start_time = time.time()
    sm.set("000002", COOLDOWN)
    duration = time.time() - start_time

    assert duration < 0.5  # 证明没有被死锁挂起
    assert sm.get("000002") == COOLDOWN
    assert not os.path.exists(lockpath)  # 死锁文件已被物理清除
