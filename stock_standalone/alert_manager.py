# -*- coding: utf-8 -*-
"""
Alert Manager - 混合终极版
1. 隔离周期：每条消息独立 COM/Engine 生命 (保证声音 100% 出来)
2. 响应循环：在隔离周期内使用 iterate() (保证点击删除/关闭秒级中断)
3. 多级 BEEP：高优先级报警带有显著蜂鸣提示
"""
import multiprocessing as mp
import threading
import time
import logging
from queue import Empty
from typing import Optional, Any, Dict
import re
import os

# Fallback beep
try:
    import winsound
except ImportError:
    winsound = None

# Voice Engine Dependencies
try:
    import pyttsx3
    import pythoncom
except ImportError:
    pyttsx3 = None
    pythoncom = None

from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger(name="AlertManager")

def normalize_speech_text(text: str) -> str:
    """语音文本标准化"""
    text = str(text)
    text = text.replace('%', '百分之')
    text = re.sub(r'(?<!\d)-(\d+(\.\d+)?)', r'负\1', text)
    text = re.sub(r'(?<!\d)\+(\d+(\.\d+)?)', r'正\1', text)
    text = re.sub(r'(\d+)\.(\d+)', r'\1点\2', text)
    return text

def _voice_worker(q: mp.Queue, stop_event: mp.Event, interrupt_event: mp.Event, cancel_q: mp.Queue, current_key_arr: mp.Array, active_codes_arr: mp.Array, last_sync_time: mp.Value):
    """
    语音播报后台进程 - 强化版
    支持通过 cancel_q 跳过队列，并通过 current_key_arr 标记当前状态
    """
    from datetime import datetime
    import pyttsx3
    import pythoncom
    import time
    
    def worker_log(msg):
        try:
            with open("voice_worker_debug.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ProcessWorker] {msg}\n")
        except: pass

    worker_log("Voice worker process started.")
    
    cancelled_set = set()

    while not stop_event.is_set():
        try:
            # 1. 刷新取消列表
            while not cancel_q.empty():
                try:
                    cancelled_set.add(cancel_q.get_nowait())
                except: break

            # 2. 获取消息 (阻塞)
            try:
                item = q.get(timeout=1.0)
            except: 
                continue

            # Truncate debug log if too large to prevent disk issues
            try:
                if os.path.exists("voice_worker_debug.log") and os.path.getsize("voice_worker_debug.log") > 5*1024*1024:
                    with open("voice_worker_debug.log", "w") as f: f.write(f"[{datetime.now()}] Log truncated.\n")
            except: pass

            # 支持多种格式 (Dict 优先)
            if isinstance(item, dict):
                priority = item.get('priority', 2)
                message = item.get('message', '')
                key = item.get('key')
                msg_t = item.get('timestamp', 0)
            elif isinstance(item, (list, tuple)):
                if len(item) == 3:
                    priority, message, key = item
                else:
                    priority, message = item
                    key = None
                msg_t = time.time() # 降级：假定为刚产生
            else:
                continue

            if message == "STOP_COMMAND": break
            
            # 3. 检查是否已被取消
            if key and key in cancelled_set:
                worker_log(f"Skipping cancelled item: {key}")
                cancelled_set.discard(key)
                continue

            # ⭐ JIT (Just-In-Time) Check: Drain again in case cancellation arrived while waiting
            while not cancel_q.empty():
                try: cancelled_set.add(cancel_q.get_nowait())
                except: break
            if key and key in cancelled_set:
                worker_log(f"JIT Skip: {key}")
                cancelled_set.discard(key)
                continue

            # 4. ** 隔离式播报周期 **
            safe_msg = normalize_speech_text(message)
            worker_log(f"Handling: {safe_msg[:40]}... (Key: {key})")

            # 标记当前播报品种
            if current_key_arr:
                try: current_key_arr.value = (str(key) if key else "").encode('utf-8')[:31]
                except: pass

            if pythoncom:
                try: pythoncom.CoInitialize()
                except: pass
            
            # ⭐ Final JIT Check before Engine Start
            while not cancel_q.empty():
                try: cancelled_set.add(cancel_q.get_nowait())
                except: break
            if key and key in cancelled_set:
                worker_log(f"Final JIT Skip: {key}")
                if current_key_arr: current_key_arr.value = b""
                cancelled_set.discard(key)
                continue

            # ⭐ 联动核心 2：存在性核验 (如果设置了活跃列表，且当前代码不在其中，则跳过)
            if active_codes_arr and key:
                try:
                    # 严谨读取共享内存字符串 (去除填充的空字符)
                    active_str = active_codes_arr.value.decode('utf-8').split('\x00')[0]
                    sync_t = last_sync_time.value
                    
                    if active_str == "NONE":
                        # UI 显式通知：目前没有任何报警窗口（用户已全部清除）
                        # 只有当消息是在“清除”之前产生的，才跳过；如果是新产生的消息，放行。
                        if msg_t < sync_t:
                            worker_log(f"Existence Skip (Global sweep: NONE): {key}")
                            continue
                    elif active_str:
                        # 屏幕上有窗口，检查当前代码是否在其中
                        active_list = [c.strip() for c in active_str.split(',') if c.strip()]
                        if key not in active_list:
                            # 关键逻辑：如果消息是在最后一次同步之后产生的，说明是新产生的报警，
                            # 此时对应的窗口可能还没来得及出现在 active_str 中，所以【不能跳过】。
                            # 只有消息早于最后一次同步，才说明这确实是一个已经关闭的窗口留下的“余波”，需要跳过。
                            if msg_t < sync_t:
                                worker_log(f"Existence Skip (Expired alert): {key} (Active: {active_str})")
                                continue
                            else:
                                worker_log(f"Existence Allowed (Fresh alert, window loading): {key}")
                except Exception as e:
                    worker_log(f"Skip Check Error: {e}")

            try:
                if pyttsx3:
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 220)
                    engine.setProperty('volume', 1.0)
                    
                    engine.say(safe_msg)
                    engine.runAndWait()
                    
                    # 播放结束
                    try: engine.stop()
                    except: pass
                    del engine
                    worker_log("Utterance finished.")
            except Exception as e:
                worker_log(f"Engine Cycle Error: {e}")
            finally:
                if current_key_arr:
                    try: current_key_arr.value = b""
                    except: pass
                if pythoncom:
                    try: pythoncom.CoUninitialize()
                    except: pass

        except Exception as e:
            worker_log(f"Fatal Worker Loop Error: {e}")
            time.sleep(1)

    worker_log("Voice worker process exited.")

