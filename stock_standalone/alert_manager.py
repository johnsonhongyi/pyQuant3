# -*- coding: utf-8 -*-
"""
Alert Manager - 统一报警管理模块
支持优先级队列、多进程语音播报、冷却控制
"""
import multiprocessing as mp
import threading
import time
import logging
from queue import Empty
from typing import Optional
from dataclasses import dataclass, field
import re

# Optional Imports
try:
    import pyttsx3
    import pythoncom
except ImportError:
    pyttsx3 = None
    pythoncom = None

from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger(name="AlertManager")

@dataclass(order=True)
class AlertItem:
    priority: int
    message: str = field(compare=False)
    timestamp: float = field(compare=False, default_factory=time.time)

def normalize_speech_text(text: str) -> str:
    """语音文本标准化 (处理 - % 等符号)"""
    text = str(text)
    text = text.replace('%', '百分之')
    text = re.sub(r'(?<!\d)-(\d+(\.\d+)?)', r'负\1', text)
    text = re.sub(r'(?<!\d)\+(\d+(\.\d+)?)', r'正\1', text)
    text = re.sub(r'(\d+)\.(\d+)', r'\1点\2', text)
    return text

def _voice_worker(queue: mp.Queue, stop_event: mp.Event):
    """
    语音播报后台进程
    """
    engine = None
    try:
        # COM 初始化 (Windows必需)
        if pythoncom:
            pythoncom.CoInitialize()
            
        if pyttsx3:
            engine = pyttsx3.init()
            engine.setProperty('rate', 220)  # 语速稍快
            engine.setProperty('volume', 1.0)
    except Exception as e:
        # 无法在进程中打印 logger (可能还没配置), print fallback
        print(f"Voice worker init failed: {e}")
        return

    while not stop_event.is_set():
        try:
            # 阻塞获取，超时 1s 检查 stop_event
            priority, message = queue.get(timeout=1.0)
            
            if engine:
                # 文本处理
                safe_msg = normalize_speech_text(message)
                
                # 播报
                engine.say(safe_msg)
                engine.runAndWait()
                
        except Empty:
            continue
        except Exception as e:
            print(f"Voice playback error: {e}")
            time.sleep(1) # 避免死循环刷屏

    # Cleanup
    if pythoncom:
        pythoncom.CoUninitialize()

class AlertManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.enabled = True
        self.voice_enabled = True
        
        # 优先级队列 (虽然 mp.Queue 不是 PriorityQueue，但我们可以在 push 时做简单处理或直接用 mp.PriorityQueue)
        # mp.PriorityQueue 有时在 windows 上有问题，这里为了稳健，暂时用普通 Queue，
        # 既然是语音，其实顺序也就是先进先出。如果真要插队，需要更复杂设计。
        # 考虑到"高优先级插队"需求，我们可以用 2 个队列? 
        # 简化: 目前使用单一 FIFO 队列。Voice 是一条条读的。
        self.voice_queue = mp.Queue()
        self.stop_event = mp.Event()
        
        self.process = mp.Process(
            target=_voice_worker, 
            args=(self.voice_queue, self.stop_event),
            daemon=True,
            name="AlertVoiceWorker"
        )
        
        # 冷却记录 {key: last_time}
        self.cooldowns = {}
        self.global_last_alert = 0
        
    def start(self):
        if not self.process.is_alive():
            logger.info("启动语音报警进程...")
            self.process.start()
            
    def stop(self):
        self.stop_event.set()
        if self.process.is_alive():
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.terminate()
        logger.info("语音报警进程已停止")

    def send_alert(self, message: str, priority: int = 1, key: Optional[str] = None, cooldown: int = 0):
        """
        发送报警
        :param message: 报警内容
        :param priority: 优先级 (0=Critical, 1=High, 2=Normal) - 数字越小优先级越高
        :param key: 冷却键 (例如 stock_code)
        :param cooldown: 冷却时间 (秒)
        """
        if not self.enabled:
            return
            
        # 1. 冷却检查
        now = time.time()
        if key and cooldown > 0:
            last = self.cooldowns.get(key, 0)
            if now - last < cooldown:
                return # 冷却中
            self.cooldowns[key] = now
            
        # 全局冷却 (避免极短时间刷屏，除非是 Critical)
        if priority > 0 and now - self.global_last_alert < 1.0:
            return 
        self.global_last_alert = now
        
        # 2. 日志记录
        log_prefix = "🔴" if priority == 0 else "📢" if priority == 1 else "ℹ️"
        logger.info(f"{log_prefix} [Alert] {message}")
        
        # 3. 语音播报
        if self.voice_enabled and self.process.is_alive():
            try:
                # 放入队列 (Priority, Message)
                # 由于 mp.Queue 不支持 Priority，我们直接 put
                # Worker 那边不做 Priority 排序，直接读。
                # 如果需要严格 Priority，需改用 mp.PriorityQueue 这里的参数仅作参考
                self.voice_queue.put((priority, message))
            except Exception as e:
                logger.error(f"Failed to queue alert: {e}")

# 全局单例获取
def get_alert_manager():
    return AlertManager()

if __name__ == "__main__":
    # Test
    manager = get_alert_manager()
    manager.start()
    
    print("Testing alert...")
    manager.send_alert("测试报警系统启动", priority=0)
    time.sleep(2)
    manager.send_alert("高优先级报警", priority=1)
    
    time.sleep(3)
    manager.stop()
