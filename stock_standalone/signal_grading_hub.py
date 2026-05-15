import os
import sys
import time
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional

# 核心依赖
from signal_bus import SignalBus, get_signal_bus, BusEvent
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)

class SectorSignalAggregator:
    """板块信号聚合器：监测板块内个股异动密度"""
    def __init__(self):
        self.sector_counts = {} # {sector: [timestamps]}
        self.lock = threading.Lock()
        
    def ingest(self, code, sector, sig_type, now=None, name="-"):
        if not sector: return None
        with self.lock:
            if now is None:
                now = time.time()
            if sector not in self.sector_counts:
                self.sector_counts[sector] = [] # 存储 (timestamp, code, name, sig_type)
            
            # 清理 5 分钟外的旧数据 (300s)
            history = self.sector_counts.get(sector, [])
            if not isinstance(history, list): history = []
                
            if history and abs(now - history[-1][0]) > 3600:
                history = []
                
            history = [(t, c, n, st) for t, c, n, st in history if now - t < 300]
            history.append((now, code, name, sig_type))
            self.sector_counts[sector] = history
            
            unique_codes = {} # {code: (name, sig_type)}
            for t, c, n, st in history:
                unique_codes[c] = (n, st)
                
            details = []
            for c, (n, st) in unique_codes.items():
                details.append({
                    'code': c,
                    'name': n,
                    'sig_type': st
                })
                
            return {
                'sector': sector,
                'count': len(unique_codes),
                'codes': list(unique_codes.keys()),
                'details': details
            }

class MarketAlertEngine:
    """市场级预警引擎：监测大盘温度骤变及异常"""
    def __init__(self):
        self.last_temp = None
        self.temp_history = [] # [(timestamp, temp)]
        self.last_alert_time = 0
        self.last_alert_type = None # "HOT", "COLD"
        
        # [NEW] 市场结构追踪
        self.day_high = -999
        self.day_low = 999
        self.regime = "NEUTRAL" # NEUTRAL, TREND_UP, TREND_DOWN, VOLATILE
        
    def check(self, current_temp, active_sectors_count=0, now=None):
        if now is None:
            now = time.time()
        
        # 追踪日内极值
        self.day_high = max(self.day_high, current_temp)
        self.day_low = min(self.day_low, current_temp)
            
        # [🛡️ FIX] 时钟突变保护
        if self.temp_history and abs(now - self.temp_history[-1][0]) > 3600:
            self.temp_history = []
            
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
            
            # [NEW] 引入 30 分钟宏观趋势判定
            macro_window = now - 1800
            macro_temps = [v for t, v in self.temp_history if t <= macro_window]
            macro_diff = 0
            if macro_temps:
                macro_diff = current_temp - macro_temps[-1]

            # [🛡️ FIX] 增加冷却时间限制
            cooldown = 60 if self.last_alert_type != ("HOT" if diff > 0 else "COLD") else 150 # 同向冷却更久
            if now - self.last_alert_time < cooldown:
                return None

            # [STRATEGY] 结构化深度判偏
            # 1. 持续下杀逻辑 (高开低走)
            if macro_diff <= -20 and current_temp < 40:
                self.regime = "TREND_DOWN"
                self.last_alert_time = now
                self.last_alert_type = "COLD"
                return ("S", f"📉 结构确认：市场进入持续杀跌状态！当前{current_temp}℃(距高位-{self.day_high-current_temp:.1f})")
            
            # 2. 局部剧烈波动 (震荡结构)
            if abs(diff) >= 15 and abs(macro_diff) < 10:
                self.regime = "VOLATILE"
                status = "抽风式冲高" if diff > 0 else "瞬间跳水"
                self.last_alert_time = now
                return ("A", f"🔄 震荡监测：市场出现{status}，整体热度尚未形成趋势。")

            # 3. 极度缩容/普跌
            if current_temp < 15 and active_sectors_count <= 2:
                self.last_alert_time = now
                return ("S", f"💀 极度空头：全市场仅{active_sectors_count}个板块活跃，大面积阴跌中。")

            # 4. 原有阶梯式逻辑 (带结构增强)
            if diff <= -15:
                self.last_alert_time = now
                self.last_alert_type = "COLD"
                return ("S", f"⚠️ 警报：5分钟内遭遇强力杀跌 {abs(diff):.1f}℃！")
            elif diff >= 15:
                self.last_alert_time = now
                self.last_alert_type = "HOT"
                return ("S", f"🚀 异动：5分钟内情绪暴力拉升 {diff:.1f}℃！")
        return None

