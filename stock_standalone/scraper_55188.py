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

    def fetch_ths_hotlist(self) -> pd.DataFrame:
        """
        获取同花顺人气热榜及其深度分析
        """
        try:
            resp = self.session.get(self.THS_URL, timeout=10)
            data = resp.json()
            stock_list = data.get("data", {}).get("stock_list", [])
            if not stock_list: return pd.DataFrame()
            
            items = []
            for item in stock_list:
                raw_code = item.get("code", "")
                code = raw_code[-6:] if len(raw_code) >= 6 else raw_code
                
                tags = []
                tag_obj = item.get("tag", {})
                if isinstance(tag_obj, dict):
                    c_tags = tag_obj.get("concept_tag", [])
                    if isinstance(c_tags, list): tags.extend(c_tags)
                    p_tag = tag_obj.get("popularity_tag")
                    if p_tag: tags.append(p_tag)
                
                # 组合详细理由
                title = item.get("analyse_title", "").strip()
                reason = item.get("analyse", "").replace("<br>", "\n").strip()
                reason = re.sub(r'<[^>]+>', '', reason)
                full_reason = f"【{title}】\n{reason}" if title else reason
                
                items.append({
                    "code": code,
                    "name": item.get("name", ""),
                    "hot_rank": item.get("order"), 
                    "hot_tag": ",".join(tags),
                    "hot_reason": full_reason
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
            return pd.DataFrame()
        # except Exception as e:
        #     logger.error(f"Error fetching THS data: {e}")
        #     return pd.DataFrame()

    # def fetch_concept_mining_themes(self, count: int = 15) -> list:
    #     """
    #     获取优品热门题材列表
    #     """
    #     payload = {"stReq": {"uiStart": 0, "uiCount": count}}
    #     try:
    #         resp = self.session.post(self.UPCHINA_THEME_URL, json=payload, timeout=10)
    #         data = resp.json()
    #         return data.get("stRsp", {}).get("vThemeData", [])
    #     except Exception as e:
    #         return []

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
                code = str(item.get("code", ""))
                code = code[-6:] if len(code) > 6 else code
                if not code.isnumeric(): continue
                
                logic = ""
                m2 = item.get("vLatestData", {})
                logic2 = item.get("position", "")
                updateDate = ""

                if isinstance(m2, list) and m2 and isinstance(m2[0], dict):
                    val = m2[0].get("driveContent")
                    updateDate = m2[0].get("updateDate", "")
        
                    if isinstance(val, str):
                        logic = val.strip()
                        
                    if not logic and len(m2) > 1 and isinstance(m2[1], dict):
                        val2 = m2[1].get("driveContent")
                        if isinstance(val2, str):
                            logic = val2.strip()
                            
                    if isinstance(logic2, str) and logic2 and '地址' not in logic2:
                        logic = f"{logic} {logic2}"
                    # else:
                        # print(f'position: {logic2}')
                    # if isinstance(val, list) and len(val) > 1: logic = val[1]
                    # else: logic = str(val)
                
                items.append({"code": code, "theme_logic": logic ,"updateDate": updateDate})
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
        # except Exception as e:
        #     logger.error("Exception", e)
        #     return pd.DataFrame()

    def get_combined_data_old(self) -> pd.DataFrame:
        """
        聚合多维数据：主力、人气、题材逻辑
        """
        df_zhuli = self.fetch_eastmoney_zhuli()
        df_hot = self.fetch_ths_hotlist()
        
        # 题材与逻辑整合 (增加抓取数量以覆盖更久之前的题材)
        themes = self.fetch_concept_mining_themes(count=30) 
        theme_dfs = []
        # logger.info(f'themes: {themes}')
        last_date = None
        for theme in themes:
            p_code = theme.get("sPlateCode")
            if p_code:
                df_t = self.fetch_theme_stocks(p_code)
                if not df_t.empty:
                    df_t["theme_name"] = str(theme.get("sPlateName") or "")
                    
                    # 提取日期：尝试更多可能字段并处理时间戳
                    # 优先级：effectiveTime > sDate > uiDate > uiUpdateDate > sUpdateDate > sDriveTime > ...
                    # raw_date = (theme.get("effectiveTime") or theme.get("sEffectiveTime"))
                    raw_date = (theme.get("effectiveTime") or theme.get("sEffectiveTime")  or
                                theme.get("sDate") or theme.get("uiDate") or 
                                theme.get("uiUpdateDate") or theme.get("sUpdateDate") or
                                theme.get("sDriveTime") or theme.get("sDriveDate") or 
                                theme.get("sTime") or theme.get("dt") or theme.get("uiTime") or ""
                                )
                    
                    theme_date = ""
                    try:
                        if raw_date:
                            s_date = str(raw_date).strip()
                            # 1. 处理 Unix 时间戳 (10位秒 或 13位毫秒)
                            if s_date.isdigit() and len(s_date) >= 10:
                                ts = int(s_date)
                                if len(s_date) == 13: ts //= 1000
                                theme_date = time.strftime("%Y/%m/%d", time.localtime(ts))
                            # 2. 处理 20251229 这种 8+ 位数字格式
                            elif len(s_date) >= 8 and s_date[:8].isdigit():
                                theme_date = f"{s_date[:4]}/{s_date[4:6]}/{s_date[6:8]}"
                            # 3. 处理已带有 / 或 - 的格式
                            elif "/" in s_date or "-" in s_date:
                                # 简单正则提取前 10 位
                                m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s_date)
                                if m: theme_date = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
                        else:
                            logger.info(f'p_code: {p_code} raw_date: {raw_date} theme_date: {theme_date}')
                        if not theme_date:
                            # 最后的兜底：如果完全没抓到，记录一下可能存在的 key
                            pass
                        else:
                            pass
                    except Exception as e:
                        theme_date = ""
                        logger.error(f'raw_date: {e}')
                    df_t["theme_date"] = theme_date

                    # 题材逻辑兜底：如果个股 logic 为空，使用该题材的 driveLogic
                    drive = theme.get("driveLogic", "").strip()
                    if drive:
                        df_t['theme_logic'] = df_t['theme_logic'].replace('', f"【背景】{drive}")
                    theme_dfs.append(df_t)
        
        # 题材全集（暂不消重，归并后按日期保留最新的）
        df_theme = pd.concat(theme_dfs) if theme_dfs else pd.DataFrame()
        if not df_theme.empty:
            # 统一将空日期转为 NA 以便排序，或者赋一个极小值
            df_theme['theme_date'] = df_theme['theme_date'].replace('', '1970/01/01')

        # 确立代码全集
        all_codes = set()
        if not df_zhuli.empty: all_codes.update(df_zhuli['code'])
        if not df_hot.empty: all_codes.update(df_hot['code'])
        if not df_theme.empty: all_codes.update(df_theme['code'])
        
        if not all_codes: return pd.DataFrame()
        
        # 构建主表
        result = pd.DataFrame({'code': list(all_codes)}).set_index('code')
        
        # 1. 注入主力基础面数据 (EM)
        if not df_zhuli.empty:
            result = result.join(df_zhuli.set_index('code'), how='left')
        
        # 2. 注入人气维度 (THS)
        if not df_hot.empty:
            df_hot_idx = df_hot.set_index('code')
            # 补全名称
            if 'name' not in result.columns:
                result['name'] = df_hot_idx['name']
            else:
                result['name'] = result['name'].fillna('').replace('', pd.NA).combine_first(df_hot_idx['name']).fillna('')
            
            result = result.join(df_hot_idx[['hot_rank', 'hot_tag', 'hot_reason']], how='left', rsuffix='_hot')
            
        # 3. 注入题材维度 (Upchina)
        if not df_theme.empty:
            # 确保按日期倒序排列，这样 groupby.first() 拿到的是最新的题材日期
            # 将 1970/01/01 再换回空，结果更干净
            df_theme_unique = df_theme.sort_values('theme_date', ascending=False).groupby('code').first()
            if 'theme_date' in df_theme_unique.columns:
                df_theme_unique['theme_date'] = df_theme_unique['theme_date'].replace('1970/01/01', '')
            result = result.join(df_theme_unique, how='left')
            
        # 4. 最终清洗与默认值
        result['zhuli_rank'] = result.get('zhuli_rank', pd.Series(999, index=result.index)).fillna(999)
        result['hot_rank'] = result.get('hot_rank_hot', result.get('hot_rank', pd.Series(999, index=result.index))).fillna(999)
        result['net_ratio'] = result.get('net_ratio', pd.Series(0.0, index=result.index)).fillna(0.0)
        result['change_pct'] = result.get('change_pct', pd.Series(0.0, index=result.index)).fillna(0.0)
        result['price'] = result.get('price', pd.Series(0.0, index=result.index)).fillna(0.0)

        if 'hot_rank_hot' in result.columns: result.drop(columns=['hot_rank_hot'], inplace=True)

        for col in ['name', 'theme_name', 'theme_logic', 'theme_date', 'hot_tag', 'hot_reason', 'sector']:
            if col in result.columns:
                result[col] = result[col].fillna('')
            else: result[col] = ''
            
        # 补位策略
        # # 1. 如果题材名为空但有人气标签，尝试回填
        # mask_theme_name = (result['theme_name'] == '') & (result['hot_tag'] != '')
        # result.loc[mask_theme_name, 'theme_name'] = result.loc[mask_theme_name, 'hot_tag'].apply(lambda x: x.split(',')[0])
        
        # # 2. 如果题材逻辑为空但有人气推导逻辑，回填推导逻辑作为分析参考
        # mask_theme_logic = (result['theme_logic'] == '') & (result['hot_reason'] != '')
        # result.loc[mask_theme_logic, 'theme_logic'] = result.loc[mask_theme_logic, 'hot_reason']
        logger.info(f'fetching: {len(result)}')
        return result.reset_index()

    def get_combined_data(self, force_full=False,count=30) -> pd.DataFrame:
        """
        聚合多维数据：主力、人气、题材逻辑
        """
        # 1. 抓取 L1（必须）
        df_zhuli = self.fetch_eastmoney_zhuli()
        if df_zhuli.empty:
            return load_cache()

        new_fp = df_fingerprint(df_zhuli)
        fp_info = load_fp()
        old_fp = fp_info.get("fp")
        # 2. 如果指纹相同，直接返回缓存
        if (not force_full) and new_fp == old_fp:
            logger.info("Market snapshot unchanged, use cached data.")
            return load_cache()


        # df_zhuli = self.fetch_eastmoney_zhuli()
        df_hot = self.fetch_ths_hotlist()
        
        # 题材与逻辑整合 (增加抓取数量以覆盖更久之前的题材)
        themes = self.fetch_concept_mining_themes(count=count) 
        theme_dfs = []
        # logger.info(f'themes: {themes}')
        last_date = None
        for theme in themes:
            p_code = theme.get("sPlateCode")
            if p_code:
                df_t = self.fetch_theme_stocks(p_code)
                if not df_t.empty:
                    df_t["theme_name"] = str(theme.get("sPlateName") or "")
                    
                    # 提取日期：尝试更多可能字段并处理时间戳
                    # 优先级：effectiveTime > sDate > uiDate > uiUpdateDate > sUpdateDate > sDriveTime > ...
                    # raw_date = (theme.get("effectiveTime") or theme.get("sEffectiveTime"))
                    raw_date = (theme.get("effectiveTime") or theme.get("sEffectiveTime")  or
                                theme.get("sDate") or theme.get("uiDate") or 
                                theme.get("uiUpdateDate") or theme.get("sUpdateDate") or
                                theme.get("sDriveTime") or theme.get("sDriveDate") or 
                                theme.get("sTime") or theme.get("dt") or theme.get("uiTime") or ""
                                )
                    
                    theme_date = ""
                    try:
                        if raw_date:
                            s_date = str(raw_date).strip()
                            # 1. 处理 Unix 时间戳 (10位秒 或 13位毫秒)
                            if s_date.isdigit() and len(s_date) >= 10:
                                ts = int(s_date)
                                if len(s_date) == 13: ts //= 1000
                                theme_date = time.strftime("%Y/%m/%d", time.localtime(ts))
                            # 2. 处理 20251229 这种 8+ 位数字格式
                            elif len(s_date) >= 8 and s_date[:8].isdigit():
                                theme_date = f"{s_date[:4]}/{s_date[4:6]}/{s_date[6:8]}"
                            # 3. 处理已带有 / 或 - 的格式
                            elif "/" in s_date or "-" in s_date:
                                # 简单正则提取前 10 位
                                m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s_date)
                                if m: theme_date = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
                        else:
                            logger.info(f'p_code: {p_code} raw_date: {raw_date} theme_date: {theme_date}')
                        if not theme_date:
                            # 最后的兜底：如果完全没抓到，记录一下可能存在的 key
                            pass
                        else:
                            pass
                    except Exception as e:
                        theme_date = ""
                        logger.error(f'raw_date: {e}')
                    df_t["theme_date"] = theme_date

                    # 题材逻辑兜底：如果个股 logic 为空，使用该题材的 driveLogic
                    drive = theme.get("driveLogic", "").strip()
                    if drive:
                        df_t['theme_logic'] = df_t['theme_logic'].replace('', f"【背景】{drive}")
                    theme_dfs.append(df_t)
        
        # 题材全集（暂不消重，归并后按日期保留最新的）
        df_theme = pd.concat(theme_dfs) if theme_dfs else pd.DataFrame()
        if not df_theme.empty:
            # 统一将空日期转为 NA 以便排序，或者赋一个极小值
            df_theme['theme_date'] = df_theme['theme_date'].replace('', '1970/01/01')

        # 确立代码全集
        all_codes = set()
        if not df_zhuli.empty: all_codes.update(df_zhuli['code'])
        if not df_hot.empty: all_codes.update(df_hot['code'])
        if not df_theme.empty: all_codes.update(df_theme['code'])
        
        if not all_codes: return pd.DataFrame()
        
        # 构建主表
        result = pd.DataFrame({'code': list(all_codes)}).set_index('code')
        
        # 1. 注入主力基础面数据 (EM)
        if not df_zhuli.empty:
            result = result.join(df_zhuli.set_index('code'), how='left')
        
        # 2. 注入人气维度 (THS)
        if not df_hot.empty:
            df_hot_idx = df_hot.set_index('code')
            # 补全名称
            if 'name' not in result.columns:
                result['name'] = df_hot_idx['name']
            else:
                result['name'] = result['name'].fillna('').replace('', pd.NA).combine_first(df_hot_idx['name']).fillna('')
            
            result = result.join(df_hot_idx[['hot_rank', 'hot_tag', 'hot_reason']], how='left', rsuffix='_hot')
            
        # 3. 注入题材维度 (Upchina)
        if not df_theme.empty:
            # 确保按日期倒序排列，这样 groupby.first() 拿到的是最新的题材日期
            # 将 1970/01/01 再换回空，结果更干净
            df_theme_unique = df_theme.sort_values('theme_date', ascending=False).groupby('code').first()
            if 'theme_date' in df_theme_unique.columns:
                df_theme_unique['theme_date'] = df_theme_unique['theme_date'].replace('1970/01/01', '')
            result = result.join(df_theme_unique, how='left')
            
        # 4. 最终清洗与默认值
        result['zhuli_rank'] = result.get('zhuli_rank', pd.Series(999, index=result.index)).fillna(999)
        result['hot_rank'] = result.get('hot_rank_hot', result.get('hot_rank', pd.Series(999, index=result.index))).fillna(999)
        result['net_ratio'] = result.get('net_ratio', pd.Series(0.0, index=result.index)).fillna(0.0)
        result['change_pct'] = result.get('change_pct', pd.Series(0.0, index=result.index)).fillna(0.0)
        result['price'] = result.get('price', pd.Series(0.0, index=result.index)).fillna(0.0)

        if 'hot_rank_hot' in result.columns: result.drop(columns=['hot_rank_hot'], inplace=True)

        for col in ['name', 'theme_name', 'theme_logic', 'theme_date', 'hot_tag', 'hot_reason', 'sector']:
            if col in result.columns:
                result[col] = result[col].fillna('')
            else: result[col] = ''
            
        # 补位策略
        # 1. 如果题材名为空但有人气标签，尝试回填
        mask_theme_name = (result['theme_name'] == '') & (result['hot_tag'] != '')
        result.loc[mask_theme_name, 'theme_name'] = result.loc[mask_theme_name, 'hot_tag'].apply(lambda x: x.split(',')[0])
        
        # 2. 如果题材逻辑为空但有人气推导逻辑，回填推导逻辑作为分析参考
        mask_theme_logic = (result['theme_logic'] == '') & (result['hot_reason'] != '')
        result.loc[mask_theme_logic, 'theme_logic'] = result.loc[mask_theme_logic, 'hot_reason']
        
        result = result.reset_index()

        # self.df_zhuli = result[result['zhuli_rank'] <= 200].sort_values('zhuli_rank')
        # self.df_hot = result[result['hot_rank'] <= 100].sort_values('hot_rank')
        # self.df_theme = result[(result['theme_name'] != "") & (df['theme_date'] != "")].sort_values('theme_date')

        # 7. 缓存
        ok = save_cache(result, persist=True)
        if ok:
            save_fp({"fp": new_fp, "ts": time.time()}, persist=True)
        else:
            logger.warning("cache write failed, fingerprint skipped")

        logger.info(f"Updated fetching snapshot size: {len(result)}")
        # logger.info(f'fetching: {len(result)}')

        return result

if __name__ == "__main__":
    scraper = Scraper55188()
    logger.setLevel(LoggerFactory.DEBUG)
    df = scraper.get_combined_data()
    if not df.empty:
        print(f"Total: {len(df)}")
        if '300058' in df['code'].values:
            print("\n[VERIFY] 300058:")
            print(df[df['code'] == '300058'].iloc[0])
    else:
        print("Empty.")
