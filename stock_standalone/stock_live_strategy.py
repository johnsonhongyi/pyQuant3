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
# from intraday_decision_engine import IntradayDecisionEngine
# from risk_engine import RiskEngine

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
    def __init__(self,alert_cooldown=60):
        self._voice = VoiceAnnouncer()
        self._monitored_stocks = {} 
        self._last_process_time = 0
        self._alert_cooldown = alert_cooldown # 报警冷却时间(秒)
        logger.info(f'alert_cooldown: {self._alert_cooldown}')
        self.enabled = True
        
        # 使用 max_workers=1 避免并发资源竞争，本身计算量很小
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        self.config_file = "voice_alert_config.json"
        self._load_monitors()
        self.alert_callback = None
        # self.risk_engine = RiskEngine(alert_cooldown=self._alert_cooldown)
        # self._risk_engine = RiskEngine(max_single_stock_ratio=0.2, min_ratio=0.0)
        # self.decision_engine = IntradayDecisionEngine()

    def set_alert_callback(self, callback):
        """设置报警回调函数"""
        self.alert_callback = callback
    
    def _calculate_position(self, stock, current_price, current_nclose, last_close, last_percent, last_nclose):
        """根据今日/昨日数据计算动态仓位与操作"""
        position_ratio = round(1.0/self.stock_count,1)
        logger.debug(f'仓位分配:position_ratio:{position_ratio}')
        action = "持仓"

        valid_yesterday = (last_close > 0) and (last_percent is not None and -100 < last_percent < 100) and (last_nclose > 0)
        valid_today = (current_price > 0) and (current_nclose > 0)

        # 今日均价偏离
        if valid_today:
            deviation_today = (current_nclose - current_price) / current_nclose
            max_normal_pullback = (last_percent / 5 / 100 if valid_yesterday else 0.01)
            if deviation_today > max_normal_pullback + 0.0005:
                position_ratio *= 0.7
                action = "减仓"

        # 昨日收盘偏离
        if valid_yesterday:
            deviation_last = (last_close - current_price) / last_close
            max_normal_pullback = last_percent / 5 / 100
            if deviation_last > max_normal_pullback + 0.0005:
                position_ratio *= 0.5
                action = "卖出"

        # 趋势加仓
        if valid_today and current_price > current_nclose:
            position_ratio = min(1.0, position_ratio + 0.2)
            if action == "持仓":
                action = "买入"

        position_ratio = max(0.0, min(1.0, position_ratio))
        return action, position_ratio

    def _load_monitors(self):
        """加载配置并进行结构修复，同时恢复行情快照"""
        self._monitored_stocks = {}

        try:
            import json
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._monitored_stocks = json.load(f)

                # ✅ 结构迁移 / 补齐
                for code, stock in self._monitored_stocks.items():
                    stock.setdefault('rules', [])
                    stock.setdefault('last_alert', 0)
                    stock.setdefault('snapshot', {})  # 快照信息

                    # ✅ 重建 rule_keys（不从文件读取）
                    rule_keys = set()
                    for r in stock['rules']:
                        try:
                            key = self._rule_key(r['type'], r['value'])
                            rule_keys.add(key)
                        except Exception:
                            logger.warning(f"Invalid rule skipped for {code}: {r}")

                    stock['rule_keys'] = rule_keys

                    # ✅ 可选：加载 snapshot 到运行时对象
                    snap = stock.get('snapshot', {})
                    stock['trade'] = snap.get('trade', 0)
                    stock['percent'] = snap.get('percent', 0)
                    stock['volume'] = snap.get('volume', 0)
                    stock['ratio'] = snap.get('ratio', 0)
                    stock['nclose'] = snap.get('nclose', 0)
                    stock['last_close'] = snap.get('last_close', 0)
                    stock['ma5d'] = snap.get('ma5d', 0)
                    stock['ma10d'] = snap.get('ma10d', 0)

                self.stock_count = len(self._monitored_stocks) 
                logger.info(
                    f"Loaded voice monitors from {self.config_file}, "
                    f"总计持仓stocks={len(self._monitored_stocks)}"
                )

        except Exception as e:
            logger.error(f"Failed to load voice monitors: {e}")


    def _save_monitors(self):
        """保存配置（不包含派生字段，同时增加即时行情信息）"""
        try:
            import json
            data = {}

            for code, stock in self._monitored_stocks.items():
                # --- 构建基础数据 ---
                record = {
                    'name': stock.get('name'),
                    'rules': stock.get('rules', []),
                    'last_alert': stock.get('last_alert', 0)
                }

                # --- 可选：添加行情快照 ---
                if hasattr(self, 'df') and self.df is not None and not self.df.empty:
                    if code in self.df.index:
                        row = self.df.loc[code]
                        try:
                            record['snapshot'] = {
                                'trade': float(row.get('trade', 0)),
                                'percent': float(row.get('percent', 0)),
                                'volume': float(row.get('volume', 0)),
                                'ratio': float(row.get('ratio', 0)),
                                'nclose': float(row.get('nclose', 0)),
                                'last_close': float(row.get('lastp1d', 0)),
                                'ma5d': float(row.get('ma5d', 0)),
                                'ma10d': float(row.get('ma10d', 0))
                            }
                        except (ValueError, TypeError):
                            # 如果数据异常，不存 snapshot
                            pass

                data[code] = record

            # --- 保存到 JSON ---
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Failed to save voice monitors: {e}")

    def _rule_key(self, rule_type, value):
        return f"{rule_type}:{value:.4f}"

    def add_monitor(self, code, name, rule_type, value):
        value = float(value)

        stock = self._monitored_stocks.setdefault(code, {
            'name': name,
            'rules': [],
            'last_alert': 0
        })

        # 确保派生字段存在
        stock.setdefault('rule_keys', set())

        # ✅ 查找是否已存在同 type 规则
        for r in stock['rules']:
            if r['type'] == rule_type:
                old_value = r['value']
                r['value'] = value

                # 更新 rule_keys
                old_key = self._rule_key(rule_type, old_value)
                new_key = self._rule_key(rule_type, value)
                stock['rule_keys'].discard(old_key)
                stock['rule_keys'].add(new_key)

                self._save_monitors()
                logger.info(
                    f"Monitor updated: {name}({code}) {rule_type} {old_value} → {value}"
                )
                return "updated"

        # ✅ 不存在才新增
        rule_key = self._rule_key(rule_type, value)

        stock['rules'].append({
            'type': rule_type,
            'value': value
        })
        stock['rule_keys'].add(rule_key)

        self._save_monitors()
        logger.info(
            f"Monitor added: {name}({code}) {rule_type} > {value}"
        )
        return "added"

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
        self.df = df_all.copy()
        self.executor.submit(self._check_strategies, df_all.copy())


    def _check_strategies(self, df):
        try:
            now = time.time()
            valid_codes = [c for c in self._monitored_stocks.keys() if c in df.index]

            for code in valid_codes:
                data = self._monitored_stocks[code]
                last_alert = data.get('last_alert', 0)

                # ---------- 冷却判断 ----------
                if now - last_alert < self._alert_cooldown:
                    logger.debug(f"{code} 冷却中，跳过检查")
                    continue

                row = df.loc[code]

                # ---------- 安全获取行情数据 ----------
                try:
                    current_price = float(row.get('trade', 0))
                    current_nclose = float(row.get('nclose', 0))
                    current_change = float(row.get('percent', 0))
                    volume_change = float(row.get('volume', 0))
                    ratio_change = float(row.get('ratio', 0))
                    ma5d_change = float(row.get('ma5d', 0))
                    ma10d_change = float(row.get('ma10d', 0))   
                    current_high= float(row.get('high', 0))

                except (ValueError, TypeError) as e:
                    logger.warning(f"{code} 行情数据异常: {e}")
                    continue

                # ---------- 历史 snapshot ----------
                snap = data.get('snapshot', {})
                last_close = snap.get('last_close', 0)
                last_percent = snap.get('percent', None)
                last_nclose = snap.get('nclose', 0)

                # ---------- 初始化计数器 ----------
                data.setdefault('below_nclose_count', 0)
                data.setdefault('below_nclose_start', 0)
                data.setdefault('below_last_close_count', 0)
                data.setdefault('below_last_close_start', 0)

                # ---------- 消息收集 ----------
                messages = []

                # ---------- 今日均价风控 ----------
                max_normal_pullback = (last_percent / 5 / 100 if last_percent else 0.01)
                if current_price > 0 and current_nclose > 0:
                    deviation = (current_nclose - current_price) / current_nclose
                    if deviation > max_normal_pullback + 0.0005:
                        if data['below_nclose_start'] == 0:
                            data['below_nclose_start'] = now
                        if now - data['below_nclose_start'] >= 300:
                            data['below_nclose_count'] += 1
                    else:
                        data['below_nclose_start'] = 0
                        data['below_nclose_count'] = 0

                    if data['below_nclose_count'] >= 3:
                        msg = (
                            f"卖出 {data['name']} 价格连续低于今日均价 {current_nclose} 卖出 ({current_price}) "
                        )
                        messages.append(("RISK", msg))
                            # f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"

                # ---------- 昨日收盘风控 ----------
                if last_close > 0:
                    deviation_last = (last_close - current_price) / last_close
                    if deviation_last > max_normal_pullback + 0.0005:
                        if data['below_last_close_start'] == 0:
                            data['below_last_close_start'] = now
                        if now - data['below_last_close_start'] >= 300:
                            data['below_last_close_count'] += 1
                    else:
                        data['below_last_close_start'] = 0
                        data['below_last_close_count'] = 0

                    if data['below_last_close_count'] >= 2:
                        msg = (
                            f"减仓 {data['name']} 价格连续低于昨日收盘 {last_close} ({current_price}) "
                        )
                            # f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                        messages.append(("RISK", msg))

                # ---------- 普通规则 ----------
                for rule in data.get('rules', []):
                    rtype = rule['type']
                    rval = rule['value']
                    rule_triggered = False
                    if rtype == 'price_up' and current_price >= rval:
                        rule_triggered = True
                        msg = f"{data['name']} 价格突破 {current_price} 涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                    elif rtype == 'price_down' and current_price <= rval:
                        rule_triggered = True
                        msg = f"{data['name']} 价格跌破 {current_price} 涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                    elif rtype == 'change_up' and current_change >= rval:
                        rule_triggered = True
                        msg = f"{data['name']} 涨幅达到 {current_change:.1f}% 价格 {current_price} 量能 {volume_change} 换手 {ratio_change}"

                    if rule_triggered:
                        messages.append(("RULE", msg))

                # ---------- 动态仓位建议 ----------
                action, ratio = self._calculate_position(
                    data, current_price, current_nclose, last_close, last_percent, last_nclose
                )
                # if action != "持仓":
                if action:
                    msg = (
                        f"{data['name']} {action} 当前价 {current_price} "
                        f"建议仓位 {ratio*100:.0f}% "
                    )
                        # f"今日均价 {current_nclose} 昨日收盘 {last_close} "
                        # f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                    messages.append(("POSITION", msg))

                # ---------- 调试信息 ----------
                logger.debug(
                    f"{code} 调试: price={current_price} nclose={current_nclose} "
                    f"last_close={last_close} below_nclose_count={data['below_nclose_count']} "
                    f"below_last_close_count={data['below_last_close_count']} "
                    f"max_normal_pullback={max_normal_pullback:.4f}"
                )

                if messages:
                    # ---------- 优先级定义 ----------
                    priority_order = ["RISK", "RULE", "POSITION"]
                    priority_rank = {k: i for i, k in enumerate(priority_order)}

                    # ---------- 去重（按文本） ----------
                    unique_msgs = {}
                    for mtype, msg in messages:
                        if msg not in unique_msgs:
                            unique_msgs[msg] = mtype
                        else:
                            # 同一 msg，保留更高优先级
                            if priority_rank[mtype] < priority_rank[unique_msgs[msg]]:
                                unique_msgs[msg] = mtype

                    # ---------- 按优先级排序 ----------
                    sorted_msgs = sorted(
                        unique_msgs.items(),
                        key=lambda x: priority_rank[x[1]]
                    )

                    # ---------- 合并文本 ----------
                    combined_msg = "\n".join([msg for msg, _ in sorted_msgs])

                    # ---------- 计算最终 action ----------
                    # if any(t == "RISK" for t in unique_msgs.values()):
                    #     final_action = "RISK"
                    # elif any(t == "RULE" for t in unique_msgs.values()):
                    #     final_action = "RULE"
                    # elif any(t == "POSITION" for t in unique_msgs.values()):
                    #     final_action = action  # 来自仓位模型
                    # else:
                    #     final_action = "HOLD"

                    # ---------- 调试输出 ----------
                    logger.debug(f"{code} 合并前 messages={messages}")
                    logger.debug(f"{code} 去重后 unique_msgs={unique_msgs}")
                    # logger.info(f"{code} combined_msg:\n{combined_msg}")

                    # ---------- 单次触发 ----------
                    self._trigger_alert(
                        code,
                        data['name'],
                        combined_msg,
                        action=action
                    )
                        # action=final_action

                    data['last_alert'] = now

                    # ---------- 重置计数器 ----------
                    data['below_nclose_count'] = 0
                    data['below_nclose_start'] = 0
                    data['below_last_close_count'] = 0
                    data['below_last_close_start'] = 0

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
        if code in self._monitored_stocks:
            stock = self._monitored_stocks[code]
            rules = stock['rules']

            if 0 <= rule_index < len(rules):
                rule = rules.pop(rule_index)

                if 'rule_keys' in stock:
                    stock['rule_keys'].discard(
                        self._rule_key(rule['type'], rule['value'])
                    )

                if not rules:
                    del self._monitored_stocks[code]

                self._save_monitors()
    def test_alert(self, text="这是一个测试报警"):
        """测试报警功能"""
        self._trigger_alert("TEST", "测试股票", text)

    def test_alert_specific(self, code, name, msg):
        """测试特定报警"""
        self._trigger_alert(code, name, msg)

    def _trigger_alert(self, code, name, message ,action='持仓'):
        """触发报警"""
        logger.warning(f"🔔 ALERT: {message}")
        
        # 1. 声音
        self._play_sound_async()
        
        # 2. 语音播报
        # speak_text = f"注意，{name}，{message}"
        speak_text = f"注意{action}，{name}，{message}"
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