class SignalGradingHub:
    """
    信号评分与聚合中枢 (Signal Grading & Aggregation Hub)
    
    职责：
    1. 监听 SignalBus 中的个股信号
    2. 进行板块/市场维度的二次聚合 (Aggregator)
    3. 判定并发布更高级别的预警 (EVENT_MARKET_ALERT)
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SignalGradingHub, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, simulation_mode: bool = False):
        if hasattr(self, '_initialized'): return
        self._initialized = True
        
        self.aggregator = SectorSignalAggregator()
        self.breakdown_aggregator = SectorSignalAggregator() # [NEW] 专用破位监控
        self.market_engine = MarketAlertEngine()
        self.last_alerts = {} # {alert_key: (timestamp, count)} # [NEW] 节流控制
        self.code_to_sectors = {} # [NEW] 个股与板块映射表 (由 MonitorTK 推送)
        self._simulation_mode = simulation_mode
        self._sim_time = None # 当前模拟时钟 (HH:MM:SS)
        self._published_cache = {} # {content: last_ts} [NEW] 发布去重缓存
        
        # 注册总线监听
        get_signal_bus().subscribe(SignalBus.EVENT_PATTERN, self._on_bus_event)
        logger.info(f"🚀 SignalGradingHub initialized (mode={'SIM' if simulation_mode else 'LIVE'})")

    def set_simulation_mode(self, mode: bool, sim_time: str = None):
        """动态切换模拟模式"""
        self._simulation_mode = mode
        if mode:
            self._sim_time = sim_time
            logger.info(f"📡 [HUB] 预警中枢已切换至【回测模式】，虚拟时钟激活: {sim_time}")
            # 回测开始前重置引擎状态
            self.market_engine.temp_history = []
            self.aggregator.sector_counts = {}
            if hasattr(self, 'breakdown_aggregator'):
                self.breakdown_aggregator.sector_counts = {}
        else:
            self._sim_time = None
            logger.info("📡 [HUB] 预警中枢回归【实盘模式】。")

    def update_metadata(self, code_to_sectors: dict):
        """[DATA] 更新个股与板块/概念的映射表，用于精准预警"""
        if not isinstance(code_to_sectors, dict): return
        with self.aggregator.lock:
            self.code_to_sectors.update(code_to_sectors)
            # logger.info(f"📡 [HUB] Sector metadata updated: {len(self.code_to_sectors)} codes.")

    def _on_bus_event(self, event):
        """[NEW] 处理总线推送过来的个股信号"""
        if event.event_type == SignalBus.EVENT_PATTERN:
            payload = event.payload
            # [🛡️ GUARD] 确保 payload 不为空
            if not payload: return
            
            # [🛡️ FIX] 优先从 payload 提取 ts (物理时间) 或从 event 提取 timestamp
            # 这解决了主进程 Hub 收到回测老信号时的“时差屏障”问题
            event_ts = payload.get('ts')
            if event_ts:
                now = float(event_ts)
            else:
                # Fallback 到 datetime 转换
                dt = event.timestamp if hasattr(event, 'timestamp') else datetime.now()
                now = dt.hour * 3600 + dt.minute * 60 + dt.second
            
            # 提取关键字段
            code = payload.get('code')
            name = payload.get('name')
            
            # [🛡️ FIX] 强化字段提取的健壮性，防止 NoneType 导致 split 失败
            detail_str = str(payload.get('detail', payload.get('message', '')) or '')
            
            # [MOD] 智能板块识别：优先使用元数据匹配，拒绝“其它”
            sector = payload.get('sector')
            if not sector or sector == '其它':
                # 尝试从 hub 的元数据中提取 (由 MonitorTK 定期同步)
                raw_cats = self.code_to_sectors.get(code, "")
                if raw_cats:
                    # 提取第一个非泛概念板块
                    cats = [c.strip() for c in str(raw_cats).replace("；", ";").replace("+", ";").split(";") if c.strip()]
                    for ca in cats:
                        if not self._is_generic_sector(ca):
                            sector = ca
                            break
                
                # 如果元数据未命中，再尝试从 detail 拆分
                if not sector or sector == '其它':
                    sector = (detail_str.split('|')[0] if '|' in detail_str else '其它')
            
            # [🛡️ FIX] 兼容 pattern/subtype 字段
            sig_type = payload.get('pattern') or payload.get('subtype', 'SIGNAL')
            grade = payload.get('grade', '')
            
            self.on_stock_signal(code, name, sector, sig_type, grade, now=now)

    def _get_now_seconds(self):
        """统一获取当前时间（秒数）"""
        if self._simulation_mode and self._sim_time:
            try:
                parts = str(self._sim_time).split(':')
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + (int(parts[2]) if len(parts) > 2 else 0)
            except (ValueError, IndexError):
                pass
        return time.time()

    def on_stock_signal(self, code, name, sector, sig_type, grade, now=None):
        if now is None: now = time.time()
        res = self.aggregator.ingest(code, sector, sig_type, now=now, name=name)
        if res and res['count'] >= 2:
            # [🛡️ FIX] 增加节流逻辑，避免同板块高频重复迭代
            alert_key = f"SECTOR_{res['sector']}"
            last_ts, last_count = self.last_alerts.get(alert_key, (0, 0))
            
            # 触发条件：间隔 > 20秒 OR 数量增长 >= 3
            if (now - last_ts > 20) or (res['count'] - last_count >= 3):
                sig_type_str = str(sig_type or "")
                grade_str = str(grade or "")
                alert_grade = "S" if ("极高" in grade_str or "断头" in sig_type_str) else "A"
                self._publish_alert("SECTOR_ALERT", alert_grade, f"📡 {res['sector']} {res['count']}只集体异动", res)
                self.last_alerts[alert_key] = (now, res['count'])
            
        # [NEW] 判定是否为“结构破位”类信号
        sig_type_str = str(sig_type or "")
        breakdown_keywords = ["SBC-Breakdown", "断头", "破位", "跌破", "failure", "exit"]
        if any(k.lower() in sig_type_str.lower() for k in breakdown_keywords):
            # 记录到全局破位统计 (使用虚拟板块 'GLOBAL_BREAKDOWN')
            b_res = self.breakdown_aggregator.ingest(code, "GLOBAL_BREAKDOWN", sig_type, now=now)
            if b_res and b_res['count'] >= 3:
                alert_key = "GLOBAL_BREAKDOWN_ALERT"
                last_ts, last_count = self.last_alerts.get(alert_key, (0, 0))
                if (now - last_ts > 15) or (b_res['count'] - last_count >= 2):
                    self._publish_alert("RISK_ALERT", "S", f"⚠️ 警告：全市场出现集中破位({b_res['count']}只)，请注意减仓规避风险！", b_res)
                    self.last_alerts[alert_key] = (now, b_res['count'])
            
    def update_market(self, temp, sim_time=None):
        """[MOD] 更新市场温度，支持注入模拟时间"""
        if sim_time:
            self._sim_time = sim_time
        
        now = self._get_now_seconds()
        
        # 统计活跃板块数量
        active_count = len([h for s, h in self.aggregator.sector_counts.items() if len(h) > 0])
        
        res = self.market_engine.check(temp, active_sectors_count=active_count, now=now)
        if res:
            grade, msg = res
            
            # [UPGRADE] 自动关联当前活跃板块，提供背景信息
            meta = {'temp': temp}
            try:
                # 获取当前异动密度最高的 3 个板块
                top_sectors = sorted(
                    self.aggregator.sector_counts.items(), 
                    key=lambda x: len(x[1]), 
                    reverse=True
                )[:3]
                if top_sectors:
                    sector_info = " | 活跃: " + ", ".join([f"{s}({len(h)})" for s, h in top_sectors if len(h) > 0])
                    msg += sector_info
                    meta['top_sectors'] = [s for s, h in top_sectors]
            except: pass
            
            self._publish_alert("MARKET_ALERT", grade, msg, meta)
        self._check_periodic_report(temp)

    def _check_periodic_report(self, temp):
        # [MOD] 统一时间戳获取逻辑
        if self._simulation_mode and self._sim_time:
            # 模拟模式下，使用虚拟时钟 (HH:MM:SS) 转换为自午夜起的秒数
            try:
                parts = str(self._sim_time).split(':')
                now_sec = int(parts[0]) * 3600 + int(parts[1]) * 60
            except (ValueError, IndexError):
                return
        else:
            now = datetime.now()
            now_sec = now.hour * 3600 + now.minute * 60
            
        # 整点/半点报告逻辑
        if now_sec % 1800 == 0:
            pass # 占位

    def _publish_alert(self, alert_type, grade, content, metadata=None):
        """发布市场级预警信号"""
        # [NEW] 物理发布去重：30秒内相同内容不再重复发布
        now_time = time.time()
        if content in self._published_cache:
            if now_time - self._published_cache[content] < 30:
                return
        self._published_cache[content] = now_time
        
        # [MOD] 统一时间戳
        ts_str = self._sim_time if (self._simulation_mode and self._sim_time) else datetime.now().strftime("%H:%M:%S")
        
        event_payload = {
            'type': alert_type,
            'grade': grade,
            'content': content,
            'ts': ts_str, # [FIX] 统一使用 ts 字段对齐 UI
            'metadata': metadata or {}
        }
        
        # [🔮 DEBUG] 模拟模式下输出更明显的日志
        prefix = "🔮 [SIM] " if self._simulation_mode else "📢 "
        msg = f"{prefix}Publishing Alert: {content} ({grade})"
        print(msg) # 强制控制台输出
        logger.warning(msg) # 提升至 WARNING 确保可见
        
        get_signal_bus().publish(
            SignalBus.EVENT_MARKET_ALERT,
            source="SignalGradingHub",
            payload=event_payload
        )

    def _is_generic_sector(self, name):
        """[UTIL] 过滤泛概念，聚焦行业属性"""
        if not name: return True
        generics = [
            "其它", "融资融券", "深股通", "沪股通", "预盈预增", "昨日涨停", 
            "昨日大涨", "昨日首板", "破净股", "转融券标的", "富时罗素概念股",
            "标普道琼斯纳指", "MSCI中国", "央企改革", "地方国企改革", "低价股"
        ]
        return any(g in str(name) for g in generics)

    def force_report(self):
        """手动触发状态快照报告"""
        msg = "📡 [HUB] Manual report triggered."
        print(msg)
        logger.warning(msg)
        self._publish_alert("MANUAL_CHECK", "A", "📊 预警中枢运行中：全系统链路巡检正常")

def get_signal_grading_hub():
    """获取信号分级中枢单例接口"""
    return SignalGradingHub()
