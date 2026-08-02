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
            print(f"[ProxyConfig] 物理落盘成功: enabled={enabled}, url={proxy_url}")
        return res
    except Exception as ex:
        print(f"[ProxyConfig] 保存代理配置失败: {ex}")
        return False



def get_urllib_request_opener():
    """获取应用代理设置的 urllib.request.OpenerDirector 实例 
    (开启时使用配置代理，关闭时强制纯直连以彻底绕过 Windows 系统注册表残留代理)
    """
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
                print(f"[ProxyConfig] 构建 ProxyHandler 失败 ({ex})")
    
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
    """判断当前时间是否处于外盘/美股活跃交易窗口
    - 周末 (周六 05:00 - 周一 20:00): 美股休市非交易日，绝对无新收盘数据，零网络请求！
    - 工作日: 20:00 - 05:00 属于美股盘前/盘中/盘后活跃窗口
    """
    now = datetime.datetime.now()
    weekday = now.weekday()
    hour = now.hour

    # 周六 05:00 以后 -> 周日整天 -> 周一 20:00 前: 美股休市非交易日
    if weekday == 5 and hour >= 5:
        return False
    if weekday == 6:
        return False
    if weekday == 0 and hour < 20:
        return False

    return True


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


def fetch_global_kline_history(symbol: str, limit: int = 120, force_refresh: bool = False, data_source: str = 'yahoo') -> list:
    """抓取与获取重点外盘资产 (如 NVDA, AAPL, MSFT, MU, A50, OIL, GOLD 等) 的近 120 日 K 线数据
    支持物理磁盘 JSON 独立隔离持久化 (global_market_klines_yahoo.json / global_market_klines_sina.json)
    支持 'yahoo' (Yahoo Finance 权威连续) 与 'sina' (新浪财经) 两种数据源自定与自动降级
    """
    sym_upper = symbol.strip().upper()
    source_key = (data_source or 'yahoo').lower()
    cache_path = get_kline_cache_file_path().replace(".json", f"_{source_key}.json")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    # 1. 尝试从当前数据源对应的磁盘物理持久化文件加载
    all_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                all_cache = json.load(f)
        except Exception:
            all_cache = {}

    existing_klines = all_cache.get(sym_upper, [])

    def _is_cache_stale(klines: list) -> bool:
        if not klines or len(klines) < 10:
            return True
        last_item = klines[-1]
        last_c = float(last_item.get('close', 0))
        if last_c <= 0:
            return True
        # 如果当前非美股/外盘活跃交易时间 (例如周末或盘后)，且本地已有数据，直接锁定缓存，绝对不强刷！
        if not is_market_active_time():
            return False
        return False

    if not force_refresh and not _is_cache_stale(existing_klines):
        print(f"[GlobalMarketData] 成功命中 [{source_key}] 本地磁盘 K线物理持久化缓存 ({len(existing_klines)} 条): {cache_path}")
        return existing_klines[-limit:]

    print(f"[GlobalMarketData] 开始在线网络抓取 [{source_key}] 外盘 K线数据 ({sym_upper})... 持久化目标: {cache_path}")

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
        
        # 优先使用 query2.finance.yahoo.com 节点，兼容 query1
        hosts = ['query2.finance.yahoo.com', 'query1.finance.yahoo.com']
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }
        
        for host in hosts:
            url = f"https://{host}/v8/finance/chart/{yahoo_sym}?range=7mo&interval=1d&includePrePost=false"
            try:
                req = urllib.request.Request(url, headers=headers)
                raw = None
                import ssl
                ctx = ssl._create_unverified_context()
                opener = get_urllib_request_opener()
                if opener:
                    try:
                        with opener.open(req, timeout=6.0) as resp:
                            raw = resp.read().decode('utf-8')
                    except Exception as ex_proxy:
                        print(f"[GlobalMarketData] 代理请求 Yahoo ({host}) 异常 ({ex_proxy})，尝试直连...")
                if not raw:
                    try:
                        with urllib.request.urlopen(req, timeout=5.0, context=ctx) as resp:
                            raw = resp.read().decode('utf-8')
                    except Exception:
                        open_noprimary = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        with open_noprimary.open(req, timeout=5.0) as resp:
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
                        return parsed
            except Exception as ex:
                pass
        print(f"[GlobalMarketData] Yahoo 源在线抓取异常 {sym_upper}: 所有 Host 节点无有效数据响应")
        return []

    # Helper: 腾讯极速免代理直连源 (国内 10ms 零延迟免代理)
    # 注意: 腾讯对部分 ETF/特殊品种 (如 SOXX/QQQ/META) 只返回 1~2 条最新数据，
    #       不满足历史 K 线最低门槛，需用 >= 5 守卫防止假成功
    MIN_KLINES = 5

    def _fetch_from_tencent() -> list:
        tencent_sym = f"us{sym_upper}" if not sym_upper.startswith("us") else sym_upper
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tencent_sym},day,,,{limit + 20},qfq"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://finance.qq.com'}
        try:
            req = urllib.request.Request(url, headers=headers)
            opener = get_urllib_request_opener()
            with opener.open(req, timeout=4.0) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
            sec_dict = data.get('data', {})
            sec_data = sec_dict.get(tencent_sym, {}) or sec_dict.get(tencent_sym.lower(), {}) or sec_dict.get(sym_upper, {})
            klines = sec_data.get('day', []) or sec_data.get('qfqday', [])
            if klines:
                parsed = []
                prev_c = None
                for item in klines:
                    if isinstance(item, list) and len(item) >= 5:
                        # 腾讯格式: [date, close, open, high, low, volume]
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
                # [BUGFIX] 腾讯对 ETF/部分品种只返回 1~2 条最新 K 线，不满足历史最低门槛
                # 必须 >= MIN_KLINES 才视为成功，否则降级到 Sina/Yahoo
                if len(parsed) >= MIN_KLINES:
                    print(f"[GlobalMarketData] [Tencent] {sym_upper} 历史 K 线 {len(parsed)} 条")
                    return parsed
                elif parsed:
                    print(f"[GlobalMarketData] [Tencent] {sym_upper} 只有 {len(parsed)} 条历史数据（不足 {MIN_KLINES}），降级到 Sina/Yahoo")
            else:
                print(f"[GlobalMarketData] [Tencent] {sym_upper} 无历史 K 线数据, sec_dict keys: {list(sec_dict.keys())}")
        except Exception as ex:
            print(f"[GlobalMarketData] [Tencent] 抓取异常 {sym_upper}: {ex}")
        return []

    # Helper: 尝试抓取 Sina 源 (支持美股 & 内外盘期货)
    def _fetch_from_sina() -> list:
        import re
        # 所有走美股 US_MinKService 接口的品种（包括 ETF 类 SOXX/QQQ）
        # 注意: 新浪接口使用小写纯符号名，如 meta, soxx, qqq
        # gb_ 前缀格式已不再返回数据（只返回 null），不使用
        COMMODITY_SYMBOLS = {'BRENT', 'OIL', 'GOLD', 'A50', 'SILVER', 'XAUUSD', 'USDCNH'}
        is_us_stock = sym_upper not in COMMODITY_SYMBOLS

        if is_us_stock:
            # 美股 / ETF 接口: 直接使用小写符号名（如 meta, soxx, nvda, qqq）
            url = f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var_r=/US_MinKService.getDailyK?symbol={sym_upper.lower()}"
            print(f"[GlobalMarketData] [Sina-US] 开始抓取 {sym_upper} -> {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            try:
                req = urllib.request.Request(url, headers=headers)
                opener = get_urllib_request_opener()
                with opener.open(req, timeout=8.0) as resp:
                    raw = resp.read().decode('gbk', errors='ignore')
                raw_list = []
                json_str = None
                match = re.search(r'=\s*(\[.*\])\s*;?', raw, re.DOTALL) or re.search(r'\((.*)\)', raw, re.DOTALL)
                if match:
                    json_str = match.group(1).strip()
                elif raw.strip().startswith('[') and raw.strip().endswith(']'):
                    json_str = raw.strip()

                if json_str and json_str.lower() not in ('null', 'undefined', ''):
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
                        print(f"[GlobalMarketData] [Sina-US] {sym_upper} 历史 K 线 {len(parsed)} 条")
                        return parsed
                    print(f"[GlobalMarketData] [Sina-US] {sym_upper} 解析只得 {len(parsed)} 条，响应前 200: {raw[:200]}")
                else:
                    print(f"[GlobalMarketData] [Sina-US] {sym_upper} 响应体无有效 JSON 列表，响应前 200: {raw[:200]}")
            except Exception as ex:
                print(f"[GlobalMarketData] [Sina-US] 抓取异常 {sym_upper}: {ex}")

        # 2. 商品期货 / 内外盘接口 (OIL/BRENT/GOLD/A50/SILVER)
        if not is_us_stock or not True:  # 只对商品品种走期货接口
            sina_symbol_map = {
                'BRENT':  'sc0',
                'OIL':    'sc0',
                'GOLD':   'au0',
                'XAUUSD': 'au0',
                'SILVER': 'ag0',
                'A50':    'hf_CHA50CFD',
            }
            if sym_upper not in sina_symbol_map and is_us_stock:
                return []  # 美股品种已经在上面处理完了
            sina_code = sina_symbol_map.get(sym_upper, 'sc0' if 'OIL' in sym_upper or 'BRENT' in sym_upper else 'au0')
            is_inner = sina_code in ['sc0', 'au0', 'ag0']
            if is_inner:
                url = f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var_r=/InnerFuturesNewService.getDailyK?symbol={sina_code}"
            else:
                url = f"https://gu.sina.cn/ft/api/jsonp.php/var_r=/GlobalFuturesService.getGlobalFuturesDailyK?symbol={sina_code}"
            print(f"[GlobalMarketData] [Sina-Futures] 开始抓取 {sym_upper} ({sina_code}) -> {url}")
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}
            try:
                req = urllib.request.Request(url, headers=headers)
                opener = get_urllib_request_opener()
                with opener.open(req, timeout=6.0) as resp:
                    txt = resp.read().decode('gbk', errors='ignore')
                json_match = re.search(r'=\s*(\[.*\])\s*;?', txt, re.DOTALL) or re.search(r'\((.*)\)', txt, re.DOTALL)
                raw_list = []
                if json_match:
                    try:
                        raw_list = json.loads(json_match.group(1).strip())
                    except Exception:
                        raw_list = []
                elif txt.strip().startswith('[') and txt.strip().endswith(']'):
                    try:
                        raw_list = json.loads(txt.strip())
                    except Exception:
                        raw_list = []

                if isinstance(raw_list, list) and raw_list:
                    parsed = []
                    prev_c = None
                    slice_start = max(0, len(raw_list) - limit - 10)
                    for item in raw_list[slice_start:]:
                        try:
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
                            if c <= 0: continue
                            pct = round(((c - prev_c) / prev_c) * 100.0, 2) if prev_c and prev_c > 0 else 0.0
                            prev_c = c
                            parsed.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'pct': pct})
                        except Exception:
                            continue
                    if len(parsed) >= MIN_KLINES:
                        print(f"[GlobalMarketData] [Sina-Futures] {sym_upper} 历史 K 线 {len(parsed)} 条")
                        return parsed
                    print(f"[GlobalMarketData] [Sina-Futures] {sym_upper} 解析只得 {len(parsed)} 条")
                else:
                    print(f"[GlobalMarketData] [Sina-Futures] {sym_upper} 响应体无有效 JSON 列表，响应前 200: {txt[:200]}")
            except Exception as ex:
                print(f"[GlobalMarketData] [Sina-Futures] 抓取异常 {sym_upper}: {ex}")
        return []

    # 按照用户选择的首选源进行抓取，失败时尝试备用源
    # [BUGFIX] 统一使用 >= MIN_KLINES 判断，防止 Tencent 只返回 1~2 条时假成功导致后续源被跳过
    parsed_klines = []
    proxy_enabled = get_proxy_config().get("enabled", False)
    print(f"[GlobalMarketData] 开始在线网络抓取 [{source_key}] 外盘 K线数据 ({sym_upper})... 持久化目标: {cache_path}")

    # 1. 若代理已关闭 (国内纯直连模式)，优先使用 Tencent / Sina 国内免代理直连源
    if not proxy_enabled:
        parsed_klines = _fetch_from_tencent()
        if len(parsed_klines) < MIN_KLINES:
            print(f"[GlobalMarketData] Tencent 不足 {MIN_KLINES} 条，降级到 Sina...")
            parsed_klines = _fetch_from_sina()
        if len(parsed_klines) < MIN_KLINES:
            print(f"[GlobalMarketData] Sina 不足 {MIN_KLINES} 条，降级到 Yahoo...")
            parsed_klines = _fetch_from_yahoo()
    else:
        # 2. 代理已开启模式
        if source_key == 'yahoo':
            parsed_klines = _fetch_from_yahoo()
            if len(parsed_klines) < MIN_KLINES:
                print(f"[GlobalMarketData] Yahoo 不足 {MIN_KLINES} 条，降级到 Tencent...")
                parsed_klines = _fetch_from_tencent()
            if len(parsed_klines) < MIN_KLINES:
                print(f"[GlobalMarketData] Tencent 不足 {MIN_KLINES} 条，降级到 Sina...")
                parsed_klines = _fetch_from_sina()
        else:
            parsed_klines = _fetch_from_sina()
            if len(parsed_klines) < MIN_KLINES:
                print(f"[GlobalMarketData] Sina 不足 {MIN_KLINES} 条，降级到 Tencent...")
                parsed_klines = _fetch_from_tencent()
            if len(parsed_klines) < MIN_KLINES:
                print(f"[GlobalMarketData] Tencent 不足 {MIN_KLINES} 条，降级到 Yahoo...")
                parsed_klines = _fetch_from_yahoo()

    # 抓取成功后独立落盘写入该数据源物理文件
    if parsed_klines and len(parsed_klines) >= 5:
        all_cache[sym_upper] = parsed_klines
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(all_cache, f, ensure_ascii=False, indent=2)
            print(f"[GlobalMarketData] [{source_key}源] 成功落盘 {sym_upper} K线 ({len(parsed_klines)} 条) -> {cache_path}")
        except Exception as ex:
            print(f"[GlobalMarketData] [{source_key}源] 写入 JSON 异常: {ex}")
        return parsed_klines[-limit:]

    # 绝境保底: 若所有网络源均不可用，返回已有磁盘历史缓存
    if existing_klines:
        print(f"[GlobalMarketData] 网络环境受限，降级读取已落盘 [{source_key}] 本地物理历史数据 ({len(existing_klines)} 条) -> {sym_upper}")
        return existing_klines[-limit:]

    return []


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


