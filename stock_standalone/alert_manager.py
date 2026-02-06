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
from JohnsonUtil import commonTips as cct
# Fallback beep
try:
    import winsound
except ImportError:
    winsound = None

# Voice Engine Dependencies
# pyttsx3 and pythoncom are imported lazily in _voice_worker to save memory

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

def _voice_worker(q: mp.Queue, stop_event: mp.Event, interrupt_event: mp.Event, cancel_q: mp.Queue, current_key_arr: mp.Array, active_codes_arr: mp.Array, last_sync_time: mp.Value, feedback_queue: mp.Queue = None):
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
    last_speech_end_ts = 0.0 # [FIX] Timestamp of last speech completion


    while not stop_event.is_set():
        try:
            # 1. 刷新取消列表
            while not cancel_q.empty():
                try:
                    token = cancel_q.get_nowait()
                    if token == "__CLEAR__":
                        cancelled_set.clear()
                        worker_log("Cancelled set cleared by __CLEAR__ command")
                    else:
                        cancelled_set.add(token)
                except: break

            # 2. 获取消息 (阻塞)
            try:
                item = q.get(timeout=1.0)
            except: 
                # ⚡ [FIX] 队列空闲时清除 __ALL__ 标记，允许后续新报警正常播放
                if "__ALL__" in cancelled_set:
                    cancelled_set.discard("__ALL__")
                    worker_log("Cleared __ALL__ flag (queue idle)")
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
            # ⚡ [FIX] 处理 __ALL__ 全局取消标记
            if "__ALL__" in cancelled_set:
                worker_log(f"Global cancel (__ALL__): skipping {key}")
                # 不移除 __ALL__，保持全局取消状态直到队列清空
                continue
            if key and key in cancelled_set:
                worker_log(f"Skipping cancelled item: {key}")
                cancelled_set.discard(key)
                continue

            # ⭐ JIT (Just-In-Time) Check: Drain again in case cancellation arrived while waiting
            while not cancel_q.empty():
                try: cancelled_set.add(cancel_q.get_nowait())
                except: break
            # ⚡ [FIX] 再次检查 __ALL__
            if "__ALL__" in cancelled_set:
                worker_log(f"JIT Global cancel: skipping {key}")
                continue
            if key and key in cancelled_set:
                worker_log(f"JIT Skip: {key}")
                cancelled_set.discard(key)
                continue

            # 4. ** 隔离式播报周期 **
            # [FIX] 移除错误的时间戳过滤逻辑，改为仅在清空标记存在时跳过
            # if msg_t < last_speech_end_ts: 
            #     continue -- 此逻辑会导致排队中的信号被丢弃


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
                    
                    if active_str:
                        # 屏幕上有窗口，检查当前代码是否在其中
                        active_list = [c.strip() for c in active_str.split(',') if c.strip()]
                        if key not in active_list:
                            worker_log(f"Existence Warning (Window not active yet?): {key} (Active: {active_str})")
                            # continue # [FIX] Don't skip, assume window is creating
                except Exception as e:
                    worker_log(f"Skip Check Error: {e}")

            try:
                if pyttsx3:
                    engine = pyttsx3.init()
                    engine.setProperty('rate', cct.voice_rate)
                    engine.setProperty('volume', cct.voice_volume)
                    
                    if feedback_queue and key:
                        try: feedback_queue.put(('START', key))
                        except: pass

                    engine.say(safe_msg)
                    engine.runAndWait()
                    last_speech_end_ts = time.time() # [FIX] Update completion time
                    
                    # 播放结束
                    if feedback_queue and key:
                        try: feedback_queue.put(('END', key))
                        except: pass

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
        self.feedback_queue: mp.Queue = mp.Queue() # [NEW] 用于反馈开始/结束事件
        self.stop_event: mp.Event = mp.Event()
        self.interrupt_event: mp.Event = mp.Event()
        
        # Callbacks
        self.on_speak_start = None
        self.on_speak_end = None
        
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
        self._start_feedback_listener()
        
    def start(self):
        """启动或重启语音线程"""
        if self.process is None or not self.process.is_alive():
            self.stop_event.clear()
            self.interrupt_event.clear()
            
            self.process = mp.Process(
                target=_voice_worker, 
                args=(self.voice_queue, self.stop_event, self.interrupt_event, self.cancel_queue, self.current_key, self.active_codes_arr, self.last_sync_time, self.feedback_queue),
                daemon=True,
                name="AlertVoiceWorker"
            )
            logger.info("Alert voice worker (Enhanced Linkage) started.")
            self.process.start()

    def _start_feedback_listener(self):
        """启动反馈监听线程"""
        t = threading.Thread(target=self._feedback_loop, daemon=True, name="FeedbackListener")
        t.start()

    def _feedback_loop(self):
        """监听 worker 状态反馈"""
        logger.info("Feedback loop started.")
        while True:
            try:
                msg = self.feedback_queue.get(timeout=1.0)
                # logger.info(f"Feedback Received: {msg}") # Debug
                etype, key = msg
                if etype == 'START':
                    if self.on_speak_start:
                        try: self.on_speak_start(key)
                        except Exception as e: logger.error(f"Callback Start Error: {e}")
                elif etype == 'END':
                    if self.on_speak_end:
                        try: self.on_speak_end(key)
                        except Exception as e: logger.error(f"Callback End Error: {e}")
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Feedback loop error: {e}")

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

    def resume_voice(self):
        """
        恢复语音播报并清除取消标记
        [FIX] 清空积压的旧消息，防止恢复时突然播放大量过时报警 (幽灵语音)
        """
        self.voice_enabled = True
        try:
            # 1. 清空积压队列
            while not self.voice_queue.empty():
                try: self.voice_queue.get_nowait()
                except: break
            
            # 2. 清除 global stop 标记
            self.cancel_queue.put("__CLEAR__")
            logger.info("AlertManager: Voice resumed and queue flushed.")
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
            
        # 2. 日志 (Throttled)
        is_high = (priority <= 1)
        
        # [OPTIMIZATION] 全局报警日志流控
        # 如果短时间内大量报警，仅记录高优先级，或每隔一定时间记录一次
        log_allowed = True
        if not is_high:
            if now - self.global_last_alert < 0.1: # 100ms 内的连续低优先级报警不打印日志，防止 IO 阻塞
                log_allowed = False
        
        if log_allowed or is_high:
            self.global_last_alert = now
            prefix = "🔴" if priority == 0 else "📢" if priority == 1 else "ℹ️"
            logger.info(f"{prefix} [Alert] {message}")
        
        # 3. 语音 & BEEP (已禁用滴滴声)
        
        # [OPTIMIZATION] 队列深度保护
        # [FIX] 放宽限制：从20提升到50,避免过早丢弃语音
        # 如果队列堆积超过 50 条，且当前不是高优先级，则丢弃，防止语音进程处理不过来导致系统卡顿
        if self.voice_enabled and self.process and self.process.is_alive():
            try:
                q_size = self.voice_queue.qsize()
                if q_size > 50 and not is_high:
                    logger.warning(f"AlertManager: Queue full ({q_size}), dropped low priority alert: {key}")
                    return

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
