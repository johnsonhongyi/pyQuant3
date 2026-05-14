import threading
import time
from datetime import datetime
from typing import Dict, List, Optional
from signal_bus import get_signal_bus, SignalBus
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)

class SectorSignalAggregator:
    """板块信号聚合器：监测板块内个股异动密度"""
    def __init__(self):
        self.sector_counts = {} # {sector: [timestamps]}
        self.lock = threading.Lock()
        
    def ingest(self, code, sector, sig_type):
        if not sector: return None
        with self.lock:
            now = time.time()
            if sector not in self.sector_counts:
                self.sector_counts[sector] = []
            
            # 清理 5 分钟外的旧数据 (300s)
            self.sector_counts[sector] = [t for t in self.sector_counts[sector] if now - t < 300]
            self.sector_counts[sector].append(now)
            
            return {
                'sector': sector,
                'count': len(self.sector_counts[sector]),
                'last_code': code
            }

class MarketAlertEngine:
    """市场级预警引擎：监测大盘温度骤变及异常"""
    def __init__(self):
        self.last_temp = None
        self.temp_history = [] # [(timestamp, temp)]
        
    def check(self, current_temp):
        now = time.time()
        self.temp_history.append((now, current_temp))
        
        # 仅保留最近 10 分钟
        self.temp_history = [(t, v) for t, v in self.temp_history if now - t < 600]
        
        if len(self.temp_history) < 2: return None
        
        # 监测 5 分钟内骤降/骤升
        five_min_ago = now - 300
        past_temps = [v for t, v in self.temp_history if t <= five_min_ago]
        
        if past_temps:
            base_temp = past_temps[-1]
            diff = current_temp - base_temp
            if diff <= -15:
                return ("S", f"⚠️ 市场急冻：5分钟内温度骤降 {abs(diff):.1f}℃！")
            elif diff >= 15:
                return ("S", f"🔥 情绪突燃：5分钟内温度暴升 {diff:.1f}℃！")
        
        return None

class SignalGradingHub:
    """信号分级中枢：核心调度器"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance
    
    def _init(self):
        from JohnsonUtil.commonTips import GlobalConfig
        self.aggregator = SectorSignalAggregator()
        self.market_engine = MarketAlertEngine()
        self.active_alerts = [] 
        self._last_periodic_report = 0
        # [MOD] 从配置文件读取播报周期 (分钟转秒)
        conf = GlobalConfig()
        interval_min = getattr(conf, 'periodic_report_interval', 15)
        self._periodic_interval = interval_min * 60 
        logger.info(f"✅ [HUB] SignalGradingHub initialized. Periodic interval: {interval_min} min")
        
    def on_stock_signal(self, code, name, sector, sig_type, grade):
        res = self.aggregator.ingest(code, sector, sig_type)
        if res and res['count'] >= 2:
            alert_grade = "S" if ("极高" in str(grade) or "断头" in sig_type) else "A"
            self._publish_alert("SECTOR_ALERT", alert_grade, f"📡 {res['sector']} {res['count']}只集体异动", res)
            
    def update_market(self, temp):
        res = self.market_engine.check(temp)
        if res:
            grade, msg = res
            self._publish_alert("MARKET_ALERT", grade, msg, {'temp': temp})
        self._check_periodic_report(temp)

    def _check_periodic_report(self, temp):
        now = time.time()
        if now - self._last_periodic_report >= self._periodic_interval:
            # 只有在活跃交易时段播报
            from datetime import datetime
            dt = datetime.now()
            time_hhmm = dt.hour * 100 + dt.minute
            is_trade = (915 <= time_hhmm <= 1135) or (1300 <= time_hhmm <= 1505)
            
            if is_trade:
                self._last_periodic_report = now
                suggest = self._get_suggestion(temp)
                msg = f"定点播报：当前市场温度 {temp:.1f}℃。{suggest}"
                self._publish_alert("PERIODIC_REPORT", "B", msg, {'temp': temp, 'suggest': suggest})

    def _get_suggestion(self, temp):
        if temp < 20: return "市场冰点，严控仓位，多看少动。"
        if temp < 40: return "情绪低迷，谨慎试错，关注抗跌品种。"
        if temp < 60: return "博弈震荡，均衡配置，不宜追涨。"
        if temp < 80: return "情绪转暖，积极寻找结构性机会。"
        return "市场火热，注意冲高回落，择机止盈。"

    def force_report(self, temp=None):
        """手动强制触发一次定点播报汇总"""
        from instock_MonitorTK import app_market_temperature # 尝试从主窗体获取实时温度
        try:
            curr_temp = temp if temp is not None else app_market_temperature
        except:
            curr_temp = 50.0 # 兜底温度
            
        suggest = self._get_suggestion(curr_temp)
        msg = f"📊 [手动审计] 当前市场温度 {curr_temp:.1f}℃。{suggest}"
        self._publish_alert("MANUAL_REPORT", "B", msg, {'temp': curr_temp, 'suggest': suggest})
        logger.info("📡 [HUB] User forced a market grading report.")

    def _publish_alert(self, type_str, grade, msg, extra=None):
        event = {
            'ts': datetime.now().strftime("%H:%M:%S"),
            'type': type_str,
            'grade': grade,
            'content': msg
        }
        if extra: event.update(extra)
        self.active_alerts.insert(0, event)
        if len(self.active_alerts) > 100: self.active_alerts.pop()
        
        # 发布到总线 (供 UI 和 报警管理器 订阅)
        get_signal_bus().publish(SignalBus.EVENT_MARKET_ALERT, "SignalGradingHub", event)
        
        # 如果是 S 级，额外触发一次语音/弹窗报警
        if grade == "S":
            get_signal_bus().publish(SignalBus.EVENT_ALERT, "SignalGradingHub", {
                'code': '999999', 'name': '系统预警', 'pattern': msg, 'detail': msg
            })

def get_signal_grading_hub():
    """获取信号分级中枢单例"""
    return SignalGradingHub()