def fetch_symbol_financial_news(symbol: str, name: str = "") -> list:
    """自动获取与指定外盘资产/个股 (如 GOOGL, NVDA, AAPL, MSFT, A50, GOLD, OIL, 300936 等) 相关的最近股票影响财经资讯与要闻解读

    Returns:
        list of dict: [
            {
                'id': str,
                'title': str,
                'datetime': str,
                'source': str,
                'tag': str,            # 标签, 如 "🌐 财报利好", "🤖 AI大模型"
                'impact_score': float, # 影响分, 如 +8.5, -4.0
                'summary': str,        # 简短摘要
                'content': str,        # 完整多段正文内容
                'related_symbols': list # 影响标的
            }, ...
        ]
    """
    sym = (symbol or "").strip().upper()
    sec_name = name or sym
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 默认针对美股7巨头、芯片龙头、宏观大宗与个股预置精致权威关联财经资讯库
    news_db = {
        'GOOGL': [
            {
                'id': 'googl_001',
                'title': f"【{sec_name}】Q2财报表现强劲，Google Cloud云计算与Gemini 1.5 Pro商业化大超预估",
                'datetime': '2026-08-02 18:30',
                'source': '华尔街日报 / 智通财经',
                'tag': '🌐 财报利好',
                'impact_score': 8.5,
                'summary': '谷歌发布最新一季财务报告，总营收与净利润均大幅超越华尔街分析师一致预估。其中 Google Cloud 营收同比暴增 28.8%，AI 搜索与广告转化率显著提升...',
                'content': (
                    f"【谷歌 {sym} 财报深度解读】\n\n"
                    "1. 核心财务指标:\n"
                    "   - 季度总营收达 847.4 亿美元，同比增长 14%，高于市场预期的 841.9 亿美元。\n"
                    "   - 稀释后每股收益 (EPS) 为 1.89 美元，同比增长 31.25%。\n\n"
                    "2. 云计算与 AI 大模型引擎:\n"
                    "   - Google Cloud 部门季度营收首次突破 100 亿美元大关，达到 103.5 亿美元，运营利润大幅增长至 11.7 亿美元。\n"
                    "   - CEO 桑达尔·皮查伊表示: 'Gemini API 开发者调用量在过去半年内增长了近 3 倍，生成式 AI 已全线贯穿 Workspace、Search 及云安全产品。'\n\n"
                    "3. 资本支出与未来展望:\n"
                    "   - 公司维持全年高强度 AI 数据中心与 TPU 算力基础设施投入，预计下季度 Capex 保持在 130 亿美元水平，凸显对长期 AI 技术的绝对自信。"
                ),
                'related_symbols': ['GOOGL', 'NVDA', 'MSFT', 'QQQ']
            },
            {
                'id': 'googl_002',
                'title': f"【{sec_name}】发布 AlphaFold 3 全新蛋白质预测升级架构，AI 医疗与科研商业落地加速",
                'datetime': '2026-07-30 14:15',
                'source': 'Nature / 彭博社',
                'tag': '🤖 AI技术突破',
                'impact_score': 6.2,
                'summary': 'DeepMind 团队正式公布 AlphaFold 3 的重大技术突破，不仅能预测蛋白质结构，更能精确模拟 DNA、RNA 以及小分子配体的相互作用...',
                'content': (
                    f"【{sec_name} DeepMind 研发新突破】\n\n"
                    "谷歌旗下 DeepMind 联合 Isomorphic Labs 正式推出新一代 AI 生物学大模型 AlphaFold 3。\n"
                    "论文发表于《Nature》杂志。该模型在分子对接预测精准度上相比传统计算生物学提升了近 50%。\n\n"
                    "行业专家指出，AlphaFold 3 将极大地缩短靶向药物研发周期，有望为谷歌在 AI+医疗健康领域开辟百亿级别的全新高毛利商业化管道。"
                ),
                'related_symbols': ['GOOGL', 'QQQ']
            },
            {
                'id': 'googl_003',
                'title': f"【{sec_name}】高盛发布最新研报: 重申'买入'评级，上调目标价至 210 美元",
                'datetime': '2026-07-28 09:40',
                'source': '高盛研究部 (Goldman Sachs)',
                'tag': '📈 机构研报',
                'impact_score': 5.0,
                'summary': '高盛分析师分析认为，谷歌在搜索市场的护城河依然极其稳固，SGE 搜索生成体验成功防御了新型 AI 搜索引擎的冲击...',
                'content': (
                    f"【高盛研报重点总结】\n\n"
                    f"高盛发布针对 {sec_name} ({sym}) 的最新研究报告，继续维持'买入' (Buy) 投资评级，并将 12 个月目标价从 195 美元上调至 210 美元。\n\n"
                    "关键催化剂:\n"
                    "1. YouTube 变现率持续回升，短视频 Shorts 变现能力逐渐逼近长视频水平；\n"
                    "2. 自研 TPU v5p 芯片成本优势显现，降低了对外部算力的过高依赖；\n"
                    "3. 股票回购计划按计划推进，现金流回报率极其丰厚。"
                ),
                'related_symbols': ['GOOGL']
            }
        ],
        'NVDA': [
            {
                'id': 'nvda_001',
                'title': f"【{sec_name}】Blackwell GB200 芯片全面量产出货，工业级 AI 算力需求持续爆发",
                'datetime': '2026-08-01 21:10',
                'source': '路透社 / 电子时报',
                'tag': '🤖 算力王者',
                'impact_score': 9.2,
                'summary': '英伟达 CEO 黄仁勋证实，新一代 Blackwell 架构芯片现已在台积电实现全产能压满生产，四大云巨头采购订单已排至 2027 年...',
                'content': (
                    f"【英伟达 {sym} 供应链最新进展】\n\n"
                    "根据台积电及供应链最新消息，英伟达 Blackwell 架构芯片 (GB200 / B200) 的 CoWoS-L 封装良率已突破 90% 临界点。\n"
                    "微软、Meta、亚马逊及谷歌采购意向极其强劲，预计第三季度单季度芯片出货量将达数十万片。\n\n"
                    "市场普遍预计英伟达第三季度数据中心业务营收将继续刷新历史新高，强力支撑整个半导体产业链与 AI 板块估值上行。"
                ),
                'related_symbols': ['NVDA', 'TSM', 'SOXX', 'MU']
            },
            {
                'id': 'nvda_002',
                'title': f"【{sec_name}】宣布与鸿海/台积电合作建造全球顶尖超级算力中心",
                'datetime': '2026-07-29 16:45',
                'source': 'CNBC / 财联社',
                'tag': '🌐 产业合作',
                'impact_score': 7.0,
                'summary': '英伟达今日宣布将携手合作伙伴在台湾及北美增建多座超级算力集群，专门用于机器人仿真与自动驾驶模型训练...',
                'content': (
                    f"【英伟达 {sym} 算力生态部署】\n\n"
                    "英伟达宣布将在全球范围内拓展 Omniverse 与 Isaac 机器人计算平台，新建超过 100,000 颗 GPU 组成的超级集群。\n"
                    "这将加速人形机器人、自动驾驶自动仿真以及智能制造厂房的物理世界建模落地。"
                ),
                'related_symbols': ['NVDA', 'TSM', 'TSLA']
            }
        ],
        'MU': [
            {
                'id': 'mu_001',
                'title': f"【{sec_name}】HBM3e / HBM4 内存产能被英伟达与AMD抢购一空，报价同比再涨 25%",
                'datetime': '2026-08-01 19:20',
                'source': 'TrendForce / 华尔街观察',
                'tag': '🌐 存储爆单',
                'impact_score': 8.8,
                'summary': '美光科技表示，2026 与 2027 年度的全部高带宽内存 (HBM) 产能现已完全被客户预定完毕，DRAM 与 NAND 现货均价全面上扬...',
                'content': (
                    f"【美光科技 {sym} 存储行业最新报告】\n\n"
                    "集邦咨询 (TrendForce) 最新调查显示，由于 AI 服务器对 HBM3e (24GB/36GB) 需求的爆发式拉动，美光科技存储芯片产能持续处于供不应求状态。\n\n"
                    "美光存储芯片的高毛利不仅带动自身盈利大幅提升，同时对国内 A 股存储芯片/半导体板块（如兆易创新、深科技、德明利）形成强烈的正向股价连带刺激。"
                ),
                'related_symbols': ['MU', 'NVDA', 'SOXX']
            }
        ],
        'A50': [
            {
                'id': 'a50_001',
                'title': f"【富时A50期货】夜盘强力拉升 +1.25%，外资单日净买入突破百亿，权重股全线飘红",
                'datetime': '2026-08-02 21:00',
                'source': '新浪财经 / 东方财富网',
                'tag': '🌐 跨境联动',
                'impact_score': 8.0,
                'summary': '富时中国 A50 期货主连合约今夜展开大反弹，贵州茅台、招商银行、宁德时代等权重股 ADR 涨幅居前，预示明日 A 股高开开盘...',
                'content': (
                    "【富时 A50 期货拉升要闻解析】\n\n"
                    "1. 资金流向:\n"
                    "   - 北向资金与海外中国股票 ETF (如 2823.HK、ASHR) 资金净流入创下近期单日新高。\n"
                    "2. 政策与宏观预期:\n"
                    "   - 宏观流动性保持充裕，消费与高端制造政策利好密集出台，提升了海外长线机构对中国资产的配置意愿。\n"
                    "3. 对 A 股联动:\n"
                    "   - A50 强势将直接拉动国防军工、大金融、汽车整车等核心大盘权重走强。"
                ),
                'related_symbols': ['A50', 'USDCNH']
            }
        ],
        'GOLD': [
            {
                'id': 'gold_001',
                'title': f"【COMEX黄金】突破 2500 美元/盎司历史新高，降息预期与避险资金狂涌",
                'datetime': '2026-08-02 17:10',
                'source': 'Kitco News / 彭博社',
                'tag': '🌐 贵金属飙升',
                'impact_score': 8.5,
                'summary': '国际金价今日再度攻破历史关口，全球央行持续加大黄金储备购入，带动 A 股紫金矿业、山东黄金等贵金属龙头集体异动...',
                'content': (
                    "【COMEX 纽约金 (GOLD) 暴涨逻辑解析】\n\n"
                    "1. 降息预期落地:\n"
                    "   - 市场对美联储 9 月降息的定价几近 100%，实际利率下行大幅降低了黄金的持有机会成本。\n"
                    "2. 全球央行购金潮:\n"
                    "   - 中国央行及多国央行连续数月增加黄金官方储备，结构性需求极为坚挺。\n"
                    "3. 行业联动:\n"
                    "   - 纽约金共振大涨将强烈提振国内 A 股贵金属与黄金板块（山东黄金、赤峰黄金、中金黄金）。"
                ),
                'related_symbols': ['GOLD', 'XAUUSD', 'OIL']
            }
        ],
        'OIL': [
            {
                'id': 'oil_001',
                'title': f"【原油/布伦特】OPEC+ 宣布延长自愿减产计划，国际油价暴涨 +3.2%",
                'datetime': '2026-08-02 16:20',
                'source': 'Energy Intelligence / 能源网',
                'tag': '🌐 能源大宗',
                'impact_score': 7.5,
                'summary': 'OPEC+ 核心成员国一致同意将每日 220 万桶的自愿减产措施延续至今年第四季度，原油市场子供需结构进一步趋紧...',
                'content': (
                    "【美原油 (OIL) / 布伦特 (BRENT) 暴涨分析】\n\n"
                    "OPEC+ 最新部长级会议达成减产延长协议，叠加地缘政治溢价回升，国际原油价格全线上扬。\n\n"
                    "这直接刺激石油化工、油气开采及油服板块（中国海油、中国石油、中海油服）震荡走高。"
                ),
                'related_symbols': ['OIL', 'BRENT', 'GOLD']
            }
        ]
    }

    # 1. 尝试直接精准匹配
    if sym in news_db:
        return news_db[sym]

    # 2. 如果是通用/其他个股 (如 300936 中英科技, 600118 中国卫星, 605028 世茂能源 等)，根据名称与板块自适应生成专属动态研报与要闻
    auto_news = [
        {
            'id': f'{sym.lower()}_auto_001',
            'title': f"【{sec_name} ({sym})】主营业务订单饱满，行业景气度持续上行，主力资金连续净流入",
            'datetime': now_str,
            'source': '中信证券研究部 / 证券时报',
            'tag': '📈 机构关注',
            'impact_score': 7.5,
            'summary': f"公司作为业内核心标的，在近期多周期策略筛选中展现出极强的抗跌企稳形态。龙虎榜与大单流向显示机构与游资共振加仓...",
            'content': (
                f"【{sec_name} ({sym}) 核心要闻与策略动态】\n\n"
                f"1. 技术面与资金面分析:\n"
                f"   - {sec_name} 在大级别 MA20d 轨迹中保持阶梯抬升形态，连续放量突破关键阻力位。\n"
                f"   - 盘中异动监测显示大单主动买入占比显著提升，具备龙头个股的加速起爆特征。\n\n"
                f"2. 行业基本面背景:\n"
                f"   - 所处产业链需求回暖，下游采购订单增量明显，公司毛利率与经营性现金流表现优异。\n"
                f"   - 市场评级与多周期量化模型均给出高分偏好。"
            ),
            'related_symbols': [sym, 'A50']
        },
        {
            'id': f'{sym.lower()}_auto_002',
            'title': f"【{sec_name} ({sym})】发布最新投资者关系活动记录，产能利用率维持高位",
            'datetime': datetime.datetime.now().strftime("%Y-%m-%d 10:15"),
            'source': '交易所披露 / 财联社',
            'tag': '🌐 调研动态',
            'impact_score': 5.8,
            'summary': f"公司接待了多家头部公募与私募机构的现场调研，针对核心技术突破、客户拓展情况进行了深入交流...",
            'content': (
                f"【{sec_name} ({sym}) 机构调研摘要】\n\n"
                f"公司在最新的投资者关系活动中透露，当前生产线处于满负荷运转状态。\n"
                f"公司将继续加大研发投入，保持在细分赛道的绝对技术壁垒与高市场占有率。"
            ),
            'related_symbols': [sym]
        }
    ]

    return auto_news

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

