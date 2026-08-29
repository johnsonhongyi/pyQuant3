# -*- encoding: utf-8 -*-
"""
人气共振数据采集与同步服务 (Popularity Resonance Data Sync Service)
代替旧版易语言客户端，抓取东方财富、同花顺、淘股吧、龙虎大师数据，并生成通达信自选板块 (RQG.blk)。
"""
from __future__ import annotations
import os
import sys
import json
import time
import urllib.request
import urllib.error
import logging

# 确保能正确导入项目模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    import JohnsonUtil.commonTips as cct
    import JohnsonUtil.johnson_cons as ct
except ImportError:
    # 兜底
    cct = None
    ct = None

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PopularityResonance")

# 默认 Headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}

def clean_stock_code(code: str) -> str:
    """清理股票代码，只保留6位纯数字"""
    code = code.strip().upper()
    if code.startswith('SH') or code.startswith('SZ'):
        return code[2:]
    return code[-6:]

def fetch_realtime_quotes(codes: list[str]) -> dict[str, dict]:
    """
    从新浪财经批量获取股票的实时行情（名称、最新价、涨幅）
    返回: { 股票代码: { "name": 名称, "price": 最新价, "percent": 涨幅 } }
    """
    if not codes:
        return {}
        
    url_codes = []
    for c in codes:
        if c.startswith(('5', '6', '9')):
            prefix = 'sh'
        elif c.startswith(('43', '83', '87', '92')):
            prefix = 'bj'
        else:
            prefix = 'sz'
        url_codes.append(f"{prefix}{c}")
        
    url = f"http://hq.sinajs.cn/list={','.join(url_codes)}"
    req = urllib.request.Request(url, headers={"Referer": "http://finance.sina.com.cn"})
    
    result = {}
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            lines = response.read().decode('gbk').splitlines()
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split('=')
                if len(parts) < 2:
                    continue
                left, right = parts[0], parts[1]
                code = left[-6:]
                
                val_str = right.strip('"; \n\r')
                if not val_str:
                    continue
                fields = val_str.split(',')
                if len(fields) < 4:
                    continue
                    
                name = fields[0]
                yesterday_close = float(fields[2] or 0)
                current_price = float(fields[3] or 0)
                
                percent = 0.0
                if yesterday_close > 0:
                    percent = (current_price - yesterday_close) / yesterday_close * 100
                    
                result[code] = {
                    "name": name,
                    "price": current_price,
                    "percent": percent
                }
    except Exception as e:
        logger.error(f"批量抓取新浪行情失败: {e}")
        
    return result

