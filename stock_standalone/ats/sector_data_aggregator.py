# -*- coding: utf-8 -*-
"""
ats/sector_data_aggregator.py — ATS 统一板块成分股与量化行情数据聚合中枢 (Unified Data Aggregator)
职责：
1. 【统一数据源架构 (完全对齐新股/次新股标准策略体系)】：
   - 基础实时行情 (现价, 昨收, 涨跌幅, 开盘, 最高, 最低, 成交量, 成交额, 买点评级, 量比): 100% 优先由 TDX API 权威直连获取；
   - 极速备用兜底通道: 当 TDX 离线或缺失时，自动通过新浪/腾讯 50ms 国内免代理极速直连补充；
   - 动态策略与自定义指标列 (dff, dff2, dff3, rank, perc3d 及 ats_col 扩展列): 100% 全部从策略 DataFrame (current_df) 动态提取并精确格式化；
2. 【全局活跃策略 DataFrame 自动感知探测】：
   - 无论独立窗口启动还是子组件调用，自动从 Parent 链、Window 链、QApplication 活跃顶层窗口中感知主程序正在轮询的最新 DataFrame；
3. 【全市场多赛道行业中军龙头储备与同义词泛化匹配】：
   - 覆盖 15 大核心赛道经典中军代表库，支持同义词模糊向量匹配；
4. 【多模块统一出口】：
   - 为板块明细弹窗、外盘看板、强势板块排行、异动联动等所有业务模块提供统一、高效、非阻塞的数据接口。
"""

import os
import sys
import time
import json
import zlib
import re
import math
import logging
import datetime
import threading
import urllib.request
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any, Callable

from sys_utils import get_app_root, get_conf_path
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("SectorDataAggregator")

# 纯直连 Opener (杜绝本地代理对国内行情 API 干扰)
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.sina.com.cn/'
}

# 经典行业中军龙头核心储备库 (覆盖全行业 15 大核心赛道)
FAMOUS_SECTOR_LEADERS: Dict[str, List[Tuple[str, str]]] = {
    "半导体": [("688981", "中芯国际"), ("603501", "韦尔股份"), ("002371", "北方华创"), ("688012", "华海清科"), ("688008", "澜起科技"), ("688036", "传音控股"), ("688126", "沪硅产业"), ("600584", "长电科技")],
    "存储芯片": [("603986", "兆易创新"), ("688981", "中芯国际"), ("002156", "通富微电"), ("688041", "普冉股份"), ("300661", "圣邦股份"), ("688008", "澜起科技"), ("688521", "芯原股份"), ("300223", "北京君正")],
    "传媒": [("300058", "蓝色光标"), ("603533", "掌阅科技"), ("301171", "易点天下"), ("002624", "完美世界"), ("300413", "芒果超媒"), ("002354", "天娱数科"), ("600633", "浙数文化"), ("300364", "中文在线")],
    "软件开发": [("300496", "中科创达"), ("600588", "用友网络"), ("300033", "同花顺"), ("688111", "金山办公"), ("300229", "拓尔思"), ("600570", "恒生电子"), ("002230", "科大讯飞"), ("300339", "润和软件")],
    "国防军工": [("601606", "长城军工"), ("600118", "中国卫星"), ("002179", "中航光电"), ("600760", "中航沈飞"), ("000768", "中航西飞"), ("600893", "航发动力"), ("002013", "中航机载"), ("600372", "中航电子")],
    "汽车整车": [("600733", "北汽蓝谷"), ("002594", "比亚迪"), ("601633", "长城汽车"), ("601127", "赛力斯"), ("600104", "上汽集团"), ("000625", "长安汽车"), ("600066", "宇通客车"), ("601238", "广汽集团")],
    "贵金属": [("601899", "紫金矿业"), ("600988", "赤峰黄金"), ("600547", "山东黄金"), ("600489", "中金黄金"), ("000975", "山金国际"), ("600960", "渤海化学"), ("000506", "中润资源")],
    "石油化工": [("600938", "中国海油"), ("601857", "中国石油"), ("600583", "中海油服"), ("600028", "中国石化"), ("600346", "恒力石化"), ("002493", "荣盛石化"), ("600256", "广汇能源")],
    "有色金属": [("603993", "洛阳钼业"), ("601899", "紫金矿业"), ("600362", "江西铜业"), ("601600", "中国铝业"), ("000630", "铜陵有色"), ("600111", "北方稀土"), ("002460", "赣锋锂业"), ("002466", "天齐锂业")],
    "AI/软件": [("300058", "蓝色光标"), ("002230", "科大讯飞"), ("688111", "金山办公"), ("300033", "同花顺"), ("300496", "中科创达"), ("300229", "拓尔思"), ("300364", "中文在线"), ("688256", "寒武纪")],
    "金融/权重龙头": [("600036", "招商银行"), ("601318", "中国平安"), ("600030", "中信证券"), ("601688", "华泰证券"), ("601211", "国泰君安"), ("601166", "兴业银行"), ("600999", "招商证券")],
    "石油化工/资源": [("601857", "中国石油"), ("600028", "中国石化"), ("600938", "中国海油"), ("601088", "中国神华"), ("600188", "兖矿能源"), ("601225", "陕西煤业")],
    "消费电子": [("002475", "立讯精密"), ("002241", "歌尔股份"), ("603501", "韦尔股份"), ("300433", "蓝思科技"), ("002456", "欧菲光"), ("002384", "东山精密")],
    "通信设备": [("000063", "中兴通讯"), ("300308", "中际旭创"), ("300502", "新易盛"), ("300394", "天孚通信"), ("600498", "烽火通信"), ("600487", "亨通光电")],
    "电力设备": [("300750", "宁德时代"), ("601012", "隆基绿能"), ("600406", "国电南瑞"), ("002459", "晶澳科技"), ("300274", "阳光电源"), ("601877", "正泰电器")]
}

