# -*- coding: utf-8 -*-
import os
import shutil
import requests
import pandas as pd
import time
import json
import re
from typing import Dict, Any, Optional
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct
import hashlib
# logger = LoggerFactory.getLogger(name="scraper_55188")
logger = LoggerFactory.getLogger()
CFG = cct.GlobalConfig()
win10_ramdisk_triton = CFG.get_path("win10_ramdisk_triton")
if re.fullmatch(r"[A-Z]:", win10_ramdisk_triton, re.I):
    win10_ramdisk_triton = win10_ramdisk_triton + "\\"
CACHE_FILE = os.path.join(win10_ramdisk_triton, "cache_55188_snapshot.pkl")
FP_FILE    = os.path.join(win10_ramdisk_triton, "cache_55188_fp.json")

# =========================
# 内存级缓存（模块级）
# =========================
_MEM_CACHE_DF: Optional[pd.DataFrame] = None
_MEM_CACHE_FP: Optional[dict] = None
_MEM_CACHE_TS: float = 0.0

def load_cache() -> pd.DataFrame:
    global _MEM_CACHE_DF

    if _MEM_CACHE_DF is not None and not _MEM_CACHE_DF.empty:
        return _MEM_CACHE_DF

    if not os.path.exists(CACHE_FILE):
        return pd.DataFrame()

    try:
        df = pd.read_pickle(CACHE_FILE)
        _MEM_CACHE_DF = df
        return df
    except Exception as e:
        logger.error(f"load_cache corrupted, ignored: {e}")
        try:
            os.remove(CACHE_FILE)
        except Exception:
            pass
        return pd.DataFrame()

def save_cache(df: pd.DataFrame, persist: bool = True) -> bool:
    """
    Returns:
        True  -> 写入成功（内存 + 磁盘）
        False -> 磁盘写入失败（内存有效，但不应推进指纹）
    """
    global _MEM_CACHE_DF, _MEM_CACHE_TS

    if df is None or df.empty:
        logger.warning("save_cache skipped: empty df")
        return False

    # 1️⃣ 内存先更新（进程内可用）
    _MEM_CACHE_DF = df
    _MEM_CACHE_TS = time.time()

    if not persist:
        return True

    try:
        # 2️⃣ 空间检查（非常关键，避免 pickle 卡死）
        disk = shutil.disk_usage(os.path.dirname(CACHE_FILE) or ".")
        if disk.free < 50 * 1024 * 1024:  # 50MB safety
            raise OSError("Disk space insufficient")

        # 3️⃣ 以写模式打开并强制截断
        with open(CACHE_FILE, "wb") as f:
            df.to_pickle(f)
            f.flush()
            os.fsync(f.fileno())

        return True

    except Exception as e:
        logger.error(f"save_cache failed: {e}")

        # 4️⃣ 写失败时，主动删除“可能损坏”的文件
        try:
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
        except Exception:
            pass

        return False


def load_fp() -> dict:
    global _MEM_CACHE_FP

    if _MEM_CACHE_FP is not None:
        return _MEM_CACHE_FP

    if os.path.exists(FP_FILE):
        try:
            with open(FP_FILE, 'r', encoding='utf-8') as f:
                _MEM_CACHE_FP = json.load(f)
                return _MEM_CACHE_FP
        except Exception as e:
            logger.error(f"load_fp failed: {e}")

    _MEM_CACHE_FP = {}
    return _MEM_CACHE_FP

def save_fp(fp: dict, persist: bool = True):
    global _MEM_CACHE_FP

    if not isinstance(fp, dict):
        return

    _MEM_CACHE_FP = fp

    if persist:
        try:
            with open(FP_FILE, 'w', encoding='utf-8') as f:
                json.dump(fp, f)
        except Exception as e:
            logger.error(f"save_fp failed: {e}")


def df_fingerprint(df: pd.DataFrame, cols=None) -> str:
    if df.empty:
        return ""
    if cols is None:
        cols = ['code', 'price', 'change_pct', 'net_ratio']
    # df_zhuli = df[df['zhuli_rank'] <= 200].sort_values('zhuli_rank')
    # df_hot = df[df['hot_rank'] <= 100].sort_values('hot_rank')
    # df_theme = df[(df['theme_name'] != "") & (df['theme_date'] != "")]
    _df = df[cols].copy()
    _df = _df.sort_values('code')
    raw = _df.to_csv(index=False)
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def clean_text(text: str) -> str:
    """
    保留中文字符、常用标点和文字，去掉数字、特殊符号、URL、HTML
    """
    if not text:
        return ""
    # 去掉 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 去掉 URL
    text = re.sub(r'https?://\S+', '', text)
    # 只保留中文、中文标点和空格
    text = "".join(re.findall(r'[\u4e00-\u9fff。，！？；：、“”‘’（）—…《》【】]+', text))
    return text