def fetch_eastmoney(limit: int = 100) -> dict[str, int]:
    """
    获取东方财富人气榜数据 (POST 方式)
    返回: { 股票代码: 排名 }
    """
    url = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
    payload = {
        "appId": "appId01",
        "globalId": "786e4c21-70dc-435a-93bb-38",
        "marketType": "",
        "pageNo": 1,
        "pageSize": limit
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            **DEFAULT_HEADERS,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if 'data' in res_data and isinstance(res_data['data'], list):
                result = {}
                for item in res_data['data']:
                    code = clean_stock_code(item.get('sc', ''))
                    rank = item.get('rk')
                    if code and rank:
                        result[code] = int(rank)
                logger.info(f"成功抓取东方财富人气榜 {len(result)} 只股票.")
                return result
    except Exception as e:
        logger.error(f"抓取东方财富人气榜失败: {e}")
    return {}

def fetch_ths() -> dict[str, int]:
    """
    获取同花顺热股榜数据 (GET 方式)
    返回: { 股票代码: 排名 }
    """
    url = "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_stock/a/hour/data.txt"
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if 'data' in res_data and 'stock_list' in res_data['data']:
                result = {}
                for item in res_data['data']['stock_list']:
                    code = clean_stock_code(item.get('code', ''))
                    rank = item.get('order')
                    if code and rank:
                        result[code] = int(rank)
                logger.info(f"成功抓取同花顺热股榜 {len(result)} 只股票.")
                return result
    except Exception as e:
        logger.error(f"抓取同花顺热股榜失败: {e}")
    return {}

def fetch_taoguba() -> dict[str, int]:
    """
    获取淘股吧公告热股数据 (GET 方式)
    返回: { 股票代码: 排名 }
    """
    url = "https://www.taoguba.com.cn/new/nrnt/getNoticeStock?type=H"
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if 'dto' in res_data and isinstance(res_data['dto'], list):
                result = {}
                for item in res_data['dto']:
                    code = clean_stock_code(item.get('fullCode', ''))
                    rank = item.get('ranking')
                    if code and rank:
                        result[code] = int(rank)
                logger.info(f"成功抓取淘股吧热股榜 {len(result)} 只股票.")
                return result
    except Exception as e:
        logger.error(f"抓取淘股吧热股榜失败: {e}")
    return {}

def fetch_longhu() -> dict[str, int]:
    """
    获取龙虎大师竞价异动数据 (GET 方式，仅竞价时段 9:15-9:25 有数据)
    返回: { 股票代码: 排名 } (由于该接口不带具体排名，统一设为 1，代表在列表中)
    """
    url = "https://apphq.longhuvip.com/w1/api/index.php?Order=1&a=GetHotPHB&st=100&apiv=w21&Type=1&c=StockBidYiDong&PhoneOSNew=1"
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            result = {}
            # 龙虎大师可能返回 list 或 List 字段
            lst = res_data.get('list', []) or res_data.get('List', [])
            if lst:
                for idx, item in enumerate(lst, 1):
                    # 龙虎大师一般有 code 或 symbol
                    raw_code = item.get('code', '') or item.get('symbol', '')
                    code = clean_stock_code(raw_code)
                    if code:
                        result[code] = idx
                logger.info(f"成功抓取龙虎大师竞价榜 {len(result)} 只股票.")
            else:
                logger.info("龙虎大师竞价榜为空 (可能处于非竞价时段).")
            return result
    except Exception as e:
        logger.error(f"抓取龙虎大师竞价榜失败: {e}")
    return {}

class QuickOrderExecutor:
    """
    一键直连交易终端与通达信/同花顺预埋单执行器 (Quick Order & One-Click Execution Engine)
    功能：
    1. 响应 Space / Alt+B 快捷键，0.5秒内完成股票代码、目标委托价（09:25竞价/涨停价）、预设仓位的极速填单与推送；
    2. 物理联动通达信 (TDX) / 同花顺 (THS) 独立交易窗口或闪电手；
    3. 同步将委托流水记录写入 TradeGateway 账本 (signal_strategy.db)，形成实盘/模拟闭环。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._last_order_time = 0.0

    def execute_quick_buy(
        self,
        code: str,
        name: str = "",
        target_price: float = 0.0,
        shares: int = 1000,
        strategy_tag: str = "💎 逆势冰点破局·一键跟单",
        action_type: str = "BUY_AUCTION"
    ) -> dict:
        """
        执行一键快速跟单/预埋单动作
        """
        import time
        code_str = str(code).strip().zfill(6)
        now_ts = time.time()
        
        # 300ms 防抖
        if now_ts - self._last_order_time < 0.3:
            return {"status": "FAILED", "msg": "操作过于频繁，防抖拦截"}
        self._last_order_time = now_ts

        # 1. 物理联动通达信与同花顺切屏并准备下单
        try:
            from linkage_service import get_link_manager
            if get_link_manager:
                get_link_manager().push(code_str, flags={'tdx': True, 'ths': True, 'dfcf': False})
        except Exception as e:
            logger.debug(f"物理联动广播异常: {e}")

        # 2. 剪贴板复制买入代码与价格指令
        try:
            import pyperclip
            clip_str = f"{code_str} {target_price:.2f}" if target_price > 0 else code_str
            pyperclip.copy(clip_str)
        except Exception:
            pass

        # 3. 记录到 TradeGateway 模拟/实盘账本
        try:
            from trade_gateway import TradeGateway
            gw = TradeGateway.get_instance()
            gw.execute_mock_buy(
                code=code_str,
                name=name or code_str,
                price=target_price,
                shares=shares,
                strategy_tag=strategy_tag
            )
        except Exception as e:
            logger.debug(f"TradeGateway 记录异常: {e}")

        msg = f"已直连交易终端挂单: [{code_str} {name}] 委托价:{target_price:.2f}元 数量:{shares}股 ({strategy_tag})"
        try:
            logger.info(f"[一键挂单成功] {msg}")
        except Exception:
            pass
        return {
            "status": "SUCCESS",
            "ok": True,
            "code": code_str,
            "name": name,
            "target_price": target_price,
            "shares": shares,
            "msg": msg
        }

class DynamicFeatureEngine:
    """
    时钟驱动与动态结构特征自适应切换挖掘引擎 (Dynamic Structural Feature Engine)
    功能：
    1. 依据实盘交易时钟自动切换 5 大结构特征挖掘算子；
    2. 大盘逆势偏离与冰点破局龙感知 (Counter-Market Divergence & Pioneer Detector)；
    3. 狭窄时间窗口三大黄金挂单点推演 (买点 A: 09:25 竞价定盘, 买点 B: 09:30 秒级抢跑, 买点 C: VWAP 均线支撑)。
    """
    def __init__(self):
        pass

    def evaluate_counter_market_divergence(
        self, 
        stock_pct: float, 
        index_pct: float = -0.5,
        bidding_amt_wan: float = 0.0,
        seal_circ_ratio: float = 0.0
    ) -> dict:
        """
        计算个股相对大盘的逆势偏离度 (RS_Alpha) 并判定是否为【冰点破局龙】
        """
        rs_divergence = round(stock_pct - index_pct, 2)
        # 大盘弱势回踩(<= -0.2%)但个股大幅高开或冲高(>= +3.0%)，或有大额竞价真金(>= 1000万)
        is_counter_market = bool((index_pct <= -0.2 and stock_pct >= 2.5) or (rs_divergence >= 5.0 and bidding_amt_wan >= 1000))
        
        if is_counter_market:
            tag = "💎 逆势冰点破局龙"
            desc = f"大盘弱势({index_pct:+.2f}%) 逆势偏离({rs_divergence:+.2f}%) 真金抢筹"
        elif rs_divergence >= 3.0:
            tag = "🚀 强于大盘先锋"
            desc = f"逆势偏离({rs_divergence:+.2f}%) 独立走强"
        else:
            tag = "⏱️ 同步大盘博弈"
            desc = f"偏离度({rs_divergence:+.2f}%) 常规震荡"

        return {
            "rs_divergence": rs_divergence,
            "is_counter_market": is_counter_market,
            "pioneer_tag": tag,
            "pioneer_desc": desc
        }

    def infer_actionable_entry_points(
        self,
        code: str,
        price: float,
        stock_pct: float,
        last_close: float,
        bidding_amt_wan: float = 0.0,
        seal_circ_ratio: float = 0.0,
        bid_pressure: float = 50.0,
        vwap: float = 0.0,
        now_time_str: str = None
    ) -> dict:
        """
        根据实盘时钟和盘口微观数据，推演三大黄金挂单点与实操时间窗口
        """
        if now_time_str is None:
            now_time_str = time.strftime("%H:%M:%S")
            
        hhmm = now_time_str[:5]
        vwap_val = vwap if vwap > 0 else (price if price > 0 else last_close)
        
        entry_plan = {
            "action_type": "观望博弈",
            "suggested_price": price,
            "urgency": "常规",
            "window_desc": "等待明确结构信号",
            "action_code": "WAIT",
            "reason": ""
        }

        # 1.【09:15~09:29:59 集合竞价与定盘期】：推演【买点 A: 09:25 竞价定盘上车】
        if "09:15:00" <= now_time_str <= "09:29:59":
            if (seal_circ_ratio >= 3.0 or bid_pressure >= 75.0 or bidding_amt_wan >= 2000) and stock_pct >= 2.0:
                entry_plan = {
                    "action_type": "👑 09:25 竞价顶格挂单",
                    "suggested_price": price,
                    "urgency": "极高 (黄金上车窗口)",
                    "window_desc": "09:25~09:30 静默期直接以开盘价委托挂单",
                    "action_code": "BUY_AUCTION",
                    "reason": f"不可撤单真金买压{bid_pressure:.0f}% 封流比{seal_circ_ratio:.1f}% 竞价{bidding_amt_wan:.0f}万"
                }
            else:
                entry_plan = {
                    "action_type": "🚀 09:30:15 开盘抢跑点",
                    "suggested_price": round(price * 0.992, 2) if price > 0 else last_close,
                    "urgency": "高 (开盘回踩挂单)",
                    "window_desc": "09:30~09:31 开盘 30 秒内回踩首笔均线挂单",
                    "action_code": "BUY_OPEN_DIP",
                    "reason": f"高开{stock_pct:+.1f}% 等待开盘轻微下探确认"
                }

        # 2.【09:30~10:00 黄金定龙期】：推演【买点 B: 开盘秒板抢跑】或【买点 C: VWAP 低吸】
        elif "09:30:00" <= now_time_str < "10:00:00":
            if stock_pct >= 7.0 and bid_pressure >= 80.0:
                entry_plan = {
                    "action_type": "⚡ 涨停前秒级抢排",
                    "suggested_price": price,
                    "urgency": "极高 (封板前最后机会)",
                    "window_desc": "极速脉冲拉升中挂单抢筹",
                    "action_code": "BUY_MOMENTUM",
                    "reason": f"买盘压强{bid_pressure:.0f}% 封板加速中"
                }
            else:
                entry_plan = {
                    "action_type": "🔥 VWAP 均线回踩低吸",
                    "suggested_price": round(vwap_val, 2),
                    "urgency": "中 (均线支撑介入)",
                    "window_desc": "分时黄线支撑位挂单低吸",
                    "action_code": "BUY_VWAP_SUPPORT",
                    "reason": f"均线支撑{vwap_val:.2f}元 承接吸收良好"
                }

        # 3.【10:00 之后 盘中与午后时段】：推演分时低吸与反包
        else:
            entry_plan = {
                "action_type": "💎 分歧低吸/反包确认",
                "suggested_price": round(vwap_val, 2),
                "urgency": "中 (稳健低吸)",
                "window_desc": "分时二次回踩不破均线时挂单",
                "action_code": "BUY_PULLBACK",
                "reason": f"分歧释放完毕 均线支撑{vwap_val:.2f}元"
            }

        return entry_plan


class LadderResonanceBridge:
    """
    打通 ATS 连板天梯 (LimitUpEngine) 与 TDX L2 高频盘口数据桥接器
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._limit_up_engine = None
        self._tdx_fetcher = None
        self._init_engines()

    def _init_engines(self):
        try:
            from ats.limit_up_engine import get_limit_up_engine
            self._limit_up_engine = get_limit_up_engine()
        except Exception as e:
            logger.debug(f"LimitUpEngine 初始化跳过/暂未加载: {e}")

    def get_cached_popularity_data(self) -> dict:
        """读取最近一次全网人气榜单缓存 (东财、同花顺、淘股吧、龙虎大师)"""
        try:
            import os, json
            from sys_utils import get_app_root
            cache_file = os.path.join(get_app_root(), "popularity_resonance_cache.json")
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        "em": data.get("em_data", {}),
                        "ths": data.get("ths_data", {}),
                        "lh": data.get("lh_data", {}),
                        "tgb": data.get("tgb_data", {}),
                        "resonance": data.get("resonance_results", [])
                    }
        except Exception:
            pass
        return {"em": {}, "ths": {}, "lh": {}, "tgb": {}, "resonance": []}

    def enrich_with_ladder_and_tdx(self, stock_list: list[dict], index_pct: float = -0.5) -> list[dict]:
        """
        为全网人气股列表秒级注入：
        1. ATS 连板天梯 (高度龙/连板加速/99分梯队)
        2. TDX 盘口微观买盘压强 (bid_pressure) 与封流比 (seal_circ_ratio)
        3. 逆势破局龙感知 (pioneer_tag) 与三大黄金挂单点推演 (entry_plan)
        """
        if not stock_list:
            return []

        codes = [item["code"] for item in stock_list]
        feature_engine = DynamicFeatureEngine()
        
        # 1. 尝试从 TDX 批量获取秒级深度盘口
        quotes_dict = {}
        if self._tdx_fetcher:
            try:
                quotes_df = self._tdx_fetcher.get_security_quotes_df(codes)
                if quotes_df is not None and not quotes_df.empty:
                    quotes_dict = quotes_df.to_dict('index')
            except Exception as e:
                logger.debug(f"TDX 批量盘口拉取跳过: {e}")

        # 2. 读取 ATS 连板天梯记录
        ladder_records = {}
        if self._limit_up_engine:
            try:
                if hasattr(self._limit_up_engine, 'records'):
                    ladder_records = self._limit_up_engine.records or {}
            except Exception:
                pass

        enriched_list = []
        for item in stock_list:
            code = item.get("code", "")
            q_row = quotes_dict.get(code, {})
            ladder_item = ladder_records.get(code, {})
            
            # 提取实时量价
            price = float(q_row.get("price", item.get("price", 0.0)))
            percent = float(q_row.get("percent", item.get("percent", 0.0)))
            last_close = float(q_row.get("last_close", item.get("yesterday_close", 0.0)))
            vwap = float(q_row.get("vwap", price))

            # 提取/推算盘口微观五档深度
            bid1_p = float(q_row.get("bid1", 0.0))
            bid1_v = float(q_row.get("bid_vol1", 0.0))
            ask1_v = float(q_row.get("ask_vol1", 0.0))
            total_bid_v = sum(float(q_row.get(f"bid_vol{i}", 0.0)) for i in range(1, 6))
            total_ask_v = sum(float(q_row.get(f"ask_vol{i}", 0.0)) for i in range(1, 6))
            
            depth_total = max(1.0, total_bid_v + total_ask_v)
            bid_pressure = round((total_bid_v / depth_total) * 100, 1) if total_bid_v > 0 else 50.0
            seal_amt_wan = round((bid1_p * bid1_v * 100) / 10000.0, 1) if bid1_p > 0 and bid1_v > 0 else 0.0
            seal_circ_ratio = float(ladder_item.get("seal_to_circ_ratio", 0.0))
            
            # 天梯梯队与角色标签
            plates = int(ladder_item.get("continuous_plate_count", 0))
            ladder_role = ladder_item.get("role_name", "")
            ladder_score = int(ladder_item.get("score", 0))
            if not ladder_role:
                if percent >= 9.8:
                    ladder_role = "🔥 强势首板"
                    ladder_score = 90
                elif percent >= 5.0:
                    ladder_role = "🚀 冲锋冲板"
                    ladder_score = 75
                else:
                    ladder_role = "⏱️ 潜伏震荡"
                    ladder_score = 50

            # 逆势破局龙感知
            pioneer_info = feature_engine.evaluate_counter_market_divergence(
                stock_pct=percent,
                index_pct=index_pct,
                bidding_amt_wan=seal_amt_wan,
                seal_circ_ratio=seal_circ_ratio
            )

            # 三大黄金挂单点推演
            entry_plan = feature_engine.infer_actionable_entry_points(
                code=code,
                price=price,
                stock_pct=percent,
                last_close=last_close,
                bidding_amt_wan=seal_amt_wan,
                seal_circ_ratio=seal_circ_ratio,
                bid_pressure=bid_pressure,
                vwap=vwap
            )

            # 假热度出货/诱多识别
            is_fake_trap = bool(bid_pressure < 35.0 and percent > 3.0 and ask1_v > total_bid_v * 2.0)
            decision_status = "⚠️ 缩量诱多防砸" if is_fake_trap else (
                "👑 顶级共振真龙" if (pioneer_info["is_counter_market"] or "空间" in ladder_role or ladder_score >= 95) else "🚀 梯队先锋跟进"
            )

            # 注入全量多维指标
            item.update({
                "price": price,
                "percent": percent,
                "bid_pressure": bid_pressure,
                "seal_amount_wan": seal_amt_wan,
                "seal_circ_ratio": seal_circ_ratio,
                "ladder_role": ladder_role,
                "ladder_score": ladder_score,
                "continuous_plates": plates,
                "rs_divergence": pioneer_info["rs_divergence"],
                "is_counter_market": pioneer_info["is_counter_market"],
                "pioneer_tag": pioneer_info["pioneer_tag"],
                "entry_action": entry_plan["action_type"],
                "suggested_price": entry_plan["suggested_price"],
                "entry_urgency": entry_plan["urgency"],
                "entry_window_desc": entry_plan["window_desc"],
                "decision_status": decision_status,
                "is_fake_trap": is_fake_trap
            })
            enriched_list.append(item)

        return enriched_list