SECTOR_SYNONYMS: Dict[str, List[str]] = {
    "半导体": ["半导体及部件", "半导体", "芯片", "电子元器件"],
    "存储芯片": ["半导体及部件", "存储芯片", "芯片", "电子元器件"],
    "传媒": ["传媒娱乐", "文化传媒", "传媒", "互联网"],
    "软件开发": ["软件服务", "软件开发", "IT设备", "计算机"],
    "国防军工": ["国防军工", "军工", "航天装备", "通用设备"],
    "汽车整车": ["汽车类", "汽车整车", "新能源车", "交运设备"],
    "贵金属": ["贵金属", "黄金", "珠宝首饰"],
    "石油化工": ["石油行业", "石油", "石油化工", "采掘行业", "化学原料"],
    "有色金属": ["有色金属", "有色", "小金属", "稀缺资源", "工业金属"],
    "AI/软件": ["软件服务", "人工智能", "互联网", "软件开发", "算力"],
    "金融/权重龙头": ["银行", "证券", "保险"],
    "石油化工/资源": ["石油", "煤炭开采", "化工", "化学原料"],
    "消费电子": ["消费电子", "苹果概念", "电子元件"],
    "通信设备": ["通信设备", "CPO", "5G概念", "光通信"]
}


def _safe_float(val: Any, default: float = 0.0) -> float:
    """安全转换为 float，杜绝 NaN, Inf, None, 空字符串及非数字异常"""
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """安全转换为 int"""
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else int(f)
    except (ValueError, TypeError):
        return default


def _get_sina_market_code(code: str) -> str:
    """精准映射 A 股各板块交易所前缀 (上交所 sh / 深交所 sz / 北交所 bj / 基金 ETF / 可转债)"""
    c = str(code).strip().zfill(6)
    # 上交所: 60xxxx, 688xxx, 900xxx(B股), 11xxxx(可转债), 51xxxx/56xxxx/58xxxx(ETF/基金)
    if c.startswith(('60', '68', '90', '11', '51', '56', '58')):
        return f"sh{c}"
    # 北交所: 83xxxx, 87xxxx, 88xxxx, 43xxxx, 920xxx
    elif c.startswith(('83', '87', '88', '43', '92')):
        return f"bj{c}"
    # 深交所: 00xxxx, 20xxxx(B股), 30xxxx(创业板), 12xxxx(可转债), 15xxxx/16xxxx/18xxxx(ETF/基金)
    elif c.startswith(('00', '20', '30', '12', '15', '16', '18')):
        return f"sz{c}"
    elif c.startswith(('6', '9')):
        return f"sh{c}"
    else:
        return f"sz{c}"


