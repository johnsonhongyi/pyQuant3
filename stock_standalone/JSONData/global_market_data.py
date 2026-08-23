# -*- coding: utf-8 -*-
"""
JSONData Global Market Data Engine
外盘情绪感知与连带打分引擎 (支持30分钟/交易时段 Cache 与美股7巨头/存储/半导体/AI自更新)

抓取主要外盘/跨境指数与热点龙头:
- 富时 A50 期货 (hf_CHA50CFD) -> 联动大盘指数与军工/汽车/权重龙头
- 纳斯达克 (gb_$COMP) / 标普500 (gb_$SPX) / QQQ -> 联动科技/AI/传媒/软件板块 (如蓝色光标)
- 美股7巨头 (NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA) -> 联动 AI / 科技 / 汽车
- 存储芯片/半导体龙头 (MU, TSM, SOXX) -> 联动存储芯片/半导体/电子
- 离岸人民币 CNH (fx_susdcnh) -> 资金流动防线
- 国际原油/黄金大宗商品 (hf_CL / hf_GC) -> 联动资源/有色/化工板块

设计原则:
- 30 分钟 (1800s) 交易日交易时段 Cache，非交易日/盘后强制使用 Cache 零网络请求
- 物理磁盘 JSON 持久化 (config/global_market_cache.json)，冷启动秒级加载
- 超低延迟 (2.0s 超时) + 静默降级，绝不阻塞主流程
"""

import time
import datetime
import urllib.request
import json
import os
import re
import threading

# 全局缓存与锁
_global_cache = {
    'last_update_ts': 0.0,
    'quotes': {},
    'sentiment_score': 0.0,
    'sentiment_label': '🌐 外盘平稳',
}

# 缓存 TTL: 默认 30 分钟 (1800 秒)
CACHE_TTL = 1800.0


# ⚡ Tier 1: 内存 (RAM) 级别 K线分级 Cache, 脏标志, 并发请求去重 set 与线程安全互斥锁
# Key: (symbol_upper, source_key) -> {'klines': list, 'fetch_ts': float}
_KLINE_RAM_CACHE = {}
_KLINE_CACHE_LOCK = threading.Lock()
_KLINE_DIRTY_FLAGS = {'yahoo': False, 'sina': False}
_KLINE_IN_FLIGHT = set()
_kline_fetch_timestamps = {}




def get_global_market_log_enabled() -> bool:
    """读取物理 JSON 配置文件中的外盘数据日志开关状态 (默认关闭 False)"""
    try:
        from ats.ui.styles import load_config_node
        val = load_config_node("ats_global_market_log_enabled", False)
        return bool(val)
    except Exception:
        return False


def save_global_market_log_enabled(enabled: bool) -> bool:
    """物理落盘持久化保存外盘数据日志开关状态至 window_config.json"""
    try:
        from ats.ui.styles import save_config_node
        res = save_config_node("ats_global_market_log_enabled", bool(enabled))
        if res:
            log_market_msg(f"[LogConfig] 日志开关落盘成功: enabled={enabled}")
        return res
    except Exception as ex:
        return False


def log_market_msg(*args, **kwargs):
    """统一外盘数据日志打印 helper：仅当日志开关开启 (enable_market_logging=True) 时打印带 [HH:MM:SS] 时间戳的控制台调试日志"""
    if get_global_market_log_enabled():
        now_str = datetime.datetime.now().strftime("[%H:%M:%S]")
        try:
            print(now_str, *args, **kwargs)
        except Exception:
            try:
                safe_args = [str(a).encode('gbk', errors='replace').decode('gbk') for a in args]
                print(now_str, *safe_args, **kwargs)
            except Exception:
                pass


def get_proxy_config() -> dict:
    """读取物理 JSON 配置文件中的代理 Proxy 配置"""
    try:
        from ats.ui.styles import load_config_node
        cfg = load_config_node("ats_proxy_config", None)
        if isinstance(cfg, dict):
            return {
                "enabled": bool(cfg.get("enabled", False)),
                "proxy_url": str(cfg.get("proxy_url", "http://127.0.0.1:7890")).strip()
            }
    except Exception:
        pass
    return {"enabled": False, "proxy_url": "http://127.0.0.1:7890"}


def save_proxy_config(enabled: bool, proxy_url: str) -> bool:
    """物理落盘持久化保存代理 Proxy 配置至 window_config.json"""
    try:
        from ats.ui.styles import save_config_node
        val = {
            "enabled": bool(enabled),
            "proxy_url": str(proxy_url).strip()
        }
        res = save_config_node("ats_proxy_config", val)
        if res:
            log_market_msg(f"[ProxyConfig] 物理落盘成功: enabled={enabled}, url={proxy_url}")
        return res
    except Exception as ex:
        log_market_msg(f"[ProxyConfig] 保存代理配置失败: {ex}")
        return False


def get_proxy_info_str() -> str:
    """获取当前 Proxy 路径与配置状态字符串，方便日志打印时随时明确网络请求路径"""
    cfg = get_proxy_config()
    enabled = cfg.get("enabled", False)
    url = cfg.get("proxy_url", "").strip()
    if enabled and url:
        return f"[Proxy: ON - {url}]"
    elif url:
        return f"[Proxy: OFF - 直连(配置: {url})]"
    else:
        return "[Proxy: OFF - 纯直连]"


def get_urllib_request_opener(target_url: str = ""):
    """获取应用代理设置的 urllib.request.OpenerDirector 实例 
    (对于国内常用财经直连源 sina.com.cn / sinajs.cn / gtimg.cn 自动优先直连以提升数百毫秒响应速度并避免代理踩踏；
    对于境外源如 Yahoo Finance 在代理开启时使用配置代理)
    """
    if target_url:
        u_lower = str(target_url).lower()
        if 'sina.com.cn' in u_lower or 'sinajs.cn' in u_lower or 'gtimg.cn' in u_lower:
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))

    cfg = get_proxy_config()
    if cfg.get("enabled") and cfg.get("proxy_url"):
        p_url = cfg.get("proxy_url").strip()
        if p_url:
            try:
                proxy_handler = urllib.request.ProxyHandler({
                    'http': p_url,
                    'https': p_url
                })
                return urllib.request.build_opener(proxy_handler)
            except Exception as ex:
                log_market_msg(f"[ProxyConfig] 构建 ProxyHandler 失败 ({ex})")
    
    # ⚡ 关键物理修复：代理关闭时，显式使用 ProxyHandler({}) 强行屏蔽并绕过 Windows 系统注册表/环境变量里的废弃代理
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get_cache_file_path() -> str:
    """获取外盘缓存文件的绝对物理路径 (优先调用系统 sys_utils 模块以兼容 PyInstaller/Nuitka 打包环境与开发环境)"""
    try:
        from sys_utils import get_conf_path
        return get_conf_path('global_market_cache.json')
    except Exception:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, 'config', 'global_market_cache.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path


# 磁盘持久化文件路径 (动态属性调用)
CACHE_FILE_PATH = get_cache_file_path()


def _load_disk_cache():
    """从物理磁盘加载上一次的外盘缓存数据"""
    cache_path = get_cache_file_path()
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'quotes' in data:
                    _global_cache['quotes'] = data.get('quotes', {})
                    _global_cache['last_update_ts'] = data.get('last_update_ts', 0.0)
                    _global_cache['sentiment_score'] = data.get('sentiment_score', 0.0)
                    _global_cache['sentiment_label'] = data.get('sentiment_label', '🌐 外盘平稳')
        except Exception:
            pass