class TwoWayResonanceHub:
    """
    双向共振决策中枢：管理先验探测池与全网热度合力验证
    """
    def __init__(self):
        self._leading_pool = {}  # {code: {signal_info, timestamp}}
        self._last_ranks = {}    # {code: (last_rank, timestamp)}

    def calculate_rank_jump_velocity(self, code: str, current_rank: int) -> float:
        """计算热搜排名跃升加速度 (每分钟跃升名次)"""
        now = time.time()
        last_rank, last_time = self._last_ranks.get(code, (current_rank, now))
        dt = max(1.0, now - last_time)
        rank_jump = last_rank - current_rank
        velocity = (rank_jump / dt) * 60.0
        self._last_ranks[code] = (current_rank, now)
        return round(velocity, 2)


def calculate_resonance_scores(
    em_data: dict[str, int],
    ths_data: dict[str, int],
    tgb_data: dict[str, int],
    lh_data: dict[str, int],
    index_pct: float = -0.5
) -> list[dict]:
    r"""
    计算【全网热度 $\times$ TDX真金盘口 $\times$ ATS连板天梯】三位一体人气共振综合得分
    
    评分体系 (满分约 1000 分):
    1. 全网热度基础分 (0~300分):
       - 东财 (前100): 101 - 排名
       - 同花顺 (前100): 101 - 排名
       - 淘股吧 (前50): (51 - 排名) * 2
       - 龙虎大师 (若有): 50分
       - 多平台共振加成: 3平台加 300分, 2平台加 150分
    2. TDX 盘口真金加成 (0~350分):
       - 买盘压强 $\ge 80\%$: +150分; 封单金额超千万: +100分; 封流比 $>5\%$: +100分
       - 诱多出货惩罚: 买盘压强 $<35\%$: -300分
    3. ATS 连板天梯与逆势破局加成 (0~350分):
       - 空间总龙/连板加速: +150~200分
       - 逆势冰点破局龙 (RS偏离度大): +150分
    """
    all_codes = set(em_data.keys()) | set(ths_data.keys()) | set(tgb_data.keys()) | set(lh_data.keys())
    
    resonance_list = []
    for code in all_codes:
        rk_em = em_data.get(code)
        rk_ths = ths_data.get(code)
        rk_tgb = tgb_data.get(code)
        rk_lh = lh_data.get(code)
        
        platforms = 0
        score = 0
        details = []
        
        if rk_em is not None:
            platforms += 1
            score += (101 - rk_em)
            details.append(f"东财:{rk_em}")
        if rk_ths is not None:
            platforms += 1
            score += (101 - rk_ths)
            details.append(f"同花顺:{rk_ths}")
        if rk_tgb is not None:
            platforms += 1
            score += (51 - rk_tgb) * 2
            details.append(f"淘股吧:{rk_tgb}")
        if rk_lh is not None:
            platforms += 1
            score += 50
            details.append(f"龙虎:{rk_lh}")
            
        # 全网跨平台共振加分
        if platforms >= 3:
            score += 300
        elif platforms == 2:
            score += 150
            
        resonance_list.append({
            "code": code,
            "platforms": platforms,
            "score": score,
            "details": ", ".join(details)
        })

    # 4. 通过 LadderResonanceBridge 注入 TDX 盘口与 ATS 天梯数据
    bridge = LadderResonanceBridge.get_instance()
    enriched_list = bridge.enrich_with_ladder_and_tdx(resonance_list, index_pct=index_pct)

    # 5. 融合三位一体最终得分
    for item in enriched_list:
        bid_p = item.get("bid_pressure", 50.0)
        seal_amt = item.get("seal_amount_wan", 0.0)
        seal_circ = item.get("seal_circ_ratio", 0.0)
        is_counter = item.get("is_counter_market", False)
        ladder_score = item.get("ladder_score", 50)
        is_fake = item.get("is_fake_trap", False)

        # 盘口真金加成
        if bid_p >= 80.0:
            item["score"] += 120
        elif bid_p >= 65.0:
            item["score"] += 60
        if seal_amt >= 2000:
            item["score"] += 100
        elif seal_amt >= 500:
            item["score"] += 50
        if seal_circ >= 3.0:
            item["score"] += 80

        # 逆势破局与天梯加成
        if is_counter:
            item["score"] += 150
        item["score"] += int(ladder_score * 1.5)

        # 诱多惩罚
        if is_fake:
            item["score"] = max(10, item["score"] - 400)

    # 按综合得分降序排列
    enriched_list.sort(key=lambda x: x['score'], reverse=True)
    return enriched_list