def fetch_sina_stock_quotes_fast(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """批量通过新浪 A 股接口获取股票实时现价、昨收、涨跌幅、今开、最高、最低 (国内直连 50ms 极速响应，单行异常安全隔离)"""
    if not codes:
        return {}
    results = {}
    clean_codes = [str(c).strip().zfill(6) for c in codes if str(c).strip()]
    
    batch_size = 60
    for i in range(0, len(clean_codes), batch_size):
        batch = clean_codes[i:i + batch_size]
        sina_codes = [_get_sina_market_code(c) for c in batch]
        url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
        try:
            req = urllib.request.Request(url, headers=_HTTP_HEADERS)
            with _DIRECT_OPENER.open(req, timeout=2.5) as resp:
                content = resp.read().decode('gbk', errors='ignore')
                for line in content.strip().split('\n'):
                    if line and '="' in line:
                        try:
                            parts = line.split('="')
                            sym = parts[0].split('hq_str_')[-1]
                            code = sym[2:] if len(sym) > 6 else sym
                            fields = parts[1].replace('";', '').split(',')
                            if len(fields) >= 5:
                                name = fields[0].strip()
                                open_p = _safe_float(fields[1])
                                prev_close = _safe_float(fields[2])
                                curr_p = _safe_float(fields[3])
                                high_p = _safe_float(fields[4])
                                low_p = _safe_float(fields[5])
                                pct = round((curr_p - prev_close) / prev_close * 100.0, 2) if prev_close > 0 else 0.0
                                vol = _safe_float(fields[8]) if len(fields) > 8 else 0.0
                                amount = _safe_float(fields[9]) if len(fields) > 9 else 0.0
                                code_clean = str(code).strip().zfill(6)
                                results[code_clean] = {
                                    'code': code_clean,
                                    'name': name,
                                    'price': curr_p,
                                    'prev_close': prev_close,
                                    'open': open_p,
                                    'high': high_p,
                                    'low': low_p,
                                    'pct': pct,
                                    'volume': vol,
                                    'amount': amount
                                }
                        except Exception as parse_err:
                            logger.debug(f"单只新浪行情解析异常 {line[:30]}: {parse_err}")
        except Exception as e:
            logger.debug(f"fetch_sina_stock_quotes_fast error: {e}")
    return results


def get_sector_extra_cols() -> List[str]:
    """获取板块明细追加的动态自定义列（排除基础列已有的字段）"""
    try:
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['ch_bc2']
    BASE_EXCLUDE = {
        'code', 'name', 'score', 'type', 'pct', 'percent', 'start_pct', 
        'dff', 'rank', 'dff2', 'dff3', 'pattern', 'price', 'trade'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


def get_sector_table_headers(extra_cols: Optional[List[str]] = None) -> List[str]:
    """获取板块明细表格标准表头字段名称列表"""
    if extra_cols is None:
        extra_cols = get_sector_extra_cols()
    try:
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}
    base_pre = ["代码", "名称", "得分", "类型", "涨幅", "起点", "DFF", "Rank", "DFF2", "DFF3"]
    extra_headers = [col_map.get(c, c) for c in extra_cols]
    base_post = ["形态提示"]
    return base_pre + extra_headers + base_post


class SectorDataAggregator:
    """
    ATS 统一板块与个股量化数据聚合引擎 (单例)
    提供标准统一的行情直连、策略 DataFrame 融合、动态指标提取与领涨龙头评选
    """
    _instance: Optional['SectorDataAggregator'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'SectorDataAggregator':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _get_df_row_safe(self, df: Optional[pd.DataFrame], code_str: str) -> Optional[Any]:
        """从 DataFrame 中安全、多格式兼容地检索对应股票行 (支持 6 位纯数字/原字符串/整型索引/带前缀/列匹配)"""
        if df is None or df.empty:
            return None
        c_clean = str(code_str).strip().zfill(6)
        # 尝试 1: 直接 6 位纯数字字符串
        if c_clean in df.index:
            r = df.loc[c_clean]
            return r.iloc[0] if isinstance(r, pd.DataFrame) else r
        # 尝试 2: 原始传入字符串
        if code_str in df.index:
            r = df.loc[code_str]
            return r.iloc[0] if isinstance(r, pd.DataFrame) else r
        # 尝试 3: 整型索引匹配 (如 300115 或 2055)
        try:
            c_int = int(c_clean)
            if c_int in df.index:
                r = df.loc[c_int]
                return r.iloc[0] if isinstance(r, pd.DataFrame) else r
            # 也尝试去掉前导 0 的字符串 (如 '2055')
            c_stripped = str(c_int)
            if c_stripped in df.index:
                r = df.loc[c_stripped]
                return r.iloc[0] if isinstance(r, pd.DataFrame) else r
        except Exception:
            pass
        # 尝试 4: 带市场前缀 (sh600000, sz000001, etc.)
        for pfx in ('sh', 'sz', 'bj', 'SH', 'SZ', 'BJ'):
            cand = f"{pfx}{c_clean}"
            if cand in df.index:
                r = df.loc[cand]
                return r.iloc[0] if isinstance(r, pd.DataFrame) else r
        # 尝试 5: 存在 'code' 字段列
        if 'code' in df.columns:
            try:
                matched = df[df['code'].astype(str).str.strip().str.zfill(6) == c_clean]
                if not matched.empty:
                    return matched.iloc[0]
            except Exception:
                pass
        return None

    def resolve_active_strategy_df(self, widget_or_parent=None) -> Tuple[Optional[pd.DataFrame], Optional[Callable[[str], str]]]:
        """
        递归感知与探测系统当前运行中的量化策略主 DataFrame (提取 dff, dff2, dff3, rank, custom_cols)
        与股票名称获取函数 get_stock_name
        """
        get_name_fn = None
        current_df = None

        # 1. 优先从传入的 Widget 及其父链中查找
        p = widget_or_parent
        while p:
            if hasattr(p, 'get_stock_name') and not get_name_fn:
                get_name_fn = p.get_stock_name
            for attr in ('current_df', '_last_flat_df', 'last_result_df', 'flat_df', 'result_df', 'df_all', 'top_now'):
                df_cand = getattr(p, attr, None)
                if df_cand is not None and not df_cand.empty:
                    current_df = df_cand
                    break
            if current_df is not None and get_name_fn:
                break
            p = getattr(p, '_py_parent', None) or (p.parent() if hasattr(p, 'parent') and callable(p.parent) else None)

        # 2. 降级：从 QApplication 顶层所有活跃窗口中探测
        if current_df is None:
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for top_w in app.topLevelWidgets():
                        for attr in ('current_df', '_last_flat_df', 'last_result_df', 'flat_df', 'result_df', 'df_all', 'top_now'):
                            df_cand = getattr(top_w, attr, None)
                            if df_cand is not None and not df_cand.empty:
                                current_df = df_cand
                                if not get_name_fn and hasattr(top_w, 'get_stock_name'):
                                    get_name_fn = top_w.get_stock_name
                                break
                        if current_df is not None:
                            break
            except Exception:
                pass

        return current_df, get_name_fn

    def _load_bidding_sector_data(self) -> Dict[str, Any]:
        """[SSOT] 权威加载最新的 bidding_session_data / 快照文件 (含 mtime 缓存)"""
        import glob
        import gzip
        import re
        import zlib

        base = get_app_root()
        path = None
        try:
            ram_path = cct.get_ramdisk_path("bidding_session_data.json.gz")
            if ram_path and os.path.exists(ram_path):
                path = ram_path
        except Exception:
            pass

        if not path:
            try:
                fallback_path = os.path.abspath(os.path.join(base, "snapshots", "bidding_session_data.json.gz"))
                if os.path.exists(fallback_path):
                    path = fallback_path
                else:
                    snap_pattern = os.path.join(base, "snapshots", "bidding_*.json.gz")
                    snap_files = [f for f in glob.glob(snap_pattern) if re.search(r'bidding_\d{8}\.json\.gz$', f)]
                    if snap_files:
                        path = sorted(snap_files)[-1]
            except Exception:
                pass

        if not path or not os.path.exists(path):
            return {}

        mtime = os.path.getmtime(path)
        if (getattr(self, '_cached_bidding_path', None) == path and
            getattr(self, '_cached_bidding_mtime', None) == mtime and
            hasattr(self, '_cached_bidding_data')):
            return self._cached_bidding_data

        try:
            with open(path, 'rb') as f:
                raw = f.read()
            if raw:
                json_str = zlib.decompress(raw).decode('utf-8')
                data = json.loads(json_str)
                self._cached_bidding_data = data.get('sector_data', {})
                self._cached_bidding_path = path
                self._cached_bidding_mtime = mtime
                return self._cached_bidding_data
        except Exception as e:
            logger.debug(f"SectorDataAggregator _load_bidding_sector_data error: {e}")

        return {}

    def get_bidding_sector_info(self, sector_name: str) -> Optional[Dict[str, Any]]:
        """获取板块在 bidding_session_data 中的元数据"""
        clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(sector_name)).strip()
        bidding_sec_data = self._load_bidding_sector_data()
        if bidding_sec_data:
            if clean_sec in bidding_sec_data:
                return bidding_sec_data[clean_sec]
            elif sector_name in bidding_sec_data:
                return bidding_sec_data[sector_name]
            else:
                synonyms = [clean_sec] + SECTOR_SYNONYMS.get(clean_sec, [])
                for syn in synonyms:
                    for k, v in bidding_sec_data.items():
                        if syn == k or syn in k or k in syn:
                            return v
        return None

    def resolve_sector_member_codes(
        self,
        sector_name: str,
        member_codes: Optional[List[str]] = None,
        current_df: Optional[pd.DataFrame] = None
    ) -> Tuple[List[str], Dict[str, str]]:
        """
        解析板块成分股代码列表与名称映射:
        - 若显式传入 member_codes，严格以 member_codes 为准；
        - 若未传入 member_codes，100% 优先从全市场竞价快照 (bidding_session_data) 解析全量成分股 (龙头 + 赛马成员 + 跟随者)；
        - 若快照中未找到，则依序从 current_df 同义词模糊匹配与经典中军库兜底。
        """
        target_codes = []
        seen_codes = set()
        code_to_name = {}

        # 清洗板块名称（去除 ⭐, 🔥, ⚡, 📊, 👑 及前后空格）
        clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(sector_name)).strip()

        # ── 1. 若外部显式传入非空 member_codes，严格以输入为准 ──
        if member_codes is not None and len(member_codes) > 0:
            for c in member_codes:
                c_clean = str(c).strip().zfill(6)
                if c_clean and c_clean not in seen_codes:
                    target_codes.append(c_clean)
                    seen_codes.add(c_clean)
            return target_codes, code_to_name

        # ── 2. 优先从 bidding_session_data 权威读取全量成分股 ──
        matched_sec_info = self.get_bidding_sector_info(sector_name)
        if matched_sec_info:
            # 龙头
            l_code = str(matched_sec_info.get('leader', '')).strip().zfill(6)
            l_name = str(matched_sec_info.get('leader_name', '')).strip()
            if l_code and l_code != '000000' and l_code not in seen_codes:
                target_codes.append(l_code)
                seen_codes.add(l_code)
                if l_name:
                    code_to_name[l_code] = l_name

            # 竞价赛马候选成员
            for rc in matched_sec_info.get('race_candidates', []):
                c = str(rc.get('code', '')).strip().zfill(6)
                if c and c != '000000' and c not in seen_codes:
                    target_codes.append(c)
                    seen_codes.add(c)
                n = str(rc.get('name', '')).strip()
                if c and n and n != '未知':
                    code_to_name[c] = n

            # 跟随者成员
            for fol in matched_sec_info.get('followers', []):
                c = str(fol.get('code', '')).strip().zfill(6)
                if c and c != '000000' and c not in seen_codes:
                    target_codes.append(c)
                    seen_codes.add(c)
                n = str(fol.get('name', '')).strip()
                if c and n and n != '未知':
                    code_to_name[c] = n

        # ── 3. 若 current_df 包含 category 列，将模糊匹配到的成分股合并入池 ──
        if current_df is not None and not current_df.empty and 'category' in current_df.columns:
            try:
                synonyms = [clean_sec] + SECTOR_SYNONYMS.get(clean_sec, [])
                pattern = '|'.join([re.escape(s) for s in synonyms if s])
                matched_series = current_df['category'].astype(str).str.contains(pattern, case=False, na=False)
                df_matched = current_df[matched_series]
                if not df_matched.empty:
                    use_col = 'code' in df_matched.columns
                    for idx, row_item in df_matched.iloc[:60].iterrows():
                        raw_c = row_item['code'] if use_col else idx
                        c_clean = str(raw_c).strip().zfill(6)
                        if c_clean and len(c_clean) == 6 and c_clean not in seen_codes:
                            target_codes.append(c_clean)
                            seen_codes.add(c_clean)
                            n_val = str(row_item.get('name', '')).strip()
                            if n_val and n_val != '未知' and n_val != c_clean:
                                code_to_name[c_clean] = n_val
            except Exception as ex:
                logger.debug(f"current_df 板块匹配异常: {ex}")

        # ── 4. 若成分股仍不足，从著名经典中军龙头库 FAMOUS_SECTOR_LEADERS 补齐 ──
        if len(target_codes) < 6:
            for key, st_list in FAMOUS_SECTOR_LEADERS.items():
                if key == clean_sec or key in clean_sec or clean_sec in key:
                    for c_code, def_name in st_list:
                        c_clean = str(c_code).strip().zfill(6)
                        if c_clean not in seen_codes:
                            target_codes.append(c_clean)
                            seen_codes.add(c_clean)
                        if c_clean not in code_to_name:
                            code_to_name[c_clean] = def_name
                    break

        return target_codes, code_to_name

    def fetch_quotes_unified(
        self,
        codes: List[str],
        current_df: Optional[pd.DataFrame] = None,
        extra_cols: Optional[List[str]] = None,
        sector_name: str = "",
        code_to_name: Optional[Dict[str, str]] = None,
        get_name_fn: Optional[Callable[[str], str]] = None
    ) -> List[Dict[str, Any]]:
        """
        【🎯 核心统一接口】输入股票代码列表，全自动完成：
        1. 基础实时行情优先通过 TDX API 直连获取 (现价, 昨收, 涨跌幅, 开盘, 最高, 最低, 成交量, 成交额)；
        2. 极速备用兜底通道: 当 TDX 离线或缺失时，通过新浪 50ms 国内免代理直连补充；
        3. 动态策略列与扩展指标 (dff, dff2, dff3, rank, custom_cols) 100% 全部从 current_df 获取；
        4. TDX 高频 Alpha 买点评级与量比特征融合。
        """
        if not codes:
            return []

        clean_codes = [str(c).strip().zfill(6) for c in codes if str(c).strip()]
        extra_cols = extra_cols or get_sector_extra_cols()
        code_to_name = code_to_name or {}

        # 1. 基础行情通道 1: TDX API 直连 (最高优先级)
        tdx_quote_map = {}
        tdx_alpha_map = {}
        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            fetcher = TDXRealtimeFetcher.get_instance()
            
            # A. 批量获取 TDX 官方基础行情
            tdx_quotes = fetcher.get_security_quotes_safe(clean_codes, force=False)
            if tdx_quotes:
                for q in tdx_quotes:
                    c_clean = str(q.get("code", "")).strip().zfill(6)
                    p = _safe_float(q.get("price"))
                    bid1_p = _safe_float(q.get("bid1"))
                    ask1_p = _safe_float(q.get("ask1"))
                    open_p = _safe_float(q.get("open"))
                    last_c = _safe_float(q.get("last_close"))
                    
                    # ⚡ 09:15~09:25 集合竞价有效参考价多级回退
                    effective_p = p if p > 0 else (bid1_p if bid1_p > 0 else (ask1_p if ask1_p > 0 else open_p))
                    vol = _safe_float(q.get("vol"))
                    bid1_v = _safe_float(q.get("bid_vol1"))
                    effective_vol = vol if vol > 0 else bid1_v
                    amt = _safe_float(q.get("amount"))
                    if amt <= 0 and effective_p > 0 and effective_vol > 0:
                        amt = effective_p * effective_vol * 100.0

                    if c_clean and (effective_p > 0 or last_c > 0):
                        pct = round((effective_p - last_c) / last_c * 100.0, 2) if (last_c > 0 and effective_p > 0) else 0.0
                        tdx_quote_map[c_clean] = {
                            'price': effective_p,
                            'prev_close': last_c,
                            'open': open_p if open_p > 0 else effective_p,
                            'high': _safe_float(q.get("high")) if _safe_float(q.get("high")) > 0 else effective_p,
                            'low': _safe_float(q.get("low")) if _safe_float(q.get("low")) > 0 else effective_p,
                            'amount': amt,
                            'vol': effective_vol,
                            'pct': pct
                        }

            # B. 批量获取 TDX 高频 Alpha 盘口买点评级
            sec_map = {c: sector_name for c in clean_codes}
            mp_cache = {}
            n_map = {}
            if current_df is not None:
                for c in clean_codes:
                    r_row = self._get_df_row_safe(current_df, c)
                    if r_row is not None:
                        n_map[c] = str(r_row.get('name', r_row.get('名称', c)))
                        mp_cache[c] = {
                            'dff': _safe_float(r_row.get('dff', r_row.get('DFF'))),
                            'dff2': _safe_float(r_row.get('DFF2', r_row.get('dff2'))),
                            'dff3': _safe_float(r_row.get('DFF3', r_row.get('dff3'))),
                            'rank': _safe_int(r_row.get('Rank', r_row.get('rank', r_row.get('排名', r_row.get('topR', 0)))), 0)
                        }
            alpha_quotes = fetcher.fetch_multi_stock_alpha_quotes(clean_codes, sec_map, mp_cache, n_map)
            for aq in alpha_quotes:
                aq_code = str(aq.get("code", "")).strip().zfill(6)
                if aq_code:
                    tdx_alpha_map[aq_code] = aq
        except Exception as e:
            logger.debug(f"TDX API 批量行情拉取降级: {e}")

        # 2. 基础行情通道 2: 新浪直连 50ms 极速备用兜底 (当 TDX 离线或缺失时补充)
        sina_quotes_map = {}
        missing_codes = [c for c in clean_codes if c not in tdx_quote_map or tdx_quote_map[c].get('price', 0) <= 0]
        if missing_codes:
            sina_quotes_map = fetch_sina_stock_quotes_fast(missing_codes)

        # 2.5 探测全量快照底表 (当 current_df 仅为局部策略过滤池时用于回补 Rank、DFF2、DFF3 等指标)
        fallback_df = None
        if current_df is None or len(current_df) < 1500:
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for top_w in app.topLevelWidgets():
                        for attr in ('df_all', '_last_flat_df', 'flat_df', 'last_result_df', 'current_df', 'top_now'):
                            cand = getattr(top_w, attr, None)
                            if cand is not None and isinstance(cand, pd.DataFrame) and len(cand) > len(current_df if current_df is not None else []):
                                fallback_df = cand
                                break
                        if fallback_df is not None:
                            break
            except Exception:
                pass

        # 3. 组装行数据
        rows = []
        for code_str in clean_codes:
            name = code_to_name.get(code_str) or (get_name_fn(code_str) if get_name_fn else "个股")
            if not name or name == "未知" or name == code_str:
                if code_str in sina_quotes_map:
                    name = sina_quotes_map[code_str].get('name', name)

            score = 75.0
            pct_val = 0.0
            dff_val = 0.0
            rank_val = 0
            dff2_val = 0.0
            dff3_val = 0.0
            pattern_hint = "行业核心中军"
            type_str = "跟涨"

            # ── 💡 动态列与策略自定义列：优先从 current_df 获取，缺失时自动从 fallback_df 回补 ──
            row = self._get_df_row_safe(current_df, code_str)
            if row is not None:
                name_df = str(row.get('name', row.get('名称', ''))).strip()
                if name_df and name_df != "未知":
                    name = name_df
                pct_val = _safe_float(row.get('percent', row.get('pct', row.get('涨幅', 0.0))))
                dff_val = _safe_float(row.get('dff', row.get('DFF', 0.0)))
                rank_val = _safe_int(row.get('Rank', row.get('rank', row.get('排名', row.get('topR', 0)))))
                dff2_val = _safe_float(row.get('DFF2', row.get('dff2', 0.0)))
                dff3_val = _safe_float(row.get('DFF3', row.get('dff3', 0.0)))

            # 🛡️【二级回补兜底】：如果当前策略池缺少该股票或 rank/dff 缺失，从全量快照池 fallback_df 补齐
            if fallback_df is not None and (row is None or rank_val == 0 or dff2_val == 0.0):
                row_fb = self._get_df_row_safe(fallback_df, code_str)
                if row_fb is not None:
                    if not name or name == "个股" or name == code_str:
                        name_fb = str(row_fb.get('name', row_fb.get('名称', ''))).strip()
                        if name_fb and name_fb != "未知":
                            name = name_fb
                    if pct_val == 0.0:
                        pct_val = _safe_float(row_fb.get('percent', row_fb.get('pct', row_fb.get('涨幅', 0.0))))
                    if dff_val == 0.0:
                        dff_val = _safe_float(row_fb.get('dff', row_fb.get('DFF', 0.0)))
                    if rank_val == 0:
                        rank_val = _safe_int(row_fb.get('Rank', row_fb.get('rank', row_fb.get('排名', row_fb.get('topR', 0)))))
                    if dff2_val == 0.0:
                        dff2_val = _safe_float(row_fb.get('DFF2', row_fb.get('dff2', 0.0)))
                    if dff3_val == 0.0:
                        dff3_val = _safe_float(row_fb.get('DFF3', row_fb.get('dff3', 0.0)))

            # ── 💡 基础数据：优先使用 TDX API 权威实时行情驱动 ──
            tq = tdx_quote_map.get(code_str)
            if tq and tq.get('price', 0) > 0:
                pct_val = _safe_float(tq.get('pct', pct_val))
                pattern_hint = f"现价 {tq.get('price'):.2f} | 昨收 {tq.get('prev_close'):.2f}"
            elif code_str in sina_quotes_map:
                sq = sina_quotes_map[code_str]
                pct_val = _safe_float(sq.get('pct', pct_val))
                if not name or name == "个股" or name == code_str:
                    name = sq.get('name', name)
                pattern_hint = f"现价 {sq.get('price'):.2f} | 昨收 {sq.get('prev_close'):.2f}"

            # 叠加 TDX 高频买点评级与形态特征
            aq = tdx_alpha_map.get(code_str)
            if aq:
                pct_val = _safe_float(aq.get("pct", pct_val))
                type_str = aq.get("buy_type", type_str)
                score = _safe_float(aq.get("alpha_score", score), 75.0)
                vwap_dev = _safe_float(aq.get("vwap_dev_pct", 0.0))
                vol_r = _safe_float(aq.get("vol_ratio", 1.0), 1.0)
                pattern_hint = f"{aq.get('buy_tag', '')} | VWAP偏离{vwap_dev:+.1f}% | 量比{vol_r:.1f}"

            # ── 💡 动态自定义列：从 df 严格映射提取 (优先 current_df，缺失从 fallback_df 补齐) ──
            extra_dict = {}
            for ec in extra_cols:
                val_raw = None
                if row is not None:
                    for k in (ec, ec.lower(), ec.upper()):
                        if k in row:
                            val_raw = row[k]
                            break
                if val_raw is None and fallback_df is not None:
                    row_fb = self._get_df_row_safe(fallback_df, code_str)
                    if row_fb is not None:
                        for k in (ec, ec.lower(), ec.upper()):
                            if k in row_fb:
                                val_raw = row_fb[k]
                                break
                extra_dict[ec] = cct.format_col_value(ec, val_raw)

            rows.append({
                'code': code_str,
                'name': name,
                'score': score,
                'type': type_str,
                'pct': round(pct_val, 2),
                'start_pct': round(pct_val - dff_val, 2),
                'dff': dff_val,
                'rank': rank_val,
                'dff2': dff2_val,
                'dff3': dff3_val,
                'extra_cols': extra_dict,
                'pattern': pattern_hint
            })

        return rows

    def fetch_sector_detail(
        self,
        sector_name: str,
        member_codes: Optional[List[str]] = None,
        current_df: Optional[pd.DataFrame] = None,
        extra_cols: Optional[List[str]] = None,
        get_name_fn: Optional[Callable[[str], str]] = None
    ) -> Tuple[List[Dict[str, Any]], float, str, Dict[str, Any]]:
        """
        【🎯 板块明细核心入口】一键完成板块成分股发现、高频行情拉取、动态列映射、领涨龙头评选与强度打分
        返回: (rows, score, leader_str, meta)
        """
        matched_sec_info = self.get_bidding_sector_info(sector_name)
        code_list, code_to_name = self.resolve_sector_member_codes(
            sector_name=sector_name,
            member_codes=member_codes,
            current_df=current_df
        )

        if not code_list:
            return [], 0.0, "--", {'status': '无成分股数据', 'count': 0}

        rows = self.fetch_quotes_unified(
            codes=code_list,
            current_df=current_df,
            extra_cols=extra_cols,
            sector_name=sector_name,
            code_to_name=code_to_name,
            get_name_fn=get_name_fn
        )

        # ── 1. 从 bidding_session_data 提取权威龙头与角色映射 ──
        authoritative_score = 0.0
        auth_leader_code = ""
        auth_leader_name = ""
        auth_leader_pct = 0.0
        race_roles = {}
        race_scores = {}
        race_hints = {}

        if matched_sec_info:
            authoritative_score = float(matched_sec_info.get('score', 0.0))
            auth_leader_code = str(matched_sec_info.get('leader', '')).strip().zfill(6)
            auth_leader_name = str(matched_sec_info.get('leader_name', '')).strip()
            auth_leader_pct = float(matched_sec_info.get('leader_pct', 0.0))

            for rc in matched_sec_info.get('race_candidates', []):
                c = str(rc.get('code', '')).strip().zfill(6)
                if c:
                    if rc.get('role'):
                        race_roles[c] = str(rc.get('role'))
                    if rc.get('score') is not None:
                        race_scores[c] = float(rc.get('score', 0.0))
                    if rc.get('hint') or rc.get('pattern_hint'):
                        race_hints[c] = str(rc.get('hint', rc.get('pattern_hint')))

            for fol in matched_sec_info.get('followers', []):
                c = str(fol.get('code', '')).strip().zfill(6)
                if c:
                    if fol.get('role') and c not in race_roles:
                        race_roles[c] = str(fol.get('role'))
                    if fol.get('score') is not None and c not in race_scores:
                        race_scores[c] = float(fol.get('score', 0.0))
                    if (fol.get('hint') or fol.get('pattern_hint')) and c not in race_hints:
                        race_hints[c] = str(fol.get('hint', fol.get('pattern_hint')))

        # ── 2. 计算动态涨幅与龙头标的 ──
        dynamic_leader_code = ""
        dynamic_leader_name = ""
        max_pct = -999.0
        sum_pct = 0.0
        up_count = 0

        for r in rows:
            pct_val = _safe_float(r.get('pct', 0.0))
            if pct_val > max_pct:
                max_pct = pct_val
                dynamic_leader_code = r['code']
                dynamic_leader_name = r['name']
            if pct_val > 0.001:
                up_count += 1
            sum_pct += pct_val

        present_codes = {r['code'] for r in rows}
        if auth_leader_code and auth_leader_code != '000000' and auth_leader_code in present_codes:
            final_leader_code = auth_leader_code
            final_leader_name = auth_leader_name if auth_leader_name else dynamic_leader_name
        else:
            final_leader_code = dynamic_leader_code
            final_leader_name = dynamic_leader_name

        for r in rows:
            c = r['code']
            if c == final_leader_code:
                r['type'] = '👑 领涨龙头'
                r['score'] = max(98.0, race_scores.get(c, _safe_float(r.get('score', 75.0))))
                r['pattern'] = race_hints.get(c, '板块领涨核心龙头')
                if not final_leader_name or final_leader_name == '个股' or final_leader_name == c:
                    final_leader_name = r['name']
            elif c in race_roles:
                r['type'] = race_roles[c]
                if c in race_scores:
                    r['score'] = race_scores[c]
                if c in race_hints and race_hints[c]:
                    r['pattern'] = race_hints[c]

        # ── 3. 排序：龙头置顶，其余按得分/涨幅降序排列 ──
        def _get_sort_tuple(item):
            is_lead = 1 if item.get('code') == final_leader_code else 0
            is_champ = 1 if '👑' in str(item.get('type', '')) else 0
            is_pioneer = 1 if '🚀' in str(item.get('type', '')) else 0
            sc = _safe_float(item.get('score', 0.0))
            pct = _safe_float(item.get('pct', 0.0))
            return (is_lead, is_champ, is_pioneer, sc, pct)

        rows.sort(key=_get_sort_tuple, reverse=True)

        avg_pct = sum_pct / len(rows) if rows else 0.0
        if math.isnan(avg_pct) or math.isinf(avg_pct):
            avg_pct = 0.0

        limit_up_cnt = sum(1 for r in rows if _safe_float(r.get('pct', 0.0)) >= 9.5)
        if authoritative_score > 0:
            final_score = authoritative_score
        elif rows:
            live_score = min(100.0, max(0.0, 50.0 + avg_pct * 8.0 + (up_count / max(1, len(rows))) * 30.0 + min(15.0, limit_up_cnt * 5.0)))
            if math.isnan(live_score) or math.isinf(live_score):
                live_score = 50.0
            final_score = live_score
        else:
            final_score = 50.0

        # 获取龙头最新涨幅
        lead_row = next((r for r in rows if r['code'] == final_leader_code), None)
        lead_pct_display = lead_row['pct'] if lead_row else (auth_leader_pct if auth_leader_pct != 0.0 else max_pct)
        if lead_pct_display <= -900.0:
            lead_pct_display = 0.0
            
        leader_str = f"{final_leader_name} ({final_leader_code}) [{lead_pct_display:+.2f}%]" if final_leader_code else "--"

        meta = {
            'status': '✅ 实时在线更新 (TDX API直连 + 快照对齐)',
            'count': len(rows),
            'up_count': up_count,
            'avg_pct': round(avg_pct, 2)
        }

        return rows, round(final_score, 1), leader_str, meta
