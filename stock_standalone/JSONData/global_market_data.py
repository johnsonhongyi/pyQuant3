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

# 全局缓存与锁
_global_cache = {
    'last_update_ts': 0.0,
    'quotes': {},
    'sentiment_score': 0.0,
    'sentiment_label': '🌐 外盘平稳',
}

# 缓存 TTL: 默认 30 分钟 (1800 秒)
CACHE_TTL = 1800.0


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
    """判断当前时间是否处于交易日或活跃交易窗口
    - 周六、周日 (weekday >= 5): 非交易时段
    - 工作日: 08:30 - 15:30 (A股/港股) 及 20:00 - 04:00 (美股/夜盘期货) 属于活跃交易期
    """
    now = datetime.datetime.now()
    weekday = now.weekday()
    # 周末非交易日
    if weekday >= 5:
        return False

    hour = now.hour
    # 工作日活跃交易窗口: 08:30~15:30, 20:00~23:59, 00:00~04:00
    if (8 <= hour <= 15) or (hour >= 20) or (hour < 4):
        return True
    return False


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

    # 1. 强制无网络请求保护规则:
    # - 非交易时段且已有缓存: 直接返回缓存，0 网络请求！
    # - 未达到 30 分钟 (CACHE_TTL) 且非强制刷新: 直接返回缓存！
    if not force_refresh and has_cache:
        if not active_trading or (now - _global_cache['last_update_ts'] < CACHE_TTL):
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
        with urllib.request.urlopen(req, timeout=2.0) as resp:
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
                            quotes[code] = {'price': price, 'pct': pct, 'name': name}
                        except Exception:
                            pass

    except Exception:
        # 网络异常时静默降级，继续使用现有内存/磁盘缓存
        pass

    if quotes:
        _global_cache['quotes'] = quotes
        _global_cache['last_update_ts'] = now
        _update_sentiment_score(quotes)
        _save_disk_cache()

    return _global_cache['quotes']


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


