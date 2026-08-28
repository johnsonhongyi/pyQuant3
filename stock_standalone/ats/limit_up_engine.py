# -*- coding: utf-8 -*-
"""
ats/limit_up_engine.py — ATS 每日涨停个股数据统计、封单比/量能比分析、多日强势股聚合与持久化核心引擎
职责：
1. 【实时与盘后涨停个股精准识别与盘口提取】：
   - 支持全市场各板涨停规则判定 (主板 10%、创业/科创板 20%、北交所 30%、ST 5%) 与炸板/触板状态标记；
   - 直连 TDX Realtime Fetcher 获取秒级五档挂单、买一封单量、真实流通股本与总股本；
2. 【全维封单比与量能比指标推演】：
   - 封单金额 (万元/亿元) = bid1_vol * 100 * price；
   - 封流比 (%) = (bid1_vol * 100 / 流通股本) * 100% (精准反映封单占流通盘比例，>5%为强板，>10%为特强一字/大单)；
   - 封成比 (%) = (bid1_vol / 当日总成交量) * 100% (反映买盘封板相对实际成交的厚度)；
   - 买盘压强 (bid_pressure %) = 买一~买五总量 / 五档总深度 * 100%；
   - 封板质量综合评分 (0~100)；
   - 真实量比 (vol_ratio)、换手率 (turnover_rate %)、成交金额 (亿元)；
3. 【多日强势股与连板天梯快速聚合】：
   - 支持滑动窗口快速聚合统计 (1日、2日、3日、5日、10日、20日)；
   - 自动统计 N 日 M 板 (如 5日3板、10日6板)、最高连板数、区间累计涨幅与区间换手率；
   - 梯队分类标签 (【👑 空间高度龙】、【🚀 连板接力梯队】、【🔥 强势换手首板】、【💥 强势反包】、【🛡️ 稳健中军】)；
4. 【跟随 ATS 的 dff 等策略特征与 ats_col 动态自定义列】：
   - 严格继承 ATS 指标体系：dff, dff2, dff3, rank, perc3d, 大盘偏离度 (rs_val) 与大盘共振 (resonance)；
   - 动态解析并格式化 cct.ats_col / cct.CFG.ats_col 自定义扩展列；
5. 【安全原子持久化与多日历史时序回溯】：
   - 数据原子存储至 datacsv/ats_limit_up_records.json 与按日归档的 datacsv/ats_limit_up_daily_archive_{date}.json；
   - 提供多日历史数据回放、查询与对比分析能力。
"""

import os
import sys
import json
import gzip
import time
import math
import logging
import datetime
import threading
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any, Set

from sys_utils import get_app_root, get_conf_path
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory
from ats.opening_bubble_engine import get_opening_bubble_engine, OpeningBubbleEngine

logger = LoggerFactory.getLogger("LimitUpEngine")

# 本地数据持久化文件路径 (采用 Gzip 压缩打包优化，完全双向兼容纯 JSON)
DATA_DIR = os.path.join(get_app_root(), "datacsv")
LIMIT_UP_RECORDS_FILE = os.path.join(DATA_DIR, "ats_limit_up_records.json.gz")
LIMIT_UP_RECORDS_FILE_LEGACY = os.path.join(DATA_DIR, "ats_limit_up_records.json")
ARCHIVE_PREFIX = os.path.join(DATA_DIR, "ats_limit_up_daily_archive_")


def get_live_time_slice_name() -> str:
    """根据当前实盘 A 股时钟返回对应的生命周期时间片名称"""
    now_hhmm = time.strftime("%H:%M")
    if "09:15" <= now_hhmm < "10:00":
        return "👑 09:30~10:00 黄金定龙"
    elif "10:00" <= now_hhmm < "11:30":
        return "💎 10:00~11:30 分歧低吸"
    elif "11:30" <= now_hhmm < "13:00":
        return "💎 10:00~11:30 分歧低吸"
    elif "13:00" <= now_hhmm < "14:00":
        return "🚀 13:00~14:00 午后助攻"
    elif "14:00" <= now_hhmm < "14:45":
        return "⚠️ 14:00~14:45 尾盘诱多"
    elif "14:45" <= now_hhmm <= "15:30":
        return "🔒 14:45~15:00 尾盘定盘"
    else:
        return "⏱️ 全天全时段"


def _safe_float(val: Any, default: float = 0.0) -> float:
    """健壮的浮点数安全转换函数，杜绝 '-', '--', 'None', NaN, Inf 抛出异常"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """安全转换为 int"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


def get_limit_up_ratio_threshold(code: str, name: str = "") -> float:
    """
    获取不同板块个股的理论涨停涨幅阈值 (%):
    - 北交所 (920, 83, 87, 88, 43, 82 等): 30.0% (阈值 29.2%)
    - 科创板 (688)/创业板 (300, 301): 20.0% (阈值 19.5%)
    - ST / *ST 股票: 5.0% (阈值 4.85%)
    - 主板 (600, 601, 603, 605, 000, 001, 002, 003): 10.0% (阈值 9.8%)
    """
    c_clean = str(code).strip().zfill(6)
    n_clean = str(name).strip().upper()
    if "ST" in n_clean or "*ST" in n_clean or "退" in n_clean:
        return 4.85
    if c_clean.startswith(("920", "83", "87", "88", "43", "82")):
        return 29.2
    elif c_clean.startswith(("688", "300", "301", "302")):
        return 19.5
    return 9.8


def calc_theoretical_limit_up_price(code: str, last_close: float, name: str = "") -> float:
    """计算个股精准理论涨停价 (元)"""
    if last_close <= 0:
        return 0.0
    c_clean = str(code).strip().zfill(6)
    n_clean = str(name).strip().upper()
    if "ST" in n_clean or "*ST" in n_clean:
        ratio = 0.05
    elif c_clean.startswith(("920", "83", "87", "88", "43", "82")):
        ratio = 0.30
    elif c_clean.startswith(("688", "300", "301", "302")):
        ratio = 0.20
    else:
        ratio = 0.10
    return round(last_close * (1.0 + ratio), 2)


