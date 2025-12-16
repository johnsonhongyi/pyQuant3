# -*- coding: utf-8 -*-
"""
Stock Live Strategy & Alert System
高性能实时股票跟踪与语音报警模块
"""
import threading
import queue
import time
import os
import winsound
from datetime import datetime
import pandas as pd
from JohnsonUtil import LoggerFactory
from concurrent.futures import ThreadPoolExecutor

logger = LoggerFactory.getLogger()

# Optional imports
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None
    logger.warning("pyttsx3 not found, voice disabled.")

try:
    import pythoncom
except ImportError:
    pythoncom = None

class VoiceAnnouncer:
    """独立的语音播报引擎"""
    def __init__(self):
        self.queue = queue.Queue()
        self._stop_event = threading.Event()
        # 仅当 pyttsx3 可用时启动线程
        if pyttsx3:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        else:
            self._thread = None

    def _speak_one(self, text):
        """单次播报，每次重新初始化以避免 COM 状态问题"""
        engine = None
        try:
            if pythoncom:
                pythoncom.CoInitialize()
            
            engine = pyttsx3.init()
            # 设置语速
            rate = engine.getProperty('rate')
            engine.setProperty('rate', rate + 20)
            
            logger.info(f"📢 语音播报: {text}")
            engine.say(text)
            engine.runAndWait()
            
        except Exception as e:
            logger.error(f"TTS Play Error: {e}")
        finally:
            # 尝试清理
            if engine:
                try:
                    engine.stop()
                    del engine
                except:
                    pass
            if pythoncom:
                pythoncom.CoUninitialize()

    def _run_loop(self):
        """后台语音线程"""
        if not pyttsx3:
            return
            
        while not self._stop_event.is_set():
            try:
                text = self.queue.get(timeout=1)
                if text:
                    self._speak_one(text)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Voice Loop Error: {e}")
                time.sleep(1) # 防止死循环刷屏

    def say(self, text):
        if self._thread and self._thread.is_alive():
            if self.queue.qsize() < 5: # 防止堆积
                self.queue.put(text)
        else:
            logger.info(f"Voice (Disabled): {text}")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)


