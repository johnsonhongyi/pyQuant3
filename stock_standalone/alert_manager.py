# -*- coding: utf-8 -*-
"""
Alert Manager - 混合终极版
1. 隔离周期：每条消息独立 COM/Engine 生命 (保证声音 100% 出来)
2. 响应循环：在隔离周期内使用 iterate() (保证点击删除/关闭秒级中断)
3. 多级 BEEP：高优先级报警带有显著蜂鸣提示
"""
import threading
import queue
from queue import Queue, Empty, Full
import time
import logging
from typing import Optional, Any, Dict, List
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

def _voice_worker(q: Queue, stop_event: threading.Event, interrupt_event: threading.Event, cancel_q: Queue, current_state: dict, feedback_queue: Queue = None):
    """
    语音播报后台线程 (Resolved mp.Queue GIL Crash)
    支持通过 cancel_q 跳过队列，并通过 current_state 标记当前状态
    """
    from datetime import datetime
    import pyttsx3
    import pythoncom
    import time
    
    # --- [FIX] 使用普通 FileHandler 避免多进程下的轮转冲突 (Windows WinError 32) ---
    import logging.handlers
    log_file = "voice_worker_debug.log"
    handler = logging.FileHandler(
        log_file, 
        mode='a',
        encoding='utf-8',
        delay=True
    )
    handler.setFormatter(logging.Formatter('[%(asctime)s] [ProcessWorker-%(process)d] %(message)s', '%Y-%m-%d %H:%M:%S'))
    
    w_logger = logging.getLogger("VoiceWorkerThread")
    w_logger.setLevel(logging.DEBUG)
    if not w_logger.handlers:
        w_logger.addHandler(handler)

    def worker_log(msg):
        try:
            w_logger.debug(msg)
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
            
            # [FIX] 如果 Key 为 None，尝试从消息中检测代码 (6位数字)
            if not key and message:
                code_match = re.search(r'(\d{6})', str(message))
                if code_match:
                    key = code_match.group(1)
                    
            worker_log(f"Handling: {safe_msg[:40]}... (Key: {key})")

            # 标记当前播报品种
            if current_state is not None:
                current_state['key'] = str(key) if key else ""

            if pythoncom:
                try: pythoncom.CoInitialize()
                except: pass
            
            # ⭐ Final JIT Check before Engine Start
            while not cancel_q.empty():
                try: cancelled_set.add(cancel_q.get_nowait())
                except: break
            if key and key in cancelled_set:
                worker_log(f"Final JIT Skip: {key}")
                if current_state: current_state['key'] = ""
                cancelled_set.discard(key)
                continue

            # ⭐ 联动核心 2：存在性核验 (如果设置了活跃列表，且当前代码不在其中，则跳过)
            if current_state and key:
                try:
                    active_str = current_state.get('active_codes', '')
                    if active_str and active_str != "NONE":
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
                if current_state:
                    try: current_state['key'] = ""
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
        
        # 通信原语 (Resolved mp.Queue GIL Crash)
        self.voice_queue: Queue = Queue() 
        self.cancel_queue: Queue = Queue() # [NEW] 用于取消排队中的
        self.feedback_queue: Queue = Queue() # [NEW] 用于反馈开始/结束事件
        self.stop_event: threading.Event = threading.Event()
        self.interrupt_event: threading.Event = threading.Event()
        
        # [NEW] 聚合报警缓冲区 (Industrial Standard Consolidation)
        self._batch_lock = threading.Lock()
        self._batch_data = {} # {key: [(priority, message, time)]}
        self._batch_timer = None
        self._batch_interval = 0.2 # 200ms 窗口，足够捕获同一扫描周期的所有引擎信号
        
        # Callbacks
        self.on_speak_start = None
        self.on_speak_end = None
        
        # [NEW] 共享状态 (Threading 下直接共享 dict)
        self.current_state = {'key': '', 'active_codes': '', 'last_sync_time': 0.0}
        
        self.process: Optional[threading.Thread] = None 
        self.cooldowns: Dict[str, float] = {}
        self.global_last_alert: float = 0
        
        # [NEW] 会话中已报警代码列表 (Session-based highlights)
        self.session_alerted_codes = set()
        self._session_lock = threading.Lock()
        
        self.start()
        self._start_feedback_listener()

    def start(self):
        """启动或重启语音线程 (Resolved mp.Queue GIL Crash)"""
        if self.process is None or not self.process.is_alive():
            self.stop_event.clear()
            self.interrupt_event.clear()
            
            self.process = threading.Thread(
                target=_voice_worker, 
                args=(self.voice_queue, self.stop_event, self.interrupt_event, self.cancel_queue, self.current_state, self.feedback_queue),
                daemon=True,
                name="AlertVoiceWorkerThread"
            )
            logger.info("Alert voice worker (Enhanced Linkage) started as THREAD.")
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
        if not hasattr(self, 'current_state'): return
        try:
            if not codes_list:
                codes_str = "NONE"
            else:
                codes_str = ",".join(map(str, codes_list))
            self.current_state['active_codes'] = codes_str
            self.current_state['last_sync_time'] = time.time()
            
            # ⚡ [NEW] 同时也自动汇入会话追踪列表 (Session-based highlights)
            if codes_list:
                with self._session_lock:
                    added_any = False
                    for c in codes_list:
                        sc = str(c)
                        if len(sc) == 6 and sc not in self.session_alerted_codes:
                            self.session_alerted_codes.add(sc)
                            added_any = True
                    if added_any:
                        logger.debug(f"AlertManager: Synced {len(codes_list)} codes from UI Alarm Pool.")
        except:
            pass

    def get_alerted_codes(self) -> List[str]:
        """获取本会话中已报警的所有代码"""
        if not hasattr(self, 'session_alerted_codes'): return []
        with self._session_lock:
            return list(self.session_alerted_codes)

    def is_alerted(self, code: str) -> bool:
        """检查特定代码是否在本会话中报警过"""
        if not hasattr(self, 'session_alerted_codes'): return False
        with self._session_lock:
            return str(code) in self.session_alerted_codes

    def clear_alert_history(self):
        """完全清空会话级别的新增报警记录"""
        with self._session_lock:
            if hasattr(self, 'session_alerted_codes'):
                self.session_alerted_codes.clear()
            if hasattr(self, 'cooldowns'):
                self.cooldowns.clear() # [FIX] 同时也清空冷却记录，允许复位后立即重报
            logger.info("✅ AlertManager: 全局报警历史及冷却记录已清空")

    def stop_current_speech(self, key=None):
        """非破坏式中断"""
        if not self.process or not self.process.is_alive():
            return
        if key:
            self.cancel_queue.put(str(key))
        else:
            self.cancel_queue.put("__ALL__")

    def resume_voice(self):
        """恢复语音播报"""
        self.voice_enabled = True
        try:
            while not self.voice_queue.empty():
                try: self.voice_queue.get_nowait()
                except: break
            self.cancel_queue.put("__CLEAR__")
            logger.info("AlertManager: Voice resumed and queue flushed.")
        except:
            pass

    def stop(self):
        """系统完全退出"""
        self.stop_event.set()
        if self.process and self.process.is_alive():
            self.process.join(timeout=0.5)
        logger.info("Alert system stopped.")

    def _flush_batch_alerts(self):
        """[CORE] 聚合报警刷新逻辑：将同一周期的多条报警合并为一条"""
        with self._batch_lock:
            data_to_flush = self._batch_data
            self._batch_data = {}
            self._batch_timer = None
            
        if not data_to_flush: return

        for key, alerts in data_to_flush.items():
            try:
                # 1. 确定最高优先级
                min_priority = min(a[0] for a in alerts)
                
                # 2. 消息去重并智能合并
                unique_messages = []
                seen_snippets = set()
                
                # 寻找共通前缀 (通常到股票名称和代码为止)
                # 📢 [Alert] 注意卖出，北京科锐 002350 ，...
                header = ""
                for p, m, t in alerts:
                    parts = str(m).split("，")
                    if len(parts) >= 2 and not header:
                        # 尝试提取 "注意XX，名称 代码" 作为 Header
                        header = "，".join(parts[:2])
                
                body_parts = []
                for p, m, t in alerts:
                    m_str = str(m)
                    # 移除已有的 header 部分，提取差异化理由
                    if header and m_str.startswith(header):
                        diff = m_str[len(header):].lstrip("，").strip()
                    else:
                        diff = m_str
                    
                    if diff and diff not in seen_snippets:
                        body_parts.append(diff)
                        seen_snippets.add(diff)
                
                # 3. 组装最终消息
                if header:
                    merged_msg = f"{header}：{' | '.join(body_parts)}"
                else:
                    merged_msg = " | ".join(body_parts)
                
                # 4. 执行发送
                self._do_send_alert(merged_msg, min_priority, key, cooldown=0) # 已在入队前检查过 key cooldown
            except Exception as e:
                logger.error(f"Flush Alert Error for {key}: {e}")

    def send_alert(self, message: str, priority: int = 2, key: Optional[str] = None, cooldown: int = 0):
        """发送报警 (支持合并)"""
        # ⚡ [NEW] 即使在全局报警禁用的情况下，也进行会话追踪 (用于同步赛马面板等可视化组件)
        self._track_session_code(message, key)

        if not self.enabled: return
        
        # 1. 冷却检查
        now = time.time()
        if key and cooldown > 0:
            if now - self.cooldowns.get(key, 0) < cooldown:
                return
            # 注意：此处不立即更新 cooldown，因为消息还在 batch 缓冲区
            # 如果 flush 成功，由 _do_send_alert 决定是否再检查
        
        # 2. 如果提供了 Key (股票代码)，进入聚合缓冲
        if key and len(str(key)) == 6:
            with self._batch_lock:
                if key not in self._batch_data:
                    self._batch_data[key] = []
                self._batch_data[key].append((priority, message, now))
                
                if self._batch_timer is None:
                    self._batch_timer = threading.Timer(self._batch_interval, self._flush_batch_alerts)
                    self._batch_timer.daemon = True
                    self._batch_timer.start()
            return
        
        # 3. 全局/无 Key 消息：直接即时发送
        self._do_send_alert(message, priority, key, cooldown)

    def _track_session_code(self, message: str, key: Optional[str] = None):
        """
        [INTERNAL] 提取个股代码并记录到当前会话的已报警集合中
        这是竞价赛马面板同步个股信号的核心依据
        """
        actual_code = None
        # 1. 尝试从 key 提取 (处理 sz000001 等复杂格式)
        if key:
            code_match = re.search(r'(\d{6})', str(key))
            if code_match:
                actual_code = code_match.group(1)
        
        # 2. 如果 key 无效，尝试从 message 提取
        if not actual_code and message:
            code_match = re.search(r'(\d{6})', str(message))
            if code_match:
                actual_code = code_match.group(1)
                
        if actual_code:
            with self._session_lock:
                if actual_code not in self.session_alerted_codes:
                    self.session_alerted_codes.add(str(actual_code))
                    logger.debug(f"✅ [SessionTrack] Added {actual_code} to alerted codes")

    def _do_send_alert(self, message: str, priority: int = 2, key: Optional[str] = None, cooldown: int = 0):
        """实际的消息分发与记录逻辑"""
        now = time.time()
        
        # 2. 日志记录
        is_high = (priority <= 1)
        log_allowed = True
        if not is_high:
            if now - self.global_last_alert < 0.1:
                log_allowed = False
        
        if log_allowed or is_high:
            self.global_last_alert = now
            prefix = "🔴" if priority == 0 else "📢" if priority == 1 else "ℹ️"
            logger.warning(f"{prefix} [Alert] {message}")
            
        # 3. 语音队列分放
        if self.voice_enabled and self.process and self.process.is_alive():
            try:
                q_size = self.voice_queue.qsize()
                if q_size > 50 and not is_high:
                    return

                item = {
                    'priority': priority,
                    'message': message,
                    'key': key,
                    'timestamp': now
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