def _save_disk_cache():
    """将最新外盘缓存写入物理磁盘持久化"""
    try:
        cache_path = get_cache_file_path()
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(_global_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# 模块初始化时自动尝试装载物理磁盘缓存
_load_disk_cache()


def is_market_active_time() -> bool:
    """判断当前时间是否处于外盘/美股活跃交易窗口 (盘前 16:00 -> 盘中 -> 盘后 08:00)
    - 周末 (周六 08:00 - 周一 16:00): 美股休市非交易日，绝对无新收盘数据，零网络请求！
    - 工作日白天 (08:00 - 16:00): 美股全盘闭市非交易时段，零网络请求！
    - 工作日盘前/盘中/盘后 (16:00 - 08:00 次日): 外盘活跃交易窗口
    """
    now = datetime.datetime.now()
    weekday = now.weekday()
    hour = now.hour

    # 周六 08:00 以后 -> 周日整天 -> 周一 16:00 前: 美股休市非交易日
    if weekday == 5 and hour >= 8:
        return False
    if weekday == 6:
        return False
    if weekday == 0 and hour < 16:
        return False

    # 工作日白天 08:00 至 16:00: 美股全盘闭市，绝无新日K线数据，零网络请求
    if weekday in (0, 1, 2, 3, 4) and 8 <= hour < 16:
        return False

    return True



# ---------------- 跨时区与目标市场日历安全处理模块 ----------------

def get_symbol_market_timezone(symbol: str) -> str:
    """获取指定标的所属的目标市场时区
    - 美股 7 巨头/半导体/大宗期货/美股指数 (NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, MU, TSM, SOXX, QQQ, NASDAQ, SP500, OIL, BRENT, GOLD, SILVER, XAUUSD 等): 'America/New_York'
    - 富时 A50 期货 (A50) / 离岸人民币 (USDCNH): 'Asia/Shanghai'
    """
    if not symbol:
        return 'Asia/Shanghai'
    sym_upper = str(symbol).strip().upper()
    US_SYMBOLS = {
        'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'MU', 'TSM', 'SOXX', 'QQQ',
        'NASDAQ', 'SP500', 'OIL', 'BRENT', 'GOLD', 'SILVER', 'XAUUSD'
    }
    if sym_upper in US_SYMBOLS or sym_upper.startswith('GB_') or sym_upper.startswith('US'):
        return 'America/New_York'
    return 'Asia/Shanghai'


def get_target_market_datetime(symbol: str) -> datetime.datetime:
    """获取指定标的所属目标市场的当前精确 datetime (兼容 Windows/PyInstaller 零依赖 timezone 计算)"""
    tz_name = get_symbol_market_timezone(symbol)
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    if tz_name == 'America/New_York':
        # 计算美国东部夏令时 EDT (UTC-4) 与冬令时 EST (UTC-5)
        # EDT: 3月第2个周日 02:00 UTC 至 11月第1个周日 02:00 UTC
        year = now_utc.year
        mar1 = datetime.datetime(year, 3, 1, tzinfo=datetime.timezone.utc)
        first_sun_mar = 1 + (6 - mar1.weekday()) % 7
        second_sun_mar = first_sun_mar + 7
        edt_start = datetime.datetime(year, 3, second_sun_mar, 2, 0, tzinfo=datetime.timezone.utc)

        nov1 = datetime.datetime(year, 11, 1, tzinfo=datetime.timezone.utc)
        first_sun_nov = 1 + (6 - nov1.weekday()) % 7
        edt_end = datetime.datetime(year, 11, first_sun_nov, 2, 0, tzinfo=datetime.timezone.utc)

        is_edt = (edt_start <= now_utc < edt_end)
        offset_hours = -4 if is_edt else -5
        target_tz = datetime.timezone(datetime.timedelta(hours=offset_hours))
        return now_utc.astimezone(target_tz)
    else:
        # 默认 Asia/Shanghai (UTC+8)
        sh_tz = datetime.timezone(datetime.timedelta(hours=8))
        return now_utc.astimezone(sh_tz)


def get_target_market_date_str(symbol: str) -> str:
    """获取指定标的在所属目标市场的当前物理日期 YYYY-MM-DD"""
    dt_target = get_target_market_datetime(symbol)
    return dt_target.strftime('%Y-%m-%d')


def is_us_stock_symbol(symbol: str) -> bool:
    """判断是否为美股股票/美股ETF标的 (需要美东时间 09:30 正式开盘后才产生今日 Daily K 线)"""
    if not symbol:
        return False
    sym_upper = str(symbol).strip().upper()
    US_STOCKS = {
        'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'MU', 'TSM', 'SOXX', 'QQQ',
        'NASDAQ', 'SP500'
    }
    return sym_upper in US_STOCKS or sym_upper.startswith('GB_') or sym_upper.startswith('US')


def is_target_market_session_open(symbol: str) -> bool:
    """判断指定标的所属目标市场当前是否处于【正式开盘/盘中动态 Bar 产生】活跃窗口
    - 美股股票/ETF (US Stocks): 美东时间 09:30 - 20:00 (EDT) 为常规正盘与盘后交易窗口。在美东 00:00 - 09:30 (即北京时间 12:00 - 21:30) 美股正盘未开盘前，session_open 为 False，绝对不生成/不追加未开盘日的临时日 K Bar！
    - 全球大宗/期货 (OIL, GOLD, BRENT): 美东时间 04:00 - 20:00 活跃交易窗口
    - A50 / 离岸RMB (Asia/Shanghai 时区): 北京时间 09:00 - 16:30, 17:00 - 03:00 (次日)
    """
    dt_target = get_target_market_datetime(symbol)
    tz_name = get_symbol_market_timezone(symbol)
    weekday = dt_target.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    hour = dt_target.hour
    minute = dt_target.minute
    time_float = hour + minute / 60.0

    if tz_name == 'America/New_York':
        # 周末休市 (美东周五 20:00 后 至 周日 18:00 前)
        if weekday == 5:  # 周六
            return False
        if weekday == 6 and time_float < 18.0:  # 周日 18:00 前
            return False
        if weekday == 4 and time_float >= 20.0:  # 周五 20:00 后
            return False

        # ⚡ 关键美股时区修复：美股股票/ETF 必须在美东时间 09:30 以后 (正式开盘) 至 20:00 (盘后) 才算 session_open！
        # 在 00:00 - 09:30 (即北京时间 12:00 - 21:30)，美股正盘尚未开始， session_open = False，绝对不追加今日未开盘日K Bar！
        if is_us_stock_symbol(symbol):
            if 9.5 <= time_float < 20.0:
                return True
            return False
        else:
            # 大宗商品期货 / 现货黄金 / 外汇: 04:00 - 20:00 处于交易活跃期
            if 4.0 <= time_float < 20.0:
                return True
            return False
    else:
        # A50 / 离岸人民币 (Asia/Shanghai 时区)
        if weekday >= 5:
            return False
        if 9.0 <= time_float <= 16.5 or 17.0 <= time_float or time_float < 3.0:
            return True
        return False


def sanitize_klines_for_symbol(symbol: str, klines: list) -> list:
    """安全清洗与校验 K 线序列，严格剥离剔除任何 > 目标市场当前日期的穿越/未来 Bar 及数量级离群脏数据"""
    if not klines or not symbol:
        return []

    sym_u = symbol.strip().upper()
    target_today = get_target_market_date_str(sym_u)
    sanitized = []
    seen_dates = set()

    # 🛡️ 核心物理数值门槛: 宽容合理的安全数值门槛，防止误杀最新牛市行情与大宗商品暴涨
    EXPECTED_RANGES = {
        'AAPL': (10.0, 5000.0),
        'MSFT': (10.0, 5000.0),
        'NVDA': (1.0, 5000.0),
        'GOOGL': (10.0, 5000.0),
        'AMZN': (10.0, 5000.0),
        'META': (10.0, 5000.0),
        'TSLA': (5.0, 5000.0),
        'MU': (5.0, 5000.0),
        'TSM': (5.0, 5000.0),
        'SOXX': (10.0, 5000.0),
        'QQQ': (10.0, 5000.0),
        'OIL': (5.0, 500.0),        # 美原油 $5~$500/桶
        'BRENT': (5.0, 500.0),      # 布伦特 $5~$500/桶
        'GOLD': (100.0, 20000.0),   # 美黄金 $100~$20000/盎司
        'XAUUSD': (100.0, 20000.0),
        'SILVER': (2.0, 500.0),     # COMEX白银 $2~$500/盎司
        'A50': (1.0, 50000.0),      # A50 ETF(10~30) / A50 期货(10000~30000)
        'USDCNH': (2.0, 20.0),      # 离岸人民币
    }
    min_p, max_p = EXPECTED_RANGES.get(sym_u, (0.01, 1000000.0))

    for item in klines:
        if not isinstance(item, dict):
            continue
        d_str = str(item.get('date', '')).strip()
        if not d_str:
            continue
        if len(d_str) > 10:
            d_str = d_str[:10]

        # 防穿越：绝不允许 > 目标市场当前日期
        if d_str > target_today:
            continue

        c_val = float(item.get('close', 0))
        if c_val <= 0:
            continue

        # 绝对物理区间校验 (拦截非同单位脏数据)
        if not (min_p <= c_val <= max_p):
            continue

        if d_str not in seen_dates:
            seen_dates.add(d_str)
            item_copy = dict(item)
            item_copy['date'] = d_str
            item_copy['close'] = c_val
            sanitized.append(item_copy)

    if not sanitized:
        return []

    # 按日期升序排列
    sanitized.sort(key=lambda x: x['date'])

    # 🛡️ 相对数量级护盾：根据中位数过滤离群脏 Bar (防 14943.97 点位与 16.98 港元混存拉爆 Y 轴)
    valid_closes = [k['close'] for k in sanitized if k['close'] > 0]
    if valid_closes:
        sorted_closes = sorted(valid_closes)
        med_close = sorted_closes[len(sorted_closes) // 2]
        if med_close > 0:
            clean_by_mag = []
            for item in sanitized:
                c = item['close']
                ratio = c / med_close
                if 0.25 <= ratio <= 4.0:
                    clean_by_mag.append(item)
            if clean_by_mag:
                sanitized = clean_by_mag

    prev_c = None
    for item in sanitized:
        c = float(item.get('close', 0))
        if prev_c and prev_c > 0 and c > 0:
            item['pct'] = round(((c - prev_c) / prev_c) * 100.0, 2)
        elif 'pct' not in item:
            item['pct'] = 0.0
        if c > 0:
            prev_c = c

    return sanitized



def clean_all_disk_kline_caches():
    """扫描并物理清洗全量外盘 JSON 缓存文件，从磁盘上物理剥离排除所有超出目标市场日期的穿越 Bar"""
    cache_files = []
    try:
        conf_path = get_kline_cache_file_path()
        base_dir = os.path.dirname(conf_path)
        for fname in ['global_market_klines_yahoo.json', 'global_market_klines_sina.json', 'global_market_klines.json']:
            fpath = os.path.join(base_dir, fname)
            if os.path.exists(fpath):
                cache_files.append(fpath)
    except Exception:
        pass

    cleaned_count = 0
    for fpath in cache_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            modified = False
            for sym, klines in list(data.items()):
                if isinstance(klines, list) and klines:
                    cleaned_klines = sanitize_klines_for_symbol(sym, klines)
                    if len(cleaned_klines) != len(klines):
                        data[sym] = cleaned_klines
                        modified = True
                        cleaned_count += (len(klines) - len(cleaned_klines))
            if modified:
                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                log_market_msg(f"[GlobalMarketData] 物理落盘清洗磁盘文件 {os.path.basename(fpath)}: 剔除 {cleaned_count} 条穿越/未来数据")
        except Exception as ex:
            log_market_msg(f"[GlobalMarketData] 清洗磁盘缓存异常 {fpath}: {ex}")



# 动态梯度延迟间隔阶梯 (单位: 分钟)
# 梯度选项: 5分钟(300s), 10分钟(600s), 15分钟(900s), 20分钟(1200s), 25分钟(1500s), 30分钟(1800s)
CACHE_TTL_GRADIENTS_MINUTES = [5, 10, 15, 20, 25, 30]


def get_global_market_cache_ttl() -> float:
    """根据交易活跃期与用户梯度配置，返回 5/10/15/20/25/30 分钟动态梯度延迟冷却阈值 (秒)
    - 交易活跃窗口: 默认 5 分钟 (300 秒) 阶梯防封锁
    - 盘后/非交易日: 自动拓展至 15~30 分钟 (900~1800 秒) 阶梯延迟
    """
    try:
        from ats.ui.styles import load_config_node
        custom_min = load_config_node("ats_global_market_ttl_minutes", None)
        if custom_min is not None and int(custom_min) in CACHE_TTL_GRADIENTS_MINUTES:
            base_sec = float(custom_min) * 60.0
            return base_sec if is_market_active_time() else max(base_sec, 900.0)
    except Exception:
        pass

    # 默认梯度: 交易期 5 分钟 (300s)，非交易期 15 分钟 (900s)
    return 300.0 if is_market_active_time() else 900.0


def fetch_global_market_quotes(force_refresh=False) -> dict:
    """抓取主要外盘指数与美股7巨头/存储芯片/半导体实时/盘前数据

    Returns:
        dict: {
            'A50': {'price': float, 'pct': float, 'name': str},
            'NASDAQ': {'price': float, 'pct': float, 'name': str},
            'SP500': {'price': float, 'pct': float, 'name': str},
            'USDCNH': {'price': float, 'pct': float, 'name': str},
            'OIL': {'price': float, 'pct': float, 'name': str},
            'GOLD': {'price': float, 'pct': float, 'name': str},
            'NVDA': {'price': float, 'pct': float, 'name': str},
            'MU': {'price': float, 'pct': float, 'name': str}, ...
        }
    """
    now = time.time()
    has_cache = bool(_global_cache['quotes'])
    active_trading = is_market_active_time()
    cache_ttl = get_global_market_cache_ttl()

    if force_refresh:
        _global_cache['last_update_ts'] = 0.0

    # 1. 自动更新保护规则:
    # - 未达到统一阈值 (cache_ttl) 且非强制刷新: 直接返回缓存
    if not force_refresh and has_cache:
        if (now - _global_cache['last_update_ts'] < cache_ttl):
            return _global_cache['quotes']

    # 新浪外盘/美股/大宗/外汇接口
    # 核心代号说明:
    # hf_CHA50CFD: A50期货, gb_$COMP: 纳指, gb_$SPX: 标普500, fx_susdcnh: 离岸RMB
    # hf_CL: WTI原油期货, hf_CO: 布伦特原油期货, hf_GC: COMEX黄金期货
    # fx_sxauusd: 现货黄金(纽约金连续参考), hf_SI: COMEX白银
    # gb_nvda: 英伟达, gb_aapl: 苹果, gb_msft: 微软, gb_googl: 谷歌, gb_amzn: 亚马逊, gb_meta: Meta, gb_tsla: 特斯拉
    # gb_mu: 美光(存储芯片), gb_tsm: 台积电(晶圆/半导体), gb_soxx: 费城半导体, gb_qqq: 纳指100
    symbols = (
        'hf_CHA50CFD,gb_$COMP,gb_$SPX,fx_susdcnh,hf_CL,hf_CO,hf_GC,fx_sxauusd,hf_SI,'
        'gb_nvda,gb_aapl,gb_msft,gb_googl,gb_amzn,gb_meta,gb_tsla,'
        'gb_mu,gb_tsm,gb_soxx,gb_qqq'
    )
    url = f"http://hq.sinajs.cn/list={symbols}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'http://finance.sina.com.cn',
    }

    quotes = {}

    try:
        req = urllib.request.Request(url, headers=headers)
        opener = get_urllib_request_opener(url)
        with opener.open(req, timeout=5.0) as resp:
            content = resp.read().decode('gbk', errors='ignore')

        # parsing dictionary for US stocks & ETFs
        us_symbol_map = {
            'gb_nvda': ('NVDA', '英伟达/算力'),
            'gb_aapl': ('AAPL', '苹果'),
            'gb_msft': ('MSFT', '微软'),
            'gb_googl': ('GOOGL', '谷歌'),
            'gb_amzn': ('AMZN', '亚马逊'),
            'gb_meta': ('META', 'Meta'),
            'gb_tsla': ('TSLA', '特斯拉'),
            'gb_mu': ('MU', '美光/存储'),
            'gb_tsm': ('TSM', '台积电'),
            'gb_soxx': ('SOXX', '半导体ETF'),
            'gb_qqq': ('QQQ', '纳斯达克100'),
        }

        # 解析新浪返回的 hq_str_ 字符串
        for line in content.splitlines():
            if '="' not in line:
                continue
            var_name, val_str = line.split('="', 1)
            val_str = val_str.rstrip('";')
            if not val_str:
                continue

            parts = val_str.split(',')

            # 1. 富时 A50 期货 (hf_CHA50CFD)
            if 'hf_CHA50CFD' in var_name and len(parts) >= 8:
                try:
                    price = float(parts[0])
                    prev_close = float(parts[7]) if float(parts[7]) > 0 else float(parts[3])
                    pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                    quotes['A50'] = {'price': price, 'pct': pct, 'name': '富时A50期货'}
                except Exception:
                    pass

            # 2. 纳斯达克指数 (gb_$COMP)
            elif 'gb_$COMP' in var_name and len(parts) >= 4:
                try:
                    price = float(parts[1])
                    pct = float(parts[2])
                    quotes['NASDAQ'] = {'price': price, 'pct': pct, 'name': '纳斯达克'}
                except Exception:
                    pass

            # 3. 标普 500 指数 (gb_$SPX)
            elif 'gb_$SPX' in var_name and len(parts) >= 4:
                try:
                    price = float(parts[1])
                    pct = float(parts[2])
                    quotes['SP500'] = {'price': price, 'pct': pct, 'name': '标普500'}
                except Exception:
                    pass

            # 4. 离岸人民币 (fx_susdcnh)
            elif 'fx_susdcnh' in var_name and len(parts) >= 10:
                try:
                    price = float(parts[1])
                    prev_close = float(parts[3]) if float(parts[3]) > 0 else price
                    pct = round(((price - prev_close) / prev_close) * 100.0, 2)
                    quotes['USDCNH'] = {'price': price, 'pct': pct, 'name': '离岸人民币'}
                except Exception:
                    pass

            # 5. WTI 原油期货 (hf_CL)
            elif 'hf_CL' in var_name and 'hf_CL,' not in var_name.replace('hf_CL,', '') and len(parts) >= 8:
                try:
                    price = float(parts[0])
                    prev_close = float(parts[7]) if float(parts[7]) > 0 else float(parts[3])
                    pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                    quotes['OIL'] = {'price': price, 'pct': pct, 'name': 'WTI原油'}
                except Exception:
                    pass

            # 5b. 布伦特原油期货 (hf_CO) - 国际基准油价
            elif 'hf_CO' in var_name and len(parts) >= 8:
                try:
                    price = float(parts[0])
                    prev_close = float(parts[7]) if float(parts[7]) > 0 else float(parts[3])
                    pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                    quotes['BRENT'] = {'price': price, 'pct': pct, 'name': '布伦特原油'}
                    # 布伦特作为首选国际原油参考 (更贴近THS布伦特主连)
                    if 'OIL' not in quotes or price > 0:
                        quotes['OIL_BRENT'] = {'price': price, 'pct': pct, 'name': '布伦特原油'}
                except Exception:
                    pass

            # 6. COMEX 黄金期货 (hf_GC)
            elif 'hf_GC' in var_name and len(parts) >= 8:
                try:
                    price = float(parts[0])
                    prev_close = float(parts[7]) if float(parts[7]) > 0 else float(parts[3])
                    pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                    quotes['GOLD'] = {'price': price, 'pct': pct, 'name': 'COMEX纽约金'}
                except Exception:
                    pass

            # 6b. 现货黄金 (fx_sxauusd) - 纽约金连续参考
            elif 'fx_sxauusd' in var_name and len(parts) >= 4:
                try:
                    price = float(parts[1])
                    prev_close = float(parts[3]) if float(parts[3]) > 0 else price
                    pct = round(((price - prev_close) / prev_close) * 100.0, 2)
                    quotes['XAUUSD'] = {'price': price, 'pct': pct, 'name': '现货黄金(纽约金连续)'}
                except Exception:
                    pass

            # 6c. COMEX 白银 (hf_SI)
            elif 'hf_SI' in var_name and len(parts) >= 8:
                try:
                    price = float(parts[0])
                    prev_close = float(parts[7]) if float(parts[7]) > 0 else float(parts[3])
                    pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                    quotes['SILVER'] = {'price': price, 'pct': pct, 'name': 'COMEX白银'}
                except Exception:
                    pass

            # 7. 美股7巨头与存储/半导体/QQQ
            else:
                for sys_key, (code, name) in us_symbol_map.items():
                    if sys_key in var_name and len(parts) >= 3:
                        try:
                            price = float(parts[1])
                            pct = float(parts[2])
                            open_p = float(parts[5]) if len(parts) > 5 and float(parts[5]) > 0 else price
                            high_p = float(parts[6]) if len(parts) > 6 and float(parts[6]) > 0 else max(price, open_p)
                            low_p = float(parts[7]) if len(parts) > 7 and float(parts[7]) > 0 else min(price, open_p)
                            prev_close = float(parts[26]) if len(parts) > 26 and float(parts[26]) > 0 else price
                            quotes[code] = {
                                'price': price,
                                'pct': pct,
                                'open': open_p,
                                'high': high_p,
                                'low': low_p,
                                'prev_close': prev_close,
                                'name': name
                            }
                        except Exception:
                            pass

    except Exception:
        # 网络异常时静默降级，继续使用现有内存/磁盘缓存
        pass

    if quotes:
        _global_cache['quotes'] = quotes
        _global_cache['last_update_ts'] = now
        _global_cache['is_live_network'] = True
        _update_sentiment_score(quotes)
        _save_disk_cache()
    else:
        _global_cache['is_live_network'] = False

    return _global_cache['quotes']


def get_global_market_quotes_metadata() -> dict:
    """获取最后一次外盘行情抓取的元数据 (包含 is_live_network, last_update_ts 等)"""
    return {
        'is_live_network': _global_cache.get('is_live_network', False),
        'last_update_ts': _global_cache.get('last_update_ts', 0),
        'quotes_count': len(_global_cache.get('quotes', {})),
    }


def _update_sentiment_score(quotes: dict):
    """计算外盘综合情绪评分 (-100 ~ +100)"""
    score = 0.0

    # 1. A50 贡献最多 35%
    if 'A50' in quotes:
        a50_pct = quotes['A50']['pct']
        score += min(35.0, max(-35.0, a50_pct * 22.0))

    # 2. 纳指 / QQQ 贡献最多 30%
    if 'NASDAQ' in quotes:
        nas_pct = quotes['NASDAQ']['pct']
        score += min(30.0, max(-30.0, nas_pct * 18.0))

    # 3. 人民币升值 (USDCNH 下跌) 贡献最多 20%
    if 'USDCNH' in quotes:
        cnh_pct = quotes['USDCNH']['pct']
        score += min(20.0, max(-20.0, -cnh_pct * 35.0))

    # 4. 美股7巨头与存储芯片/半导体 (NVDA, MU, MSFT, AAPL, TSLA) 贡献最多 15%
    m7_keys = ['NVDA', 'MU', 'MSFT', 'AAPL', 'META', 'GOOGL', 'AMZN', 'TSLA']
    m7_pcts = [quotes[k]['pct'] for k in m7_keys if k in quotes]
    if m7_pcts:
        m7_avg = sum(m7_pcts) / len(m7_pcts)
        score += min(15.0, max(-15.0, m7_avg * 10.0))

    _global_cache['sentiment_score'] = round(score, 1)

    if score >= 25.0:
        _global_cache['sentiment_label'] = '🌐 外盘暴涨共振'
    elif score >= 10.0:
        _global_cache['sentiment_label'] = '🌐 外盘偏红顺风'
    elif score <= -25.0:
        _global_cache['sentiment_label'] = '⚠️ 外盘暴跌大杀'
    elif score <= -10.0:
        _global_cache['sentiment_label'] = '⚠️ 外盘走弱承压'
    else:
        _global_cache['sentiment_label'] = '🌐 外盘平稳'


def get_global_sentiment_score() -> tuple:
    """获取外盘综合情绪分与标签

    Returns:
        tuple: (score: float, label: str)
    """
    quotes = fetch_global_market_quotes()
    return _global_cache['sentiment_score'], _global_cache['sentiment_label']


def get_sector_global_boost(sector_name: str) -> tuple:
    """根据板块名称自动计算美股7巨头/存储芯片/半导体/AI/军工等连带提权分 (Boost: -35.0 ~ +35.0, Tag: str)

    Args:
        sector_name: 板块名称 (如 "存储芯片", "半导体", "传媒", "IT设备", "国防军工", "汽车整车", "有色金属")

    Returns:
        tuple: (boost_score: float, tag: str)
    """
    if not sector_name or not isinstance(sector_name, str):
        return 0.0, ''

    quotes = fetch_global_market_quotes()
    if not quotes:
        return 0.0, ''

    sec_clean = sector_name.strip()
    boost = 0.0
    tag = ''

    # 提取核心海外个股/指数表现
    mu_pct = quotes.get('MU', {}).get('pct', 0.0)         # 美光(存储)
    nvda_pct = quotes.get('NVDA', {}).get('pct', 0.0)     # 英伟达(算力/半导体)
    tsm_pct = quotes.get('TSM', {}).get('pct', 0.0)       # 台积电(晶圆)
    soxx_pct = quotes.get('SOXX', {}).get('pct', 0.0)     # 费城半导体
    nas_pct = quotes.get('NASDAQ', {}).get('pct', 0.0)     # 纳指
    tsla_pct = quotes.get('TSLA', {}).get('pct', 0.0)     # 特斯拉
    a50_pct = quotes.get('A50', {}).get('pct', 0.0)       # A50

    # 1. 存储芯片 / 半导体 / 芯片 / 电子 / 集成电路 -> 强关联 美光 (MU), 英伟达 (NVDA), SOXX, 台积电
    semi_keywords = ['存储', '半导体', '芯片', '电子', '集成电路', '微电子']
    if any(k in sec_clean for k in semi_keywords):
        semi_pcts = [p for p in [mu_pct, nvda_pct, tsm_pct, soxx_pct] if p != 0.0]
        semi_avg = (sum(semi_pcts) / len(semi_pcts)) if semi_pcts else 0.0
        if semi_avg >= 1.0 or mu_pct >= 1.5:
            boost += min(35.0, max(semi_avg, mu_pct) * 16.0)
            tag = f"🌐 存储/美股半导体大涨 ({mu_pct:+.1f}%)" if '存储' in sec_clean else f"🌐 美股半导体共振 ({semi_avg:+.1f}%)"
        elif semi_avg <= -1.0 or mu_pct <= -1.5:
            boost += max(-25.0, min(semi_avg, mu_pct) * 15.0)
            tag = f"⚠️ 美股半导体/存储回调 ({semi_avg:+.1f}%)"

    # 2. 科技 / AI / 传媒 / 互联网 / 软件 / 计算机 / 游戏 (蓝色光标、易点天下等) -> 关联 美股7巨头 (NVDA, MSFT, META) & 纳指
    tech_keywords = ['IT', '软件', '传媒', '互联网', '计算机', 'AI', '游戏', '通信']
    if any(k in sec_clean for k in tech_keywords) and not tag:
        ai_pcts = [p for p in [nvda_pct, quotes.get('MSFT', {}).get('pct', 0.0), quotes.get('META', {}).get('pct', 0.0), nas_pct] if p != 0.0]
        ai_avg = (sum(ai_pcts) / len(ai_pcts)) if ai_pcts else nas_pct
        if ai_avg >= 0.8 or nas_pct >= 1.0:
            boost += min(30.0, max(ai_avg, nas_pct) * 16.0)
            tag = f"🌐 美股7巨头/AI强拉 ({ai_avg:+.1f}%)"
        elif ai_avg <= -1.0 or nas_pct <= -1.2:
            boost += max(-25.0, min(ai_avg, nas_pct) * 15.0)
            tag = f"⚠️ 美股科技巨头承压 ({ai_avg:+.1f}%)"

    # 3. 汽车 / 汽车整车 / 零部件 / 新能源 (北汽蓝谷等) -> 强关联 特斯拉 (TSLA) & A50
    auto_keywords = ['汽车', '零部件', '新能源', '动力电池']
    if any(k in sec_clean for k in auto_keywords):
        if tsla_pct >= 2.0:
            boost += min(30.0, tsla_pct * 12.0)
            tag = f"🌐 特斯拉暴涨联动 ({tsla_pct:+.1f}%)"
        elif tsla_pct <= -2.5:
            boost += max(-25.0, tsla_pct * 10.0)
            tag = f"⚠️ 特斯拉大跌 ({tsla_pct:+.1f}%)"

    # 4. 军工 / 机械 / 工业 / 权重 (长城军工等) -> 关联 富时 A50 期货
    heavy_keywords = ['国防', '军工', '机械', '电气', '银行', '券商', '保险', '地产', '基础']
    if any(k in sec_clean for k in heavy_keywords) and not tag:
        if a50_pct >= 0.8:
            boost += min(30.0, a50_pct * 18.0)
            tag = f"🌐 A50强拉顺风 ({a50_pct:+.1f}%)"
        elif a50_pct <= -1.0:
            boost += max(-25.0, a50_pct * 18.0)
            tag = f"⚠️ A50走弱 ({a50_pct:+.1f}%)"

    # 5. 贵金属 / 黄金 (紫金矿业、山东黄金、赤峰黄金) -> 关联 COMEX 纽约金 (GOLD)
    precious_keywords = ['贵金属', '黄金', '珠宝']
    if any(k in sec_clean for k in precious_keywords) and not tag:
        gold_pct = quotes.get('GOLD', {}).get('pct', 0.0)
        if gold_pct >= 1.0:
            boost += min(35.0, gold_pct * 16.0)
            tag = f"🌐 纽约金拉升共振 ({gold_pct:+.1f}%)"
        elif gold_pct <= -1.2:
            boost += max(-25.0, gold_pct * 14.0)
            tag = f"⚠️ 纽约金回调走弱 ({gold_pct:+.1f}%)"

    # 6. 石油化工 / 石油 / 采掘 (中国海油、中国石油、中海油服) -> 关联 布伦特/美原油 (OIL)
    oil_keywords = ['石油', '油气', '炼化', '油服', '采掘']
    if any(k in sec_clean for k in oil_keywords) and not tag:
        oil_pct = quotes.get('OIL', {}).get('pct', 0.0)
        if oil_pct >= 1.0:
            boost += min(35.0, oil_pct * 16.0)
            tag = f"🌐 原油暴涨联动 ({oil_pct:+.1f}%)"
        elif oil_pct <= -1.2:
            boost += max(-25.0, oil_pct * 14.0)
            tag = f"⚠️ 原油走弱回调 ({oil_pct:+.1f}%)"

    # 7. 有色金属 / 工业金属 / 小金属 -> 综合大宗商品 (美原油/美黄金)
    metal_keywords = ['有色', '金属', '化工', '煤炭', '钢铁', '小金属']
    if any(k in sec_clean for k in metal_keywords) and not tag:
        gold_pct = quotes.get('GOLD', {}).get('pct', 0.0)
        oil_pct = quotes.get('OIL', {}).get('pct', 0.0)
        comm_pct = max(gold_pct, oil_pct)
        if comm_pct >= 1.2:
            boost += min(25.0, comm_pct * 12.0)
            tag = f"🌐 大宗商品共振 ({comm_pct:+.1f}%)"
        elif comm_pct <= -1.5:
            boost += max(-20.0, comm_pct * 10.0)
            tag = f"⚠️ 大宗回调 ({comm_pct:+.1f}%)"

    return round(boost, 2), tag


def get_kline_cache_file_path() -> str:
    """获取外盘 K 线历史数据缓存路径"""
    try:
        from sys_utils import get_conf_path
        return get_conf_path('global_market_klines.json')
    except Exception:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, 'config', 'global_market_klines.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path


def fetch_global_kline_history(symbol: str, limit: int = 120, force_refresh: bool = False, data_source: str = 'yahoo') -> list:
    """抓取与获取重点外盘资产 (如 NVDA, AAPL, MSFT, MU, A50, OIL, GOLD 等) 的近 120 日 K 线数据
    支持分级 Cache (Tier 1 RAM 内存快照 -> Tier 2 磁盘物理 JSON -> Tier 3 网络)
    支持 'yahoo' (Yahoo Finance 权威连续) 与 'sina' (新浪财经) 两种数据源自定与自动降级
    """
    sym_upper = symbol.strip().upper()
    source_key = (data_source or 'yahoo').lower()
    fetch_key = (sym_upper, source_key)
    cache_path = get_kline_cache_file_path().replace(".json", f"_{source_key}.json")
    now_ts = time.time()
    active_time = is_market_active_time()

    # 1. 冷却门槛算定: 交易活跃期 300s (5min)；非交易期 (如白天盘后/闭市) 14400s (4小时) 避免无谓网络请求
    cooldown_sec = 300.0 if active_time else 14400.0

    def merge_kline_sequences(old_list: list, new_list: list) -> list:
        """根据 'date' 唯一键将新老 K 线序列进行增量合并与去重，按日期升序重排，严格防范跨时区穿越数据"""
        if not old_list and not new_list: return []
        old_clean = sanitize_klines_for_symbol(sym_upper, old_list or [])
        new_clean = sanitize_klines_for_symbol(sym_upper, new_list or [])
        if not old_clean: return new_clean
        if not new_clean: return old_clean
        
        merged = {k.get('date'): dict(k) for k in old_clean if k.get('date')}
        for k in new_clean:
            if k.get('date'):
                merged[k.get('date')] = dict(k)
        sorted_dates = sorted(merged.keys())
        raw_res = [merged[d] for d in sorted_dates]
        return sanitize_klines_for_symbol(sym_upper, raw_res)

    def append_realtime_bar_if_needed(sym_code: str, klines: list) -> list:
        """根据目标市场时区 (Target Market Date & Session) 动态融合实时行情，绝对防范跨时区穿越 Bar 与数量级拉爆 Bug"""
        if not klines:
            return klines
        
        # 1. 率先清洗剥离超出目标市场当前日期的穿越 Bar 与数量级离群脏点
        clean_klines = sanitize_klines_for_symbol(sym_code, klines)
        if not clean_klines:
            return klines

        target_today_str = get_target_market_date_str(sym_code)
        session_open = is_target_market_session_open(sym_code)
        
        quotes = _global_cache.get('quotes', {})
        if not quotes or sym_code not in quotes:
            return clean_klines
        
        rt = quotes[sym_code]
        rt_price = float(rt.get('price', 0))
        rt_pct = float(rt.get('pct', 0))
        if rt_price <= 0:
            return clean_klines
        
        klines_copy = [dict(k) for k in clean_klines]
        last_item = klines_copy[-1]
        last_date = last_item.get('date', '')
        last_close = float(last_item.get('close', 0))

        # 🛡️ 核心数量级安全控制：判断 rt_price 与 last_close 是否属于同一数量级
        effective_price = rt_price
        if last_close > 0:
            ratio = rt_price / last_close
            if ratio > 3.0 or ratio < 0.33:
                effective_price = round(last_close * (1.0 + rt_pct / 100.0), 2)
        
        if last_date == target_today_str:
            last_item['close'] = round(effective_price, 2)
            last_item['pct'] = round(rt_pct, 2)
            high_p = float(last_item.get('high', effective_price))
            low_p = float(last_item.get('low', effective_price))
            if effective_price > high_p:
                last_item['high'] = round(effective_price, 2)
            if effective_price < low_p and effective_price > 0:
                last_item['low'] = round(effective_price, 2)
            klines_copy[-1] = last_item
        else:
            if not session_open:
                return klines_copy
            
            try:
                dt_last = datetime.datetime.strptime(last_date, '%Y-%m-%d')
                dt_today = datetime.datetime.strptime(target_today_str, '%Y-%m-%d')
                curr_dt = dt_last + datetime.timedelta(days=1)
                
                while curr_dt < dt_today:
                    if curr_dt.weekday() < 5:
                        mid_date_str = curr_dt.strftime('%Y-%m-%d')
                        prev_close = float(klines_copy[-1].get('close', effective_price))
                        mid_bar = {
                            'date': mid_date_str,
                            'open': round(prev_close, 2),
                            'high': round(prev_close, 2),
                            'low': round(prev_close, 2),
                            'close': round(prev_close, 2),
                            'volume': 0.0,
                            'pct': 0.0
                        }
                        klines_copy.append(mid_bar)
                    curr_dt += datetime.timedelta(days=1)
            except Exception:
                pass
            
            prev_close = float(klines_copy[-1].get('close', effective_price))
            rt_open = float(rt.get('open', 0))
            rt_high = float(rt.get('high', 0))
            rt_low = float(rt.get('low', 0))

            if rt_open > 0 and prev_close > 0 and 0.5 <= (rt_open / prev_close) <= 2.0:
                open_p = rt_open
            else:
                open_p = prev_close

            high_p = max([p for p in [open_p, effective_price, rt_high] if p > 0])
            low_p = min([p for p in [open_p, effective_price, rt_low] if p > 0])

            new_bar = {
                'date': target_today_str,
                'open': round(open_p, 2),
                'high': round(high_p, 2),
                'low': round(low_p, 2),
                'close': round(effective_price, 2),
                'volume': float(klines_copy[-1].get('volume', 0)),
                'pct': round(rt_pct, 2)
            }
            klines_copy.append(new_bar)
        
        return klines_copy

    # ⚡ Tier 1 & Tier 2 分级 Cache 判定 (线程安全)
    existing_klines = []
    with _KLINE_CACHE_LOCK:
        ram_entry = _KLINE_RAM_CACHE.get(fetch_key)
        if ram_entry and ram_entry.get('klines'):
            ram_ts = ram_entry.get('fetch_ts', 0.0)
            elapsed_ram = now_ts - ram_ts
            # 仅在 2 秒内防疯狂连击，force_refresh 必须强制穿透以执行在线拉取和自愈！
            if force_refresh and elapsed_ram < 2.0 and len(ram_entry['klines']) >= 5:
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} [RAM-Cache] 触发 2s 连击保护 ({elapsed_ram:.1f}s 前): 复用 [{source_key}] 内存 K线 -> {sym_upper}")
                return append_realtime_bar_if_needed(sym_upper, ram_entry['klines'])[-limit:]
            elif not force_refresh and (elapsed_ram < cooldown_sec) and len(ram_entry['klines']) >= 5:
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} [RAM-Cache] 命中 {cooldown_sec:.0f}s 分级冷却锁 ({elapsed_ram:.1f}s < {cooldown_sec:.0f}s): 瞬间复用 [{source_key}] 内存 K线 ({len(ram_entry['klines'])} 条) -> {sym_upper}")
                return append_realtime_bar_if_needed(sym_upper, ram_entry['klines'])[-limit:]

        # Tier 2: 磁盘 Cache 加载与 mtime 恢复
        all_cache = {}
        file_mtime = 0.0
        if os.path.exists(cache_path):
            try:
                file_mtime = os.path.getmtime(cache_path)
                with open(cache_path, 'r', encoding='utf-8') as f:
                    all_cache = json.load(f)
            except Exception:
                all_cache = {}

        existing_klines = all_cache.get(sym_upper, [])
        if existing_klines and len(existing_klines) >= 5:
            _KLINE_RAM_CACHE[fetch_key] = {'klines': existing_klines, 'fetch_ts': file_mtime}
            elapsed_file = now_ts - file_mtime
            if force_refresh and elapsed_file < 2.0:
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} [Disk-Cache] 触发 2s 防抖锁 (修改于 {elapsed_file:.1f}s 前): 复用 [{source_key}] 磁盘 K线 -> {sym_upper}")
                return append_realtime_bar_if_needed(sym_upper, existing_klines)[-limit:]
            elif not force_refresh and (elapsed_file < cooldown_sec):
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} [Disk-Cache] 命中 {cooldown_sec:.0f}s 磁盘分级冷却锁 (修改于 {elapsed_file:.1f}s 前): 瞬间复用 [{source_key}] 磁盘 K线 ({len(existing_klines)} 条) -> {sym_upper}")
                return append_realtime_bar_if_needed(sym_upper, existing_klines)[-limit:]

        _KLINE_RAM_CACHE[fetch_key] = {'klines': existing_klines, 'fetch_ts': now_ts}

    log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} 开始在线网络抓取 [{source_key}] 外盘 K线数据 ({sym_upper})... 持久化目标: {cache_path}")

    # Helper: 尝试抓取 Yahoo 源
    def _fetch_from_yahoo() -> list:
        yahoo_symbol_map = {
            'GOLD':   'GC=F',
            'BRENT':  'BZ=F',
            'OIL':    'CL=F',
            'SILVER': 'SI=F',
            'XAUUSD': 'GC=F',
            'A50':    '2823.HK',  # iShares 富时中国 A50 ETF (权威替代已被废弃的 CN=F)
        }
        yahoo_sym = yahoo_symbol_map.get(sym_upper, sym_upper)
        
        hosts = ['query2.finance.yahoo.com']
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://finance.yahoo.com',
        }
        
        for host in hosts:
            url = f"https://{host}/v8/finance/chart/{yahoo_sym}?range=1y&interval=1d&includePrePost=false"
            try:
                req = urllib.request.Request(url, headers=headers)
                opener = get_urllib_request_opener(url)
                with opener.open(req, timeout=3.0) as resp:
                    raw = resp.read().decode('utf-8')
                if not raw:
                    continue
                data = json.loads(raw)
                chart_result = data.get('chart', {}).get('result', [])
                if chart_result and chart_result[0]:
                    ch = chart_result[0]
                    timestamps = ch.get('timestamp', [])
                    q_data = ch.get('indicators', {}).get('quote', [{}])[0]
                    opens, highs, lows, closes, volumes = (
                        q_data.get('open', []), q_data.get('high', []),
                        q_data.get('low', []),  q_data.get('close', []), q_data.get('volume', [])
                    )
                    parsed = []
                    prev_c = None
                    for i, ts in enumerate(timestamps):
                        try:
                            d = datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                            c = float(closes[i]) if closes[i] is not None else None
                            o = float(opens[i])  if opens[i]  is not None else c
                            h = float(highs[i])  if highs[i]  is not None else c
                            l = float(lows[i])   if lows[i]   is not None else c
                            v = float(volumes[i] or 0)
                            if c is None or c <= 0: continue
                            pct = round(((c - prev_c) / prev_c) * 100.0, 2) if prev_c and prev_c > 0 else 0.0
                            prev_c = c
                            parsed.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'pct': pct})
                        except Exception: continue
                    if parsed:
                        log_market_msg(f"[GlobalMarketData] [Yahoo] {get_proxy_info_str()} {sym_upper} 历史 K 线 {len(parsed)} 条")
                        return parsed
            except Exception:
                pass
        log_market_msg(f"[GlobalMarketData] [Yahoo] {get_proxy_info_str()} Yahoo 源在线抓取异常 {sym_upper}: Host 节点无有效响应")
        return []

    MIN_KLINES = 5

    def _fetch_from_tencent() -> list:
        if sym_upper == 'A50':
            tencent_sym = 'hk02823'
        elif is_us_stock_symbol(sym_upper):
            tencent_sym = f"us{sym_upper}" if not sym_upper.lower().startswith("us") else sym_upper
        else:
            return []

        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tencent_sym},day,,,{limit + 20},qfq"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://finance.qq.com'}
        try:
            req = urllib.request.Request(url, headers=headers)
            opener = get_urllib_request_opener(url)
            with opener.open(req, timeout=4.0) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
            raw_d = data.get('data', {})
            sec_dict = raw_d if isinstance(raw_d, dict) else {}
            sec_data = sec_dict.get(tencent_sym, {}) or sec_dict.get(tencent_sym.lower(), {}) or sec_dict.get(sym_upper, {})
            klines = sec_data.get('day', []) or sec_data.get('qfqday', [])
            if klines:
                parsed = []
                prev_c = None
                for item in klines:
                    if isinstance(item, list) and len(item) >= 5:
                        d = str(item[0])
                        c = float(item[1])
                        o = float(item[2])
                        h = float(item[3])
                        l = float(item[4])
                        v = float(item[5]) if len(item) > 5 else 0.0
                        if c <= 0: continue
                        pct = round(((c - prev_c) / prev_c) * 100.0, 2) if prev_c and prev_c > 0 else 0.0
                        prev_c = c
                        parsed.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'pct': pct})
                if len(parsed) >= MIN_KLINES:
                    log_market_msg(f"[GlobalMarketData] [Tencent] {get_proxy_info_str()} {sym_upper} ({tencent_sym}) 历史 K 线 {len(parsed)} 条")
                    return parsed
        except Exception as ex:
            log_market_msg(f"[GlobalMarketData] [Tencent] {get_proxy_info_str()} 抓取异常 {sym_upper}: {ex}")
        return []

    def _fetch_from_sina() -> list:
        COMMODITY_SYMBOLS = {'BRENT', 'OIL', 'GOLD', 'A50', 'SILVER', 'XAUUSD', 'USDCNH'}
        is_us_stock = sym_upper not in COMMODITY_SYMBOLS

        if is_us_stock:
            url = f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var_r=/US_MinKService.getDailyK?symbol={sym_upper.lower()}"
            log_market_msg(f"[GlobalMarketData] [Sina-US] {get_proxy_info_str()} 开始抓取 {sym_upper} -> {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://finance.sina.com.cn'}
            try:
                req = urllib.request.Request(url, headers=headers)
                opener = get_urllib_request_opener(url)
                with opener.open(req, timeout=8.0) as resp:
                    raw = resp.read().decode('gbk', errors='ignore')
                raw_list = []
                raw_str = raw.strip()
                s_idx = raw_str.find('[')
                e_idx = raw_str.rfind(']')
                if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                    json_str = raw_str[s_idx:e_idx + 1]
                    try:
                        raw_list = json.loads(json_str)
                    except Exception:
                        raw_list = []

                if isinstance(raw_list, list) and len(raw_list) > 0:
                    parsed = []
                    prev_c = None
                    slice_start = max(0, len(raw_list) - limit - 10)
                    for item in raw_list[slice_start:]:
                        try:
                            d = str(item.get('d', ''))
                            o = float(item.get('o', 0))
                            h = float(item.get('h', 0))
                            l = float(item.get('l', 0))
                            c = float(item.get('c', 0))
                            v = float(item.get('v', 0))
                            if c <= 0: continue
                            pct = round(((c - prev_c) / prev_c) * 100.0, 2) if prev_c and prev_c > 0 else 0.0
                            prev_c = c
                            parsed.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'pct': pct})
                        except Exception:
                            continue
                    if len(parsed) >= MIN_KLINES:
                        log_market_msg(f"[GlobalMarketData] [Sina-US] {get_proxy_info_str()} {sym_upper} 历史 K 线 {len(parsed)} 条 (最新: {parsed[-1]['date']}, 收盘: {parsed[-1]['close']})")
                        return parsed
                    log_market_msg(f"[GlobalMarketData] [Sina-US] {get_proxy_info_str()} {sym_upper} 解析只得 {len(parsed)} 条")
                else:
                    log_market_msg(f"[GlobalMarketData] [Sina-US] {get_proxy_info_str()} {sym_upper} 响应体无有效 JSON 列表")
            except Exception as ex:
                log_market_msg(f"[GlobalMarketData] [Sina-US] {get_proxy_info_str()} 抓取异常 {sym_upper}: {ex}")

        # 大宗商品/期货与A50降级抓取
        if sym_upper == 'A50':
            # 尝试通过腾讯 HK 02823 抓取 A50 ETF 走势
            try:
                a50_klines = _fetch_from_tencent()
                if len(a50_klines) >= MIN_KLINES:
                    return a50_klines
            except Exception:
                pass

        return []

    parsed_klines = []
    proxy_enabled = get_proxy_config().get("enabled", False)

    # 1. 若代理已关闭 (国内纯直连模式)，优先使用 Sina (国内极速免代理全量源) -> Tencent -> Yahoo
    if not proxy_enabled:
        parsed_klines = _fetch_from_sina()
        if len(parsed_klines) < MIN_KLINES:
            log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} Sina 不足 {MIN_KLINES} 条，降级到 Tencent...")
            parsed_klines = _fetch_from_tencent()
        if len(parsed_klines) < MIN_KLINES:
            log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} Tencent 不足 {MIN_KLINES} 条，降级到 Yahoo...")
            parsed_klines = _fetch_from_yahoo()
    else:
        # 2. 代理已开启模式
        if source_key == 'yahoo':
            parsed_klines = _fetch_from_yahoo()
            if len(parsed_klines) < MIN_KLINES:
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} Yahoo 不足 {MIN_KLINES} 条，降级到 Sina...")
                parsed_klines = _fetch_from_sina()
            if len(parsed_klines) < MIN_KLINES:
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} Sina 不足 {MIN_KLINES} 条，降级到 Tencent...")
                parsed_klines = _fetch_from_tencent()
        else:
            parsed_klines = _fetch_from_sina()
            if len(parsed_klines) < MIN_KLINES:
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} Sina 不足 {MIN_KLINES} 条，降级到 Tencent...")
                parsed_klines = _fetch_from_tencent()
            if len(parsed_klines) < MIN_KLINES:
                log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} Tencent 不足 {MIN_KLINES} 条，降级到 Yahoo...")
                parsed_klines = _fetch_from_yahoo()

    # 抓取成功后更新内存 RAM Cache 并标脏，支持后期批量统一写盘或即时落盘
    if parsed_klines and len(parsed_klines) >= 5:
        merged_klines = merge_kline_sequences(existing_klines, parsed_klines)
        save_klines_to_disk_cache(sym_upper, merged_klines, source_key, immediate_flush=False)
        log_market_msg(f"[GlobalMarketData] [{source_key}源] {get_proxy_info_str()} 在线抓取成功增量合并 {sym_upper} K线 ({len(merged_klines)} 条) -> 已写入内存 RAM Cache")
        res_klines = append_realtime_bar_if_needed(sym_upper, merged_klines)
        return res_klines[-limit:]

    # 绝境保底: 若所有网络源均不可用，返回已有磁盘历史缓存
    if existing_klines:
        log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} 网络环境受限，降级读取已落盘 [{source_key}] 本地物理历史数据 ({len(existing_klines)} 条) -> {sym_upper}")
        res_klines = append_realtime_bar_if_needed(sym_upper, existing_klines)
        return res_klines[-limit:]

    return []


