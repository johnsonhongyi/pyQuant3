# -*- coding: utf-8 -*-
"""
ATS Sector Detail Dialog
Displays all constituent stocks of a given sector from the bidding session data.
"""

import os
import json
import zlib
import re
import time
import datetime
import urllib.request
from typing import List, Dict, Tuple, Optional, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QApplication, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut

from ats.ui.styles import NumericTableWidgetItem, setup_header_persistence, apply_dark_theme, CONFIG_FILE_LOCK
from sys_utils import get_app_root, get_conf_path
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)

# 纯直连 Opener (杜绝本地代理对国内行情 API 干扰)
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.sina.com.cn/'
}

def fetch_sina_stock_quotes_fast(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """批量通过新浪 A 股接口获取股票实时现价、涨跌幅、昨收、今开 (国内直连 50ms 极速响应)"""
    if not codes:
        return {}
    results = {}
    clean_codes = [str(c).strip().zfill(6) for c in codes if str(c).strip()]
    
    # 分批，每批最多 60 个
    batch_size = 60
    for i in range(0, len(clean_codes), batch_size):
        batch = clean_codes[i:i + batch_size]
        sina_codes = [f"{'sh' if c.startswith(('6', '9')) or c.startswith('688') else 'sz'}{c}" for c in batch]
        url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
        try:
            req = urllib.request.Request(url, headers=_HTTP_HEADERS)
            with _DIRECT_OPENER.open(req, timeout=2.5) as resp:
                content = resp.read().decode('gbk', errors='ignore')
                for line in content.strip().split('\n'):
                    if line and '="' in line:
                        parts = line.split('="')
                        sym = parts[0].split('hq_str_')[-1]
                        code = sym[2:]
                        fields = parts[1].replace('";', '').split(',')
                        if len(fields) >= 5:
                            name = fields[0].strip()
                            open_p = float(fields[1] or 0.0)
                            prev_close = float(fields[2] or 0.0)
                            curr_p = float(fields[3] or 0.0)
                            high_p = float(fields[4] or 0.0)
                            low_p = float(fields[5] or 0.0)
                            pct = (curr_p - prev_close) / prev_close * 100.0 if prev_close > 0 else 0.0
                            vol = float(fields[8] or 0.0) if len(fields) > 8 else 0.0
                            amount = float(fields[9] or 0.0) if len(fields) > 9 else 0.0
                            results[code] = {
                                'code': code,
                                'name': name,
                                'price': curr_p,
                                'prev_close': prev_close,
                                'open': open_p,
                                'high': high_p,
                                'low': low_p,
                                'pct': round(pct, 2),
                                'volume': vol,
                                'amount': amount
                            }
        except Exception as e:
            logger.debug(f"fetch_sina_stock_quotes_fast error: {e}")
    return results


# 经典行业中军龙头核心储备库 (覆盖全行业 15 大核心赛道)
FAMOUS_SECTOR_LEADERS = {
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

SECTOR_SYNONYMS = {
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


class SectorDetailWorker(QThread):
    """后台异步板块成分股发现与高频行情拉取工作线程 (绝不阻塞 UI 主线程)"""
    finished_signal = pyqtSignal(list, float, str, dict) # (rows, score, leader_info_str, meta_dict)

    def __init__(self, sector_name: str, member_codes: list = None, current_df = None, extra_cols: list = None, get_name_fn = None, parent=None):
        super().__init__(parent)
        self.sector_name = sector_name
        self.member_codes = member_codes or []
        self.current_df = current_df
        self.extra_cols = extra_cols or []
        self.get_name_fn = get_name_fn

    def run(self):
        try:
            target_codes = set()
            code_to_name = {}

            # 1. 优先使用外部传入的 member_codes
            if self.member_codes:
                for c in self.member_codes:
                    c_clean = str(c).strip().zfill(6)
                    if c_clean:
                        target_codes.add(c_clean)

            # 2. 如果 current_df 存在且包含 category 列，进行板块关键词模糊向量匹配
            if self.current_df is not None and not self.current_df.empty and 'category' in self.current_df.columns:
                try:
                    synonyms = [self.sector_name] + SECTOR_SYNONYMS.get(self.sector_name, [])
                    pattern = '|'.join([re.escape(s) for s in synonyms if s])
                    matched_series = self.current_df['category'].astype(str).str.contains(pattern, case=False, na=False)
                    df_matched = self.current_df[matched_series]
                    if not df_matched.empty:
                        for code_idx in df_matched.index[:60]:
                            c_clean = str(code_idx).strip().zfill(6)
                            if c_clean:
                                target_codes.add(c_clean)
                except Exception as ex:
                    logger.debug(f"current_df 板块匹配异常: {ex}")

            # 3. 若成分股不足，从著名经典中军龙头库 FAMOUS_SECTOR_LEADERS 补齐
            if len(target_codes) < 6:
                for key, st_list in FAMOUS_SECTOR_LEADERS.items():
                    if key == self.sector_name or key in self.sector_name or self.sector_name in key:
                        for c_code, def_name in st_list:
                            c_clean = str(c_code).strip().zfill(6)
                            target_codes.add(c_clean)
                            code_to_name[c_clean] = def_name
                        break

            # 4. 若仍不足，从 bidding_session_data 尝试补齐
            if len(target_codes) < 6:
                try:
                    ram_path = cct.get_ramdisk_path("bidding_session_data.json.gz")
                    if ram_path and os.path.exists(ram_path):
                        with open(ram_path, 'rb') as f:
                            data = json.loads(zlib.decompress(f.read()).decode('utf-8'))
                            sec_data = data.get('sector_data', {}).get(self.sector_name, {})
                            if sec_data:
                                l_c = str(sec_data.get('leader', '')).strip().zfill(6)
                                if l_c: target_codes.add(l_c)
                                for fol in sec_data.get('followers', []):
                                    f_c = str(fol.get('code', '')).strip().zfill(6)
                                    if f_c: target_codes.add(f_c)
                except Exception:
                    pass

            code_list = list(target_codes)
            if not code_list:
                self.finished_signal.emit([], 0.0, "--", {'status': '无成分股数据'})
                return

            # 5. 基础行情获取通道 1: TDX API 直连 (最高优先级，完全对齐新股/次新股策略体系)
            tdx_quote_map = {}
            tdx_alpha_map = {}
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                fetcher = TDXRealtimeFetcher.get_instance()
                
                # A. 批量极速获取 TDX 官方基础行情 (现价, 昨收, 涨跌幅, 开盘, 最高, 最低, 成交额)
                tdx_quotes = fetcher.get_security_quotes_safe(code_list, force=False)
                if tdx_quotes:
                    for q in tdx_quotes:
                        c_clean = str(q.get("code", "")).strip().zfill(6)
                        p = float(q.get("price", 0.0) or 0.0)
                        last_c = float(q.get("last_close", 0.0) or 0.0)
                        if c_clean and (p > 0 or last_c > 0):
                            pct = round((p - last_c) / last_c * 100.0, 2) if last_c > 0 else 0.0
                            tdx_quote_map[c_clean] = {
                                'price': p,
                                'prev_close': last_c,
                                'open': float(q.get("open", 0.0) or 0.0),
                                'high': float(q.get("high", 0.0) or 0.0),
                                'low': float(q.get("low", 0.0) or 0.0),
                                'amount': float(q.get("amount", 0.0) or 0.0),
                                'vol': float(q.get("vol", 0.0) or 0.0),
                                'pct': pct
                            }

                # B. 批量获取 TDX 高频 Alpha 盘口买点评级
                sec_map = {c: self.sector_name for c in code_list}
                mp_cache = {}
                n_map = {}
                if self.current_df is not None:
                    import pandas as pd
                    for c in code_list:
                        if c in self.current_df.index:
                            r_row = self.current_df.loc[c]
                            if isinstance(r_row, pd.DataFrame): r_row = r_row.iloc[0]
                            n_map[c] = str(r_row.get('name', c))
                            mp_cache[c] = {
                                'dff': float(r_row.get('dff', 0.0) or 0.0),
                                'dff2': float(r_row.get('DFF2', r_row.get('dff2', 0.0)) or 0.0),
                                'dff3': float(r_row.get('DFF3', r_row.get('dff3', 0.0)) or 0.0),
                                'rank': int(r_row.get('Rank', r_row.get('rank', 999)) or 999)
                            }
                alpha_quotes = fetcher.fetch_multi_stock_alpha_quotes(code_list, sec_map, mp_cache, n_map)
                for aq in alpha_quotes:
                    tdx_alpha_map[aq["code"]] = aq
            except Exception as e:
                logger.debug(f"TDX API 批量行情拉取降级: {e}")

            # 6. 基础行情获取通道 2: 新浪直连 50ms 极速备用兜底 (当 TDX 离线或缺失时补充)
            sina_quotes_map = {}
            missing_codes = [c for c in code_list if c not in tdx_quote_map or tdx_quote_map[c].get('price', 0) <= 0]
            if missing_codes:
                sina_quotes_map = fetch_sina_stock_quotes_fast(missing_codes)

            # 7. 组装行数据：动态列(dff, dff2, dff3, rank, 自定义列)全部从 df 获取，基础行情从 TDX API 获取
            rows = []
            leader_code = ""
            leader_name = ""
            max_pct = -999.0
            sum_pct = 0.0
            up_count = 0

            for code_str in code_list:
                name = code_to_name.get(code_str) or (self.get_name_fn(code_str) if self.get_name_fn else "个股")
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
                row = None

                # ── 💡 动态列与策略自定义列：100% 全部使用 df 获取 ──
                if self.current_df is not None:
                    import pandas as pd
                    if code_str in self.current_df.index:
                        row = self.current_df.loc[code_str]
                        if isinstance(row, pd.DataFrame): row = row.iloc[0]
                        name_df = str(row.get('name', '')).strip()
                        if name_df and name_df != "未知": name = name_df
                        try: pct_val = float(row.get('percent', row.get('pct', 0.0)))
                        except: pass
                        try: dff_val = float(row.get('dff', 0.0))
                        except: pass
                        try: rank_val = int(row.get('Rank', row.get('rank', 0)))
                        except: pass
                        try: dff2_val = float(row.get('DFF2', row.get('dff2', 0.0)))
                        except: pass
                        try: dff3_val = float(row.get('DFF3', row.get('dff3', 0.0)))
                        except: pass

                # ── 💡 基础数据：优先使用 TDX API 权威实时行情驱动 ──
                tq = tdx_quote_map.get(code_str)
                if tq and tq.get('price', 0) > 0:
                    pct_val = tq.get('pct', pct_val)
                    pattern_hint = f"现价 {tq.get('price'):.2f} | 昨收 {tq.get('prev_close'):.2f}"
                elif code_str in sina_quotes_map:
                    sq = sina_quotes_map[code_str]
                    pct_val = sq.get('pct', pct_val)
                    if not name or name == "个股" or name == code_str:
                        name = sq.get('name', name)
                    pattern_hint = f"现价 {sq.get('price'):.2f} | 昨收 {sq.get('prev_close'):.2f}"

                # 叠加 TDX 高频买点评级与形态特征
                aq = tdx_alpha_map.get(code_str)
                if aq:
                    pct_val = aq.get("pct", pct_val)
                    type_str = aq.get("buy_type", type_str)
                    score = aq.get("alpha_score", score)
                    vwap_dev = aq.get("vwap_dev_pct", 0.0)
                    vol_r = aq.get("vol_ratio", 1.0)
                    pattern_hint = f"{aq.get('buy_tag', '')} | VWAP偏离{vwap_dev:+.1f}% | 量比{vol_r:.1f}"

                # ── 💡 动态自定义列：从 df 严格映射提取 ──
                extra_dict = {}
                for ec in self.extra_cols:
                    val_raw = None
                    if row is not None:
                        for k in (ec, ec.lower(), ec.upper()):
                            if k in row:
                                val_raw = row[k]
                                break
                    extra_dict[ec] = cct.format_col_value(ec, val_raw)

                if pct_val > max_pct:
                    max_pct = pct_val
                    leader_code = code_str
                    leader_name = name

                if pct_val > 0.001:
                    up_count += 1
                sum_pct += pct_val

                rows.append({
                    'code': code_str,
                    'name': name,
                    'score': score,
                    'type': type_str,
                    'pct': pct_val,
                    'start_pct': round(pct_val - dff_val, 2),
                    'dff': dff_val,
                    'rank': rank_val,
                    'dff2': dff2_val,
                    'dff3': dff3_val,
                    'extra_cols': extra_dict,
                    'pattern': pattern_hint
                })

            # 动态标记 👑 领涨龙头
            for r in rows:
                if r['code'] == leader_code:
                    r['type'] = '👑 领涨龙头'
                    r['score'] = max(98.0, r['score'])
                    r['pattern'] = '板块领涨核心先锋'

            rows.sort(key=lambda x: (x['score'], x['pct']), reverse=True)

            # 计算板块整体强度得分
            avg_pct = sum_pct / len(rows) if rows else 0.0
            calc_score = min(100.0, max(0.0, 50.0 + avg_pct * 8.0 + (up_count / len(rows)) * 30.0))

            leader_str = f"{leader_name} ({leader_code}) [{max_pct:+.2f}%]"
            meta = {
                'status': '✅ 实时在线更新 (新浪50ms直连 + TDX秒级)',
                'count': len(rows),
                'up_count': up_count,
                'avg_pct': avg_pct
            }
            self.finished_signal.emit(rows, round(calc_score, 1), leader_str, meta)
        except Exception as e:
            logger.error(f"SectorDetailWorker run error: {e}")
            self.finished_signal.emit([], 0.0, "--", {'status': f'⚠️ 更新异常: {e}'})
        
def get_sector_extra_cols():
    """获取板块明细追加的动态自定义列（排除基础列已有的字段）"""
    try:
        from JohnsonUtil import commonTips as cct
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

def get_sector_table_headers(extra_cols=None):
    if extra_cols is None:
        extra_cols = get_sector_extra_cols()
    try:
        from JohnsonUtil import commonTips as cct
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}
    base_pre = ["代码", "名称", "得分", "类型", "涨幅", "起点", "DFF", "Rank", "DFF2", "DFF3"]
    extra_headers = [col_map.get(c, c) for c in extra_cols]
    base_post = ["形态提示"]
    return base_pre + extra_headers + base_post


class ATSSectorDetailDialog(QDialog):
    """
    ATS 强势板块成分股明细与高频量化实时弹窗
    具备：新浪直连 50ms 真实股价 + TDX 秒级盘口 + 自动定时轮询 + 手动 F5 强制刷新
    """
    def __init__(self, sector_name, linkage_cb=None, double_click_cb=None, member_codes=None, parent=None):
        super().__init__(None) # [🚀 独立顶层解耦] 传入 None 剥离 Win32 HWND Owner 从属关系
        self._py_parent = parent
        self.sector_name = sector_name
        self.linkage_cb = linkage_cb
        self.double_click_cb = double_click_cb
        self.member_codes = member_codes or []
        self.extra_cols = get_sector_extra_cols()
        self._worker = None
        self._is_rendering = False
        
        self.setWindowTitle(f"🔥 {sector_name} 板块明细 (实时高频行情)")
        self.resize(780, 520)
        
        # 继承统一的 ATS 暗黑 Mode QSS 风格
        apply_dark_theme(self)
        
        self.setStyleSheet(self.styleSheet() + """
            QDialog {
                background-color: #121214;
                color: #e2e2e5;
            }
            QTableWidget {
                background-color: #18181c;
                alternate-background-color: #1c1c22;
                color: #e2e2e5;
                gridline-color: #282830;
                selection-background-color: #2e3b4e;
                selection-color: #00ff88;
                border: 1px solid #282830;
                font-family: 'Microsoft YaHei', sans-serif;
            }
            QHeaderView::section {
                background-color: #1a1a1f;
                color: #aad4ff;
                font-weight: bold;
                border: 1px solid #2e2e36;
                padding: 3px 6px;
            }
            QTableCornerButton::section {
                background-color: #1a1a1f;
                border: 1px solid #2e2e36;
            }
        """)
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags |= Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)

        self._init_ui()
        self._start_auto_refresh_timer()
        self.refresh_data(force=True)
        self._restore_geometry()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # 1. 顶部 Header 状态栏与操作区域
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background-color: #18181c; border: 1px solid #282830; border-radius: 4px; padding: 4px 8px; }")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(4, 4, 4, 4)
        header_layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.title_lbl = QLabel(f"板块名称: {self.sector_name}")
        self.title_lbl.setStyleSheet("font-size: 12.5pt; font-weight: bold; color: #00ff88;")
        top_row.addWidget(self.title_lbl)

        self.score_lbl = QLabel("强度得分: --")
        self.score_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #ff9900; margin-left: 10px;")
        top_row.addWidget(self.score_lbl)

        top_row.addStretch()

        self.lbl_status = QLabel("📡 状态: 初始化...")
        self.lbl_status.setStyleSheet("color: #00e5ff; font-size: 8.5pt; margin-right: 6px;")
        top_row.addWidget(self.lbl_status)

        self.lbl_update_time = QLabel("最后更新: --:--:--")
        self.lbl_update_time.setStyleSheet("color: #888888; font-size: 8.5pt;")
        top_row.addWidget(self.lbl_update_time)

        header_layout.addLayout(top_row)
        
        # Stats info (成员数与领涨标的)
        self.stats_lbl = QLabel("成员数: 0 | 领涨标的: --")
        self.stats_lbl.setStyleSheet("font-size: 9.5pt; color: #aad4ff;")
        header_layout.addWidget(self.stats_lbl)

        layout.addWidget(header_frame)
        
        # 2. Table of members
        self.table = QTableWidget()
        headers = get_sector_table_headers(self.extra_cols)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        
        header_view = self.table.horizontalHeader()
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_view.setStretchLastSection(False)
        
        self.table.setAlternatingRowColors(True)
        self.table.setCornerButtonEnabled(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        default_widths = [60, 75, 48, 65, 68, 68, 58, 45, 58, 58] + [55] * len(self.extra_cols) + [100]
        setup_header_persistence(self.table, "ats_sector_detail_table_v2", default_widths=default_widths)
        
        self.table.itemClicked.connect(self.on_item_clicked)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.currentItemChanged.connect(self.on_current_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        
        # 3. Bottom action bar
        btn_layout = QHBoxLayout()

        self.btn_refresh = QPushButton("🔄 强制刷新数据")
        self.btn_refresh.setStyleSheet("""
            QPushButton { background-color: #1976d2; color: #ffffff; border: 1px solid #2196f3;
                          border-radius: 4px; padding: 4px 12px; font-weight: bold; font-size: 9pt; }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:disabled { background-color: #333333; color: #777777; border-color: #444444; }
        """)
        self.btn_refresh.clicked.connect(lambda: self.refresh_data(force=True))
        btn_layout.addWidget(self.btn_refresh)

        btn_dna = QPushButton("🧬 DNA审计")
        btn_dna.setStyleSheet("""
            QPushButton { background-color: #1b5e20; color: #a5d6a7; border: 1px solid #388e3c;
                          border-radius: 4px; padding: 4px 10px; font-weight: bold; font-size: 9pt; }
            QPushButton:hover { background-color: #2e7d32; }
        """)
        btn_dna.clicked.connect(self._run_dna_audit)
        btn_layout.addWidget(btn_dna)

        btn_layout.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("""
            QPushButton { background-color: #2a2e39; color: #d1d4dc; border: 1px solid #363c4e;
                          border-radius: 4px; padding: 4px 14px; font-size: 9pt; }
            QPushButton:hover { background-color: #363c4e; color: #ffffff; }
        """)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        # 4. 绑定 F5 键盘刷新快捷键
        self._f5_shortcut = QShortcut(QKeySequence("F5"), self)
        self._f5_shortcut.activated.connect(lambda: self.refresh_data(force=True))

    def _get_parent_mw(self):
        return getattr(self, '_py_parent', None) or self.parent()

    def _restore_geometry(self):
        """从 window_config.json 恢复弹窗位置与大小"""
        try:
            from ats.ui.styles import load_config_node
            geom = load_config_node("ats_sector_detail_dialog_geom")
            if geom:
                from PyQt6.QtCore import QByteArray
                self.restoreGeometry(QByteArray.fromHex(geom.encode('utf-8')))
        except Exception:
            pass

    def _save_geometry(self):
        """原子写盘持久化弹窗位置与大小至 window_config.json"""
        try:
            from ats.ui.styles import save_config_node
            hex_data = self.saveGeometry().toHex().data().decode('utf-8')
            save_config_node("ats_sector_detail_dialog_geom", hex_data)
        except Exception:
            pass

    def accept(self):
        """OK/关闭按钮同样触发持久化"""
        self._save_geometry()
        super().accept()

    def _start_auto_refresh_timer(self):
        """启动后台定时自动静默更新 (盘中 15 秒轮询，休市 60 秒轮询)"""
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(lambda: self.refresh_data(force=False))
        self._auto_timer.start(15000)

    def refresh_data(self, force: bool = False):
        """异步拉取板块成分股最新实时高频行情与特征"""
        if self._worker and self._worker.isRunning():
            return

        if force:
            self.btn_refresh.setEnabled(False)
            self.btn_refresh.setText("⏳ 正在刷新...")

        # 解析 parent 链中的 current_df 与 get_name_fn
        # 递归从 parent 链与全局所有活跃窗口中搜寻全量策略 DataFrame (提取 dff, dff2, dff3, rank, custom_cols)
        get_name_fn = None
        current_df = None
        
        # 1. 优先从父窗口链检索
        p = self._get_parent_mw() or self.parent() or self.window()
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

        # 2. 若仍未找到，从 QApplication 所有顶层窗口中探测主策略窗口的 current_df
        if current_df is None:
            try:
                for top_w in QApplication.topLevelWidgets():
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

        self._worker = SectorDetailWorker(
            sector_name=self.sector_name,
            member_codes=self.member_codes,
            current_df=current_df,
            extra_cols=self.extra_cols,
            get_name_fn=get_name_fn,
            parent=self
        )
        self._worker.finished_signal.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self, rows: list, score: float, leader_str: str, meta: dict):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 强制刷新数据")

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.lbl_update_time.setText(f"最后更新: {now_str}")

        if hasattr(self, 'title_lbl'):
            self.title_lbl.setText(f"板块名称: {self.sector_name}")

        self.score_lbl.setText(f"强度得分: {score:.1f}")
        self.stats_lbl.setText(f"成员数: {len(rows)} | 领涨标的: {leader_str}")

        st_text = meta.get('status', '✅ 实时数据已同步')
        self.lbl_status.setText(f"📡 状态: {st_text}")
        if '⚠️' in st_text:
            self.lbl_status.setStyleSheet("color: #ffa500; font-size: 8.5pt; margin-right: 6px;")
        else:
            self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; margin-right: 6px;")

        self.setWindowTitle(f"🔥 {self.sector_name} 板块明细 (实时高频 {len(rows)}只)")
        self._render_rows(rows)

    def _render_rows(self, rows):
        self._is_rendering = True
        self.table.blockSignals(True)
        try:
            current_extra = get_sector_extra_cols()
            if not hasattr(self, 'extra_cols') or self.extra_cols != current_extra:
                self.extra_cols = current_extra
                headers = get_sector_table_headers(self.extra_cols)
                if self.table.columnCount() != len(headers):
                    self.table.setColumnCount(len(headers))
                    self.table.setHorizontalHeaderLabels(headers)
                    default_widths = [60, 75, 48, 65, 68, 68, 58, 45, 58, 58] + [55] * len(self.extra_cols) + [100]
                    setup_header_persistence(self.table, "ats_sector_detail_table_v2", default_widths=default_widths)

            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(rows))
            num_extra = len(self.extra_cols)
            
            for row_idx, r in enumerate(rows):
                # 0. Code
                code_item = QTableWidgetItem(str(r['code']))
                code_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 0, code_item)
                
                # 1. Name
                name_item = QTableWidgetItem(str(r['name']))
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 1, name_item)
                
                # 2. Score
                score_item = NumericTableWidgetItem(f"{r['score']:.1f}")
                score_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 2, score_item)
                
                # 3. Type
                type_item = QTableWidgetItem(str(r['type']))
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if '👑' in r['type']:
                    type_item.setForeground(QColor("#ffcc00")) # gold
                self.table.setItem(row_idx, 3, type_item)
                
                # 4. Pct
                pct_val = r['pct']
                pct_str = f"{pct_val:+.2f}%"
                pct_item = NumericTableWidgetItem(pct_str)
                pct_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if pct_val > 0.001:
                    pct_item.setForeground(QColor("#ff4444"))
                elif pct_val < -0.001:
                    pct_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 4, pct_item)
                
                # 5. Start Pct
                start_val = r['start_pct']
                start_str = f"{start_val:+.2f}%"
                start_item = NumericTableWidgetItem(start_str)
                start_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if start_val > 0.001:
                    start_item.setForeground(QColor("#ff4444"))
                elif start_val < -0.001:
                    start_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 5, start_item)
                
                # 6. DFF
                dff_val = r['dff']
                dff_str = f"{dff_val:+.2f}%"
                dff_item = NumericTableWidgetItem(dff_str)
                dff_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff_val > 0.001:
                    dff_item.setForeground(QColor("#ff4444"))
                elif dff_val < -0.001:
                    dff_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 6, dff_item)
                
                # 7. Rank
                rank_item = NumericTableWidgetItem(str(r['rank']))
                rank_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 7, rank_item)
                
                # 8. DFF2
                dff2_val = r['dff2']
                dff2_item = NumericTableWidgetItem(f"{dff2_val:+.2f}%")
                dff2_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff2_val > 0.001:
                    dff2_item.setForeground(QColor("#ff4444"))
                elif dff2_val < -0.001:
                    dff2_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 8, dff2_item)
                
                # 9. DFF3
                dff3_val = r['dff3']
                dff3_item = NumericTableWidgetItem(f"{dff3_val:+.2f}%")
                dff3_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff3_val > 0.001:
                    dff3_item.setForeground(QColor("#ff4444"))
                elif dff3_val < -0.001:
                    dff3_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 9, dff3_item)
                
                # 10 ~ 10 + num_extra - 1: Dynamic Extra Cols
                extra_data = r.get('extra_cols', {})
                for ei, ec in enumerate(self.extra_cols):
                    c_idx = 10 + ei
                    e_val = extra_data.get(ec, '--')
                    e_item = NumericTableWidgetItem(str(e_val))
                    e_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if str(e_val).startswith('+'):
                        e_item.setForeground(QColor("#ff4444"))
                    elif str(e_val).startswith('-'):
                        e_item.setForeground(QColor("#33cc5a"))
                    else:
                        e_item.setForeground(QColor("#e2e2e5"))
                    self.table.setItem(row_idx, c_idx, e_item)

                # Pattern (Last Column)
                pat_col_idx = 10 + num_extra
                pat_item = QTableWidgetItem(str(r['pattern'] or '--'))
                pat_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, pat_col_idx, pat_item)
                
            self.table.setSortingEnabled(True)
            self.table.clearSelection()
        finally:
            self.table.blockSignals(False)
            self._is_rendering = False
            
    def on_item_clicked(self, item):
        if getattr(self, '_is_rendering', False) or self.table.signalsBlocked():
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.linkage_cb:
            code = code_item.text().strip()
            name = name_item.text().strip()
            if getattr(self, '_last_linked_code', None) != code:
                self._last_linked_code = code
                self.linkage_cb(code, name)
            
    def on_current_item_changed(self, current, previous):
        if getattr(self, '_is_rendering', False) or self.table.signalsBlocked():
            return
        if current and self.linkage_cb:
            row = current.row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                code = code_item.text().strip()
                name = name_item.text().strip()
                if getattr(self, '_last_linked_code', None) != code:
                    self._last_linked_code = code
                    self.linkage_cb(code, name)
                
    def on_item_double_clicked(self, item):
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.double_click_cb:
            self.double_click_cb(code_item.text().strip(), name_item.text().strip())

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else ""
        if not code:
            return

        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtGui import QAction
        from ats.ui.base_table import send_to_linkage

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                border: 1px solid #2e2e36;
                color: #e2e2e5;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c35;
                color: #ffffff;
            }
        """)

        # 🔄 强制刷新
        refresh_act = menu.addAction(f"🔄 强制刷新【{self.sector_name}】板块实时行情 (F5)")
        refresh_act.triggered.connect(lambda: self.refresh_data(force=True))

        menu.addSeparator()

        # 选中联动
        if self.linkage_cb:
            link_act = menu.addAction(f"⚡ 选中联动 ({code})")
            link_act.triggered.connect(lambda: self.linkage_cb(code, name))

        # 📈 调出 SBC 实盘分时走势
        sbc_act = menu.addAction(f"📈 调出 {name or code} SBC 实盘分时走势")
        def _open_sbc():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code)
        sbc_act.triggered.connect(_open_sbc)

        # 发送到异动联动
        pipe_act = menu.addAction(f"⚡ 发送到异动联动 ({code})")
        pipe_act.triggered.connect(lambda: send_to_linkage(code, name, self))

        menu.addSeparator()

        copy_code_act = menu.addAction("📋 复制代码")
        copy_code_act.triggered.connect(lambda: QApplication.clipboard().setText(code))
        copy_name_act = menu.addAction("📋 复制名称")
        copy_name_act.triggered.connect(lambda: QApplication.clipboard().setText(name))

        menu.addSeparator()
        from ats.ui.styles import auto_fit_columns_once
        fit_act = menu.addAction("↔️ 一键自适应全列宽")
        fit_act.triggered.connect(lambda: auto_fit_columns_once(self.table))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _run_dna_audit(self):
        """对板块内所有成员股（按表格顺序，最多20只）执行 DNA 审计。
        优先通过主程序 parent_app._run_dna_audit_batch，降级到本地 QtDnaAuditReportWindow。
        """
        rows = self.table.rowCount()
        if rows == 0:
            return

        # Collect all member stocks from the table (code in col 0, name in col 1)
        items = []
        for r in range(rows):
            c_it = self.table.item(r, 0)
            n_it = self.table.item(r, 1)
            if c_it and n_it:
                items.append((c_it.text().strip(), n_it.text().strip()))

        # Align with chart_widgets.py selection logic:
        #   multi-select  → all selected rows (up to 50)
        #   single-select → current row + next 19 rows (total ≤ 20)
        #   no selection  → first 20 rows of the table
        sel_rows = sorted(set(i.row() for i in self.table.selectedItems()))
        if len(sel_rows) > 1:
            target = [(self.table.item(r, 0).text().strip(),
                       self.table.item(r, 1).text().strip()) for r in sel_rows[:50]
                      if self.table.item(r, 0) and self.table.item(r, 1)]
        elif len(sel_rows) == 1:
            start = sel_rows[0]
            target = [(self.table.item(r, 0).text().strip(),
                       self.table.item(r, 1).text().strip())
                      for r in range(start, min(start + 20, rows))
                      if self.table.item(r, 0) and self.table.item(r, 1)]
        else:
            target = items[:20]

        code_to_name = {c: n for c, n in target if c}
        if not code_to_name:
            return

        # Try main app first
        main_app = getattr(self.parent(), 'parent_app', None)
        if not main_app:
            main_app = getattr(self.window(), 'parent_app', None)
        if not main_app:
            main_app = getattr(QApplication.instance(), 'parent_app', None)

        if main_app and hasattr(main_app, '_run_dna_audit_batch'):
            if hasattr(main_app, 'tk_dispatch_queue'):
                _cn = dict(code_to_name)
                main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
            else:
                main_app._run_dna_audit_batch(code_to_name)
            return

        # ATSMainWindow or any Qt window with _run_dna_audit_batch
        win = self.window()
        if hasattr(win, '_run_dna_audit_batch'):
            win._run_dna_audit_batch(code_to_name)
            return

        # Local PyQt6 fallback (packaged env)
        try:
            from backtest_feature_auditor import audit_multiple_codes
            from ats.ui.multi_period_dialog import QtDnaAuditReportWindow
            from PyQt6.QtCore import Qt as _Qt
            QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            # 尝试从 parent 链或活跃窗口中获取包含自定义列的 DataFrame
            _period_data = None
            try:
                p = self.parent() or self.window()
                while p:
                    for attr in ('_last_flat_df', 'last_result_df', 'flat_df', 'result_df', 'df_all', 'current_df', 'top_now'):
                        df_cand = getattr(p, attr, None)
                        if df_cand is not None and not df_cand.empty:
                            _period_data = df_cand
                            break
                    if _period_data is not None:
                        break
                    p = p.parent() if hasattr(p, 'parent') and callable(p.parent) else None
            except Exception:
                pass
            summaries = audit_multiple_codes(
                list(code_to_name.keys()),
                end_date=None,
                code_to_name=code_to_name,
                progress_callback=None,
                resample='d',
                period_data=_period_data
            )
            if summaries:
                self._dna_audit_win = QtDnaAuditReportWindow(
                    summaries, parent=self.window(), end_date=None, resample='d'
                )
                self._dna_audit_win.show()
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "DNA 审计", "没有产生审计数据或结论。")
        except Exception as e:
            print(f"[ATSSectorDetailDialog] DNA audit local fallback failed: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def closeEvent(self, event):
        self._save_geometry()
        # Save header state of the table
        if hasattr(self.table, 'save_column_widths'):
            try:
                self.table.save_column_widths()
            except Exception:
                pass
        super().closeEvent(event)
