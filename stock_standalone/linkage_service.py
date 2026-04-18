# -*- coding: utf-8 -*-
"""
LinkageService - 独立联动与 IO 处理进程
核心理念：一阶解耦，状态驱动 (State-Driven) 而非任务驱动。
"""

import multiprocessing
import queue
import time
import os
import traceback
import sys
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct
# [ROOT-FIX] 设置标记，防止本进程内部调用 StockSender 时再次通过 Proxy 转发导致无限递归
os.environ["IN_LINKAGE_PROCESS_MARK"] = "1"

# 获取日志
logger = LoggerFactory.getLogger("LinkageService")

class LinkageService:
    def __init__(self, task_queue):
        self.task_queue = task_queue
        self.latest_cmd = None
        self.last_exec_ts = 0
        self.throttle_interval = 0.05  # 50ms 强制节流
        self._running = True
        self.sender = None

    def _init_sender(self):
        if self.sender is None:
            try:
                from JohnsonUtil.stock_sender import StockSender
                self.sender = StockSender()
                logger.info("📡 Linkage Service: StockSender initialized.")
            except Exception as e:
                logger.error(f"Failed to init StockSender: {e}")

    def run(self):
        logger.info(f"🚀 Linkage Service process started (PID: {os.getpid()})")
        
        while self._running:
            try:
                # 1. 状态覆盖模型：尽可能清空队列，只保留最后一项“意图”
                while True:
                    try:
                        msg = self.task_queue.get(timeout=0.02)
                        if msg == "EXIT":
                            self._running = False
                            break
                        self.latest_cmd = msg
                    except queue.Empty:
                        break

                if not self._running: break

                # 2. 状态执行与节流逻辑
                now = time.time()
                if self.latest_cmd and (now - self.last_exec_ts >= self.throttle_interval):
                    self._execute(self.latest_cmd)
                    self.latest_cmd = None  # 执行完即视为状态已对齐
                    self.last_exec_ts = now

                time.sleep(0.01) # 防止空转

            except Exception as e:
                logger.error(f"❌ LinkageService Inner Error: {e}\n{traceback.format_exc()}")
                time.sleep(1)

        logger.info("🛑 Linkage Service process exiting.")

    def _execute(self, cmd_opt):
        """处理具体联动指令"""
        code = cmd_opt.get('code')
        flags = cmd_opt.get('flags', {})
        
        if not code: return

        try:
            self._init_sender()
            
            # 1. 核心物理联动派发
            if self.sender:
                self.sender._do_send(code, flags)
                
        except Exception as e:
            logger.error(f"Execution error for {code}: {e}")

def _start_linkage_worker(q):
    service = LinkageService(q)
    service.run()

class LinkageManagerProxy:
    """管理后台进程的生命周期与通讯接口"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LinkageManagerProxy, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        _multiprocessingQueue = getattr(cct, "multiprocessingQueue", 300)
        self.queue = multiprocessing.Queue(maxsize=_multiprocessingQueue)
        self.process = multiprocessing.Process(
            target=_start_linkage_worker,
            args=(self.queue,),
            name="LinkageProcess",
            daemon=True
        )
        self.process.start()
        logger.info(f"Linkage process launched. PID: {self.process.pid}")

    def push(self, code, flags=None):
        """投递一个联动意图 (State Overwrite)"""
        if not code: return
        flags = flags or {'tdx': True, 'ths': True, 'dfcf': True}

        # 状态覆盖：如果队列已满，尝试清理旧数据
        if self.queue.full():
            try:
                # 尽可能清空积压，因为联动只关心最新的
                for _ in range(5):
                    self.queue.get_nowait()
            except: pass
        
        try:
            self.queue.put_nowait({
                'code': code,
                'flags': flags,
                'ts': time.time()
            })
        except queue.Full:
            # 极端高频下如果还是满的，直接忽略，保证主流程不中断
            pass
        except Exception as e:
            logger.error(f"LinkageManagerProxy push error: {e}")

    def stop(self):
        try:
            self.queue.put("EXIT")
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.terminate()
        except: pass

global_manager = None
def get_link_manager():
    global global_manager
    if global_manager is None:
        global_manager = LinkageManagerProxy()
    return global_manager