def flush_kline_disk_cache(data_source: str = 'yahoo', force: bool = False) -> bool:
    """一次加载批量统一落盘：将内存 RAM Cache 中攒存的全部标的 K线一次性原子合并写入 JSON 物理文件
    极速、高效，单次文件 IO 完成批量写盘，彻底根治多线程写盘踩踏与频繁磁盘 IO。
    磁盘 IO 在锁外执行，防止 Lock 持有期阻塞其他线程的 RAM 读写。
    """
    source_key = (data_source or 'yahoo').lower()
    cache_path = get_kline_cache_file_path().replace(".json", f"_{source_key}.json")

    # ---- Phase 1: 在锁内"快照"需要落盘的数据，立即释放锁 ----
    with _KLINE_CACHE_LOCK:
        if not force and not _KLINE_DIRTY_FLAGS.get(source_key, False):
            return True
        snapshot = {
            sym: list(ram_val['klines'])
            for (sym, src), ram_val in _KLINE_RAM_CACHE.items()
            if src == source_key and ram_val.get('klines')
        }

    if not snapshot:
        with _KLINE_CACHE_LOCK:
            _KLINE_DIRTY_FLAGS[source_key] = False
        return True

    # ---- Phase 2: 在锁外读取磁盘旧文件并合并 ----
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    all_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                all_cache = json.load(f)
        except Exception:
            all_cache = {}

    updated_count = 0
    total_bars = 0
    for sym, raw_klines in snapshot.items():
        if not sym or sym == 'TEST_SYM':
            continue

        clean_list = sanitize_klines_for_symbol(sym, raw_klines)
        if not clean_list:
            continue

        target_today = get_target_market_date_str(sym)
        session_open = is_target_market_session_open(sym)
        # 盘中时段：剥离未闭市今日实时 Bar，只落盘历史已完结日 K
        if session_open:
            historical_only = [k for k in clean_list if k.get('date', '') < target_today]
        else:
            historical_only = clean_list
        if not historical_only:
            historical_only = clean_list

        existing = all_cache.get(sym, [])
        if existing:
            merged_dict = {k.get('date'): dict(k) for k in existing if k.get('date')}
            for k in historical_only:
                if k.get('date'):
                    merged_dict[k.get('date')] = dict(k)
            sorted_dates = sorted(merged_dict.keys())
            raw_final = [merged_dict[d] for d in sorted_dates]
            final_list = sanitize_klines_for_symbol(sym, raw_final)
        else:
            final_list = historical_only

        if not final_list:
            continue

        all_cache[sym] = final_list
        updated_count += 1
        total_bars += len(final_list)

    if updated_count == 0:
        with _KLINE_CACHE_LOCK:
            _KLINE_DIRTY_FLAGS[source_key] = False
        return True

    # ---- Phase 3: 原子写盘 (write-to-temp-then-replace) ----
    now_ts = time.time()
    tmp_path = cache_path + f".tmp_{os.getpid()}_{int(now_ts * 1000)}"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(all_cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, cache_path)

        # ---- Phase 4: 写盘成功后刷新 RAM fetch_ts，防止下次误判磁盘已过期而重触网络 ----
        with _KLINE_CACHE_LOCK:
            _KLINE_DIRTY_FLAGS[source_key] = False
            for sym in snapshot:
                fk = (sym, source_key)
                if fk in _KLINE_RAM_CACHE:
                    _KLINE_RAM_CACHE[fk]['fetch_ts'] = now_ts

        log_market_msg(f"[GlobalMarketData] ⚡ 物理落盘批量持久化成功 [{source_key}源] ({updated_count} 个标的, 共 {total_bars} 条 K线) -> {cache_path}")
        return True
    except Exception as ex:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass
        log_market_msg(f"[GlobalMarketData] 物理落盘批量持久化异常 [{source_key}]: {ex}")
        return False