class StockLiveStrategy:
    """
    高性能实时行情监控策略类
    """
    def __init__(self):
        self._voice = VoiceAnnouncer()
        self._monitored_stocks = {} 
        self._last_process_time = 0
        self._alert_cooldown = 60 # 报警冷却时间(秒)
        self.enabled = True
        
        # 使用 max_workers=1 避免并发资源竞争，本身计算量很小
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        self.config_file = "voice_alert_config.json"
        self._load_monitors()
        self.alert_callback = None

    def set_alert_callback(self, callback):
        """设置报警回调函数"""
        self.alert_callback = callback
    
    def _load_monitors(self):
        """加载配置"""
        try:
            import json
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._monitored_stocks = json.load(f)
                logger.info(f"Loaded voice monitors from {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to load voice monitors: {e}")

    def _save_monitors(self):
        """保存配置"""
        try:
            import json
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._monitored_stocks, f, ensure_ascii=False, indent=2)
            # logger.info("Saved voice monitors")
        except Exception as e:
            logger.error(f"Failed to save voice monitors: {e}")

    def add_monitor(self, code, name, rule_type, value):
        """添加监控规则"""
        if code not in self._monitored_stocks:
            self._monitored_stocks[code] = {
                'name': name,
                'rules': [],
                'last_alert': 0
            }
        
        self._monitored_stocks[code]['rules'].append({
            'type': rule_type, 
            'value': float(value)
        })
        self._save_monitors()
        logger.info(f"Adding monitor: {name}({code}) {rule_type} > {value}")

    def process_data(self, df_all):
        """
        处理每一帧的行情数据
        """
        if not self.enabled or df_all is None or df_all.empty:
            return

        # 限制频率: 至少间隔 1s 处理一次，避免 UI 线程密集调用导致积压
        now = time.time()
        if now - self._last_process_time < 1.0:
            return
        
        self._last_process_time = now
        
        # 异步执行，传递 df 的轻量副本(如果 df 很大，这依然耗时，建议只传需要的行)
        # 这里为了简单，假设 row access 是安全的。但 df_all 在主线程可能被修改 (pandas 不是线程安全的)
        # 最好是 copy，但 copy 耗时。
        # 妥协：copy()
        
        # 提交前检查 executor 队列是否太满？Executor 不支持直接检查。
        # 简单策略：try submit
        self.executor.submit(self._check_strategies, df_all.copy())

    def _check_strategies(self, df):
        try:
            now = time.time()
            valid_codes = [c for c in self._monitored_stocks.keys() if c in df.index]
            
            for code in valid_codes:
                data = self._monitored_stocks[code]
                last_alert = data.get('last_alert', 0)
                
                if now - last_alert < self._alert_cooldown:
                    continue
                
                row = df.loc[code]
                try:
                    # 安全获取数据
                    current_price = float(row.get('trade', 0))
                    current_change = float(row.get('changepercent', 0))
                except (ValueError, TypeError):
                    continue

                name = data['name']
                triggered = False
                msg = ""
                
                for rule in data['rules']:
                    rtype = rule['type']
                    rval = rule['value']
                    
                    if rtype == 'price_up' and current_price >= rval:
                        triggered = True
                        msg = f"{name} 价格突破 {current_price}"
                    elif rtype == 'price_down' and current_price <= rval:
                        triggered = True
                        msg = f"{name} 价格跌破 {current_price}"
                    elif rtype == 'change_up' and current_change >= rval:
                        triggered = True
                        msg = f"{name} 涨幅达到 {current_change:.1f}%"
                        
                    if triggered:
                        break
                
                if triggered:
                    self._trigger_alert(code, name, msg)
                    data['last_alert'] = now
            
        except Exception as e:
            logger.error(f"Strategy Check Error: {e}")

    def get_monitors(self):
        """获取所有监控数据"""
        return self._monitored_stocks

    def remove_monitor(self, code):
        """移除指定股票的所有监控"""
        if code in self._monitored_stocks:
            del self._monitored_stocks[code]
            self._save_monitors()
            logger.info(f"Removed monitor for {code}")

    def update_rule(self, code, rule_index, new_type, new_value):
        """更新指定规则"""
        if code in self._monitored_stocks:
            rules = self._monitored_stocks[code]['rules']
            if 0 <= rule_index < len(rules):
                rules[rule_index]['type'] = new_type
                rules[rule_index]['value'] = float(new_value)
                self._save_monitors()
                logger.info(f"Updated rule for {code} index {rule_index}: {new_type} {new_value}")

    def remove_rule(self, code, rule_index):
        """移除指定股票的某条规则"""
        if code in self._monitored_stocks:
            rules = self._monitored_stocks[code]['rules']
            if 0 <= rule_index < len(rules):
                logger.info(f"Removing rule for {code}: {rules[rule_index]}")
                rules.pop(rule_index)
                if not rules: # 如果没有规则了，移除股票
                    del self._monitored_stocks[code]
                self._save_monitors()

    def test_alert(self, text="这是一个测试报警"):
        """测试报警功能"""
        self._trigger_alert("TEST", "测试股票", text)

    def test_alert_specific(self, code, name, msg):
        """测试特定报警"""
        self._trigger_alert(code, name, msg)

    def _trigger_alert(self, code, name, message):
        """触发报警"""
        logger.warning(f"🔔 ALERT: {message}")
        
        # 1. 声音
        self._play_sound_async()
        
        # 2. 语音播报
        speak_text = f"注意，{name}，{message}"
        self._voice.say(speak_text)
        
        # 3. 回调
        if self.alert_callback:
            try:
                self.alert_callback(code, name, message)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

    def _play_sound_async(self):
        try:
             winsound.Beep(1000, 200) 
        except:
            pass

    def stop(self):
        self.enabled = False
        self._voice.stop()
        self.executor.shutdown(wait=False)