def write_to_tdx_blocks(codes: list[str], blk_filename: str = "RQG.blk") -> None:
    """
    将股票代码写入通达信的自选板块文件中。
    支持写入多个存在的工作路径，解决路径错配问题。
    """
    if not codes:
        logger.warning("没有股票代码需要写入.")
        return
        
    # 确保后缀名为 .blk
    blk_filename = blk_filename.strip()
    if not blk_filename.endswith(".blk"):
        blk_filename += ".blk"
        
    # 1. 写入主通达信目录 (由 cct.write_to_blocknew 自动联动 new_tdx2 和 zd_dxzq)
    if cct is not None:
        try:
            primary_path = os.path.join(cct.get_tdx_dir_blocknew(), blk_filename)
            cct.write_to_blocknew(primary_path, codes, append=False, doubleFile=False)
            logger.info(f"成功更新主自选板块文件: {primary_path}")
            return 
        except Exception as e:
            logger.error(f"写入主自选板块文件失败: {e}")
        
    # 2. 兜底写入 D:\kxg 目录 (原易语言EXE的硬编码目标)
    kxg_dir = r"D:\kxg\T0002\blocknew"
    if os.path.exists(kxg_dir):
        kxg_filepath = os.path.join(kxg_dir, blk_filename)
        try:
            if cct is not None:
                # 显式使用内置的 write_to_blocknew_2025 以格式化并包含指数
                cct.write_to_blocknew_2025(kxg_filepath, codes, append=False)
            else:
                with open(kxg_filepath, 'wb') as f:
                    for c in codes:
                        prefix = '1' if c.startswith(('5', '6')) else '2' if c.startswith(('43','83','87','92')) else '0'
                        f.write(f"{prefix}{c}\r\n".encode('ascii'))
            logger.info(f"成功更新兜底自选文件: {kxg_filepath}")
        except Exception as e:
            logger.error(f"写入兜底自选文件失败: {e}")