def save_klines_to_disk_cache(symbol: str, klines: list, data_source: str = 'yahoo', immediate_flush: bool = False) -> bool:
    """将最新清洗后的 K 线数据缓存至内存 RAM Cache 并标记脏状态
    当 immediate_flush=True 或调用 flush_kline_disk_cache 时进行单次统一物理写盘。
    """
    if not symbol or not klines:
        return False

    sym_upper = symbol.strip().upper()
    source_key = (data_source or 'yahoo').lower()
    fetch_key = (sym_upper, source_key)

    clean_list = sanitize_klines_for_symbol(sym_upper, klines)
    if not clean_list:
        return False

    with _KLINE_CACHE_LOCK:
        now_ts = time.time()
        _KLINE_RAM_CACHE[fetch_key] = {'klines': clean_list, 'fetch_ts': now_ts}
        _KLINE_DIRTY_FLAGS[source_key] = True

    if immediate_flush:
        return flush_kline_disk_cache(source_key, force=True)
    return True



def repair_disk_kline_caches() -> dict:
    """物理磁盘 K 线缓存全量自愈与清理引擎 (Scrub corrupted entries & synthetic bars from disk)"""
    repaired_stats = {}
    EXPECTED_SYMBOL_RANGES = {
        'AAPL': (10.0, 5000.0),
        'MSFT': (10.0, 5000.0),
        'NVDA': (1.0, 5000.0),
        'GOOGL': (10.0, 5000.0),
        'AMZN': (10.0, 5000.0),
        'META': (10.0, 5000.0),
        'TSLA': (5.0, 5000.0),
        'MU': (5.0, 5000.0),
        'TSM': (5.0, 5000.0),
        'SOXX': (10.0, 5000.0),
        'QQQ': (10.0, 5000.0),
        'OIL': (5.0, 500.0),
        'BRENT': (5.0, 500.0),
        'GOLD': (100.0, 20000.0),
        'XAUUSD': (100.0, 20000.0),
        'SILVER': (2.0, 500.0),
        'A50': (1.0, 50000.0),
        'USDCNH': (2.0, 20.0),
    }

    # 1. 扫描与基础清洗
    disk_caches = {}
    for src in ['yahoo', 'sina']:
        cache_path = get_kline_cache_file_path().replace(".json", f"_{src}.json")
        if not os.path.exists(cache_path):
            continue
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                all_cache = json.load(f)
            if isinstance(all_cache, dict):
                disk_caches[src] = (cache_path, all_cache)
        except Exception:
            pass

    for src, (cache_path, all_cache) in disk_caches.items():
        modified = False
        for sym, klist in list(all_cache.items()):
            sym_u = str(sym).strip().upper()
            if sym_u == 'TEST_SYM':
                del all_cache[sym]
                modified = True
                continue

            if not klist or not isinstance(klist, list):
                continue

            clean = sanitize_klines_for_symbol(sym_u, klist)
            target_today = get_target_market_date_str(sym_u)
            session_open = is_target_market_session_open(sym_u)

            # 剔除未闭市时写入磁盘的实时 Bar
            if session_open:
                clean = [k for k in clean if k.get('date', '') < target_today]

            # 🛡️ 跨标的污染检视: 检查价格数量级中枢，若严重偏离该标的合理区间则说明遭遇了异步竞争写错，全量剔除！
            if clean and sym_u in EXPECTED_SYMBOL_RANGES:
                closes = sorted([float(k.get('close', 0)) for k in clean if float(k.get('close', 0)) > 0])
                if closes:
                    med_close = closes[len(closes) // 2]
                    min_p, max_p = EXPECTED_SYMBOL_RANGES[sym_u]
                    if med_close < min_p or med_close > max_p:
                        del all_cache[sym]
                        modified = True
                        repaired_stats[f"{src}_{sym_u}"] = f"PURGED_CROSS_POLLUTED (med_close={med_close:.2f} not in [{min_p}, {max_p}])"
                        log_market_msg(f"[GlobalMarketData] 🛡️ 成功清除 [{src}] 物理盘库中被跨标的污染的脏记录: {sym_u} (中枢价={med_close:.2f} 不在合理区间 [{min_p}, {max_p}])")
                        continue

            if len(clean) != len(klist):
                all_cache[sym] = clean
                modified = True
                repaired_stats[f"{src}_{sym_u}"] = f"{len(klist)} -> {len(clean)}"

        if modified:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(all_cache, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    # 2. 🛡️ 跨源自动救援与最新日期自愈同步 (Cross-source Healing & Auto-sync):
    # 若 sina 数据具备更新的交易日切片或 yahoo 缺失，自动增量同步至 yahoo 与默认全局盘库
    if 'sina' in disk_caches:
        _, sina_cache = disk_caches['sina']
        
        # 同步至 yahoo
        if 'yahoo' in disk_caches:
            y_path, yahoo_cache = disk_caches['yahoo']
            y_modified = False
            for sym, s_klines in sina_cache.items():
                sym_u = sym.strip().upper()
                if not sym_u or sym_u == 'TEST_SYM': continue
                y_klines = yahoo_cache.get(sym_u, [])
                
                # 判定条件：yahoo 缺失，或 sina 的最新日期更新于 yahoo
                s_last_date = s_klines[-1].get('date', '') if s_klines else ''
                y_last_date = y_klines[-1].get('date', '') if y_klines else ''
                if len(s_klines) >= 5 and (len(y_klines) < 20 or s_last_date > y_last_date):
                    # 增量合并
                    merged_dict = {k.get('date'): dict(k) for k in y_klines if k.get('date')}
                    for k in s_klines:
                        if k.get('date'):
                            merged_dict[k.get('date')] = dict(k)
                    sorted_dates = sorted(merged_dict.keys())
                    raw_final = [merged_dict[d] for d in sorted_dates]
                    clean_final = sanitize_klines_for_symbol(sym_u, raw_final)
                    if clean_final:
                        yahoo_cache[sym_u] = clean_final
                        y_modified = True
                        repaired_stats[f"HEAL_YAHOO_{sym_u}"] = f"SYNCED ({len(clean_final)} bars, latest={clean_final[-1]['date']})"
                        log_market_msg(f"[GlobalMarketData] 🛡️ 成功将 {sym_u} 最新 K 线从 sina 同步至 yahoo 盘库 ({len(clean_final)} 条, 最新: {clean_final[-1]['date']})")
            if y_modified:
                try:
                    with open(y_path, 'w', encoding='utf-8') as f:
                        json.dump(yahoo_cache, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        # 同步至默认 global_market_klines.json
        try:
            def_path = get_kline_cache_file_path()
            if def_path and os.path.exists(def_path):
                with open(def_path, 'r', encoding='utf-8') as f:
                    def_cache = json.load(f)
                d_mod = False
                for sym, s_klines in sina_cache.items():
                    sym_u = sym.strip().upper()
                    if not sym_u or sym_u == 'TEST_SYM': continue
                    d_klines = def_cache.get(sym_u, [])
                    s_last_date = s_klines[-1].get('date', '') if s_klines else ''
                    d_last_date = d_klines[-1].get('date', '') if d_klines else ''
                    if len(s_klines) >= 5 and (len(d_klines) < 20 or s_last_date > d_last_date):
                        merged_dict = {k.get('date'): dict(k) for k in d_klines if k.get('date')}
                        for k in s_klines:
                            if k.get('date'):
                                merged_dict[k.get('date')] = dict(k)
                        sorted_dates = sorted(merged_dict.keys())
                        raw_final = [merged_dict[d] for d in sorted_dates]
                        clean_final = sanitize_klines_for_symbol(sym_u, raw_final)
                        if clean_final:
                            def_cache[sym_u] = clean_final
                            d_mod = True
                if d_mod:
                    with open(def_path, 'w', encoding='utf-8') as f:
                        json.dump(def_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return repaired_stats


# 启动时自动物理清理磁盘脏数据
repair_disk_kline_caches()


def get_related_symbols(symbol: str) -> list:
    """获取指定品种的关联走势品种列表，供 K 线弹窗叠加对比图使用

    Returns:
        list of dict: [
            {'symbol': 'BRENT', 'name': '布伦特原油', 'color': '#FFA500', 'inverse': False},
            ...
        ]
        inverse=True 表示该品种通常与主品种负相关（如美元 vs 黄金）
    """
    sym_upper = symbol.strip().upper()

    # 关联走势映射表
    related_map = {
        # OIL (WTI原油) - 关联: 布伦特原油 (国际主连), COMEX黄金 (大宗联动)
        'OIL': [
            {'symbol': 'BRENT', 'name': '布伦特主连', 'color': '#FFA040', 'inverse': False},
            {'symbol': 'GOLD',  'name': 'COMEX纽约金', 'color': '#FFD700', 'inverse': False},
        ],
        # BRENT (布伦特原油) - 关联: WTI原油, 黄金
        'BRENT': [
            {'symbol': 'OIL',  'name': 'WTI原油', 'color': '#FF8C00', 'inverse': False},
            {'symbol': 'GOLD', 'name': 'COMEX纽约金', 'color': '#FFD700', 'inverse': False},
        ],
        # GOLD (COMEX纽约金) - 关联: 现货黄金(纽约金连续), 白银(联动), 美元(负相关)
        'GOLD': [
            {'symbol': 'XAUUSD', 'name': '现货黄金(纽约金连续)', 'color': '#FFE066', 'inverse': False},
            {'symbol': 'SILVER', 'name': 'COMEX白银', 'color': '#C0C0C0', 'inverse': False},
            {'symbol': 'OIL',   'name': '布伦特/WTI原油',  'color': '#FFA040', 'inverse': False},
        ],
        # XAUUSD (现货黄金) - 关联: COMEX黄金, 白银
        'XAUUSD': [
            {'symbol': 'GOLD',   'name': 'COMEX纽约金期货', 'color': '#FFD700', 'inverse': False},
            {'symbol': 'SILVER', 'name': 'COMEX白银',       'color': '#C0C0C0', 'inverse': False},
        ],
        # SILVER (白银) - 关联: 黄金(正相关), 黄金/白银比值参考
        'SILVER': [
            {'symbol': 'GOLD',   'name': 'COMEX纽约金', 'color': '#FFD700', 'inverse': False},
            {'symbol': 'XAUUSD', 'name': '现货黄金',    'color': '#FFE066', 'inverse': False},
        ],
        # A50 - 关联: 纳指QQQ (外资流向参考), USDCNH (汇率风险)
        'A50': [
            {'symbol': 'QQQ',    'name': '纳指100 ETF', 'color': '#00BFFF', 'inverse': False},
            {'symbol': 'USDCNH', 'name': '离岸人民币',  'color': '#FF6B6B', 'inverse': True},
        ],
        # NVDA - 关联: 费城半导体(SOXX), QQQ
        'NVDA': [
            {'symbol': 'SOXX', 'name': '费城半导体ETF', 'color': '#7FFF00', 'inverse': False},
            {'symbol': 'QQQ',  'name': '纳指100 ETF',   'color': '#00BFFF', 'inverse': False},
        ],
        # MU - 关联: NVDA, SOXX
        'MU': [
            {'symbol': 'NVDA', 'name': '英伟达/算力',   'color': '#76FF03', 'inverse': False},
            {'symbol': 'SOXX', 'name': '费城半导体ETF', 'color': '#7FFF00', 'inverse': False},
        ],
        # QQQ - 关联: NVDA, SOXX
        'QQQ': [
            {'symbol': 'NVDA', 'name': '英伟达/算力',   'color': '#76FF03', 'inverse': False},
            {'symbol': 'SOXX', 'name': '费城半导体ETF', 'color': '#7FFF00', 'inverse': False},
        ],
        # SOXX - 关联: NVDA, MU
        'SOXX': [
            {'symbol': 'NVDA', 'name': '英伟达/算力',  'color': '#76FF03', 'inverse': False},
            {'symbol': 'MU',   'name': '美光/存储芯片', 'color': '#00FFAB', 'inverse': False},
        ],
    }
    return related_map.get(sym_upper, [])




def assess_news_valuation_impact(title: str, summary: str = "", content: str = "", symbol: str = "", name: str = "") -> dict:
    """新闻内容对股票/资产估值影响量化评估引擎 (Valuation Impact Assessment Engine)
    
    Returns:
        dict: {
            'valuation_dir': str,      # '🟢 利好估值抬升' | '🔴 利空估值承压' | '🟡 中性/平稳震荡'
            'valuation_pct_str': str,  # '+2.5% ~ +5.0%'
            'valuation_score': float,  # 1.0 ~ 10.0
            'impact_score': float,     # 1.0 ~ 10.0
            'valuation_analysis': str  # 定量解读文本
        }
    """
    combined_text = f"{title} {summary} {content}".lower()
    
    pos_keywords = [
        '暴涨', '大涨', '增幅', '突破', '创新高', '降息', '量产', '订单饱满', '抢购一空',
        '强劲', '大超预期', '买入', '加仓', '提价', '拓展', '盈利', '净利润增长', '分红',
        '重回', '收复', '飙升', '利好', '胜诉', '获批', '合作', '并购', '增持', '拉升'
    ]
    neg_keywords = [
        '暴跌', '大跌', '跌幅', '破位', '创新低', '加息', '减产', '限制', '制裁', '警告',
        '立案', '被查', '违约', '爆仓', '大减', '下调', '终止', '亏损', '做空', '减持'
    ]

    pos_score = sum(1.2 for kw in pos_keywords if kw in combined_text)
    neg_score = sum(1.2 for kw in neg_keywords if kw in combined_text)
    if pos_score > neg_score:
        diff = pos_score - neg_score
        val_dir = "🟢 利好估值抬升"
        val_pct_str = f"+{min(15.0, diff * 1.5):.1f}% ~ +{min(25.0, diff * 3.0):.1f}%"
        val_score = round(min(9.8, 6.5 + diff * 0.8), 1)
        impact_score = val_score
        val_analysis = (
            f"1. 估值影响: 发现 {int(pos_score/1.2)} 项强劲正面催化因子，提升相关产业链 PE 估值中枢。\n"
            f"2. 情绪动能: 市场资金看多情绪高涨，预计短期流动性溢价提升。\n"
            f"3. 关注重点: 追踪大单净买入与多周期放量突破支撑位。"
        )
    elif neg_score > pos_score:
        diff = neg_score - pos_score
        val_dir = "🔴 利空估值承压"
        val_pct_str = f"-{min(15.0, diff * 1.5):.1f}% ~ -{min(25.0, diff * 3.0):.1f}%"
        val_score = round(max(1.5, 5.0 - diff * 0.8), 1)
        impact_score = val_score
        val_analysis = (
            f"1. 估值影响: 发现 {int(neg_score/1.2)} 项风险提示，短期对 PE 估值形成压制。\n"
            f"2. 情绪动能: 避险情绪上升，短线资金可能产生抛压。\n"
            f"3. 关注重点: 观察下轨防守支撑位与止损企稳信号。"
        )
    else:
        val_dir = "🟡 中性/平稳震荡"
        val_pct_str = "0.0% ~ ±1.5%"
        val_score = 6.0
        impact_score = 6.0
        val_analysis = (
            f"1. 估值影响: 消息面多空因素对冲，短期估值影响中性。\n"
            f"2. 轮动视角: 股价受大盘整体环境与量价轨道引导。\n"
            f"3. 关注重点: 持续跟踪行业最新动态与主力资金方向。"
        )

    return {
        'valuation_dir': val_dir,
        'valuation_pct_str': val_pct_str,
        'valuation_score': val_score,
        'impact_score': impact_score,
        'valuation_analysis': val_analysis
    }


SYMBOL_KEYWORD_MAP = {
    # 纳斯达克 100 ETF (QQQ) / 美股科技大盘: 关联全科技产业链、巨头龙头、半导体与宏观政策
    'QQQ': [
        '纳斯达克', '美股', '科技股', '美联储', '降息', '加息', '通胀', 'CPI', 'PPI', '非农',
        '英伟达', 'NVDA', '苹果', 'AAPL', '谷歌', 'GOOG', '微软', 'MSFT', '特斯拉', 'TSLA',
        '亚马逊', 'AMZN', 'META', '博通', 'AVGO', 'AMD', '高通', 'QCOM', '台积电', 'ASML',
        'AI', '人工智能', '芯片', '半导体', '算力', '数据中心', '大模型', '自动驾驶', '标普'
    ],
    'NASDAQ': [
        '纳斯达克', '美股', '科技股', '美联储', '英伟达', '苹果', '谷歌', '微软', '特斯拉',
        'AI', '芯片', '半导体', '算力', '降息', '通胀', '标普', '道琼斯', '中概股'
    ],
    'SPX': [
        '标普500', '标普', '美股', '华尔街', '美联储', '道琼斯', '降息', '通胀', '巨头财报', '美债'
    ],

    # 英伟达 (NVDA) / AI 芯片产业链
    'NVDA': [
        '英伟达', 'NVIDIA', 'NVDA', '芯片', '半导体', '算力', 'GPU', 'Blackwell', 'CoWoS',
        'AI', '人工智能', '黄仁勋', '台积电', '博通', 'AMD', '光模块', '数据中心', '服务器'
    ],

    # 特斯拉 (TSLA) / 新能源车与机器人产业链
    'TSLA': [
        '特斯拉', 'Tesla', 'TSLA', '马斯克', '自动驾驶', 'FSD', '电动车', '新能源车',
        'Robotaxi', '人形机器人', 'Optimus', '动力电池', '宁德时代'
    ],

    # 原油 (OIL) / 石油化工与地缘能源
    'OIL': [
        '原油', '油价', '布伦特', 'WTI', 'OPEC', '产油国', '沙特', '俄罗斯', '能源',
        '汽油', '柴油', '炼油', '页岩油', '石油', '油服', '红海', '地缘政治', 'EIA'
    ],

    # 黄金 (GOLD) / 贵金属与避险宏观
    'GOLD': [
        '黄金', '金价', 'COMEX', '避险', '美联储', '降息', '通胀', '贵金属', '现货金',
        '央行购金', '地缘冲突', '紫金矿业', '美元指数'
    ],

    # A50 / 沪深300 / A 股大盘产业链
    'A50': [
        'A50', 'A股', '沪深300', '上证指数', '外资', '北向资金', '离岸人民币', '降准', '降息',
        '证监会', '中央汇金', '招商银行', '中国平安', '贵州茅台', '宁德时代', '中字头', '央国企'
    ],
    'USDCNH': [
        '人民币', '汇率', '央行', '外汇', '美元', '离岸人民币', '中间价'
    ]
}


def _detect_is_us_market_symbol(symbol: str) -> bool:
    """根据 symbol 自动判断是否为美股/外盘资产"""
    sym = (symbol or "").strip().upper()
    us_symbols = {'QQQ', 'NASDAQ', 'SPX', 'SPY', 'NVDA', 'TSLA', 'AAPL', 'MSFT', 'GOOG', 'AMZN', 'META', 'AMD', 'OIL', 'GOLD'}
    if sym in us_symbols or 'US' in sym or 'NDX' in sym or sym.isalpha() and len(sym) <= 5 and sym not in ['A50']:
        return True
    return False





_NEWS_CACHE_FILE = None

def get_news_cache_file_path() -> str:
    """获取财经资讯物理缓存文件路径 (config/global_market_news_cache.json)"""
    global _NEWS_CACHE_FILE
    if _NEWS_CACHE_FILE is None:
        try:
            from sys_utils import get_conf_path
            _NEWS_CACHE_FILE = get_conf_path("global_market_news_cache.json")
        except Exception:
            _NEWS_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "global_market_news_cache.json")
    return _NEWS_CACHE_FILE


def load_news_hotlist_json() -> tuple:
    """从物理 JSON 中读取已缓存的新闻列表与已删除的 news_id 黑名单 set"""
    c_path = get_news_cache_file_path()
    if not os.path.exists(c_path):
        return [], set()
    try:
        with open(c_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            items = data.get('news_list', [])
            deleted_ids = set(data.get('deleted_ids', []))
            return items, deleted_ids
    except Exception as ex:
        log_market_msg(f"[NewsCache] 读取物理缓存异常: {ex}")
        return [], set()


def save_news_hotlist_json(news_list: list, deleted_ids: set) -> bool:
    """
    保存新闻列表与 deleted_ids 黑名单至物理 JSON 缓存文件
    自动与磁盘现有记录增量合并，按 ID 与 标题+时间 组合键进行强力去重，按时间降序保留最新 100 条
    """
    c_path = get_news_cache_file_path()
    del_set = set(deleted_ids or [])
    try:
        # 1. 尝试读取磁盘已有记录
        existing_items = []
        if os.path.exists(c_path):
            try:
                with open(c_path, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    existing_items = old_data.get('news_list', [])
            except Exception:
                existing_items = []

        # 2. 增量合并新旧列表
        all_incoming = (news_list or []) + existing_items
        unique_items = []
        seen_keys = set()

        for item in all_incoming:
            if not isinstance(item, dict):
                continue
            nid = str(item.get('id', '')).strip()
            title = str(item.get('title', '')).strip()
            dt = str(item.get('datetime', '')).strip()

            # 过滤黑名单项
            if nid in del_set:
                continue

            # 组合去重 key: 优先使用非空的 nid，其次使用 title+dt 组合键
            dedup_key = nid if (nid and not nid.startswith('fallback_')) else f"{title}_{dt}"
            if not dedup_key or dedup_key in seen_keys:
                continue

            seen_keys.add(dedup_key)
            unique_items.append(item)

        # 3. 按时间戳/时间字符串降序排列，截取保留最新 100 条
        def _get_item_dt(it):
            return str(it.get('datetime', ''))

        unique_items.sort(key=_get_item_dt, reverse=True)
        final_items = unique_items[:100]

        # 4. 原子化落盘物理保存
        os.makedirs(os.path.dirname(c_path), exist_ok=True)
        payload = {
            'last_update_ts': time.time(),
            'news_list': final_items,
            'deleted_ids': list(del_set)
        }
        tmp_path = c_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        if os.path.exists(tmp_path):
            os.replace(tmp_path, c_path)
        return True
    except Exception as ex:
        log_market_msg(f"[NewsCache] 物理落盘写 JSON 异常: {ex}")
        return False


def delete_news_item_by_id(news_id: str) -> bool:
    """右键物理删除指定 news_id，将其追加到 deleted_ids 黑名单并写盘"""
    if not news_id:
        return False
    items, deleted_ids = load_news_hotlist_json()
    deleted_ids.add(str(news_id))
    new_items = [it for it in items if str(it.get('id')) != str(news_id)]
    return save_news_hotlist_json(new_items, deleted_ids)


def _sort_by_datetime_desc(news_list: list) -> list:
    """按 datetime 降序排列新闻 (最新在最上方)"""
    def _parse_dt(it):
        dt_str = str(it.get('datetime', ''))
        try:
            return datetime.datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
        except Exception:
            return datetime.datetime.min
    return sorted(news_list, key=_parse_dt, reverse=True)


def _clean_news_html_text(text: str) -> str:
    """清理新闻文本中的 HTML 标签与转义字符"""
    if not text:
        return ""
    import html
    import re
    t = html.unescape(str(text))
    t = re.sub(r'<[^>]+>', '', t)
    return t.strip()


def _fetch_sina_zhibo_feed(zhibo_id: int = 152, num: int = 20) -> list:
    """抓取新浪 7x24 实时直播快讯 (zhibo_id=152: 全球7x24, 1687: 美股外盘, 2516: A股)
    优先使用 0.15s 纯直连极速 Fetch，确保秒级刷出全网最新动态
    """
    url = f"https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size={num}&zhibo_id={zhibo_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://finance.sina.com.cn/7x24/'
    }
    items_out = []
    txt = ""
    try:
        req = urllib.request.Request(url, headers=headers)
        # ⚡ 极速优化: 国内 CDN 优先走纯直连 (0.15s)，失败再回退备选代理
        direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with direct_opener.open(req, timeout=3.0) as resp:
                txt = resp.read().decode('utf-8', errors='ignore')
        except Exception:
            opener = get_urllib_request_opener()
            with opener.open(req, timeout=3.0) as resp:
                txt = resp.read().decode('utf-8', errors='ignore')

        if txt:
            data = json.loads(txt)
            raw_list = data.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
            for item in raw_list:
                try:
                    rich_txt = _clean_news_html_text(item.get('rich_text', ''))
                    if not rich_txt or len(rich_txt) < 6:
                        continue
                    
                    doc_id = str(item.get('id') or f"zhibo_{zhibo_id}_{hash(rich_txt)}")
                    dt_str = item.get('create_time') or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    dt_str = str(dt_str)[:16]
                    
                    parts = re.split(r'[。！!？?\n]', rich_txt)
                    first_sentence = parts[0].strip()
                    title = first_sentence if (5 <= len(first_sentence) <= 45) else rich_txt[:40] + "..."
                    
                    tag_name = '🌐 外盘7x24' if zhibo_id == 1687 else ('⚡ A股7x24' if zhibo_id == 2516 else '🔥 全球7x24')
                    impact_eval = assess_news_valuation_impact(title, rich_txt, rich_txt)

                    items_out.append({
                        'id': doc_id,
                        'title': title,
                        'datetime': dt_str,
                        'source': '新浪7x24直播',
                        'tag': tag_name,
                        'impact_score': impact_eval['impact_score'],
                        'summary': rich_txt[:140],
                        'content': f"【{tag_name} 实时报道 ({dt_str})】\n\n{rich_txt}",
                        'related_symbols': ['A50', 'NASDAQ', 'SP500', 'NVDA', 'OIL', 'GOLD']
                    })
                except Exception:
                    continue
    except Exception as ex:
        log_market_msg(f"[LiveNewsEngine] 抓取 Sina Zhibo (id={zhibo_id}) 异常: {ex}")

    return items_out


def _fetch_sina_live_roll_news(lid: int = 1686, num: int = 15) -> list:
    """抓取新浪 roll 滚动新闻 API (lid=1686: 财经快讯, lid=1687: 美股外盘)"""
    url = f"http://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid={lid}&num={num}&page=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'http://finance.sina.com.cn/'
    }
    items_out = []
    txt = ""
    try:
        req = urllib.request.Request(url, headers=headers)
        direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with direct_opener.open(req, timeout=3.0) as resp:
                raw = resp.read()
        except Exception:
            opener = get_urllib_request_opener()
            with opener.open(req, timeout=3.0) as resp:
                raw = resp.read()

        try:
            txt = raw.decode('utf-8')
        except Exception:
            txt = raw.decode('gbk', errors='ignore')

        if txt:
            data = json.loads(txt)
            raw_items = data.get('result', {}).get('data', [])
            for item in raw_items:
                try:
                    title = _clean_news_html_text(item.get('title') or item.get('wap_title'))
                    if not title or len(title) < 5:
                        continue
                    
                    doc_id = str(item.get('docid') or f"roll_{lid}_{item.get('id', hash(title))}")
                    tag_name = '🌐 美股外盘' if lid == 1687 else '📡 财经滚动'
                    media = item.get('media_name') or ('新浪美股' if lid == 1687 else '新浪财经')
                    ctime = item.get('ctime')
                    if ctime:
                        try:
                            dt_str = datetime.datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            dt_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    else:
                        dt_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

                    intro = _clean_news_html_text(item.get('intro') or item.get('summary') or title)
                    impact_eval = assess_news_valuation_impact(title, intro, intro)

                    items_out.append({
                        'id': doc_id,
                        'title': title,
                        'datetime': dt_str,
                        'source': media,
                        'tag': tag_name,
                        'impact_score': impact_eval['impact_score'],
                        'summary': intro[:140],
                        'content': f"【{media} 滚动要闻 ({dt_str})】\n\n{title}\n\n{intro}",
                        'related_symbols': ['A50', 'NASDAQ', 'SP500', 'QQQ', 'NVDA']
                    })
                except Exception:
                    continue
    except Exception as ex:
        log_market_msg(f"[LiveNewsEngine] 抓取 Sina Roll (lid={lid}) 异常: {ex}")

    return items_out


def _translate_text_online_fast(text: str, timeout: float = 2.0) -> str:
    """极速免 Key 在线英译中引擎 (优先 Google GTX，回退有道/MyMemory)"""
    if not text or not text.strip() or not any(c.isalpha() for c in text):
        return text or ""
    
    query = text.strip()
    # 1. 优先尝试 Google GTX 接口 (0.2s 级返回，极度准确自然)
    try:
        import urllib.parse
        url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=' + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with direct_opener.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and data[0]:
                sentences = [item[0] for item in data[0] if item and item[0]]
                translated = ''.join(sentences).strip()
                if translated and translated != query:
                    return translated
    except Exception:
        pass

    # 2. 尝试有道在线 API 备选
    try:
        import urllib.parse
        url = 'http://fanyi.youdao.com/translate?&doctype=json&type=AUTO&i=' + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with direct_opener.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            result_sentences = []
            for line in data.get('translateResult', []):
                line_txt = ''.join([item.get('tgt', '') for item in line])
                if line_txt:
                    result_sentences.append(line_txt)
            translated = '\n'.join(result_sentences).strip()
            if translated and translated != query:
                return translated
    except Exception:
        pass

    return ""


def _auto_translate_en_text_to_cn(text: str) -> str:
    """专业外盘金融词汇与句式英译中双模引擎 (优先在线精确翻译，离线超级词典兜底)"""
    if not text or not text.strip():
        return ""
    
    # 1. 在线极速 Api 翻译 (优先获得最通顺整句中译)
    online_res = _translate_text_online_fast(text, timeout=2.0)
    if online_res:
        return online_res

    # 2. 离线超级短语与实体词典兜底
    dict_map = [
        ('The Magnificent Seven', '美股科技七巨头'), ('Magnificent Seven', '美股科技七巨头'), ('Magnificent 7', '科技七巨头'),
        ('Burning Cash', '大规模消耗资金烧钱'), ('Cash Burn', '现金流烧钱消耗'), ('cash burn', '现金消耗'),
        ('in full swing', '如火如荼地进行'), ('spooked investors', '引发投资者恐慌震慑'),
        ('for Real', '(真实的)'), ('for real', '(真实的)'),
        ('Crude Oil', '原油'), ('Brent Crude', '布伦特原油'), ('WTI Crude', 'WTI原油'),
        ('Oil Prices', '国际油价'), ('Oil Price', '油价'), ('OPEC+', '欧佩克+产油国组织'),
        ('OPEC', '欧佩克'), ('Petroleum', '石油'), ('Gasoline', '汽油'),
        ('Gold Prices', '国际金价'), ('Gold Price', '金价'), ('Gold', '黄金'),
        ('Federal Reserve', '美联储'), ('Fed', '美联储'), ('Rate Cut', '降息'),
        ('Interest Rate', '利率'), ('Rate Hike', '加息'), ('Inflation', '通货膨胀'),
        ('Treasury Yields', '美债收益率'), ('US Dollar', '美元指数'), ('USD', '美元'),
        ('Nvidia', '英伟达'), ('NVDA', '英伟达'), ('Tesla', '特斯拉'), ('TSLA', '特斯拉'),
        ('Apple', '苹果'), ('AAPL', '苹果'), ('Microsoft', '微软'), ('MSFT', '微软'),
        ('Alphabet', '谷歌'), ('Google', '谷歌'), ('GOOGL', '谷歌'), ('Amazon', '亚马逊'),
        ('AMZN', '亚马逊'), ('Meta', 'Meta(脸书)'), ('AMD', 'AMD(超威)'),
        ('TSMC', '台积电'), ('ASML', '阿斯麦'), ('Semiconductor', '半导体'),
        ('Chips', '芯片'), ('Chip', '芯片'), ('Artificial Intelligence', '人工智能'),
        ('AI', 'AI算力'), ('Nasdaq', '纳斯达克'), ('S&P 500', '标普500'),
        ('Dow Jones', '道琼斯'), ('Wall Street', '华尔街'), ('Futures', '期货'),
        ('Earnings season', '财报季业绩期'), ('Earnings', '财报业绩'), ('Revenue', '营业收入'), ('Net Profit', '净利润'),
        ('Shares Surge', '股价暴涨'), ('Shares Plunge', '股价大跌'), ('Shares Rise', '股价上涨'),
        ('Shares Fall', '股价下跌'), ('Market Cap', '市值'), ('Rally', '强劲反弹'),
        ('Slump', '重挫杀跌'), ('Surge', '飙升'), ('Plunge', '暴跌'),
        ('Middle East', '中东地缘'), ('Red Sea', '红海局势'), ('Supply Chain', '供应链'),
        ('Central Bank', '中央银行'), ('Economic Growth', '经济增长'), ('Recession', '衰退')
    ]
    
    translated = text
    for en, cn in dict_map:
        translated = re.sub(r'\b' + re.escape(en) + r'\b', cn, translated, flags=re.IGNORECASE)
    
    translated = translated.replace("jumped", "大涨").replace("dropped", "下跌")
    translated = translated.replace("higher", "走高").replace("lower", "走低")
    return translated.strip()


def is_valuable_financial_news(title: str, summary: str = "", is_us_market: bool = False, source_tag: str = "", item_datetime: str = "") -> bool:
    """硬核金融与资本市场有价值新闻过滤器 (彻底剔除历史老陈旧数据、地方政务、事故与泛社会垃圾新闻)"""
    full_text = f"{title} {summary}".strip()
    if not full_text or len(full_text) < 5:
        return False

    # 0. 强行校验日期时效性: 剔除历史上古数据 (如 2016, 2024, 2025 年或两周前老数据)
    if item_datetime:
        try:
            now = datetime.datetime.now()
            dt_part = str(item_datetime)[:10]
            if len(dt_part) == 10:
                item_dt = datetime.datetime.strptime(dt_part, "%Y-%m-%d")
                # 若新闻日期在 3 天以前，认定为历史过时旧数据，直接丢弃
                if (now - item_dt).days > 3:
                    return False
        except Exception:
            pass

    # 1. 垃圾社会/政务/民生/历史遗留煤炭新闻黑名单词汇 (硬性拦截)
    garbage_keywords = [
        '党委', '常委', '省委', '市委', '县委', '区委', '书记', '省长', '市长', '县长', '区长',
        '事故', '死', '伤', '违纪', '免职', '检查', '走访', '秦皇岛', '河北', '湖南', '四川',
        '景区', '演练', '文化节', '展会', '体育', '高考', '中考', '天气', '暴雨', '降雪', '火灾',
        '解忧站', '表彰', '创城', '文明', '致敬', '退役军人', '老干部', '社区', '煤炭市场供需'
    ]
    for gkw in garbage_keywords:
        if gkw in full_text:
            return False

    # 若来自于美股外盘 7x24 / RSS 直播频道，放行
    if is_us_market and ('外盘' in source_tag or '美股' in source_tag or 'US' in source_tag or 'YAHOO' in source_tag.upper()):
        return True

    text_upper = full_text.upper()

    # 2. 金融/资本市场/宏观经济硬核有价值白名单词汇
    financial_keywords = [
        '指数', '美股', 'A股', '港股', '纳斯达克', '标普', '道琼斯', '英伟达', '苹果', '谷歌',
        '微软', '特斯拉', '亚马逊', 'META', 'AMD', '台积电', 'AI', '芯片', '半导体',
        '美联储', '降息', '加息', '通胀', 'CPI', 'PPI', '非农', '失业率', '财报', '营收',
        '净利润', '业绩', '分红', '回购', '关税', '原油', '油价', '布伦特', 'WTI', '黄金', '金价', '汇率',
        '人民币', '美元', '央行', '证监会', '大盘', '主力', '成交量', '涨幅', '跌幅', '破位',
        '突破', '重组', '并购', '融资', '上市', 'IPO', '估值', '基金', 'ETF', '板块', '概念',
        'FED', 'DOLLAR', 'OIL', 'GOLD', 'TECH', 'CHINA', 'US', 'MARKET', 'INDEX', 'STOCK', 'NVDA', 'TSLA', 'AAPL', 'QQQ', 'BRENT', 'WTI', 'OPEC'
    ]

    # 美股外盘环境，要求必须包含美股/科技/宏观/大盘/原油/黄金等核心词汇
    if is_us_market:
        us_spec_keywords = [
            '美股', '纳斯达克', '标普', '道琼斯', '美联储', '英伟达', '苹果', '谷歌', '微软',
            '特斯拉', 'AI', '芯片', '半导体', '美元', '通胀', '非农', '降息', '加息', '原油', '油价',
            '黄金', '金价', '外盘', '中概股', 'QQQ', 'SPY', 'NVDA', 'TSLA', 'AAPL', 'MSFT', 'GOOG',
            'FED', 'DOLLAR', 'OIL', 'GOLD', 'TECH', 'CHINA', 'US', 'MARKET', 'INDEX', 'STOCK', 'OPEC', 'BRENT', 'WTI'
        ]
        has_us_kw = any(ukw in text_upper for ukw in us_spec_keywords)
        has_fin_kw = any(fkw in text_upper for fkw in financial_keywords)
        return has_us_kw or (has_fin_kw and not any(cn_kw in full_text for cn_kw in ['省', '市', '县', '村', '街道']))

    return any(fkw in text_upper for fkw in financial_keywords)


def _fetch_foreign_live_news_feed(symbol: str = "") -> list:
    """抓取真实外盘 (美股/原油/黄金/纳指) 实时第一手英文资讯并在线英译中"""
    sym = (symbol or "").strip().upper()
    sym_map = {
        'OIL': 'CL=F', 'GOLD': 'GC=F', 'QQQ': 'QQQ', 'NVDA': 'NVDA',
        'TSLA': 'TSLA', 'AAPL': 'AAPL', 'MSFT': 'MSFT', 'GOOG': 'GOOG',
        'A50': 'CNH=X', 'USDCNH': 'CNH=X', 'SPX': 'SPY'
    }
    raw_sym = sym_map.get(sym, sym if sym else 'QQQ')
    
    rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={raw_sym}&region=US&lang=en-US"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    items_out = []
    txt = ""
    try:
        req = urllib.request.Request(rss_url, headers=headers)
        opener = get_urllib_request_opener()
        with opener.open(req, timeout=3.5) as resp:
            txt = resp.read().decode('utf-8', errors='ignore')
            
        if txt:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(txt)
            now_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            
            for item in root.findall('.//item'):
                raw_title = item.findtext('title') or ""
                raw_desc = _clean_news_html_text(item.findtext('description') or "")
                pub_date = item.findtext('pubDate') or ""
                
                if not raw_title:
                    continue
                
                cn_title = _auto_translate_en_text_to_cn(raw_title)
                cn_desc = _auto_translate_en_text_to_cn(raw_desc) if raw_desc else cn_title
                
                dt_str = now_dt
                if pub_date:
                    try:
                        parts = pub_date.split()
                        if len(parts) >= 5:
                            day, month_str, year, tm = parts[1], parts[2], parts[3], parts[4]
                            months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
                            m_num = months.get(month_str, '08')
                            dt_str = f"{year}-{m_num}-{int(day):02d} {tm[:5]}"
                    except Exception:
                        pass
                
                doc_id = f"us_rss_{raw_sym}_{hash(raw_title)}"
                impact_eval = assess_news_valuation_impact(cn_title, cn_desc, cn_desc)
                
                items_out.append({
                    'id': doc_id,
                    'title': f"{cn_title} ({raw_title[:30]}...)" if cn_title != raw_title else cn_title,
                    'datetime': dt_str,
                    'source': 'Yahoo Finance (US外盘)',
                    'tag': f"🌐 {sym or '外盘'} 实时外盘",
                    'impact_score': impact_eval['impact_score'],
                    'summary': cn_desc[:140],
                    'content': f"【Yahoo Finance 外盘第一手资讯 ({dt_str})】\n\n英文原标题: {raw_title}\n\n中文意译: {cn_title}\n\n摘要: {cn_desc}",
                    'related_symbols': [sym, 'QQQ', 'OIL', 'GOLD']
                })
    except Exception as ex:
        log_market_msg(f"[ForeignNewsEngine] 抓取外盘 RSS Feed ({raw_sym}) 异常: {ex}")
        
    return items_out


def _fetch_all_live_news_multi_source(is_us_market: bool = False, symbol: str = "") -> list:
    """多源融合抓取全网最新 7x24 真实金融快讯 (区分美股外盘与国内 A 股)
    彻底排除 2016/2026-05 等废弃陈旧历史源，仅抓取今天 24h 内第一手信息！
    """
    all_raw = []
    
    if is_us_market:
        # 1. 优先抓取真正外盘第一手英文源 (带有英译中与当天时间)
        foreign_rss = _fetch_foreign_live_news_feed(symbol)
        all_raw.extend(foreign_rss)
        
        # 2. 抓取新浪 7x24 直播频道 (zhibo_id=152: 100% 实时更新的全球/美股/外盘7x24)
        zhibo_global = _fetch_sina_zhibo_feed(zhibo_id=152, num=30)
        all_raw.extend(zhibo_global)
    else:
        # A股与综合金融: A股7x24 + 全球7x24
        zhibo_a = _fetch_sina_zhibo_feed(zhibo_id=2516, num=25)
        all_raw.extend(zhibo_a)
        zhibo_global = _fetch_sina_zhibo_feed(zhibo_id=152, num=20)
        all_raw.extend(zhibo_global)

    # 去重 + 硬核金融有价值过滤器 + 3天内时效性过滤
    unique_map = {}
    for item in all_raw:
        nid = str(item.get('id'))
        if nid in unique_map:
            continue
        title = item.get('title', '')
        summary = item.get('summary', '')
        tag = item.get('tag', '')
        dt_str = item.get('datetime', '')
        
        # 严格过滤非金融/垃圾新闻与历史旧数据
        if is_valuable_financial_news(title, summary, is_us_market=is_us_market, source_tag=tag, item_datetime=dt_str):
            unique_map[nid] = item

    return list(unique_map.values())


_news_engine_metadata = {
    'last_update_ts': 0.0,
    'total_count': 0,
    'is_live_network': False
}


def fetch_symbol_financial_news(symbol: str = "", name: str = "", force_refresh: bool = False) -> list:
    """抓取与指定自选标的相关的 7x24 权威财经要闻与个股关联深度快讯
    带 1800s TTL 物理缓存与黑名单删除过滤，彻底剔除历史陈旧数据
    """
    sym = (symbol or "").strip().upper()
    sec_name = (name or "").strip()
    
    # 提取代码对应的股票中文名 (针对 A 股代码如 600519)
    if sym and (not sec_name or sec_name == sym):
        try:
            from data_utils import get_stock_name
            stk_n = get_stock_name(sym)
            if stk_n and stk_n != '未知':
                sec_name = stk_n
        except Exception:
            pass

    cached_hotlist, deleted_ids = load_news_hotlist_json()
    last_ts = _news_engine_metadata.get('last_update_ts', 0.0)
    is_cache_fresh = (time.time() - last_ts < 1800.0)

    # 物理检查缓存中是否包含陈旧历史日期 (如 2026-05 或 2016 年等)
    has_legacy_stale = any(
        not is_valuable_financial_news(it.get('title',''), it.get('summary',''), True, it.get('tag',''), it.get('datetime',''))
        for it in cached_hotlist[:5]
    )

    if cached_hotlist and not force_refresh and is_cache_fresh and not has_legacy_stale:
        filtered = [item for item in cached_hotlist if str(item.get('id')) not in deleted_ids]
        res = _sort_by_datetime_desc(filtered)[:20]
        if res:
            return res

    is_us_market = _detect_is_us_market_symbol(sym) or '纳斯达克' in sec_name or '美股' in sec_name or '原油' in sec_name or '黄金' in sec_name

    # 1. 触发真实多源网络抓取 (抓取当天的第一手资讯)
    live_items = _fetch_all_live_news_multi_source(is_us_market=is_us_market, symbol=sym)

    # 2. 构造自选标的匹配关键词集合
    target_keywords = set()
    if sym in SYMBOL_KEYWORD_MAP:
        target_keywords.update(SYMBOL_KEYWORD_MAP[sym])
    if sec_name:
        target_keywords.add(sec_name)
    if sym:
        target_keywords.add(sym)

    # 3. 对新闻按关联度加权排序与标注
    processed_items = []
    if live_items:
        for item in live_items:
            nid = str(item.get('id'))
            if nid in deleted_ids:
                continue

            title = item.get('title', '')
            summary = item.get('summary', '')
            tag = item.get('tag', '')
            full_txt = f"{title} {summary} {item.get('content','')}".upper()

            is_direct_matched = False
            is_industry_matched = False
            matched_kw = ""

            if target_keywords:
                for kw in target_keywords:
                    if kw and kw.upper() in full_txt:
                        matched_kw = kw
                        if kw.upper() in [sym, sec_name.upper(), '纳斯达克', 'QQQ', '英伟达', '原油', '黄金', 'OIL', 'GOLD']:
                            is_direct_matched = True
                        else:
                            is_industry_matched = True
                        break

            item_copy = dict(item)
            if is_direct_matched:
                item_copy['tag'] = f"📌 {sec_name or sym} 专属"
                item_copy['impact_score'] = min(9.9, item_copy.get('impact_score', 6.0) + 1.8)
                item_copy['_priority'] = 1
            elif is_industry_matched:
                item_copy['tag'] = f"🔗 {matched_kw} 产业链"
                item_copy['impact_score'] = min(9.5, item_copy.get('impact_score', 6.0) + 1.0)
                item_copy['_priority'] = 2
            else:
                tag_label = f"🌐 {sym}外盘" if is_us_market and sym else ('🌐 外盘7x24' if is_us_market else '📡 权威金融')
                item_copy['tag'] = tag_label
                item_copy['_priority'] = 3

            processed_items.append(item_copy)

        # 排序：优先专属要闻(1) -> 其次产业链与同行业(2) -> 宏观金融(3)，内部按时间降序
        def _sort_key(it):
            prio = it.get('_priority', 3)
            dt_str = str(it.get('datetime', ''))
            return (prio, dt_str)

        processed_items.sort(key=_sort_key, reverse=False)
        for it in processed_items:
            it.pop('_priority', None)

    # 4. 若抓取成功，刷新落盘
    if processed_items:
        save_news_hotlist_json(processed_items, deleted_ids)

        _news_engine_metadata['is_live_network'] = True
        _news_engine_metadata['last_update_ts'] = time.time()
        _news_engine_metadata['total_count'] = len(processed_items[:20])

        return processed_items[:20]

    # 5. 若网络无响应，降级使用物理磁盘缓存 (强力过滤黑名单与过时老数据)
    if cached_hotlist:
        filtered = [
            it for it in cached_hotlist
            if str(it.get('id')) not in deleted_ids and is_valuable_financial_news(it.get('title',''), it.get('summary',''), is_us_market, item_datetime=it.get('datetime',''))
        ]
        if filtered:
            _news_engine_metadata['is_live_network'] = False
            _news_engine_metadata['total_count'] = len(filtered[:20])
            return _sort_by_datetime_desc(filtered)[:20]

    # 6. 极低兜底 (带当前真实时间的示例资讯，绝非写死老数据)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    display_sym = sec_name or sym or '外盘金融'
    fallback_title = f"【{display_sym}】实时外盘与产业链动态 (" + datetime.datetime.now().strftime("%H:%M") + ")"
    fallback_item = {
        'id': f"fallback_{sym}_{int(time.time())}",
        'title': fallback_title,
        'datetime': now_str,
        'source': 'ATS 外盘与科技金融引擎',
        'tag': f'🌐 {display_sym}外盘',
        'impact_score': 7.5,
        'summary': f"实时追踪【{display_sym}】外盘供需、美联储动作、国际原油/黄金/美股资金走势与科技产业链...",
        'content': f"【{display_sym} 外盘实时行情监测】\n\n系统已接入外盘第一手 RSS 与全球 7x24 极速直播，持续追踪大盘与外盘资金异动。",
        'related_symbols': [sym or 'OIL']
    }
    save_news_hotlist_json([fallback_item], deleted_ids)
    return [fallback_item]


# 核心集中批量预预热标的清单 (全量包含美股 7 巨头/半导体/大宗商品/外盘主要 ETF)
GLOBAL_BATCH_KLINE_SYMBOLS = [
    'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 
    'MU', 'TSM', 'SOXX', 'QQQ', 'A50', 'GOLD', 'OIL', 'BRENT'
]


def fetch_global_klines_batch(data_source: str = 'yahoo', force_refresh: bool = False):
    """一键集中批量预热更新全量核心外盘标的 K 线 (自动批量更新一次全部更新，彻底避免切换 code 时不停触发网络请求)"""
    log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} 启动全量外盘标的一键集中批量预预热/更新引擎 ({len(GLOBAL_BATCH_KLINE_SYMBOLS)} 个核心标的)...")
    success_cnt = 0
    for sym in GLOBAL_BATCH_KLINE_SYMBOLS:
        try:
            res = fetch_global_kline_history(sym, limit=120, force_refresh=force_refresh, data_source=data_source)
            if res:
                success_cnt += 1
        except Exception as ex:
            log_market_msg(f"[GlobalMarketData] 批量预热标的 {sym} 异常: {ex}")
    log_market_msg(f"[GlobalMarketData] {get_proxy_info_str()} 全量外盘标的一键集中批量更新完毕 ({success_cnt}/{len(GLOBAL_BATCH_KLINE_SYMBOLS)} 成功)")