def get_ats_custom_extra_cols() -> List[str]:
    """获取 ats_col 排除已有基础固定列后的自定义追加列"""
    try:
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['ch_bc2']
    BASE_EXCLUDE = {
        'code', 'name', 'price', 'close', 'trade', 'pct', 'percent', 'ratio',
        'state', 'dff', 'dff2', 'dff3', 'rank', 'rs_val', 'dev', 'resonance',
        'volume', 'vol', 'amount', 'turnover', 'vol_ratio', 'open', 'high', 'low'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


_PERSIST_FILE_LOCK = threading.Lock()


def _safe_atomic_write_json_gz(filepath: str, data: Any):
    """【Windows 友好型高压 Gzip 原子 JSON 写盘】带重试与清理，极大压缩磁盘并杜绝文件占用与 tmp 残留"""
    gz_target = filepath if filepath.endswith(".gz") else f"{filepath}.gz"
    tmp_path = f"{gz_target}.tmp_{int(time.time()*1000)}_{os.getpid()}"
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8", compresslevel=6) as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        
        # 多次重试替换，应对 Windows 文件短暂占用
        for retry in range(5):
            try:
                if os.path.exists(gz_target):
                    os.replace(tmp_path, gz_target)
                else:
                    os.rename(tmp_path, gz_target)
                return
            except Exception:
                time.sleep(0.05 * (retry + 1))
        # 最终兜底
        if os.path.exists(tmp_path):
            import shutil
            shutil.move(tmp_path, gz_target)
    except Exception as e:
        logger.error(f"原子写入 Gzip JSON 失败 ({gz_target}): {e}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _safe_read_json_or_gz(filepath_without_ext: str) -> Optional[Any]:
    """【双向透明兼容读取】优先解压读取 .json.gz，不存在时回退读取 .json"""
    # 1. 优先尝试 .json.gz
    gz_path = filepath_without_ext if filepath_without_ext.endswith(".gz") else f"{filepath_without_ext}.gz"
    if os.path.exists(gz_path):
        try:
            with gzip.open(gz_path, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取 Gzip JSON 文件异常 ({gz_path}): {e}")

    # 2. 回退尝试未压缩的 .json
    raw_path = filepath_without_ext.replace(".json.gz", "").replace(".gz", "")
    if not raw_path.endswith(".json"):
        raw_path = f"{raw_path}.json"
    if os.path.exists(raw_path):
        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取未压缩 JSON 文件异常 ({raw_path}): {e}")

    return None


def _clean_stale_tmp_files(directory: str):
    """自动清理磁盘上遗留的历史 .tmp_* 临时碎片文件 (支持 .json.tmp 和 .json.gz.tmp)"""
    try:
        if not os.path.exists(directory):
            return
        now_ts = time.time()
        for fname in os.listdir(directory):
            if ".tmp_" in fname and fname.startswith("ats_limit_up_"):
                fpath = os.path.join(directory, fname)
                try:
                    # 清理超过 10 秒前的残留 tmp 文件
                    if now_ts - os.path.getmtime(fpath) > 10.0:
                        os.remove(fpath)
                except Exception:
                    pass
    except Exception:
        pass


def _compress_and_cleanup_archives(directory: str):
    """【交易后打包压缩与历史清理】将未压缩的 .json 历史归档自动压缩为 .json.gz 并清理遗留的大文件"""
    try:
        if not os.path.exists(directory):
            return
        for fname in os.listdir(directory):
            if fname.startswith("ats_limit_up_daily_archive_") and fname.endswith(".json") and not fname.endswith(".json.gz"):
                raw_path = os.path.join(directory, fname)
                gz_path = f"{raw_path}.gz"
                try:
                    if not os.path.exists(gz_path):
                        with open(raw_path, "r", encoding="utf-8") as f_in:
                            sub_data = json.load(f_in)
                        _safe_atomic_write_json_gz(gz_path, sub_data)
                    if os.path.exists(gz_path) and os.path.getsize(gz_path) > 0:
                        os.remove(raw_path)
                except Exception as e:
                    logger.debug(f"压缩历史分日归档异常 ({fname}): {e}")
            elif fname == "ats_limit_up_records.json":
                raw_main = os.path.join(directory, fname)
                gz_main = f"{raw_main}.gz"
                try:
                    if not os.path.exists(gz_main):
                        with open(raw_main, "r", encoding="utf-8") as f_in:
                            main_data = json.load(f_in)
                        _safe_atomic_write_json_gz(gz_main, main_data)
                    if os.path.exists(gz_main) and os.path.getsize(gz_main) > 0:
                        os.remove(raw_main)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"打包压缩历史归档失败: {e}")


class LimitUpEngine:
    """
    ATS 每日涨停与多日强势股聚合分析单例引擎
    """
    _instance: Optional['LimitUpEngine'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'LimitUpEngine':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._cache_lock = threading.RLock()
        self._history_daily_records: Dict[str, List[Dict[str, Any]]] = {}  # {date_str: [record, ...]}
        self._last_loaded_date: Optional[str] = None
        self._is_loading_history = False
        
        # 数据变动特征指纹缓存 {date_str: fingerprint_str}，实现数据无变动不落盘 (Dirty Check)
        self._last_saved_fingerprints: Dict[str, str] = {}
        
        # 内存中当前实时计算出的涨停标的列表
        self._current_live_records: List[Dict[str, Any]] = []
        self._last_scan_time: float = 0.0

        # 确保数据目录存在
        os.makedirs(DATA_DIR, exist_ok=True)

        # 启动时清理历史残留 tmp 文件、打包压缩遗留纯文本并加载持久化历史数据
        _clean_stale_tmp_files(DATA_DIR)
        _compress_and_cleanup_archives(DATA_DIR)
        self._load_persisted_history_records()

    def _load_persisted_history_records(self):
        """【💾 磁盘持久化加载】冷启动瞬间恢复历史涨停与强势股归档记录 (支持 .json.gz 与 .json)"""
        with self._cache_lock:
            # 1. 尝试从全量归档主文件加载 (优先 .json.gz)
            main_data = _safe_read_json_or_gz(LIMIT_UP_RECORDS_FILE)
            if main_data and isinstance(main_data, dict):
                self._history_daily_records = main_data
                logger.info(f"✅ 成功从主持久化文件加载涨停历史数据: 共 {len(main_data)} 个交易日记录")

            # 2. 补充扫描分日归档文件 (ats_limit_up_daily_archive_YYYY-MM-DD.json.gz / .json)
            try:
                if os.path.exists(DATA_DIR):
                    for fname in os.listdir(DATA_DIR):
                        if fname.startswith("ats_limit_up_daily_archive_") and (fname.endswith(".json.gz") or fname.endswith(".json")):
                            date_part = fname.replace("ats_limit_up_daily_archive_", "").replace(".json.gz", "").replace(".json", "")
                            if date_part not in self._history_daily_records:
                                fpath = os.path.join(DATA_DIR, fname)
                                sub_data = _safe_read_json_or_gz(fpath)
                                if isinstance(sub_data, list):
                                    self._history_daily_records[date_part] = sub_data
            except Exception as e:
                logger.debug(f"扫描分日涨停归档异常: {e}")

    def save_daily_records_atomic(self, date_str: str, records: List[Dict[str, Any]], force: bool = False, is_eod: bool = False):
        """
        【💾 安全原子持久化与交易后压缩打包】
        1. 脏检查：仅当数据特征指纹发生变动时才执行落盘；
        2. 质量防御：防空数据覆写，且收盘后/历史数据严禁被记录数严重缩水的残缺劣质数据覆盖；
        3. 交易后终态保护：15:00 收盘后或显式 is_eod 时强制原子固化并高压 Gzip 压缩打包。
        :param date_str: 格式 YYYY-MM-DD
        :param records: 涨停记录字典列表
        :param force: 是否强制覆写
        :param is_eod: 是否为收盘/交易后终态归档 (End-of-Day)
        """
        # 1. 防空数据检查
        if not date_str or not records:
            logger.debug(f"[LimitUpEngine] 持久化请求被忽略: 空日期或空记录集 (date={date_str})")
            return

        with self._cache_lock:
            # 2. 交易后/收盘终态数据防残缺劣质覆盖保护
            existing_records = self._history_daily_records.get(date_str, [])
            if not existing_records:
                disk_data = _safe_read_json_or_gz(f"{ARCHIVE_PREFIX}{date_str}.json.gz")
                if isinstance(disk_data, list):
                    existing_records = disk_data

            # 若已有 5 条以上完整记录，且传入记录数严重缩水（少于已有记录数的 60%）且非显式 force：拒绝破坏性覆盖
            if existing_records and len(existing_records) >= 5 and len(records) < len(existing_records) * 0.6 and not force:
                logger.warning(
                    f"🛡️ [数据防劣质覆盖保护] 拒绝覆写 {date_str}: "
                    f"已有完整记录 {len(existing_records)} 条，传入仅 {len(records)} 条 (非 force 模式拒绝覆盖)"
                )
                return

            # 3. 数据特征指纹变动脏检查 (Dirty Check)
            try:
                summary_tuples = [
                    (
                        r.get("code"),
                        r.get("price"),
                        r.get("pct"),
                        r.get("bid1_vol"),
                        r.get("consecutive_boards"),
                        r.get("is_broken"),
                        r.get("tier_tag")
                    )
                    for r in records
                ]
                current_fingerprint = str(hash(tuple(sorted(summary_tuples, key=lambda x: str(x[0])))))
            except Exception:
                current_fingerprint = str(time.time())

            last_fp = self._last_saved_fingerprints.get(date_str)
            # 若非强制保存、非交易后固化，且数据特征指纹未变动，直接跳过写盘
            if not force and not is_eod and last_fp == current_fingerprint:
                logger.debug(f"[LimitUpEngine] {date_str} 涨停天梯数据无变动 (DirtyCheck Passed)，跳过磁盘 I/O")
                return

            # 更新特征指纹与内存字典
            self._last_saved_fingerprints[date_str] = current_fingerprint
            self._history_daily_records[date_str] = records

            # 异步后台线程执行文件 I/O，杜绝阻塞主线程 UI
            history_copy = {d: list(recs) for d, recs in self._history_daily_records.items()}
            single_date_records = list(records)
            is_post_trading = is_eod or (time.strftime("%H:%M") >= "15:00")

            def _persist_worker():
                with _PERSIST_FILE_LOCK:
                    try:
                        # 1. 写入分日独立归档文件 (高压 Gzip 压缩，空间锐减 90%)
                        single_file_gz = f"{ARCHIVE_PREFIX}{date_str}.json.gz"
                        _safe_atomic_write_json_gz(single_file_gz, single_date_records)

                        # 2. 写入全量主归档文件 (保留最近 90 个交易日，防止文件过度膨胀)
                        sorted_dates = sorted(history_copy.keys())
                        if len(sorted_dates) > 90:
                            pruned_copy = {d: history_copy[d] for d in sorted_dates[-90:]}
                        else:
                            pruned_copy = history_copy

                        _safe_atomic_write_json_gz(LIMIT_UP_RECORDS_FILE, pruned_copy)
                        
                        # 3. 交易后自动执行历史碎片清理与存量文件打包
                        _clean_stale_tmp_files(DATA_DIR)
                        if is_post_trading:
                            _compress_and_cleanup_archives(DATA_DIR)
                            logger.info(f"✅ [交易后归档] 涨停历史数据已成功固化并完成 Gzip 压缩打包: {date_str} (共 {len(single_date_records)} 条记录)")
                        else:
                            logger.debug(f"✅ 涨停历史数据已成功原子持久化落盘: {date_str} (共 {len(single_date_records)} 条记录)")
                    except Exception as e:
                        logger.error(f"涨停数据原子持久化落盘失败: {e}")

            threading.Thread(target=_persist_worker, daemon=True, name="LimitUpPersistWorker").start()

    def scan_limit_up_records_from_df(
        self,
        current_df: pd.DataFrame,
        fetch_l2_quotes: bool = True,
        extra_cols: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        【🎯 核心识别与计算引擎】输入当前全市场/监控池 DataFrame，全自动提取：
        1. 识别真实封板、炸板与大涨个股；
        2. 直连 TDX 获取最新买一封单量、五档深度、流通股本与总股本；
        3. 精准推算封单额、封流比、封成比、买盘压强、封板质量分、量比与换手率；
        4. 融合 ATS 核心指标 (dff, dff2, dff3, rank, perc3d, 大盘偏离, 大盘共振) 与动态 ats_col；
        5. 计算连板天数与多日历史特征。
        """
        if current_df is None or current_df.empty:
            return []

        extra_cols = extra_cols or get_ats_custom_extra_cols()
        records = []
        target_codes_for_l2 = []

        # 0. 同步全网表微秒级快照
        try:
            get_opening_bubble_engine().update_market_snapshot(current_df)
        except Exception:
            pass

        # 获取大盘参考涨幅
        sh_pct = 0.0
        for idx_code in ('sh000001', '000001'):
            if idx_code in current_df.index:
                try:
                    sh_pct = _safe_float(current_df.loc[idx_code].get('percent', 0.0))
                    break
                except Exception:
                    pass
        if sh_pct == 0.0 and 'percent' in current_df.columns:
            sh_pct = _safe_float(current_df['percent'].mean(), 0.0)

        # 1. 快速遍历 DataFrame 筛选涨停与逼近涨停标的
        is_index_code = 'code' not in current_df.columns
        for idx, row in current_df.iterrows():
            code_raw = str(idx) if is_index_code else str(row.get('code', idx))
            c_clean = ''.join(c for c in code_raw if c.isdigit()).zfill(6)
            if not c_clean or len(c_clean) != 6:
                continue

            name = str(row.get('name', '')).strip()
            if not name or name == '未知' or name == c_clean or name.isdigit():
                try:
                    from sys_utils import resolve_stock_name
                    name = resolve_stock_name(c_clean) or c_clean
                except Exception:
                    name = c_clean

            price_raw = _safe_float(row.get('trade', row.get('close', row.get('price', 0.0))))
            b1_p = _safe_float(row.get('buy', row.get('bid1', row.get('buy1', row.get('b1_p', row.get('b1', 0.0))))))
            a1_p = _safe_float(row.get('sell', row.get('ask1', row.get('sell1', row.get('a1_p', row.get('a1', 0.0))))))
            open_p_raw = _safe_float(row.get('open', 0.0))
            last_close = _safe_float(row.get('last_close', row.get('prev_close', 0.0)))

            # ⚡ 统一有效价格：连续撮合优先 price_raw；09:15~09:25 集合竞价期依次回退买一价、开盘试撮合价、卖一价
            price = price_raw if price_raw > 0 else (b1_p if b1_p > 0 else (open_p_raw if open_p_raw > 0 else (a1_p if a1_p > 0 else 0.0)))
            if last_close <= 0:
                last_close = price

            pct = _safe_float(row.get('percent', row.get('pct', 0.0)))
            if last_close > 0 and (pct == 0.0 or price_raw <= 0) and price > 0:
                pct = round((price - last_close) / last_close * 100.0, 2)

            high_p = _safe_float(row.get('high', price))
            low_p = _safe_float(row.get('low', price))
            open_p = open_p_raw if open_p_raw > 0 else price
            vol = _safe_float(row.get('volume', row.get('vol', row.get('b1_v', row.get('bid_vol1', 0.0)))))
            amount = _safe_float(row.get('amount', row.get('turnover', 0.0)))
            if amount <= 0 and price > 0 and vol > 0:
                amount = price * vol * 100.0

            threshold = get_limit_up_ratio_threshold(c_clean, name)
            theoretical_zt_price = calc_theoretical_limit_up_price(c_clean, last_close, name)

            # 判定是否涨停或炸板 (支持集合竞价一字试撮合)
            is_at_limit_price = (price >= theoretical_zt_price - 0.01) if (theoretical_zt_price > 0 and price > 0) else False
            is_pct_limit = (pct >= threshold)
            is_limit_up = is_pct_limit or is_at_limit_price

            # 判定炸板 (最高价触及涨停价但现价脱离涨停)
            was_touch_zt = (high_p >= theoretical_zt_price - 0.01) if (theoretical_zt_price > 0 and high_p > 0) else False
            is_broken = was_touch_zt and not is_limit_up and (pct < threshold - 0.5)

            # 如果既未涨停也非炸板且涨幅未达大阳线 (>=7%)，则跳过
            if not is_limit_up and not is_broken and pct < 7.0:
                continue

            target_codes_for_l2.append(c_clean)

            # 提取 ATS 核心策略指标 (支持全量大写/小写/中文别名)
            dff = _safe_float(row.get('dff', row.get('DFF', 0.0)))
            dff2 = _safe_float(row.get('DFF2', row.get('dff2', 0.0)))
            dff3 = _safe_float(row.get('DFF3', row.get('dff3', 0.0)))
            rank_val = _safe_int(row.get('Rank', row.get('rank', row.get('排名', row.get('topR', 0)))), 0)
            perc3d = _safe_float(row.get('perc3d', 0.0))

            rs_val = round(pct - sh_pct, 2)
            resonance = "同步整理"
            if sh_pct < -0.3 and pct > 1.5:
                resonance = "逆市抗跌"
            elif sh_pct > 0.3 and pct > 3.0 and dff > 2.0:
                resonance = "大盘共振"
            elif pct < -3.0 and rs_val < -2.0:
                resonance = "同步走弱"

            # 提取动态自定义列 (ats_col)
            extra_dict = {}
            for ec in extra_cols:
                val_raw = None
                for k in (ec, ec.lower(), ec.upper()):
                    if k in row:
                        val_raw = row[k]
                        break
                extra_dict[ec] = cct.format_col_value(ec, val_raw)

            # 板块分类
            category = str(row.get('category', row.get('industry', row.get('hy', '')))).strip()

            records.append({
                "code": c_clean,
                "name": name,
                "price": price,
                "pct": pct,
                "last_close": last_close,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "vol": vol,
                "amount": amount,
                "amount_yi": round(amount / 1e8, 2) if amount > 1e5 else round((price * vol * 100) / 1e8, 2),
                "is_limit_up": is_limit_up,
                "is_broken": is_broken,
                "threshold": threshold,
                "theoretical_zt_price": theoretical_zt_price,
                "dff": dff,
                "dff2": dff2,
                "dff3": dff3,
                "rank": rank_val,
                "perc3d": perc3d,
                "rs_val": rs_val,
                "resonance": resonance,
                "category": category,
                "extra_cols": extra_dict,
                # 下列字段由后续 TDX 盘口与股本接口精准补齐
                "bid1_vol": 0.0,
                "seal_amount_wan": 0.0,
                "seal_amount_yi": 0.0,
                "seal_to_circ_ratio": 0.0,
                "seal_to_vol_ratio": 0.0,
                "bid_pressure": 50.0,
                "seal_quality_score": 70.0,
                "vol_ratio": _safe_float(row.get('vol_ratio', row.get('ratio', 1.0)), 1.0),
                "turnover_rate": _safe_float(row.get('turnover', row.get('turnover_rate', 0.0))),
                "consecutive_boards": 1,
                "tier_tag": "🔥 换手首板"
            })

        # 2. 直连 TDX Realtime Fetcher 获取秒级高精度盘口五档与真实流通股本
        if fetch_l2_quotes and target_codes_for_l2:
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                fetcher = TDXRealtimeFetcher.get_instance()
                
                # 批量获取五档盘口
                quotes = fetcher.get_security_quotes_safe(target_codes_for_l2)
                quote_map = {str(q.get("code", "")).strip().zfill(6): q for q in quotes if q.get("code")}

                # 批量拉取真实流通股本与总股本字典 {code: (liutong_shares, total_shares)}
                shares_map = fetcher.get_batch_finance_shares(target_codes_for_l2)

                for r in records:
                    c = r["code"]
                    q = quote_map.get(c)
                    shares_info = shares_map.get(c, (150000000.0, 150000000.0))
                    circ_shares = shares_info[0] if (shares_info and shares_info[0] > 0) else 150000000.0

                    if q:
                        p_tdx = _safe_float(q.get("price", 0.0))
                        bid1_p = _safe_float(q.get("bid1", 0.0))
                        ask1_p = _safe_float(q.get("ask1", 0.0))
                        open_tdx = _safe_float(q.get("open", 0.0))
                        
                        price_now = p_tdx if p_tdx > 0 else (bid1_p if bid1_p > 0 else (open_tdx if open_tdx > 0 else (ask1_p if ask1_p > 0 else r["price"])))
                        last_c = _safe_float(q.get("last_close", r["last_close"]))
                        if price_now > 0:
                            r["price"] = price_now
                        if last_c > 0:
                            r["last_close"] = last_c
                            r["pct"] = round((price_now - last_c) / last_c * 100.0, 2)

                        vol_now = _safe_float(q.get("vol", r["vol"]))
                        amt_now = _safe_float(q.get("amount", r["amount"]))
                        if vol_now > 0:
                            r["vol"] = vol_now
                        if amt_now > 0:
                            r["amount"] = amt_now
                            r["amount_yi"] = round(amt_now / 1e8, 2)

                        # 日内 VWAP 均价与偏离度测算
                        vwap_now = round(amt_now / (vol_now * 100.0), 2) if (amt_now > 0 and vol_now > 0) else price_now
                        r["vwap"] = vwap_now
                        r["vwap_dev_pct"] = round((price_now - vwap_now) / vwap_now * 100.0, 2) if vwap_now > 0 else 0.0

                        # 买一封单量 (手)
                        bid1_v = _safe_float(q.get("bid_vol1", 0.0))
                        r["bid1_vol"] = bid1_v

                        # 买一~买五与卖一~卖五深度计算与买盘压强
                        bid_sum = sum(_safe_float(q.get(f"bid_vol{i}", 0.0)) for i in range(1, 6))
                        ask_sum = sum(_safe_float(q.get(f"ask_vol{i}", 0.0)) for i in range(1, 6))
                        tot_depth = bid_sum + ask_sum
                        r["bid_pressure"] = round((bid_sum / tot_depth) * 100.0, 1) if tot_depth > 0 else 50.0

                        # 真实换手率 (%)
                        if circ_shares > 0 and vol_now > 0:
                            r["turnover_rate"] = round((vol_now * 100.0 / circ_shares) * 100.0, 2)

                        # 封板状态核实 (支持集合竞价涨停状态判定)
                        if price_now >= r["theoretical_zt_price"] - 0.01 or r["pct"] >= r["threshold"]:
                            r["is_limit_up"] = True
                        if r["is_limit_up"] and ask_sum > 0 and bid1_v < ask_sum * 0.1:
                            r["is_limit_up"] = False
                            r["is_broken"] = True

                        # 仅对真实封涨停 (is_limit_up == True) 计算封单指标，非涨停/炸板一律清零杜绝误导
                        if r["is_limit_up"]:
                            bid1_v = _safe_float(q.get("bid_vol1", 0.0))
                            r["bid1_vol"] = bid1_v
                            seal_amt_yuan = bid1_v * 100.0 * price_now
                            r["seal_amount_wan"] = round(seal_amt_yuan / 10000.0, 1)
                            r["seal_amount_yi"] = round(seal_amt_yuan / 1e8, 3)

                            # 封流比 (%) = 封单总股数 / 流通总股数 * 100%
                            if circ_shares > 0:
                                r["seal_to_circ_ratio"] = round((bid1_v * 100.0 / circ_shares) * 100.0, 2)
                            
                            # 封成比 (%) = 封单手数 / 当日总成交手数 * 100%
                            if vol_now > 0:
                                r["seal_to_vol_ratio"] = round((bid1_v / vol_now) * 100.0, 1)
                        else:
                            r["bid1_vol"] = 0.0
                            r["seal_amount_wan"] = 0.0
                            r["seal_amount_yi"] = 0.0
                            r["seal_to_circ_ratio"] = 0.0
                            r["seal_to_vol_ratio"] = 0.0
                    else:
                        r["bid1_vol"] = 0.0
                        r["seal_amount_wan"] = 0.0
                        r["seal_amount_yi"] = 0.0
                        r["seal_to_circ_ratio"] = 0.0
                        r["seal_to_vol_ratio"] = 0.0

            except Exception as e:
                logger.debug(f"TDX 封单与股本数据拉取补充异常: {e}")

        # 3. 结合真实封板状态、多日历史归档、ch_bc2波谷周期与两日情绪推算标志性梯队与严格分层评分
        for r in records:
            consecutive = self._calc_consecutive_boards(r["code"], r["is_limit_up"])
            r["consecutive_boards"] = consecutive

            dff = _safe_float(r.get("dff", 0.0))
            dff2 = _safe_float(r.get("dff2", 0.0))
            dff3 = _safe_float(r.get("dff3", 0.0))
            pct = _safe_float(r.get("pct", 0.0))
            price = _safe_float(r.get("price", 0.0))
            vwap = _safe_float(r.get("vwap", price))
            vwap_dev = _safe_float(r.get("vwap_dev_pct", 0.0))
            vol_ratio = _safe_float(r.get("vol_ratio", 1.0))
            turnover = _safe_float(r.get("turnover_rate", 0.0))
            bid_p = _safe_float(r.get("bid_pressure", 50.0))
            rs_val = _safe_float(r.get("rs_val", 0.0))
            seal_amt_wan = _safe_float(r.get("seal_amount_wan", 0.0))
            seal_to_circ = _safe_float(r.get("seal_to_circ_ratio", 0.0))
            seal_to_vol = _safe_float(r.get("seal_to_vol_ratio", 0.0))
            is_limit_up = bool(r.get("is_limit_up", False))
            is_broken = bool(r.get("is_broken", False))

            # 提取真实策略波谷与支撑信息
            extra_d = r.get("extra_cols", {})
            ch_bc2 = _safe_int(r.get("ch_bc2", extra_d.get("ch_bc2", 999)), 999)
            supp_price = _safe_float(r.get("support", extra_d.get("support", 0.0)))

            # 💡 最近 2日、3日与 5日平台高点计算 (max(lasth1d, lasth2d, lasth3d))
            lasth1d = _safe_float(r.get("lasth1d", extra_d.get("lasth1d", 0.0)))
            lasth2d = _safe_float(r.get("lasth2d", extra_d.get("lasth2d", 0.0)))
            lasth3d = _safe_float(r.get("lasth3d", extra_d.get("lasth3d", 0.0)))
            max5 = _safe_float(r.get("max5", extra_d.get("max5", r.get("hmax", extra_d.get("hmax", 0.0)))))

            valid_2d = [v for v in (lasth1d, lasth2d) if v > 0]
            max_2d = max(valid_2d) if valid_2d else 0.0
            valid_3d = [v for v in (lasth1d, lasth2d, lasth3d) if v > 0]
            max_3d = max(valid_3d) if valid_3d else 0.0
            valid_5d = [v for v in (lasth1d, lasth2d, lasth3d, max5) if v > 0]
            max_5d = max(valid_5d) if valid_5d else 0.0

            is_breakout_multiday = (price > 0 and max_5d > 0 and price >= max_5d - 0.01) or (price > 0 and max_3d > 0 and price >= max_3d - 0.01) or (dff2 >= 8.0)
            
            # 1. 两日情绪与阳包阴反包判定 (昨日洗盘震荡/小阴回调，今日放量大阳反包)
            pct_yesterday = round(dff2 - pct, 2) if abs(dff2) > 0.01 else 0.0
            is_bullish_engulfing = (pct >= 5.0 and pct_yesterday <= 3.0 and dff2 >= 7.0)

            # 2. 关键支撑位反转判定 (需满足: ch_bc2<=45波谷周期 或 真实接近有效支撑位)
            is_support_bounce = False
            supp_dist_pct = 0.0
            if supp_price > 0 and price > 0:
                supp_dist_pct = round((price - supp_price) / supp_price * 100.0, 2)
                if 0.0 <= supp_dist_pct <= 3.5:
                    is_support_bounce = True
            elif 1 <= ch_bc2 <= 45 and (is_bullish_engulfing or (dff3 > 20.0 and dff2 > 10.0)):
                is_support_bounce = True

            r["is_bullish_engulfing"] = is_bullish_engulfing
            r["is_support_bounce"] = is_support_bounce
            r["supp_dist_pct"] = supp_dist_pct
            r["pct_yesterday"] = pct_yesterday

            # ── 💡 交易时钟生命周期 (Time Window Alpha) ──
            # 区分：09:30~10:00黄金定龙期 / 10:00~11:30分歧低吸期 / 13:00~14:00午后助攻期 / 14:00~14:45尾盘诱多高危期
            curr_hhmm = time.strftime("%H:%M")
            if "09:15" <= curr_hhmm < "09:20":
                time_phase = "⏱️ 竞价试撮合期"
                time_multiplier = 1.05
                time_tip = "09:15~09:20试撮合可撤单，观察虚挂测盘与封单撤销"
            elif "09:20" <= curr_hhmm <= "09:25":
                time_phase = "👑 竞价定龙竞速期"
                time_multiplier = 1.15
                time_tip = "09:20~09:25不可撤单黄金定龙，锁定真金白银一字顶格与高开抢筹"
            elif "09:25" < curr_hhmm < "09:30":
                time_phase = "🔒 竞价定盘静默期"
                time_multiplier = 1.10
                time_tip = "09:25集合竞价已定盘，锁定开盘价与竞价量能梯队"
            elif "09:30" <= curr_hhmm < "10:00":
                time_phase = "👑 黄金定龙期"
                time_multiplier = 1.10
                time_tip = "09:30~10:00早盘黄金定龙点火，溢价最高，最佳先锋抢跑时机"
            elif "10:00" <= curr_hhmm < "11:30":
                time_phase = "💎 分歧低吸期"
                time_multiplier = 0.95
                time_tip = "10:00~11:30盘中分歧期，严禁盲目追高，只做回踩VWAP企稳低吸"
            elif "13:00" <= curr_hhmm < "14:00":
                time_phase = "🚀 午后助攻期"
                time_multiplier = 0.95
                time_tip = "13:00~14:00午后发酵期，观察板块多股共振助攻"
            elif "14:00" <= curr_hhmm < "14:45":
                time_phase = "⚠️ 尾盘高危期"
                time_multiplier = 0.75 # 尾盘脉冲大幅打折，防偷袭与次日低开闷杀
                time_tip = "14:00后尾盘高危期，脉冲多为诱多偷袭，严防尾盘炸板"
            else:
                time_phase = "📋 稳健定盘期"
                time_multiplier = 1.0
                time_tip = "大局已定，观察封单硬度与隔夜潜伏"

            r["time_phase"] = time_phase
            r["time_tip"] = time_tip

            # ── 💡 索罗斯【反身性动能指数 (Reflexivity Momentum Index)】与冰点逆市挖掘 ──
            reflex_score = 50.0
            if rs_val > 5.0: # 逆市抗跌大盘偏离
                reflex_score += 15.0
            elif rs_val > 2.0:
                reflex_score += 8.0
            
            if is_support_bounce: # 支撑线贴合
                reflex_score += 12.0
            if is_bullish_engulfing: # 突然阳包阴
                reflex_score += 10.0
            if -0.3 <= vwap_dev <= 1.8: # 紧贴VWAP黄金反身点
                reflex_score += 8.0
            if bid_p >= 70.0: # 主力主动点火压强
                reflex_score += 5.0
            
            is_reflexivity_leader = (reflex_score >= 82.0 and is_support_bounce and (is_bullish_engulfing or vol_ratio >= 1.5))
            r["reflex_score"] = round(min(99.0, reflex_score), 0)
            r["is_reflexivity_leader"] = is_reflexivity_leader

            # ── 💡 盘中上车梯度与介入时机智能判决 (Intraday Entry Timing) ──
            if is_limit_up:
                entry_stage = "🔒 封死涨停"
                entry_advice = f"已封死涨停，监控封单硬度与排撤单 ({time_tip})"
            elif is_broken:
                entry_stage = "⚠️ 炸板分歧"
                entry_advice = f"涨停炸板被砸，分歧过大谨慎接飞刀 ({time_tip})"
            elif vwap_dev > 5.5:
                entry_stage = "⚠️ 乖离过大"
                entry_advice = "远离VWAP均线(+5.5%+)，防脉冲冲高回落，切勿追高"
            elif "尾盘高危" in time_phase and pct >= 5.0 and not is_limit_up:
                entry_stage = "⚠️ 尾盘诱多"
                entry_advice = f"14:00后尾盘突然脉冲拉升，极大概率系诱多偷袭，切勿打地鼠追高！"
            elif is_reflexivity_leader and (1.0 <= pct <= 5.0):
                entry_stage = "💎 冰点反身潜伏"
                entry_advice = f"大盘冰点逆市抗跌，回踩VWAP({vwap:.2f})支撑阳包阴反身启动({time_tip})"
            elif (1.0 <= pct <= 4.5) and (-0.5 <= vwap_dev <= 1.8) and (is_support_bounce or is_bullish_engulfing or vol_ratio >= 1.3):
                entry_stage = "🟢 黄金潜伏区"
                entry_advice = f"回踩VWAP({vwap:.2f})支撑放量启动，极高盈亏比(低吸上车点 | {time_tip})"
            elif (4.5 < pct <= 7.5) and (0.5 <= vwap_dev <= 4.0) and (vol_ratio >= 1.8 or bid_p >= 65.0):
                entry_stage = "🟡 半路点火区"
                entry_advice = f"放量突破站稳均线(+{vwap_dev:.1f}%)，主力点火主升(半路上车点 | {time_tip})"
            elif (7.5 < pct < 9.8) and bid_p >= 75.0:
                entry_stage = "🔴 封板临界区"
                entry_advice = f"大单连续扫盘冲击涨停，买盘压强{bid_p:.0f}%(抢跑封板卡位点 | {time_tip})"
            else:
                entry_stage = "📋 蓄势观察区"
                entry_advice = f"分时窄幅震荡，等待放量突破或回踩均线信号 ({time_tip})"

            r["entry_stage"] = entry_stage
            
            # 注入 OpeningBubbleEngine 的开盘起点与跃迁画像
            try:
                b_prof = get_opening_bubble_engine().get_stock_profile(r["code"])
                r["open_pct"] = b_prof.get("open_pct", 0.0)
                r["pattern_type"] = b_prof.get("pattern_type", "NORMAL")
                r["pattern_tag"] = b_prof.get("pattern_tag", r.get("tier_tag", "横盘整理"))
                r["trajectory_str"] = b_prof.get("trajectory_str", "-")
                r["tier_jumps"] = b_prof.get("tier_jumps", 0)
                r["bubble_alpha_score"] = b_prof.get("alpha_score", 50.0)
            except Exception:
                r["open_pct"] = 0.0
                r["pattern_type"] = "NORMAL"
                r["pattern_tag"] = r.get("tier_tag", "横盘整理")
                r["trajectory_str"] = "-"
                r["tier_jumps"] = 0
                r["bubble_alpha_score"] = 50.0

            # ── 💡 核心量化打分：结合时序生命周期乘数 ──
            if is_limit_up:
                base_score = 80.0
                if consecutive >= 4:
                    base_score += 10.0
                elif consecutive == 3:
                    base_score += 7.0
                elif consecutive == 2:
                    base_score += 4.0

                seal_bonus = min(6.0, seal_to_circ * 0.8) + min(3.0, (seal_amt_wan / 10000.0) * 0.6)
                base_score += seal_bonus

                if pct >= 19.5:
                    base_score += 2.0

                if is_reflexivity_leader:
                    base_score += 6.0
                elif is_support_bounce and is_bullish_engulfing:
                    base_score += 5.0
                elif is_bullish_engulfing or is_support_bounce:
                    base_score += 2.5

                dff_bonus = min(3.0, max(0.0, (dff2 * 0.04 + dff3 * 0.01)))
                base_score += dff_bonus

                momentum_score = round(min(99.0, max(80.0, base_score)), 0)

                if consecutive >= 4:
                    r["tier_tag"] = f"👑 空间高度龙 ({consecutive}板)"
                    desc_tag = f"👑 空间总龙({momentum_score:.0f}分)"
                elif consecutive >= 2:
                    r["tier_tag"] = f"🚀 连板接力 ({consecutive}板)"
                    desc_tag = f"🚀 连板加速({momentum_score:.0f}分)"
                elif "09:15" <= curr_hhmm <= "09:25":
                    if (seal_amt_wan >= 2000 or seal_to_circ >= 3.0) and is_breakout_multiday:
                        r["tier_tag"] = "💎 竞价爆量突破龙"
                        desc_tag = f"💎 爆量突破({momentum_score:.0f}分)"
                    elif seal_amt_wan >= 2000 or seal_to_circ >= 3.0:
                        r["tier_tag"] = "👑 竞价一字顶格"
                        desc_tag = f"👑 竞价一字({momentum_score:.0f}分)"
                    else:
                        r["tier_tag"] = "🔥 竞价高开冲板"
                        desc_tag = f"🔥 竞价冲板({momentum_score:.0f}分)"
                elif "09:25" < curr_hhmm < "09:30":
                    if is_breakout_multiday:
                        r["tier_tag"] = "💎 定盘爆量突破龙"
                        desc_tag = f"💎 定盘突破({momentum_score:.0f}分)"
                    else:
                        r["tier_tag"] = "🔒 竞价一字定盘"
                        desc_tag = f"🔒 定盘一字({momentum_score:.0f}分)"
                elif is_reflexivity_leader:
                    r["tier_tag"] = "💎 冰点反身性龙"
                    desc_tag = f"💎 反身性龙头({momentum_score:.0f}分)"
                elif (seal_amt_wan >= 20000 or seal_to_circ >= 4.0) and momentum_score >= 95:
                    r["tier_tag"] = "💎 统治级大封单"
                    desc_tag = f"💎 极强封板({momentum_score:.0f}分)"
                elif is_support_bounce and is_bullish_engulfing:
                    r["tier_tag"] = "🎯 支撑阳包阴反转"
                    desc_tag = f"🎯 支撑反包({momentum_score:.0f}分)"
                elif pct >= 19.5:
                    r["tier_tag"] = "⭐ 20cm强势首板"
                    desc_tag = f"⭐ 20cm强封({momentum_score:.0f}分)"
                elif is_bullish_engulfing:
                    r["tier_tag"] = "⚡ 阳包阴强反转"
                    desc_tag = f"⚡ 阳包阴({momentum_score:.0f}分)"
                elif is_support_bounce:
                    r["tier_tag"] = "🛡️ 关键支撑起爆"
                    desc_tag = f"🛡️ 支撑起爆({momentum_score:.0f}分)"
                elif dff2 > 15.0 or dff3 > 30.0:
                    r["tier_tag"] = "🔥 强势主升首板"
                    desc_tag = f"🔥 主升首板({momentum_score:.0f}分)"
                else:
                    r["tier_tag"] = "📋 换手蓄势首板"
                    desc_tag = f"📋 换手首板({momentum_score:.0f}分)"

            elif is_broken:
                momentum_score = round(min(58.0, max(30.0, 35.0 + pct * 1.5)), 0)
                r["tier_tag"] = "💥 曾涨停炸板"
                desc_tag = f"⚠️ 炸板分歧({momentum_score:.0f}分)"

            else:
                # 未封板的冲板/潜伏/跟涨股 (55 ~ 88 分，融合时间窗口与地量起爆)
                ch_score = 55.0 + min(10.0, (pct - 2.0) * 1.3)
                ch_score += min(6.0, max(0.0, dff2 * 0.05 + dff3 * 0.01))
                
                # 地量地价多日震荡起爆特征判定
                is_low_vol_breakout = (vol_ratio >= 1.25 or dff2 >= 5.0) and (dff2 > 0 or dff3 > 0) and (turnover <= 5.5) and (-0.3 <= vwap_dev <= 2.5) and (1.5 <= pct <= 7.0)

                if is_reflexivity_leader:
                    ch_score += 8.0
                elif is_low_vol_breakout:
                    ch_score += 7.0
                elif "黄金潜伏" in entry_stage or "半路点火" in entry_stage:
                    ch_score += 5.0
                if vol_ratio > 1.8:
                    ch_score += 2.0

                # 应用时间衰减惩罚
                ch_score = ch_score * time_multiplier
                momentum_score = round(min(88.0, max(45.0, ch_score)), 0)

                is_first_day = ("N" in str(r.get("name", ""))) or (code_str.startswith("920") and pct > 30.0) or ("首日" in str(r.get("status", "")))
                if "09:15" <= curr_hhmm <= "09:30" and is_first_day and (seal_amt_wan >= 800.0 or bid_p >= 75.0):
                    r["tier_tag"] = "💎 新股首日真金抢筹"
                    desc_tag = f"💎 首日抢筹({momentum_score:.0f}分)"
                elif "09:20" <= curr_hhmm <= "09:25" and pct >= 3.0 and is_breakout_multiday and (seal_amt_wan >= 2000.0 or bid_p >= 75.0):
                    r["tier_tag"] = "💎 竞价爆量突破"
                    desc_tag = f"💎 爆量突破({momentum_score:.0f}分)"
                elif "09:20" <= curr_hhmm <= "09:25" and pct >= 7.0 and bid_p >= 75.0:
                    r["tier_tag"] = "🚀 竞价极速抢筹"
                    desc_tag = f"🚀 竞价抢筹({momentum_score:.0f}分)"
                elif "09:20" <= curr_hhmm <= "09:25" and pct >= 3.0 and (dff2 >= 5.0 or pct_yesterday <= 0.0) and bid_p >= 65.0:
                    r["tier_tag"] = "🔥 弱转强超预期"
                    desc_tag = f"🔥 弱转强({momentum_score:.0f}分)"
                elif "尾盘诱多" in entry_stage:
                    r["tier_tag"] = "⚠️ 尾盘诱多脉冲"
                    desc_tag = f"⚠️ 尾盘偷袭({momentum_score:.0f}分)"
                elif is_reflexivity_leader:
                    r["tier_tag"] = "💎 冰点反身潜伏"
                    desc_tag = f"💎 反身潜伏({momentum_score:.0f}分)"
                elif is_low_vol_breakout:
                    r["tier_tag"] = "💎 地量地价起爆"
                    desc_tag = f"💎 地量起爆({momentum_score:.0f}分)"
                elif "黄金潜伏" in entry_stage:
                    r["tier_tag"] = "🟢 黄金潜伏区"
                    desc_tag = f"🟢 均线低吸({momentum_score:.0f}分)"
                elif "半路点火" in entry_stage:
                    r["tier_tag"] = "🟡 半路点火区"
                    desc_tag = f"🟡 先锋点火({momentum_score:.0f}分)"
                elif "封板临界" in entry_stage:
                    r["tier_tag"] = "🔴 封板临界区"
                    desc_tag = f"🔴 冲击涨停({momentum_score:.0f}分)"
                elif pct >= 7.5:
                    r["tier_tag"] = "⚡ 大阳冲板未封"
                    desc_tag = f"⚡ 冲板未封({momentum_score:.0f}分)"
                elif is_bullish_engulfing:
                    r["tier_tag"] = "📈 阳包阴跟涨"
                    desc_tag = f"📈 阳包阴({momentum_score:.0f}分)"
                else:
                    r["tier_tag"] = "📊 板块跟涨标的"
                    desc_tag = f"📊 跟涨蓄势({momentum_score:.0f}分)"

            r["momentum_score"] = momentum_score
            r["seal_quality_score"] = momentum_score
            r["pattern_desc"] = desc_tag

        # 4. 排序：真实涨停优先 > 连板数降序 > 动能评分降序 > 封流比降序 > 涨幅降序
        records.sort(key=lambda x: (
            1 if x["is_limit_up"] else 0,
            x["consecutive_boards"],
            x.get("momentum_score", 50.0),
            x["seal_to_circ_ratio"],
            x["pct"]
        ), reverse=True)

        with self._cache_lock:
            self._current_live_records = records
            self._last_scan_time = time.time()

        return records

    def get_intraday_radar_records(self, current_df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
        """
        【🎯 盘中动态潜伏与梯度上车雷达】
        专为盘中实战打造：不盲目追涨，通过 VWAP 偏离、早盘量能爆发比、关键支撑阳包阴、买盘压强锁定日内黄金买点
        过滤出: 🟢 黄金潜伏区(低吸) / 🟡 半路点火区(顺势) / 🔴 封板临界区(抢跑) / 🎯 支撑反转板 / 👑 统治级龙头
        """
        all_recs = self.scan_limit_up_records_from_df(current_df)
        if not all_recs:
            return []

        radar_list = []
        for r in all_recs:
            if r.get("is_broken", False):
                continue
            stage = str(r.get("entry_stage", ""))
            pct = _safe_float(r.get("pct", 0.0))
            vwap_dev = _safe_float(r.get("vwap_dev_pct", 0.0))

            # 排除严重破位或分时远离均线偏离过大的虚拉标的
            if vwap_dev > 5.5:
                continue

            # 筛选具备强烈上车动能的梯度标的 (含地量起爆与重点关注)
            is_radar_hit = False
            tier_t = str(r.get("tier_tag", ""))
            if r.get("is_limit_up", False):
                is_radar_hit = True
            elif "地量" in tier_t or "地量" in str(r.get("pattern_desc", "")):
                is_radar_hit = True
            elif "黄金潜伏" in stage or "半路点火" in stage or "封板临界" in stage:
                is_radar_hit = True
            elif r.get("is_bullish_engulfing", False) and pct >= 3.0:
                is_radar_hit = True
            elif r.get("is_support_bounce", False) and pct >= 2.5:
                is_radar_hit = True
            elif r.get("category") == "重点关注" or r.get("is_focus", False):
                is_radar_hit = True

            if is_radar_hit:
                radar_list.append(r)

        # 排序：重点关注优先 > 反身性龙头优先 > 上车动能评分降序 > 买盘压强降序 > 量比降序
        radar_list.sort(key=lambda x: (
            1 if (x.get("is_focus", False) or x.get("category") == "重点关注") else 0,
            1 if x.get("is_reflexivity_leader", False) else 0,
            x.get("momentum_score", 50.0),
            x.get("bid_pressure", 50.0),
            x.get("vol_ratio", 1.0),
            x.get("pct", 0.0)
        ), reverse=True)

        return radar_list

    def get_opening_bubble_records(
        self,
        current_df: Optional[pd.DataFrame] = None,
        pattern_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        【🌅 盘中开盘起点与极速阶梯跃迁挖掘雷达】
        结合全网状态表、开盘形态分类、冒泡跃迁连续度、多日连板天梯与 DFF 特征，
        捕获: 🚀 低开高走反包 / 💎 高开放量锁筹 / ⚡ 步步高升跃迁 / 🌊 平开脉冲
        """
        engine = get_opening_bubble_engine()
        raw_bubble_list = engine.get_bubble_radar_records(current_df=current_df, pattern_filter=pattern_filter, min_score=60.0)
        if not raw_bubble_list:
            return []

        # 获取已有涨停/天梯特征字典 (按 code 快速合并)
        all_zt_recs = self.scan_limit_up_records_from_df(current_df)
        zt_map = {r["code"]: r for r in all_zt_recs} if all_zt_recs else {}

        # 提取策略 DataFrame 映射，确保非涨停冒泡标的亦能 100% 完整继承 DFF/Rank/板块等全维特征
        df_map = {}
        if current_df is not None and not current_df.empty:
            for idx_val, row in current_df.iterrows():
                code_raw = row.get('code', idx_val) if hasattr(row, 'get') else idx_val
                c_clean = ''.join(c for c in str(code_raw) if c.isdigit()).zfill(6)
                if c_clean:
                    df_map[c_clean] = row

        # 构造并丰富全量看板记录
        merged_records = []
        for b in raw_bubble_list:
            c = b["code"]
            zt_r = zt_map.get(c, {})
            df_r = df_map.get(c)

            pct = b.get("pct", zt_r.get("pct", 0.0))
            dff = zt_r.get("dff", _safe_float(df_r.get('dff', 0.0)) if df_r is not None else 0.0)
            dff2 = zt_r.get("dff2", _safe_float(df_r.get('DFF2', df_r.get('dff2', 0.0))) if df_r is not None else 0.0)
            dff3 = zt_r.get("dff3", _safe_float(df_r.get('DFF3', df_r.get('dff3', 0.0))) if df_r is not None else 0.0)
            rank_val = zt_r.get("rank", _safe_int(df_r.get('Rank', df_r.get('rank', 999)), 999) if df_r is not None else 999)
            category = zt_r.get("category", str(df_r.get('category', df_r.get('industry', df_r.get('hy', '')))).strip() if df_r is not None else "")
            
            rs_val = zt_r.get("rs_val", round(pct, 2))
            resonance = zt_r.get("resonance", "同步整理")
            if resonance == "同步整理" and df_r is not None:
                if pct > 3.0 and dff > 2.0:
                    resonance = "大盘共振"
                elif pct > 1.5:
                    resonance = "逆市抗跌"

            # 继承已有字段或生成默认值
            rec = {
                "code": c,
                "name": b.get("name", zt_r.get("name", c)),
                "price": b.get("price", zt_r.get("price", 0.0)),
                "pct": pct,
                "open_pct": b.get("open_pct", zt_r.get("open_pct", 0.0)),
                "consecutive_boards": zt_r.get("consecutive_boards", self._calc_consecutive_boards(c, False)),
                "tier_tag": b.get("tier_tag", zt_r.get("tier_tag", "⚡ 步步高升")),
                "pattern_desc": f"{b.get('tier_tag', '')}·{b.get('pattern_desc', '')}",
                "pattern_type": b.get("pattern_type", "NORMAL"),
                "trajectory_str": b.get("trajectory_str", "-"),
                "tier_jumps": b.get("tier_jumps", 0),
                "seal_amount_wan": zt_r.get("seal_amount_wan", 0.0),
                "seal_to_circ_ratio": zt_r.get("seal_to_circ_ratio", 0.0),
                "seal_to_vol_ratio": zt_r.get("seal_to_vol_ratio", 0.0),
                "turnover_rate": (b.get("turnover_pct") if (b.get("turnover_pct") and b.get("turnover_pct", 0) <= 100) else (zt_r.get("turnover_rate", 0.0) if zt_r.get("turnover_rate", 0.0) <= 100 else 0.0)),
                "vol_ratio": b.get("vol_ratio", zt_r.get("vol_ratio", 1.0)),
                "amount_yi": b.get("amount_yi", zt_r.get("amount_yi", 0.0)),
                "dff": dff,
                "rank": rank_val,
                "dff2": dff2,
                "dff3": dff3,
                "rs_val": rs_val,
                "resonance": resonance,
                "category": category,
                "extra_cols": zt_r.get("extra_cols", {}),
                "momentum_score": b.get("momentum_score", 65.0),
                "is_limit_up": zt_r.get("is_limit_up", False),
                "is_broken": zt_r.get("is_broken", False),
                "is_bubble_hit": True
            }
            merged_records.append(rec)

        # 排序：综合评分降序 > 阶梯跃迁次数降序 > 量比降序 > 涨幅降序
        merged_records.sort(key=lambda x: (
            x.get("momentum_score", 0.0),
            x.get("tier_jumps", 0),
            x.get("vol_ratio", 1.0),
            x.get("pct", 0.0)
        ), reverse=True)

        return merged_records

    def _calc_consecutive_boards(self, code: str, is_today_zt: bool) -> int:
        """从历史归档记录中回溯推算该个股的当前连板天数"""
        c_clean = str(code).strip().zfill(6)
        if not is_today_zt:
            return 0

        boards = 1
        sorted_dates = sorted(self._history_daily_records.keys(), reverse=True)
        today_str = time.strftime("%Y-%m-%d")

        # 排除今天的记录（防止重复计数）
        past_dates = [d for d in sorted_dates if d != today_str]

        for d in past_dates:
            day_records = self._history_daily_records.get(d, [])
            # 查找该代码在历史日中是否为有效涨停
            found = False
            for rec in day_records:
                if str(rec.get("code", "")).strip().zfill(6) == c_clean:
                    if rec.get("is_limit_up", False) or _safe_float(rec.get("pct", 0.0)) >= get_limit_up_ratio_threshold(c_clean):
                        found = True
                        break
            if found:
                boards += 1
            else:
                # 连板中断
                break

        return boards

    def aggregate_multi_day_strong_stocks(
        self,
        days: int = 5,
        min_limit_ups: int = 1,
        current_df: Optional[pd.DataFrame] = None
    ) -> List[Dict[str, Any]]:
        """
        【🚀 多日强势股快速聚合分析引擎】
        快速扫描最近 N 个交易日内的涨停历史与当前最新状态，统计：
        - N日M板统计 (如 5日3板、10日6板)；
        - 区间最高连板高度与区间累计涨幅；
        - 最新的封单比、量能比、ATS dff/dff2/dff3 与自定义列；
        - 强势梯队与龙头状态。
        """
        with self._cache_lock:
            sorted_dates = sorted(self._history_daily_records.keys())

        # 获取最近 N 日的日期子集
        target_dates = sorted_dates[-days:] if len(sorted_dates) >= days else sorted_dates
        today_str = time.strftime("%Y-%m-%d")
        if today_str not in target_dates and self._current_live_records:
            target_dates.append(today_str)

        # 统计每个代码在区间内的出现频次、涨停天数与历史数据
        code_stats: Dict[str, Dict[str, Any]] = {}
        for d in target_dates:
            recs = self._current_live_records if d == today_str and self._current_live_records else self._history_daily_records.get(d, [])
            for r in recs:
                c = str(r.get("code", "")).strip().zfill(6)
                if not c:
                    continue
                if c not in code_stats:
                    code_stats[c] = {
                        "code": c,
                        "name": r.get("name", c),
                        "limit_up_dates": [],
                        "broken_dates": [],
                        "max_consecutive": 0,
                        "latest_record": dict(r),
                        "accum_pct": 0.0
                    }
                if r.get("is_limit_up", False):
                    code_stats[c]["limit_up_dates"].append(d)
                elif r.get("is_broken", False):
                    code_stats[c]["broken_dates"].append(d)
                
                cons = _safe_int(r.get("consecutive_boards", 1))
                if cons > code_stats[c]["max_consecutive"]:
                    code_stats[c]["max_consecutive"] = cons
                
                code_stats[c]["accum_pct"] += _safe_float(r.get("pct", 0.0))
                code_stats[c]["latest_record"] = dict(r)

        results = []
        extra_cols = get_ats_custom_extra_cols()

        for c, st in code_stats.items():
            zt_count = len(st["limit_up_dates"])
            if zt_count < min_limit_ups and st["max_consecutive"] < 2:
                continue

            lat = st["latest_record"]
            # 若提供了实时 current_df，从中同步最新行情与策略指标
            if current_df is not None and not current_df.empty:
                if c in current_df.index:
                    row = current_df.loc[c]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    lat["price"] = _safe_float(row.get("trade", row.get("close", lat["price"])))
                    lat["pct"] = _safe_float(row.get("percent", row.get("pct", lat["pct"])))
                    lat["dff"] = _safe_float(row.get("dff", lat["dff"]))
                    lat["dff2"] = _safe_float(row.get("DFF2", row.get("dff2", lat["dff2"])))
                    lat["dff3"] = _safe_float(row.get("DFF3", row.get("dff3", lat["dff3"])))
                    lat["rank"] = _safe_int(row.get("Rank", row.get("rank", lat["rank"])), lat["rank"])

                    for ec in extra_cols:
                        for k in (ec, ec.lower(), ec.upper()):
                            if k in row:
                                lat["extra_cols"][ec] = cct.format_col_value(ec, row[k])
                                break

            # 生成 N日M板 摘要
            n_d_m_b = f"{len(target_dates)}日{zt_count}板"
            if len(st["broken_dates"]) > 0:
                n_d_m_b += f" (炸板{len(st['broken_dates'])}次)"

            # 综合强势评分 (0~100)
            strong_score = (
                zt_count * 20.0 +
                st["max_consecutive"] * 15.0 +
                min(25.0, _safe_float(lat.get("pct", 0.0)) * 1.5) +
                min(15.0, _safe_float(lat.get("seal_to_circ_ratio", 0.0)) * 2.0) +
                (10.0 if (_safe_float(lat.get("dff2", 0.0)) > 10.0 or _safe_float(lat.get("dff3", 0.0)) > 20.0) else 0.0)
            )
            strong_score = round(min(100.0, max(20.0, strong_score)), 1)

            # 强势梯队分类
            if st["max_consecutive"] >= 4 or zt_count >= 4:
                tier = f"👑 核心总龙头 ({n_d_m_b})"
            elif st["max_consecutive"] >= 2 or zt_count >= 2:
                tier = f"🚀 连板接力梯队 ({n_d_m_b})"
            elif lat.get("is_limit_up"):
                tier = f"🔥 强势首板 ({n_d_m_b})"
            elif lat.get("is_broken"):
                tier = f"💥 炸板洗盘 ({n_d_m_b})"
            else:
                tier = f"⚡ 活跃强势反包 ({n_d_m_b})"

            res_item = dict(lat)
            res_item.update({
                "n_days_m_boards": n_d_m_b,
                "zt_count": zt_count,
                "max_consecutive": st["max_consecutive"],
                "accum_pct_nd": round(st["accum_pct"], 2),
                "strong_score": strong_score,
                "tier_tag": tier
            })
            results.append(res_item)

        # 排序：强势评分降序 > 连板数降序 > 涨幅降序
        results.sort(key=lambda x: (
            x["strong_score"],
            x["zt_count"],
            x["max_consecutive"],
            x["pct"]
        ), reverse=True)

        return results

    def get_market_limit_up_summary(self, date_str: Optional[str] = None, current_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        生成指定日期或实时的全市场情绪概览核心 KPI (涨跌家数、恐慌杀跌数、封板率、最高板、平均封流比、防猎熔断状态)
        """
        date_str = date_str or time.strftime("%Y-%m-%d")
        with self._cache_lock:
            records = self._current_live_records if (date_str == time.strftime("%Y-%m-%d") and self._current_live_records) else self._history_daily_records.get(date_str, [])

        # 全市场宏观广度数据分析 (从 5500+ 全量个股 DataFrame 中提取)
        up_cnt = 0
        down_cnt = 0
        flat_cnt = 0
        panic_down_cnt = 0 # 跌幅 <= -5% 的恐慌踩踏个股数
        limit_down_cnt = 0 # 跌停个股数
        median_pct = 0.0

        if current_df is not None and not current_df.empty:
            try:
                pct_col = 'percent' if 'percent' in current_df.columns else ('pct' if 'pct' in current_df.columns else None)
                if pct_col:
                    s_pct = pd.to_numeric(current_df[pct_col], errors='coerce').fillna(0.0)
                    up_cnt = int((s_pct > 0.0).sum())
                    down_cnt = int((s_pct < 0.0).sum())
                    flat_cnt = int((s_pct == 0.0).sum())
                    panic_down_cnt = int((s_pct <= -5.0).sum())
                    limit_down_cnt = int((s_pct <= -9.5).sum())
                    median_pct = round(float(s_pct.median()), 2)
            except Exception as e:
                logger.debug(f"宏观情绪广度提取异常: {e}")

        if not records:
            return {
                "date": date_str,
                "zt_count": 0,
                "broken_count": 0,
                "total_attempts": 0,
                "seal_rate": 0.0,
                "max_boards": 0,
                "multi_boards_count": 0,
                "avg_seal_circ_ratio": 0.0,
                "total_seal_amount_yi": 0.0,
                "top_leader": "--",
                "up_cnt": up_cnt,
                "down_cnt": down_cnt,
                "panic_down_cnt": panic_down_cnt,
                "limit_down_cnt": limit_down_cnt,
                "median_pct": median_pct,
                "sentiment_phase": "⚖️ 均衡博弈期",
                "sentiment_score": 50.0,
                "defense_status": "大盘整理中",
                "is_avalanche": False
            }

        zt_count = sum(1 for r in records if r.get("is_limit_up", False))
        broken_count = sum(1 for r in records if r.get("is_broken", False))
        total_attempts = zt_count + broken_count
        seal_rate = round((zt_count / total_attempts * 100.0), 1) if total_attempts > 0 else 0.0

        max_boards = max((_safe_int(r.get("consecutive_boards", 1)) for r in records if r.get("is_limit_up")), default=0)
        multi_boards_count = sum(1 for r in records if r.get("is_limit_up") and _safe_int(r.get("consecutive_boards", 1)) >= 2)

        seal_circ_sum = sum(_safe_float(r.get("seal_to_circ_ratio", 0.0)) for r in records if r.get("is_limit_up"))
        avg_seal_circ = round(seal_circ_sum / max(1, zt_count), 2)
        tot_seal_amt = sum(_safe_float(r.get("seal_amount_yi", 0.0)) for r in records if r.get("is_limit_up"))

        # 最高板空间龙
        top_leaders = [r for r in records if r.get("is_limit_up") and _safe_int(r.get("consecutive_boards", 1)) == max_boards]
        top_leader_code = top_leaders[0]["code"] if top_leaders else (records[0]["code"] if records else "")
        top_leader_name = top_leaders[0]["name"] if top_leaders else (records[0]["name"] if records else "")
        top_leader_str = f"{top_leader_name} ({max_boards}板)" if (top_leaders and max_boards >= 2) else (top_leader_name if top_leader_name else "--")

        # ── 💡 深度全市场情绪退潮与防猎感知指数 (Deep Market Sentiment & Avalanche Index) ──
        # 综合考量：1. 封板率与炸板数; 2. 5500股红绿比; 3. 恐慌踩踏家数(panic_down_cnt); 4. 跌停数
        is_avalanche = False
        if (total_attempts >= 10 and seal_rate < 45.0) or (down_cnt >= 3800 and panic_down_cnt >= 150) or limit_down_cnt >= 20:
            sentiment_phase = "🚨 情绪雪崩退潮"
            sentiment_score = 15.0
            defense_status = f"🚨 全市场退潮雪崩 (下跌{down_cnt}家 | 恐慌踩踏{panic_down_cnt}家 | 炸板率{100.0-seal_rate:.0f}%), 触发全局防猎熔断, 强制禁止开仓, 严守止损!"
            is_avalanche = True
        elif seal_rate < 60.0 or (down_cnt >= 3000 and down_cnt > up_cnt * 1.8) or panic_down_cnt >= 80:
            sentiment_phase = "⚠️ 退潮分歧期"
            sentiment_score = 38.0
            defense_status = f"🟠 市场分歧退潮 (下跌{down_cnt}家 | 炸板率{100.0-seal_rate:.0f}%), 谨防一致性回落与尾盘跳水, 严禁追高"
            is_avalanche = False
        elif (seal_rate >= 80.0 and zt_count >= 30) or (up_cnt >= 3500 and limit_down_cnt <= 2):
            sentiment_phase = "🔥 极度亢奋期"
            sentiment_score = 90.0
            defense_status = f"🟢 进攻顺风 (上涨{up_cnt}家 | 封板率{seal_rate:.0f}%), 主力做多情绪高涨, 顺势跟随龙头主升"
            is_avalanche = False
        else:
            sentiment_phase = "⚖️ 均衡博弈期"
            sentiment_score = 65.0
            defense_status = f"🟡 结构分化 (涨{up_cnt}/跌{down_cnt}), 重个股轻大盘, 严格控制仓位"
            is_avalanche = False

        return {
            "date": date_str,
            "zt_count": zt_count,
            "broken_count": broken_count,
            "total_attempts": total_attempts,
            "seal_rate": seal_rate,
            "max_boards": max_boards,
            "multi_boards_count": multi_boards_count,
            "avg_seal_circ_ratio": avg_seal_circ,
            "total_seal_amount_yi": round(tot_seal_amt, 2),
            "top_leader": top_leader_str,
            "top_leader_code": top_leader_code,
            "top_leader_name": top_leader_name,
            "up_cnt": up_cnt,
            "down_cnt": down_cnt,
            "panic_down_cnt": panic_down_cnt,
            "limit_down_cnt": limit_down_cnt,
            "median_pct": median_pct,
            "sentiment_phase": sentiment_phase,
            "sentiment_score": sentiment_score,
            "defense_status": defense_status,
            "is_avalanche": is_avalanche
        }

    def get_all_archived_dates(self) -> List[str]:
        """获取所有已持久化归档的历史交易日日期列表 (升序排列，带磁盘动态同步)"""
        with self._cache_lock:
            # 动态补齐磁盘最新归档日期
            try:
                if os.path.exists(DATA_DIR):
                    for fname in os.listdir(DATA_DIR):
                        if fname.startswith("ats_limit_up_daily_archive_") and (fname.endswith(".json.gz") or fname.endswith(".json")):
                            date_part = fname.replace("ats_limit_up_daily_archive_", "").replace(".json.gz", "").replace(".json", "")
                            if date_part not in self._history_daily_records:
                                fpath = os.path.join(DATA_DIR, fname)
                                sub_data = _safe_read_json_or_gz(fpath)
                                if isinstance(sub_data, list):
                                    self._history_daily_records[date_part] = sub_data
            except Exception:
                pass
            return sorted(self._history_daily_records.keys())

    def get_records_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """获取指定历史日期的涨停归档记录 (支持即时按需从 Gzip 或纯 JSON 分日归档文件加载)"""
        if not date_str:
            return []
        with self._cache_lock:
            if date_str in self._history_daily_records:
                return list(self._history_daily_records[date_str])

            # 按需从分日独立文件加载 (自动尝试 .json.gz 与 .json)
            single_base = f"{ARCHIVE_PREFIX}{date_str}"
            sub_data = _safe_read_json_or_gz(single_base)
            if isinstance(sub_data, list):
                self._history_daily_records[date_str] = sub_data
                return list(sub_data)

            return []