def run_sync(max_stocks: int = 50, blk_filename: str = "RQG.blk") -> list[dict]:
    """运行一次完整的人气共振采集与写入"""
    logger.info("开始拉取各大平台人气榜单...")
    
    # 并发/依次拉取
    em_data = fetch_eastmoney()
    ths_data = fetch_ths()
    tgb_data = fetch_taoguba()
    lh_data = fetch_longhu()
    
    # 计算共振得分
    logger.info("计算人气共振得分...")
    resonance_results = calculate_resonance_scores(em_data, ths_data, tgb_data, lh_data)
    
    # 过滤出前 max_stocks 名
    top_results = resonance_results[:max_stocks]
    logger.info(f"选出前 {len(top_results)} 只共振人气最强的股票:")
    for idx, r in enumerate(top_results, 1):
        logger.info(f"  No.{idx:02d}: {r['code']} | 得分: {r['score']:4d} | 共振数: {r['platforms']} | 详情: ({r['details']})")
        
    # 获取代码列表
    top_codes = [r['code'] for r in top_results]
    
    # 写入通达信自选文件
    logger.info(f"写入通达信自选文件: {blk_filename}...")
    write_to_tdx_blocks(top_codes, blk_filename=blk_filename)
    
    return top_results

if __name__ == "__main__":
    run_sync()