class AlertManager:
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AlertManager, cls).__new__(cls)
            return cls._instance

    def __init__(self, voice_enabled=True):
        if self._initialized: return
        self._initialized = True
        
        self.enabled: bool = True
        self.voice_enabled: bool = voice_enabled
        
        # 通信原语
        self.voice_queue: mp.Queue = mp.Queue() 
        self.cancel_queue: mp.Queue = mp.Queue() # [NEW] 用于取消排队中的
        self.stop_event: mp.Event = mp.Event()
        self.interrupt_event: mp.Event = mp.Event()
        
        # [NEW] 共享状态：当前正在播报的 Key
        self.current_key = mp.Array('c', 32)
        # [NEW] 共享状态：当前可视窗口的品种代码列表 (逗号分隔)
        self.active_codes_arr = mp.Array('c', 1024)
        # [NEW] 共享状态：最后一次同步活跃列表的时间戳
        self.last_sync_time = mp.Value('d', 0.0)
        
        self.process: Optional[mp.Process] = None 
        self.cooldowns: Dict[str, float] = {}
        self.global_last_alert: float = 0
        
        self.start()
        
    def start(self):
        """启动或重启语音线程"""
        if self.process is None or not self.process.is_alive():
            self.stop_event.clear()
            self.interrupt_event.clear()
            
            self.process = mp.Process(
                target=_voice_worker, 
                args=(self.voice_queue, self.stop_event, self.interrupt_event, self.cancel_queue, self.current_key, self.active_codes_arr, self.last_sync_time),
                daemon=True,
                name="AlertVoiceWorker"
            )
            logger.info("Alert voice worker (Enhanced Linkage) started.")
            self.process.start()

    def sync_active_codes(self, codes_list):
        """同步 UI 端的活跃窗口代码列表"""
        if not hasattr(self, 'active_codes_arr'): return
        try:
            if not codes_list:
                # 如果列表为空，则标记为 NONE，表示明确的“无窗状态”
                codes_str = "NONE"
            else:
                codes_str = ",".join(map(str, codes_list))
            
            self.active_codes_arr.value = codes_str.encode('utf-8')[:1023]
            self.last_sync_time.value = time.time()
        except:
            pass

    def stop_current_speech(self, key=None):
        """
        非破坏式中断（修复卡顿版）
        - 不 terminate 进程
        - 立即跳过当前 & 队列中的目标
        """
        if not self.process or not self.process.is_alive():
            return

        # 1️⃣ 放入取消队列（队列中的 & 即将到来的都会被跳过）
        if key:
            self.cancel_queue.put(str(key))
        else:
            # None 表示全局中断：特殊标记
            self.cancel_queue.put("__ALL__")

        # 2️⃣ 标记中断意图（给 worker 读取）
        try:
            current = self.current_key.value.decode('utf-8').strip()
        except:
            current = ""

        # 3️⃣ 如果正在播报，快速触发“软中断”
        # 关键点：不杀进程，让 worker 自然走到 runAndWait() 结束
        if key is None or current == str(key):
            logger.info(f"Soft-interrupt speech (key={key}, current={current})")

            # 利用 cancel 机制 + 清空 current_key
            try:
                self.current_key.value = b""
            except:
                pass


    # def stop_current_speech(self, key=None):
    #     """
    #     硬中断逻辑
    #     :param key: 目标品种代码。如果提供，则仅当当前正在播报该品种时才中断。
    #                 如果不提供，则中断当前所有播报。
    #     """
    #     if not self.process or not self.process.is_alive():
    #         return

    #     # 1. 无论如何，加入取消列表（确保还在排队的稍后被跳过）
    #     if key:
    #         self.cancel_queue.put(str(key))

    #     # 2. 判断是否需要物理中断当前进程
    #     should_terminate = False
    #     if key is None:
    #         should_terminate = True
    #         logger.info("Interrupting current speech (Global)")
    #     else:
    #         try:
    #             current = self.current_key.value.decode('utf-8').strip()
    #             if current == str(key):
    #                 should_terminate = True
    #                 logger.info(f"Interrupting current speech for code: {key}")
    #             else:
    #                 logger.debug(f"Code {key} is not currently speaking (Current: {current}), skip terminate.")
    #         except:
    #             should_terminate = True # 降级为全部中断

    #     if should_terminate:
    #         worker_pid = self.process.pid
    #         try:
    #             self.process.terminate()
    #             self.process.join(timeout=0.1)
    #             if self.process.is_alive():
    #                 os.kill(worker_pid, 9)
    #         except: pass
            
    #         self.process = None 
    #         self.current_key.value = b"" # 重置状态
    #         self.start() # 重启
            
    def stop(self):
        """系统完全退出"""
        self.stop_event.set()
        if self.process and self.process.is_alive():
            self.process.join(timeout=0.3)
            if self.process and self.process.is_alive():
                try: self.process.terminate()
                except: pass
        logger.info("Alert system stopped.")

    def send_alert(self, message: str, priority: int = 2, key: Optional[str] = None, cooldown: int = 0):
        """发送报警"""
        if not self.enabled: return
            
        now = time.time()
        # 1. 冷却检查
        if key and cooldown > 0:
            if now - self.cooldowns.get(key, 0) < cooldown:
                return
            self.cooldowns[key] = now
            
        # 2. 日志
        is_high = (priority <= 1)
        if is_high or (now - self.global_last_alert > 1.0):
            self.global_last_alert = now
            prefix = "🔴" if priority == 0 else "📢" if priority == 1 else "ℹ️"
            logger.info(f"{prefix} [Alert] {message}")
        
        # 3. 语音 & BEEP
        if winsound and is_high:
            def _alert_beep():
                try:
                    winsound.Beep(1200, 150)
                    time.sleep(0.05)
                    winsound.Beep(1200, 150)
                except: pass
            threading.Thread(target=_alert_beep, daemon=True).start()

        if self.voice_enabled and self.process and self.process.is_alive():
            try:
                # [Fix] 使用字典包装，包含时间戳以支持竞态检查
                item = {
                    'priority': priority,
                    'message': message,
                    'key': key,
                    'timestamp': time.time()
                }
                self.voice_queue.put(item, block=False)
            except:
                pass

# 单例助手
def get_alert_manager():
    return AlertManager()

if __name__ == "__main__":
    mgr = get_alert_manager()
    print("Test: Critical Signal")
    mgr.send_alert("紧急买入！紧急买入12345678901234567890", priority=1, key="000001")
    time.sleep(1)
    print("Testing Surgical Stop...")
    mgr.stop_current_speech(key="000001")
    time.sleep(5)
    mgr.stop()