class Scraper55188:
    """
    Scraper for 55188.cn real-time stock aggregated data.
    Enhanced to support full market (including GEM) and detailed reasoning.
    """
    
    EASTMONEY_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    THS_URL = "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_stock/a/hour/data.txt"
    UPCHINA_THEME_URL = "https://prx.upchina.com/json/specialTheme/getTSDataNewThemeByDate"
    UPCHINA_STOCK_URL = "https://gateway.upchina.com/json/stockextweb/stockExtDetail"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        # self.df_zhuli = None
        # self.df_hot = None
        # self.df_theme = None

    def fetch_eastmoney_zhuli(self, page_size: int = 5000) -> pd.DataFrame:
        """
        获取东方财富主力资金排名及全市场价格/涨幅
        fs: m:0+t:6 (深主), m:0+t:80 (深创), m:1+t:2 (沪主), m:1+t:23 (沪科)
        """
        params = {
            "fid": "f184",
            "po": "1",
            "pz": page_size,
            "pn": "1",
            "np": "1",
            "fields": "f2,f3,f12,f14,f100,f184,f225",
            # 标准全 A 股过滤字符串 (包含创业板 t:80 和科创板 t:23)
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23" 
        }
        try:
            resp = self.session.get(self.EASTMONEY_URL, params=params, timeout=10)
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
            if not items:
                logger.warning("Eastmoney API returned no data.")
                return pd.DataFrame()
            
            df = pd.DataFrame(items)
            rename_map = {
                "f12": "code",
                "f14": "name",
                "f184": "net_ratio", # 主力净占比
                "f225": "zhuli_rank", # 主力排名
                "f3": "change_pct",   # 涨跌幅 (%)
                "f2": "price",        # 现价
                "f100": "sector"      # 所属板块
            }
            df = df.rename(columns=rename_map)
            df = df[df['code'].str.isnumeric()]
            
            # 数值标准化：EM 返回的是乘以 100 后的值
            for col in ['price', 'change_pct', 'net_ratio']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0) / 100.0
                
            return df[['code', 'name', 'price', 'change_pct', 'net_ratio', 'zhuli_rank', 'sector']]
        except Exception as e:
            status = getattr(resp, "status_code", "N/A")
            text = ""
            try:
                text = resp.text[:200]
            except Exception:
                pass
            logger.warning(
                "fetch_theme_stocks failed | status=%s | resp=%s | err=%s",
                status,
                text,
                repr(e)
            )
            return pd.DataFrame()
        # except Exception as e:
        #     logger.error(f"Error fetching Eastmoney data: {e}")
        #     return pd.DataFrame()

    def fetch_ths_hotlist_full(self) -> pd.DataFrame:
        """
        获取同花顺人气热榜及其深度分析，并保留原始原始 item 数据
        """
        try:
            resp = self.session.get(self.THS_URL, timeout=10)
            data = resp.json()
            stock_list = data.get("data", {}).get("stock_list", [])
            if not stock_list:
                return pd.DataFrame()

            items = []
            for item in stock_list:
                raw_code = item.get("code", "")
                code = raw_code[-6:] if len(raw_code) >= 6 else raw_code

                # === hot_tag 解析 ===
                tags = []
                tag_obj = item.get("tag", {})
                if isinstance(tag_obj, dict):
                    concept_tags = tag_obj.get("concept_tag", [])
                    if isinstance(concept_tags, list):
                        tags.extend([str(t).strip() for t in concept_tags if t])
                    popularity_tag = tag_obj.get("popularity_tag")
                    if popularity_tag:
                        tags.append(str(popularity_tag).strip())
                hot_tag_str = ",".join(tags)  # 始终用逗号分隔

                # === 组合详细理由 ===
                title = item.get("analyse_title", "").strip()
                reason = item.get("analyse", "").replace("<br>", "\n").strip()
                reason = re.sub(r'<[^>]+>', '', reason)
                full_reason = f"【{title}】\n{reason}" if title else reason

                items.append({
                    "code": code,
                    "name": item.get("name", ""),
                    "hot_rank": item.get("order"),
                    "hot_tag": hot_tag_str,
                    "hot_reason": full_reason,
                    "raw_item": item  # 保留原始 item 数据，便于 debug 或后续扩展
                })

            df_hot = pd.DataFrame(items)

            # 保证 hot_tag 和 hot_reason 列存在，即使为空
            for col in ["hot_tag", "hot_reason"]:
                if col not in df_hot.columns:
                    df_hot[col] = ""

            return df_hot

        except Exception as e:
            status = getattr(resp, "status_code", "N/A")
            text = ""
            try:
                text = resp.text[:200]
            except Exception:
                pass
            logger.warning(
                "fetch_ths_hotlist failed | status=%s | resp=%s | err=%s",
                status,
                text,
                repr(e)
            )
            return pd.DataFrame()

    def fetch_ths_hotlist(self) -> pd.DataFrame:
        """
        获取同花顺人气热榜及其深度分析
        hot_reason 包含 analyse_title、analyse、topic、tag 中文信息
        HTML/URL/无用内容全部过滤
        """
        try:
            resp = self.session.get(self.THS_URL, timeout=10)
            data = resp.json()
            stock_list = data.get("data", {}).get("stock_list", [])
            if not stock_list:
                return pd.DataFrame()

            items = []
            for item in stock_list:
                # === 代码 ===
                raw_code = item.get("code", "")
                code = raw_code[-6:] if len(raw_code) >= 6 else raw_code

                # === 热榜标签 hot_tag ===
                tags = []
                tag_obj = item.get("tag", {})
                if isinstance(tag_obj, dict):
                    concept_tags = tag_obj.get("concept_tag", [])
                    if isinstance(concept_tags, list):
                        tags.extend([str(t).strip() for t in concept_tags if t])
                    popularity_tag = tag_obj.get("popularity_tag")
                    if popularity_tag:
                        tags.append(str(popularity_tag).strip())
                hot_tag_str = ",".join(tags)

                # === 分析信息 analyse ===
                title = item.get("analyse_title", "").strip()
                reason = item.get("analyse", "").replace("<br>", "\n").strip()
                # 去掉 HTML 标签、URL，只保留中文和数字标点
                reason = re.sub(r'<[^>]+>', '', reason)
                reason = re.sub(r'http\S+', '', reason)
                reason = re.sub(r'[^\u4e00-\u9fff0-9a-zA-Z：：,.、\n]', '', reason)
                full_reason = f"【{title}】\n{reason}" if title else reason

                # === topic 信息 ===
                topic = item.get("topic")
                topic_info = ""
                if isinstance(topic, dict):
                    t_title = topic.get("title", "").strip()
                    if t_title:
                        topic_info = f"【主题】{t_title}"

                # === tag 信息（其他标签） ===
                other_tags = []
                if isinstance(tag_obj, dict):
                    for k in ['industry_tag', 'other_tag']:
                        vals = tag_obj.get(k, [])
                        if isinstance(vals, list):
                            other_tags.extend([str(v).strip() for v in vals if v])
                other_tags_str = "、".join(other_tags)

                # === 整合 hot_reason ===
                combined_reason_parts = [full_reason]
                if topic_info:
                    combined_reason_parts.append(topic_info)
                if other_tags_str:
                    combined_reason_parts.append(f"【其他标签】{other_tags_str}")
                hot_reason_final = "\n\n".join([p for p in combined_reason_parts if p])

                items.append({
                    "code": code,
                    "name": item.get("name", ""),
                    "hot_rank": item.get("order"),
                    "hot_tag": hot_tag_str,
                    "hot_reason": hot_reason_final
                })

            df_hot = pd.DataFrame(items)

            # 保证列存在，即使为空
            for col in ["hot_tag", "hot_reason"]:
                if col not in df_hot.columns:
                    df_hot[col] = ""

            return df_hot

        except Exception as e:
            status = getattr(resp, "status_code", "N/A")
            text = ""
            try:
                text = resp.text[:200]
            except Exception:
                pass
            logger.warning(
                "fetch_ths_hotlist_clean failed | status=%s | resp=%s | err=%s",
                status,
                text,
                repr(e)
            )
            return pd.DataFrame()


    # def fetch_ths_hotlist(self) -> pd.DataFrame:
    #     """
    #     获取同花顺人气热榜及其深度分析
    #     """
    #     try:
    #         resp = self.session.get(self.THS_URL, timeout=10)
    #         data = resp.json()
    #         stock_list = data.get("data", {}).get("stock_list", [])
    #         if not stock_list:
    #             return pd.DataFrame()

    #         items = []
    #         for item in stock_list:
    #             raw_code = item.get("code", "")
    #             code = raw_code[-6:] if len(raw_code) >= 6 else raw_code

    #             # === hot_tag 解析 ===
    #             tags = []
    #             tag_obj = item.get("tag", {})
    #             if isinstance(tag_obj, dict):
    #                 concept_tags = tag_obj.get("concept_tag", [])
    #                 if isinstance(concept_tags, list):
    #                     tags.extend([str(t).strip() for t in concept_tags if t])
    #                 popularity_tag = tag_obj.get("popularity_tag")
    #                 if popularity_tag:
    #                     tags.append(str(popularity_tag).strip())
    #             hot_tag_str = ",".join(tags)  # 始终用逗号分隔

    #             # === 组合详细理由 ===
    #             title = item.get("analyse_title", "").strip()
    #             reason = item.get("analyse", "").replace("<br>", "\n").strip()
    #             reason = re.sub(r'<[^>]+>', '', reason)
    #             full_reason = f"【{title}】\n{reason}" if title else reason

    #             items.append({
    #                 "code": code,
    #                 "name": item.get("name", ""),
    #                 "hot_rank": item.get("order"),
    #                 "hot_tag": hot_tag_str,
    #                 "hot_reason": full_reason
    #             })

    #         df_hot = pd.DataFrame(items)

    #         # 保证 hot_tag 列存在，即使为空
    #         if "hot_tag" not in df_hot.columns:
    #             df_hot["hot_tag"] = ""

    #         return df_hot

    #     except Exception as e:
    #         status = getattr(resp, "status_code", "N/A")
    #         text = ""
    #         try:
    #             text = resp.text[:200]
    #         except Exception:
    #             pass
    #         logger.warning(
    #             "fetch_ths_hotlist failed | status=%s | resp=%s | err=%s",
    #             status,
    #             text,
    #             repr(e)
    #         )
    #         return pd.DataFrame()


    # def fetch_ths_hotlist_old(self) -> pd.DataFrame:
    #     """
    #     获取同花顺人气热榜及其深度分析
    #     """
    #     try:
    #         resp = self.session.get(self.THS_URL, timeout=10)
    #         data = resp.json()
    #         stock_list = data.get("data", {}).get("stock_list", [])
    #         if not stock_list: return pd.DataFrame()
    #         items = []
    #         for item in stock_list:
    #             raw_code = item.get("code", "")
    #             code = raw_code[-6:] if len(raw_code) >= 6 else raw_code
                
    #             tags = []
    #             tag_obj = item.get("tag", {})
    #             if isinstance(tag_obj, dict):
    #                 c_tags = tag_obj.get("concept_tag", [])
    #                 if isinstance(c_tags, list): tags.extend(c_tags)
    #                 p_tag = tag_obj.get("popularity_tag")
    #                 if p_tag: tags.append(p_tag)
                
    #             # 组合详细理由
    #             title = item.get("analyse_title", "").strip()
    #             reason = item.get("analyse", "").replace("<br>", "\n").strip()
    #             reason = re.sub(r'<[^>]+>', '', reason)
    #             full_reason = f"【{title}】\n{reason}" if title else reason
                
    #             items.append({
    #                 "code": code,
    #                 "name": item.get("name", ""),
    #                 "hot_rank": item.get("order"), 
    #                 "hot_tag": ",".join(tags),
    #                 "hot_reason": full_reason
    #             })
            
    #         return pd.DataFrame(items)
    #     except Exception as e:
    #         status = getattr(resp, "status_code", "N/A")
    #         text = ""
    #         try:
    #             text = resp.text[:200]
    #         except Exception:
    #             pass
    #         logger.warning(
    #             "fetch_theme_stocks failed | status=%s | resp=%s | err=%s",
    #             status,
    #             text,
    #             repr(e)
    #         )
    #         return pd.DataFrame()



    def fetch_concept_mining_themes(self, count: int = 15) -> list:
        """
        获取优品热门题材列表
        """
        payload = {"stReq": {"uiStart": 0, "uiCount": count}}
        try:
            resp = self.session.post(
                self.UPCHINA_THEME_URL,
                json=payload,
                timeout=10
            )
            resp.raise_for_status()

            data = resp.json()
            return data.get("stRsp", {}).get("vThemeData", [])

        except Exception as e:
            status = getattr(resp, "status_code", "N/A")
            text = ""
            try:
                text = resp.text[:200]
            except Exception:
                pass

            logger.warning(
                "fetch_concept_mining_themes failed | status=%s | count=%s | resp=%s | err=%s",
                status,
                count,
                text,
                repr(e)
            )
            return []

    def parse_belong_gn(self,gn_str: str):
        """
        1##884164##多元金融@@1##884118##教育培训
        """
        res = []
        if not isinstance(gn_str, str):
            return res

        for part in gn_str.split("@@"):
            seg = part.split("##")
            if len(seg) >= 3:
                res.append({
                    "level": seg[0],
                    "gn_code": seg[1],
                    "gn_name": seg[2]
                })
        return res

    def extract_drive_logic(self,item: dict):
        for k in ("latestDrive", "driveContent", "position", "driveName"):
            val = item.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    def extract_ext_features(self,ext: dict):
        if not isinstance(ext, dict):
            return {}

        return {
            "bFirstZT": ext.get("bFirstZT"),
            "bCross250MA": ext.get("bCross250MA"),
            "zljm5Day": ext.get("zljm5Day"),
            "ztCnt5Days": ext.get("ztCnt5Days"),
            "niusan": ext.get("niusan"),
            "sAIFactor": ext.get("sAIFactor"),
        }


    def fetch_theme_stocks(self, plate_code: str) -> pd.DataFrame:
        """
        获取题材下个股及其 logic
        """
        payload = {
            "stReq": {
                "stHeader": { "sSource": "i-common/service/clue/getStockExtDetail" },
                "iType": 6,
                "sExt": plate_code,
                "iStart": 0,
                "iSize": 50,
                "bFromCache": True
            }
        }
        try:
            time.sleep(0.3)
            resp = self.session.post(self.UPCHINA_STOCK_URL, json=payload, timeout=10)
            data = resp.json()
            rsp = data.get("stRsp", {})
            stock_list = rsp.get("vDataSimple", []) or rsp.get("vData", [])
            
            items = []
            
            for item in stock_list:
                code = str(item.get("code", ""))[-6:]
                if not code.isnumeric():
                    continue
                logic = self.extract_drive_logic(item)
                gn_list = self.parse_belong_gn(item.get("belongGN", ""))
                ext_feat = self.extract_ext_features(item.get("extData", {}))

                items.append({
                    "code": code,
                    "name": item.get("name"),
                    "price": item.get("price"),
                    "chg": item.get("chg"),
                    "turnover": item.get("turnover"),

                    # 资金
                    "fMainBuy": item.get("fMainBuy"),
                    "fMainRatio": item.get("fMainRatio"),
                    "d5DayNetInflow": item.get("d5DayNetInflow"),

                    # 趋势
                    "d3DayChg": item.get("d3DayChg"),
                    "d5DayChg": item.get("d5DayChg"),
                    "d10DayChg": item.get("d10DayChg"),

                    # 逻辑
                    "drive_logic": logic,
                    "industry": item.get("sHyBlockName"),
                    "concepts": [g["gn_name"] for g in gn_list],

                    # ext
                    **ext_feat
                })
            return pd.DataFrame(items)
        except Exception as e:
            status = getattr(resp, "status_code", "N/A")
            text = ""
            try:
                text = resp.text[:200]
            except Exception:
                pass
            logger.warning(
                "fetch_theme_stocks failed | status=%s | resp=%s | err=%s",
                status,
                text,
                repr(e)
            )
            return []
    
    # def merge_theme_logic(self, df: pd.DataFrame) -> pd.DataFrame:
    #     """
    #     整合题材逻辑：个股驱动 / 行业定位 / 题材背景 / 市场概念
    #     """
    #     def merge_one(sub: pd.DataFrame) -> pd.Series:
    #         sub = sub.sort_values('theme_date', ascending=False)

    #         # === 1. 个股驱动（事件） ===
    #         drives = sub.get('drive_logic', pd.Series(dtype='object')).dropna().astype(str)
    #         drives = [d.strip() for d in drives if d.strip()]
    #         drives = list(dict.fromkeys(drives))

    #         # === 2. 行业 / 业务定位 ===
    #         industries = sub.get('industry', pd.Series(dtype='object')).dropna().astype(str)
    #         industries = list(dict.fromkeys([i.strip() for i in industries if i.strip()]))

    #         # === 3. 题材 / 宏观背景 ===
    #         themes = sub.get('theme_logic', pd.Series(dtype='object')).dropna().astype(str)
    #         themes = [t.strip() for t in themes if t.strip()]
    #         themes = list(dict.fromkeys(themes))

    #         # === 4. 市场概念 ===
    #         concepts_all = []
    #         if 'concepts' in sub.columns:
    #             for c in sub['concepts']:
    #                 if isinstance(c, list):
    #                     concepts_all.extend(c)
    #         concepts_all = list(dict.fromkeys([str(c).strip() for c in concepts_all if str(c).strip()]))

    #         blocks = []
    #         if drives:
    #             blocks.append("【个股驱动（事件）】: " + "\n".join(drives))
    #         if industries:
    #             blocks.append("【业务与行业定位】: " + " / ".join(industries))
    #         if themes:
    #             blocks.append("【题材 / 宏观背景】: " + "\n".join(themes))
    #         if concepts_all:
    #             blocks.append("【市场概念理解】: " + "、".join(concepts_all))

    #         return pd.Series({
    #             "theme_name": " / ".join(sub['theme_name'].dropna().astype(str).unique()),
    #             "theme_logic": "\n\n".join(blocks),
    #             "theme_date": sub['theme_date'].max()
    #         })

    #     return df.groupby('code', group_keys=False).apply(merge_one).reset_index()

    def merge_theme_logic(self, df: pd.DataFrame , debug = False) -> pd.DataFrame:
        debug_logs = []

        def merge_one(sub: pd.DataFrame,debug=debug) -> pd.Series:
            sub = sub.sort_values('theme_date', ascending=False)

            # === 1. 个股驱动（事件） ===
            drives = sub.get('drive_logic', pd.Series(dtype=str)).dropna().astype(str)
            drives = [d.strip() for d in drives if d.strip()]
            drives = list(dict.fromkeys(drives))

            # === 2. 行业 / 业务定位 ===
            industries = sub.get('industry', pd.Series(dtype=str)).dropna().astype(str)
            industries = [i.strip() for i in industries if i.strip()]
            industries = list(dict.fromkeys(industries))

            # === 3. 题材 / 宏观背景 ===
            themes = sub.get('theme_logic', pd.Series(dtype=str)).dropna().astype(str)
            themes = [t.strip() for t in themes if t.strip()]
            themes = list(dict.fromkeys(themes))

            # === 4. 市场概念 ===
            concepts_all = []
            if 'concepts' in sub.columns:
                for c in sub['concepts']:
                    if isinstance(c, list):
                        concepts_all.extend(c)
            concepts_all = list(dict.fromkeys([str(c).strip() for c in concepts_all if str(c).strip()]))

            # === 5. hot_tag ===
            hot_tags = []
            if 'hot_tag' in sub.columns:
                for t in sub['hot_tag']:
                    if isinstance(t, str) and t.strip():
                        hot_tags.append(t.strip())
            hot_tags = list(dict.fromkeys(hot_tags))  # 去重保序

            # 构造 theme_logic 块
            blocks = []
            if drives:
                # blocks.append("【个股驱动（事件）】: " + "\n".join(drives))
                drives_clean = [clean_text(d) for d in drives]
                blocks.append("".join(drives_clean))
            if industries:
                industries_clean = [clean_text(i) for i in industries]
                blocks.append("【业务与行业定位】: " + " / ".join(industries_clean))
                # blocks.append("【业务与行业定位】: " + " / ".join(industries))
            if themes:
                themes_clean = [clean_text(t) for t in themes]
                # blocks.append("【题材 / 宏观背景】: " + "\n".join(themes))
                blocks.append("【题材 / 宏观背景】: " + "\n".join(themes_clean))
            if concepts_all:
                # blocks.append("【市场概念理解】: " + "、".join(concepts_all))
                concepts_clean = [clean_text(c) for c in concepts_all]
                blocks.append("【市场概念理解】: " + "、".join(concepts_clean))

            # 构造 theme_name: hot_tag在最前面
            theme_name_parts = []
            if hot_tags:
                theme_name_parts.append(", ".join(hot_tags))  # 保留逗号
            theme_name_parts.extend(sub['theme_name'].dropna().astype(str).unique())
            if industries:
                theme_name_parts.extend(industries)
            theme_name_final = " / ".join(theme_name_parts)

            if debug:
                # 记录 debug 信息到列表    
                debug_logs.append({
                    'code': sub['code'].iloc[0],
                    'hot_tags': hot_tags,
                    'theme_name_parts': theme_name_parts,
                    'theme_logic_blocks': blocks
                })

            return pd.Series({
                "theme_name": theme_name_final,
                "theme_logic": "\n\n".join(blocks),
                "theme_date": sub['theme_date'].max()
            })

        df_merged = df.groupby('code', group_keys=False).apply(merge_one)

        if debug:
            # 输出所有 debug 信息
            for log_entry in debug_logs:
                print(f"\n=== CODE: {log_entry['code']} ===")
                print(f"hot_tags: {log_entry['hot_tags']}")
                print(f"theme_name_parts: {log_entry['theme_name_parts']}")
                print("theme_logic_blocks:")
                for b in log_entry['theme_logic_blocks']:
                    print(b)

        return df_merged



    def get_combined_data(self, force_full=False, count=30) -> pd.DataFrame:
        """
        聚合多维数据：主力、人气、题材逻辑
        """
        # 1. 抓取主力基础面数据
        df_zhuli = self.fetch_eastmoney_zhuli()
        if df_zhuli.empty:
            return load_cache()

        # 2. 缓存指纹
        new_fp = df_fingerprint(df_zhuli)
        fp_info = load_fp()
        old_fp = fp_info.get("fp")
        if not force_full and new_fp == old_fp:
            return load_cache()

        # 3. 抓取人气
        df_hot = self.fetch_ths_hotlist()

        # 4. 抓取题材与逻辑
        themes = self.fetch_concept_mining_themes(count=count)
        theme_dfs = []
        for theme in themes:
            p_code = theme.get("sPlateCode")
            if not p_code:
                continue

            df_t = self.fetch_theme_stocks(p_code)
            if df_t.empty:
                continue

            # 初始化列
            for col in ['theme_name', 'theme_logic', 'theme_date']:
                if col not in df_t.columns:
                    df_t[col] = ''

            df_t['theme_name'] = str(theme.get("sPlateName") or "")

            # 处理日期
            raw_date = (theme.get("effectiveTime") or theme.get("sEffectiveTime") or
                        theme.get("sDate") or theme.get("uiDate") or
                        theme.get("uiUpdateDate") or theme.get("sUpdateDate") or
                        theme.get("sDriveTime") or theme.get("sDriveDate") or
                        theme.get("sTime") or theme.get("dt") or theme.get("uiTime") or "")
            theme_date = ''
            try:
                s_date = str(raw_date).strip()
                if s_date.isdigit() and len(s_date) >= 10:
                    ts = int(s_date)
                    if len(s_date) == 13:
                        ts //= 1000
                    theme_date = time.strftime("%Y/%m/%d", time.localtime(ts))
                elif len(s_date) >= 8 and s_date[:8].isdigit():
                    theme_date = f"{s_date[:4]}/{s_date[4:6]}/{s_date[6:8]}"
                elif "/" in s_date or "-" in s_date:
                    m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s_date)
                    if m:
                        theme_date = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
            except Exception:
                theme_date = ''
            df_t['theme_date'] = theme_date or ''

            # 整合逻辑
            df_t['theme_logic'] = df_t.get('theme_logic', '').fillna('')
            for idx, row in df_t.iterrows():
                logic = row.get('theme_logic', '').strip()
                drive = theme.get("driveLogic", "").strip()
                if not logic and drive:
                    logic = f"【背景】{drive}"
                pos_logic = row.get('position', '').strip() if 'position' in row else ''
                if pos_logic:
                    logic = f"{logic} {pos_logic}".strip()
                df_t.at[idx, 'theme_logic'] = logic

            theme_dfs.append(df_t)

        df_theme = pd.concat(theme_dfs) if theme_dfs else pd.DataFrame()
        if not df_theme.empty:
            df_theme['theme_date'] = df_theme['theme_date'].replace('', '1970/01/01')

        # 5. 把 hot_tag join 进 df_theme
        if not df_hot.empty:
            df_hot_idx = df_hot.set_index('code')[['hot_tag', 'hot_reason']]
            df_theme = df_theme.join(df_hot_idx, on='code')

        # 6. 合并主题逻辑
        df_theme_unique = self.merge_theme_logic(df_theme)
        if 'theme_date' in df_theme_unique.columns:
            df_theme_unique['theme_date'] = df_theme_unique['theme_date'].replace('1970/01/01', '')

        # 7. 构建代码全集
        all_codes = set()
        for df in [df_zhuli, df_hot, df_theme_unique]:
            if not df.empty:
                if 'code' in df.columns:
                    all_codes.update(df['code'])
                else:
                    all_codes.update(df.index)
        if not all_codes:
            return pd.DataFrame()

        result = pd.DataFrame({'code': list(all_codes)}).set_index('code')

        # 注入主力
        if not df_zhuli.empty:
            result = result.join(df_zhuli.set_index('code'), how='left')

        # 注入人气
        if not df_hot.empty:
            df_hot_idx = df_hot.set_index('code')
            if 'name' not in result.columns:
                result['name'] = df_hot_idx['name']
            else:
                result['name'] = result['name'].fillna('').combine_first(df_hot_idx['name'])
            result = result.join(df_hot_idx[['hot_rank', 'hot_tag', 'hot_reason']], how='left', rsuffix='_hot')

        # 注入题材
        if not df_theme_unique.empty:
            result = result.join(df_theme_unique[['theme_name', 'theme_logic', 'theme_date']], how='left')

        # 8. 清洗默认值
        result['zhuli_rank'] = result.get('zhuli_rank', pd.Series(999, index=result.index)).fillna(999)
        result['hot_rank'] = result.get('hot_rank_hot', result.get('hot_rank', pd.Series(999, index=result.index))).fillna(999)
        result['price'] = result.get('price', pd.Series(0.0, index=result.index)).fillna(0.0)
        result['change_pct'] = result.get('change_pct', pd.Series(0.0, index=result.index)).fillna(0.0)

        for col in ['name', 'theme_name', 'theme_logic', 'theme_date', 'hot_tag', 'hot_reason', 'sector']:
            if col not in result.columns:
                result[col] = ''
            else:
                result[col] = result[col].fillna('')

        # 补位策略
        mask_theme_name = (result['theme_name'] == '') & (result['hot_tag'] != '')
        result.loc[mask_theme_name, 'theme_name'] = result.loc[mask_theme_name, 'hot_tag']
        mask_theme_logic = (result['theme_logic'] == '') & (result['hot_reason'] != '')
        result.loc[mask_theme_logic, 'theme_logic'] = result.loc[mask_theme_logic, 'hot_reason']

        result = result.reset_index()

        # 9. 缓存
        ok = save_cache(result, persist=True)
        if ok:
            save_fp({"fp": new_fp, "ts": time.time()}, persist=True)

        return result



    # def merge_theme_logic(self, df: pd.DataFrame) -> pd.DataFrame:
    #     def merge_one(sub: pd.DataFrame) -> pd.Series:
    #         sub = sub.sort_values('theme_date', ascending=False)

    #         # === 1. 个股驱动（事件） ===
    #         drives = sub.get('drive_logic', pd.Series(dtype=str)).dropna().astype(str)
    #         drives = [d.strip() for d in drives if d.strip()]
    #         drives = list(dict.fromkeys(drives))

    #         # === 2. 行业 / 业务定位 ===
    #         industries = sub.get('industry', pd.Series(dtype=str)).dropna().astype(str)
    #         industries = list(dict.fromkeys([i.strip() for i in industries if i.strip()]))

    #         # === 3. 原题材 / 宏观背景 ===
    #         themes = sub.get('theme_logic', pd.Series(dtype=str)).dropna().astype(str)
    #         themes = [t.strip() for t in themes if t.strip()]
    #         themes = list(dict.fromkeys(themes))

    #         # === 4. 市场概念 ===
    #         concepts_all = []
    #         if 'concepts' in sub.columns:
    #             for c in sub['concepts']:
    #                 if isinstance(c, list):
    #                     concepts_all.extend(c)
    #         concepts_all = list(dict.fromkeys([str(c).strip() for c in concepts_all if str(c).strip()]))

    #         # === 5. hot_tag ===
    #         hot_tags = []
    #         if 'hot_tag' in sub.columns:
    #             for ht in sub['hot_tag']:
    #                 if isinstance(ht, str) and ht.strip():
    #                     hot_tags.append(ht.strip())
    #             # 去重但保留逗号内原顺序
    #             hot_tags = list(dict.fromkeys(hot_tags))

    #         # === 构建 theme_logic 内容块 ===
    #         blocks = []
    #         if drives:
    #             blocks.append("【个股驱动（事件）】: " + "\n".join(drives))
    #         if industries:
    #             blocks.append("【业务与行业定位】: " + " / ".join(industries))
    #         if themes:
    #             blocks.append("【题材 / 宏观背景】: " + "\n".join(themes))
    #         if concepts_all:
    #             blocks.append("【市场概念理解】: " + "、".join(concepts_all))

    #         # === 构建 theme_name ===
    #         name_parts = []

    #         # hot_tag 放最前面，逗号保留
    #         if hot_tags:
    #             name_parts += hot_tags

    #         # 原 theme_name
    #         name_parts += list(sub['theme_name'].dropna().astype(str).unique())

    #         # industry 内容追加
    #         if industries:
    #             name_parts += industries

    #         # 去重保序
    #         seen = set()
    #         name_parts = [x for x in name_parts if not (x in seen or seen.add(x))]

    #         theme_name_final = " / ".join(name_parts)

    #         return pd.Series({
    #             "theme_name": theme_name_final,
    #             "theme_logic": "\n\n".join(blocks),
    #             "theme_date": sub['theme_date'].max()
    #         })

    #     return df.groupby('code', group_keys=False).apply(merge_one)


    # def get_combined_data(self, force_full=False, count=30) -> pd.DataFrame:
    #     """
    #     聚合多维数据：主力、人气、题材逻辑
    #     """

    #     # 1. 抓取主力基础面数据
    #     df_zhuli = self.fetch_eastmoney_zhuli()
    #     if df_zhuli.empty:
    #         return load_cache()

    #     # 2. 缓存指纹
    #     new_fp = df_fingerprint(df_zhuli)
    #     fp_info = load_fp()
    #     old_fp = fp_info.get("fp")
    #     if not force_full and new_fp == old_fp:
    #         logger.info("Market snapshot unchanged, use cached data.")
    #         return load_cache()

    #     # 3. 抓取人气数据
    #     df_hot = self.fetch_ths_hotlist()

    #     # 4. 抓取题材与逻辑
    #     themes = self.fetch_concept_mining_themes(count=count)
    #     theme_dfs = []
    #     for theme in themes:
    #         p_code = theme.get("sPlateCode")
    #         if not p_code:
    #             continue

    #         df_t = self.fetch_theme_stocks(p_code)
    #         if df_t.empty:
    #             continue

    #         # 初始化必要列
    #         for col in ['theme_name', 'theme_logic', 'theme_date']:
    #             if col not in df_t.columns:
    #                 df_t[col] = ''

    #         # 设置题材名
    #         df_t['theme_name'] = str(theme.get("sPlateName") or "")

    #         # 处理题材日期
    #         raw_date = (theme.get("effectiveTime") or theme.get("sEffectiveTime") or
    #                     theme.get("sDate") or theme.get("uiDate") or
    #                     theme.get("uiUpdateDate") or theme.get("sUpdateDate") or
    #                     theme.get("sDriveTime") or theme.get("sDriveDate") or
    #                     theme.get("sTime") or theme.get("dt") or theme.get("uiTime") or "")
    #         theme_date = ''
    #         try:
    #             s_date = str(raw_date).strip()
    #             if s_date.isdigit() and len(s_date) >= 10:
    #                 ts = int(s_date)
    #                 if len(s_date) == 13: ts //= 1000
    #                 theme_date = time.strftime("%Y/%m/%d", time.localtime(ts))
    #             elif len(s_date) >= 8 and s_date[:8].isdigit():
    #                 theme_date = f"{s_date[:4]}/{s_date[4:6]}/{s_date[6:8]}"
    #             elif "/" in s_date or "-" in s_date:
    #                 m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s_date)
    #                 if m:
    #                     theme_date = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    #         except Exception:
    #             theme_date = ''
    #         df_t['theme_date'] = theme_date or ''
    #         # 整合逻辑：vLatestData > position > driveLogic
    #         df_t['theme_logic'] = df_t.get('theme_logic', '').fillna('')
    #         for idx, row in df_t.iterrows():
    #             logic = row.get('theme_logic', '').strip()
    #             # driveLogic 补充逻辑
    #             drive = theme.get("driveLogic", "").strip()
    #             if not logic and drive:
    #                 logic = f"【背景】{drive}"
    #             # position 补充逻辑
    #             pos_logic = row.get('position', '').strip() if 'position' in row else ''
    #             if pos_logic:
    #                 logic = f"{logic} {pos_logic}".strip()
    #             df_t.at[idx, 'theme_logic'] = logic

    #         theme_dfs.append(df_t)

    #     df_theme = pd.concat(theme_dfs) if theme_dfs else pd.DataFrame()
    #     if not df_theme.empty:
    #         df_theme['theme_date'] = df_theme['theme_date'].replace('', '1970/01/01')

    #     # 5. 确立所有股票代码全集
    #     all_codes = set()
    #     for df in [df_zhuli, df_hot, df_theme]:
    #         if not df.empty:
    #             all_codes.update(df['code'])
    #     if not all_codes:
    #         return pd.DataFrame()

    #     # 6. 构建主表
    #     result = pd.DataFrame({'code': list(all_codes)}).set_index('code')

    #     # 注入主力基础面
    #     if not df_zhuli.empty:
    #         result = result.join(df_zhuli.set_index('code'), how='left')

    #     # 注入人气
    #     if not df_hot.empty:
    #         df_hot_idx = df_hot.set_index('code')
    #         if 'name' not in result.columns:
    #             result['name'] = df_hot_idx['name']
    #         else:
    #             result['name'] = result['name'].fillna('').combine_first(df_hot_idx['name'])
    #         result = result.join(df_hot_idx[['hot_rank', 'hot_tag', 'hot_reason']], how='left', rsuffix='_hot')

    #     # 注入题材
    #     if not df_theme.empty:
    #         # 按日期倒序，取最新主题
    #         df_theme_unique = self.merge_theme_logic(df_theme)
    #         if 'theme_date' in df_theme_unique.columns:
    #             df_theme_unique['theme_date'] = df_theme_unique['theme_date'].replace('1970/01/01', '')
    #         # result = result.join(df_theme_unique[['theme_name', 'theme_logic', 'theme_date']], how='left')
    #         result = result.join(df_theme_unique, how='left')

    #     # 7. 清洗默认值
    #     result['zhuli_rank'] = result.get('zhuli_rank', pd.Series(999, index=result.index)).fillna(999)
    #     result['hot_rank'] = result.get('hot_rank_hot', result.get('hot_rank', pd.Series(999, index=result.index))).fillna(999)
    #     result['price'] = result.get('price', pd.Series(0.0, index=result.index)).fillna(0.0)
    #     result['change_pct'] = result.get('change_pct', pd.Series(0.0, index=result.index)).fillna(0.0)

    #     for col in ['name', 'theme_name', 'theme_logic', 'theme_date', 'hot_tag', 'hot_reason', 'sector']:
    #         if col not in result.columns:
    #             result[col] = ''
    #         else:
    #             result[col] = result[col].fillna('')

    #     # 补位策略
    #     mask_theme_name = (result['theme_name'] == '') & (result['hot_tag'] != '')
    #     result.loc[mask_theme_name, 'theme_name'] = result.loc[mask_theme_name, 'hot_tag'].apply(lambda x: x.split(',')[0])
    #     mask_theme_logic = (result['theme_logic'] == '') & (result['hot_reason'] != '')
    #     result.loc[mask_theme_logic, 'theme_logic'] = result.loc[mask_theme_logic, 'hot_reason']

    #     result = result.reset_index()

    #     # 8. 缓存
    #     ok = save_cache(result, persist=True)
    #     if ok:
    #         save_fp({"fp": new_fp, "ts": time.time()}, persist=True)
    #     else:
    #         logger.warning("cache write failed, fingerprint skipped")

    #     logger.info(f"Updated fetching snapshot size: {len(result)}")
    #     return result

if __name__ == "__main__":
    scraper = Scraper55188()
    logger.setLevel(LoggerFactory.DEBUG)
    df = scraper.get_combined_data()
    if not df.empty:
        print(f"Total: {len(df)}")
        if '300058' in df['code'].values:
            print("\n[VERIFY] 300058:")
            print(df[df['code'] == '300058'].iloc[0])
            print(df[df['code'] == '688548'].iloc[0])
    else:
        print("Empty.")