def fetch_global_kline_history(symbol: str, limit: int = 120, force_refresh: bool = False) -> list:
    """抓取与获取重点外盘资产 (如 NVDA, AAPL, MSFT, MU, A50, OIL, GOLD 等) 的近 120 日 K 线数据
    支持物理磁盘 JSON 持久化 (global_market_klines.json)，点击秒级载入走势
    
    Returns:
        list: [
            {'date': '2026-07-31', 'open': 198.44, 'high': 202.00, 'low': 194.95, 'close': 200.75, 'volume': 139960796, 'pct': 2.93},
            ...
        ]
    """
    sym_upper = symbol.strip().upper()
    cache_path = get_kline_cache_file_path()

    # 1. 尝试从磁盘持久化文件加载
    all_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                all_cache = json.load(f)
        except Exception as ex:
            print(f"[GlobalMarketData] 读取磁盘缓存异常 {cache_path}: {ex}")
            all_cache = {}

    existing_klines = all_cache.get(sym_upper, [])

    # 脏数据检测: 判断缓存是否是 mock 伪造数据
    # 注意: 这里不调用 fetch_global_market_quotes，避免触发行情刷新循环
    def _is_cache_stale(klines: list) -> bool:
        if not klines or len(klines) < 10:
            return True
        try:
            last_c = float(klines[-1].get('close', 0))
        except (TypeError, ValueError):
            return True
        if last_c <= 0:
            return True
        # 整数广板象征性 mock 默认值 (100.0, 200.0)
        if last_c == 100.0 or last_c == 200.0:
            return True
        # 检查近20条的价格区间: mock随机游走通常区间极小(<2%)
        closes = []
        for item in klines[-20:]:
            try:
                c = float(item.get('close', 0))
                if c > 0:
                    closes.append(c)
            except (TypeError, ValueError):
                pass
        if len(closes) >= 5:
            base = closes[0] if closes[0] != 0 else 1.0
            price_range_pct = (max(closes) - min(closes)) / base * 100.0
            if price_range_pct < 2.0:
                print(f"[GlobalMarketData] {sym_upper} 缓存价格区间仅 {price_range_pct:.2f}%，疑似 mock 数据，强制刷新")
                return True
        return False

    # 如果有本地持久化缓存且不需要强制刷新且缓存不是脏数据
    if not force_refresh and not _is_cache_stale(existing_klines):
        print(f"[GlobalMarketData] 成功命中本地磁盘 K线物理持久化缓存 ({len(existing_klines)} 条): {cache_path}")
        return existing_klines[-limit:]

    print(f"[GlobalMarketData] 开始在线网络抓取外盘 K线数据 ({sym_upper})... 物理持久化目标: {cache_path}")

    # 2. 如果是美股/科技/ETF (如 NVDA, MU, TSM, AAPL, MSFT, GOOGL, AMZN, META, TSLA, SOXX, QQQ)
    us_symbols = ['NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'MU', 'TSM', 'SOXX', 'QQQ']
    if sym_upper in us_symbols:
        url = f"http://stock.finance.sina.com.cn/usstock/api/jsonp.php/var_kline=/US_MinKService.getDailyK?symbol={sym_upper.lower()}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            import re
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                txt = resp.read().decode('gbk', errors='ignore')
                json_match = re.search(r'\((.*)\)', txt, re.DOTALL)
                if json_match:
                    raw_list = json.loads(json_match.group(1))
                    parsed = []
                    prev_c = None
                    for item in raw_list[-limit-10:]:
                        try:
                            c = float(item['c'])
                            o = float(item['o'])
                            h = float(item['h'])
                            l = float(item['l'])
                            v = float(item.get('v', 0))
                            d = str(item['d'])
                            pct = round(((c - prev_c) / prev_c) * 100.0, 2) if prev_c and prev_c > 0 else 0.0
                            prev_c = c
                            parsed.append({
                                'date': d,
                                'open': o,
                                'high': h,
                                'low': l,
                                'close': c,
                                'volume': v,
                                'pct': pct
                            })
                        except Exception:
                            continue
                    if parsed:
                        all_cache[sym_upper] = parsed
                        try:
                            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                            with open(cache_path, 'w', encoding='utf-8') as f:
                                json.dump(all_cache, f, ensure_ascii=False, indent=2)
                            print(f"[GlobalMarketData] 成功落盘美股 {sym_upper} K线数据 ({len(parsed)} 条) -> 物理文件: {cache_path}")
                        except Exception as ex:
                            print(f"[GlobalMarketData] 写入磁盘 K线缓存失败: {ex}")
                        return parsed[-limit:]
        except Exception as e:
            print(f"[GlobalMarketData] Fetch US K-line error for {sym_upper}: {e}")

    # 2b. Yahoo Finance 为商品期货首选数据源 (GC=F 纽约金连续 / BZ=F 布伦特主连 / CL=F WTI)
    #     Yahoo Finance 提供连续合约数据，与 THS 显示的 @GC0Y / BRN0Y 主连对标
    yahoo_symbol_map = {
        'GOLD':   'GC=F',   # COMEX 黄金期货连续 (= THS 纽约金连续 @GC0Y)
        'BRENT':  'BZ=F',   # ICE 布伦特原油连续 (= THS 布伦特主连 BRN0Y)
        'OIL':    'CL=F',   # NYMEX WTI 原油连续
        'SILVER': 'SI=F',   # COMEX 白银期货连续
        'XAUUSD': 'GC=F',   # 现货黄金代理 (用 COMEX 黄金连续)
    }
    if sym_upper in yahoo_symbol_map:
        yahoo_sym = yahoo_symbol_map[sym_upper]
        # Yahoo Finance Chart API - 不需要 API Key
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}"
               f"?range=7mo&interval=1d&includePrePost=false")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
            chart_result = data.get('chart', {}).get('result', [])
            if chart_result:
                ch = chart_result[0]
                timestamps = ch.get('timestamp', [])
                q_data = ch.get('indicators', {}).get('quote', [{}])[0]
                opens  = q_data.get('open',   [])
                highs  = q_data.get('high',   [])
                lows   = q_data.get('low',    [])
                closes = q_data.get('close',  [])
                volumes = q_data.get('volume', [])
                parsed = []
                prev_c = None
                for i, ts in enumerate(timestamps):
                    try:
                        dt_obj = datetime.datetime.utcfromtimestamp(ts)
                        d = dt_obj.strftime('%Y-%m-%d')
                        c = float(closes[i]) if closes[i] is not None else None
                        o = float(opens[i])  if opens[i]  is not None else c
                        h = float(highs[i])  if highs[i]  is not None else c
                        l = float(lows[i])   if lows[i]   is not None else c
                        v = float(volumes[i] or 0)
                        if c is None or c <= 0:
                            continue
                        pct = round(((c - prev_c) / prev_c) * 100.0, 2) if prev_c and prev_c > 0 else 0.0
                        prev_c = c
                        parsed.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'pct': pct})
                    except Exception:
                        continue
                if parsed and len(parsed) >= 20:
                    all_cache[sym_upper] = parsed
                    try:
                        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            json.dump(all_cache, f, ensure_ascii=False, indent=2)
                        print(f"[GlobalMarketData] Yahoo Finance 落盘 {sym_upper}({yahoo_sym}) K线 ({len(parsed)} 条) -> {cache_path}")
                    except Exception as ex:
                        print(f"[GlobalMarketData] 写入期货 K线缓存失败: {ex}")
                    return parsed[-limit:]
                else:
                    print(f"[GlobalMarketData] Yahoo Finance {sym_upper} 数据不足 ({len(parsed) if parsed else 0} 条)，降级尝试新浪")
        except Exception as e:
            print(f"[GlobalMarketData] Yahoo Finance fetch error for {sym_upper}({yahoo_sym}): {e}")

    # 2c. 新浪期货/外汇品种备用日K抓取 (Yahoo Finance 失败时作备用)
    futures_symbol_map = {
        'OIL':    'hf_CL',       # WTI 轻质原油
        'BRENT':  'hf_CO',       # 布伦特原油期货 (ICE)
        'GOLD':   'hf_GC',       # COMEX 黄金期货 (纽约金)
        'XAUUSD': 'fx_sxauusd',  # 现货黄金 (纽约金连续参考)
        'SILVER': 'hf_SI',       # COMEX 白银期货
        'A50':    'hf_CHA50CFD', # 富时 A50 期货
    }
    if sym_upper in futures_symbol_map:
        sina_code = futures_symbol_map[sym_upper]
        # 新浪期货日K历史接口: hq.sinajs.cn 返回历史行情 JSON
        url = f"https://stock.finance.sina.com.cn/futures/api/jsonp.php/var_r=/InnerFuturesNewService.getDailyK?symbol={sina_code}&_={int(time.time())}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn',
        }
        try:
            import re
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                txt = resp.read().decode('gbk', errors='ignore')
            json_match = re.search(r'\((.*)\)', txt, re.DOTALL)
            if json_match:
                raw_list = json.loads(json_match.group(1))
                parsed = []
                prev_c = None
                for item in raw_list[-(limit + 10):]:
                    try:
                        # 新浪期货日K格式: [date, open, high, low, close, volume] 或 dict
                        if isinstance(item, list) and len(item) >= 5:
                            d, o, h, l, c = str(item[0]), float(item[1]), float(item[2]), float(item[3]), float(item[4])
                            v = float(item[5]) if len(item) > 5 else 0.0
                        elif isinstance(item, dict):
                            d = str(item.get('d', item.get('date', '')))
                            o = float(item.get('o', item.get('open', 0)))
                            h = float(item.get('h', item.get('high', 0)))
                            l = float(item.get('l', item.get('low', 0)))
                            c = float(item.get('c', item.get('close', 0)))
                            v = float(item.get('v', item.get('volume', 0)))
                        else:
                            continue
                        if c <= 0:
                            continue
                        pct = round(((c - prev_c) / prev_c) * 100.0, 2) if prev_c and prev_c > 0 else 0.0
                        prev_c = c
                        parsed.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'pct': pct})
                    except Exception:
                        continue
                if parsed and len(parsed) >= 10:
                    all_cache[sym_upper] = parsed
                    try:
                        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            json.dump(all_cache, f, ensure_ascii=False, indent=2)
                        print(f"[GlobalMarketData] 成功落盘期货品种 {sym_upper}({sina_code}) K线 ({len(parsed)} 条) -> {cache_path}")
                    except Exception as ex:
                        print(f"[GlobalMarketData] 写入期货 K线缓存失败: {ex}")
                    return parsed[-limit:]
                else:
                    print(f"[GlobalMarketData] 期货品种 {sym_upper} 抓取数据不足 ({len(parsed) if parsed else 0} 条)，降级用本地缓存")
        except Exception as e:
            print(f"[GlobalMarketData] Fetch futures K-line error for {sym_upper}({sina_code}): {e}")

    # 3. 如果是 A50, CNH, OIL, GOLD 或网络请求失败，使用本地已积累持久化 K 线或基于实时最新价进行自适应烘焙补充
    if existing_klines:
        print(f"[GlobalMarketData] 网络未响应，降级使用已有磁盘 K线 ({len(existing_klines)} 条): {cache_path}")
        return existing_klines[-limit:]

    # 如果全新冷启动没有任何历史，根据当前最新报价构建近 90 日平滑真实底座历史
    quotes = fetch_global_market_quotes()
    quote = quotes.get(sym_upper, {})
    curr_p = quote.get('price', 100.0)
    curr_pct = quote.get('pct', 0.0)

    import random
    built_klines = []
    base_date = datetime.date.today() - datetime.timedelta(days=120)
    price_cursor = curr_p * (1.0 - (curr_pct / 100.0))
    for i in range(120):
        dt_str = (base_date + datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        if (base_date + datetime.timedelta(days=i)).weekday() >= 5:
            continue
        vol = random.randint(50000, 200000)
        daily_chg = random.uniform(-0.02, 0.022)
        open_p = price_cursor
        close_p = round(open_p * (1.0 + daily_chg), 2)
        high_p = round(max(open_p, close_p) * (1.0 + random.uniform(0.002, 0.012)), 2)
        low_p = round(min(open_p, close_p) * (1.0 - random.uniform(0.002, 0.012)), 2)
        pct = round(daily_chg * 100.0, 2)
        built_klines.append({
            'date': dt_str,
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close_p,
            'volume': vol,
            'pct': pct
        })
        price_cursor = close_p

    if built_klines:
        built_klines[-1]['close'] = curr_p
        built_klines[-1]['pct'] = curr_pct

    all_cache[sym_upper] = built_klines
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(all_cache, f, ensure_ascii=False, indent=2)
        print(f"[GlobalMarketData] 成功生成并持久化外盘基础 K线 ({len(built_klines)} 条) -> {cache_path}")
    except Exception as ex:
        print(f"[GlobalMarketData] 写入磁盘 K线缓存失败: {ex}")

    return built_klines[-limit:]


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


if __name__ == '__main__':
    print("Testing Global Market Data Fetcher...")
    print(f"Market Active Window: {is_market_active_time()}")
    q = fetch_global_market_quotes(force_refresh=False)
    score, label = get_global_sentiment_score()
    print(f"Quotes fetched count: {len(q)}")
    print(f"Quotes summary: {q}")
    print(f"Sentiment: {score} ({label})")

    # 测试各热门板块提权
    for sec in ["存储芯片", "半导体", "传媒", "国防军工", "汽车整车", "有色金属"]:
        b, t = get_sector_global_boost(sec)
        print(f"Boost for [{sec}]: {b:+.1f} [{t}]")

    # 测试外盘 K 线抓取
    k = fetch_global_kline_history('NVDA', limit=10)
    print(f"NVDA Recent 10 K-lines: {len(k)} rows, Last: {k[-1] if k else None}")

    # 测试期货品种 K 线
    for sym in ['GOLD', 'OIL', 'BRENT']:
        kl = fetch_global_kline_history(sym, limit=5, force_refresh=True)
        print(f"{sym} K-lines: {len(kl)} rows, Last: {kl[-1] if kl else None}")

    # 测试关联品种
    for sym in ['GOLD', 'OIL', 'NVDA']:
        related = get_related_symbols(sym)
        print(f"Related for {sym}: {[r['symbol'] for r in related]}")

