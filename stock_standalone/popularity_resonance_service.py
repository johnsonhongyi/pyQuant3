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

def calculate_resonance_scores(
    em_data: dict[str, int],
    ths_data: dict[str, int],
    tgb_data: dict[str, int],
    lh_data: dict[str, int]
) -> list[dict]:
    """
    计算人气共振综合得分
    评分规则:
    1. 各平台基础分:
       - 东财 (前100): 101 - 排名
       - 同花顺 (前100): 101 - 排名
       - 淘股吧 (前50): (51 - 排名) * 2  (转换为100分制)
       - 龙虎大师 (若有): 50分固定加成
    2. 共振加成 (Resonance Bonus):
       - 出现在 3 个或以上平台: 额外加 500 分
       - 出现在 2 个平台: 额外加 200 分
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
            
        # 共振加分
        if platforms >= 3:
            score += 500
        elif platforms == 2:
            score += 200
            
        resonance_list.append({
            "code": code,
            "platforms": platforms,
            "score": score,
            "details": ", ".join(details)
        })
        
    # 按综合得分降序排序
    resonance_list.sort(key=lambda x: x['score'], reverse=True)
    return resonance_list

def write_to_tdx_blocks(codes: list[str]) -> None:
    """
    将股票代码写入通达信的自选板块文件中 (RQG.blk)。
    支持写入多个存在的工作路径，解决路径错配问题。
    """
    if not codes:
        logger.warning("没有股票代码需要写入.")
        return
        
    blk_filename = "RQG.blk"
    
    # 1. 写入主通达信目录 (由 cct.write_to_blocknew 自动联动 new_tdx2 和 zd_dxzq)
    if cct is not None:
        try:
            primary_path = os.path.join(cct.get_tdx_dir_blocknew(), blk_filename)
            cct.write_to_blocknew(primary_path, codes, append=False, doubleFile=False)
            logger.info(f"成功更新主自选板块文件: {primary_path}")
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

def run_sync(max_stocks: int = 50) -> list[dict]:
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
    logger.info("写入通达信自选文件...")
    write_to_tdx_blocks(top_codes)
    
    return top_results

if __name__ == "__main__":
    run_sync()
