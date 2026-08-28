# -*- coding: utf-8 -*-
"""
ats/intraday_strategy_engine.py — 单独分时交易策略与策略路由引擎
支持新股首日分批卖出（策略A）、留仓赌趋势（策略B）以及频准激光（688826）8/18 专属上市盯盘与阶梯策略。
能够推断时间轴阶段、进行 7 节点动态评分、形态分类、实盘条件评估与阶段实操指引生成。
"""

import os
import json
import time
import shutil
import atexit
import hashlib
import threading
import logging
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time
from typing import Dict, List, Any, Optional, Tuple

from sys_utils import get_app_root, get_conf_path
from signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger("IntradayStrategyEngine")


def is_valid_stock_code(code: str) -> bool:
    """严格检验股票代码是否为合法 A 股/科创板/创业板/北交所代码 (排除 000000, 000123 等测试垃圾)"""
    if not code:
        return False
    c_str = "".join(filter(str.isdigit, str(code))).zfill(6)
    if len(c_str) != 6:
        return False
    if c_str in ("000000", "000123", "000002", "123456", "999999"):
        return False
    valid_prefixes = (
        "600", "601", "603", "605", "688", "689",
        "000", "001", "002", "003", "300", "301",
        "920", "83", "87", "43", "88"
    )
    return any(c_str.startswith(p) for p in valid_prefixes)


def resolve_stock_name(code: str) -> str:
    """根据股票代码解析标的名称（包含内置专属新股标的与保底格式）"""
    c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
    names_map = {
        "688826": "频准激光",
        "688835": "高凯技术",
        "688836": "宇树科技",
        "920199": "倍益康",
        "688787": "海天瑞声",
        "300862": "蓝盾光电",
        "000001": "平安银行"
    }
    return names_map.get(c_clean, f"标的_{c_clean}" if c_clean else "新股标的")


class IntradayStrategyEngine:
    """分时交易策略与新股阶梯盯盘引擎"""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, config_filename="intraday_newstock_strategies.json"):
        self.config_path = get_conf_path(config_filename, get_app_root())
        self.strategies: List[Dict[str, Any]] = []
        self.active_strategy: Optional[Dict[str, Any]] = None
        self.rule_state_map: Dict[str, Dict[str, Any]] = {} # code -> state
        self._is_dirty: bool = False
        self._last_saved_hash: str = ""
        self._last_save_time: float = 0.0
        self._lock = threading.RLock()
        self._cleanup_legacy_tmp_files()
        try:
            atexit.register(self._on_process_exit)
        except Exception:
            pass
        self.load_config()
        self.load_intraday_cache()

    def _cleanup_legacy_tmp_files(self):
        """[启动自愈] 自动清理 config 目录下遗留的历史 .tmp 临时碎片文件"""
        try:
            cache_dir = os.path.join(get_app_root(), "config")
            if os.path.exists(cache_dir):
                for fname in os.listdir(cache_dir):
                    if ".tmp" in fname:
                        full_p = os.path.join(cache_dir, fname)
                        try:
                            if os.path.isfile(full_p):
                                os.remove(full_p)
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"清理历史临时文件异常: {e}")

    def _on_process_exit(self):
        """系统退出安全清理钩子：仅在有数据变动时刷盘"""
        try:
            if getattr(self, "_is_dirty", False):
                self.save_intraday_cache(force=False)
        except Exception:
            pass

    def mark_dirty(self):
        """显式标记引擎数据发生实质变动"""
        self._is_dirty = True

    def _get_cache_filepath(self) -> str:
        cache_dir = os.path.join(get_app_root(), "config")
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, "intraday_strategy_state_cache.json")

    def load_intraday_cache(self) -> bool:
        """从 JSON 加载当日分时节点与状态锁，避免崩溃/重启导致时间线混乱"""
        cache_file = self._get_cache_filepath()
        if not os.path.exists(cache_file):
            return False
        with self._lock:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                today_str = datetime.now().strftime("%Y-%m-%d")
                if data.get("date") != today_str:
                    logger.info(f"🗑️ 清理非今日分时策略缓存 ({data.get('date')} vs {today_str})")
                    return False

                stocks_cache = data.get("stocks", {})
                for c_clean, s_data in stocks_cache.items():
                    raw_op = float(s_data.get("open_price", 0.0))
                    state = self._get_stock_state(c_clean, raw_op)
                    state["open_price"] = raw_op if raw_op > 1.0 else state["open_price"]
                    
                    # 清洗非交易时段的伪时间快照 (如 00:00~09:14 或 >15:05 的非盘中脏快照)
                    raw_snaps = s_data.get("time_snapshots", {})
                    clean_snaps = {}
                    if isinstance(raw_snaps, dict):
                        for t_k, s_v in raw_snaps.items():
                            t_5 = str(t_k).strip()[:5]
                            if "09:15" <= t_5 <= "15:05" and isinstance(s_v, dict):
                                clean_snaps[t_5] = s_v
                    state["time_snapshots"] = clean_snaps

                    if clean_snaps:
                        snap_highs = [float(v.get("high", v.get("price", 0.0))) for v in clean_snaps.values() if float(v.get("high", v.get("price", 0.0))) > 1.0]
                        snap_lows = [float(v.get("low", v.get("price", 0.0))) for v in clean_snaps.values() if float(v.get("low", v.get("price", 0.0))) > 1.0]
                        state["max_price"] = max(snap_highs) if snap_highs else float(s_data.get("max_price", state["open_price"]))
                        state["min_price"] = min(snap_lows) if snap_lows else float(s_data.get("min_price", state["open_price"]))
                    else:
                        state["max_price"] = state["open_price"]
                        state["min_price"] = state["open_price"]

                    state["high_am"] = float(s_data.get("high_am", state["max_price"]))
                    state["remaining_ratio"] = float(s_data.get("remaining_ratio", state["remaining_ratio"]))
                    state["triggered_rules"] = set(s_data.get("triggered_rules", []))
                    state["execution_logs"] = s_data.get("execution_logs", [])
                    state["manual_scores"] = s_data.get("manual_scores", {})
                    state["node_custom_params"] = s_data.get("node_custom_params", {})
                    state["node_locked_params"] = s_data.get("node_locked_params", {})

                    # 重构 signals 列表
                    sigs_raw = s_data.get("signals", [])
                    state["signals"] = []
                    for sig_dict in sigs_raw:
                        try:
                            sp = SignalPoint(
                                code=sig_dict.get("code", c_clean),
                                timestamp=sig_dict.get("timestamp", ""),
                                signal_type=SignalType.SELL if str(sig_dict.get("signal_type")) in ("SELL", SignalType.SELL.value) else SignalType.BUY,
                                price=float(sig_dict.get("price", 0.0)),
                                reason=sig_dict.get("reason", ""),
                                source=SignalSource.STRATEGY_RULE,
                                suggested_price=float(sig_dict.get("suggested_price", sig_dict.get("price", 0.0))),
                                sell_ratio=float(sig_dict.get("sell_ratio", 0.0))
                            )
                            state["signals"].append(sp)
                        except Exception as e_sig:
                            logger.debug(f"还原 SignalPoint 异常: {e_sig}")

                logger.info(f"✅ 成功从磁盘加载并清洗 {len(stocks_cache)} 只标的的分时节点持久化缓存 ({today_str})")
                return True
            except Exception as e:
                logger.error(f"❌ 加载分时策略持久化缓存异常: {e}")
                return False

    def _get_closing_eval_filepath(self) -> str:
        """获取新股首日收盘综合评分账本 JSON 路径"""
        config_dir = os.path.join(get_app_root(), "config")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "newstock_listing_closing_evaluations.json")

    def load_listing_closing_scorecards(self) -> Dict[str, Any]:
        """加载历史新股首日收盘定盘综合评分账本"""
        fp = self._get_closing_eval_filepath()
        if not os.path.exists(fp):
            return {}
        try:
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"加载新股首日收盘账本异常: {e}")
            return {}

    def save_listing_closing_scorecard(self, code: str, eval_result: Dict[str, Any]) -> bool:
        """【收盘定盘持久化】保存新股上市首日 15:00 收盘综合评分与 7 节点评级，作为永久历史档案"""
        c_clean = str(code).zfill(6)
        fp = self._get_closing_eval_filepath()
        try:
            data = self.load_listing_closing_scorecards()
            today_str = datetime.now().strftime("%Y-%m-%d")
            data[c_clean] = {
                "code": c_clean,
                "date": today_str,
                "listing_date": today_str,
                "open_price": eval_result.get("open_price", 0.0),
                "close_price": eval_result.get("price", 0.0),
                "max_price": eval_result.get("high_price", 0.0),
                "min_price": eval_result.get("low_price", 0.0),
                "vwap": eval_result.get("vwap", 0.0),
                "turnover_rate": eval_result.get("turnover_rate", 0.0),
                "amount_yi": eval_result.get("amount_yi", 0.0),
                "total_weighted_score": eval_result.get("total_weighted_score", 0.0),
                "pattern": eval_result.get("pattern", ""),
                "t1_advice": eval_result.get("t1_advice", ""),
                "node_results": eval_result.get("node_results", []),
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            tmp_fp = fp + f".tmp_{os.getpid()}_{threading.get_ident()}"
            try:
                with open(tmp_fp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                if os.path.exists(fp):
                    os.replace(tmp_fp, fp)
                else:
                    os.rename(tmp_fp, fp)
                logger.info(f"💾 [收盘定盘] 标的 [{c_clean}] 上市首日收盘综合评分 ({eval_result.get('total_weighted_score')}分, {eval_result.get('pattern')}) 已成功永久持久化！")
                return True
            finally:
                if os.path.exists(tmp_fp):
                    try:
                        os.remove(tmp_fp)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"保存新股首日收盘账本异常: {e}")
            return False

    def save_intraday_cache_throttled(self, interval_sec: float = 300.0) -> bool:
        """
        【低频安全节流防抖持久化（5分钟调度）】
        仅在发生实质变动 (_is_dirty) 且距上次写盘超过 interval_sec (默认300s/5分钟) 时才写盘。
        无变动时 0 磁盘 I/O，有变动时确保盘中数据不会因系统意外崩溃而丢失。
        """
        if not getattr(self, "_is_dirty", False):
            return True
        now_ts = time.time()
        if now_ts - getattr(self, "_last_save_time", 0.0) < interval_sec:
            return True
        return self.save_intraday_cache(force=False)

    def save_intraday_cache(self, force: bool = False) -> bool:
        """
        持久化保存当前盘中所有标的的分时节点、锁死状态与买卖点账本至磁盘
        【严苛写盘约束与 0 冗余 I/O 保护】：
        1. 若未被标记为 dirty 且 force=False，直接短路跳过，绝不触发物理写盘；
        2. 内存计算数据 MD5 哈希对比：若数据序列化后与上次写入磁盘的内容完全一致，自动重置 dirty 并短路，绝不触发写盘；
        3. 仅在窗口关闭、系统退出、定时防抖、或人工干预参数/产生买卖点信号时才触发持久化；
        4. 写入临时文件时使用 try...finally，确保临时文件绝不残留。
        """
        if not force and not getattr(self, "_is_dirty", False):
            return True

        with self._lock:
            cache_file = self._get_cache_filepath()
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                stocks_data = {}
                for c_clean, state in list(self.rule_state_map.items()):
                    op = float(state.get("open_price", 0.0))
                    locked = state.get("node_locked_params", {})
                    snapshots = state.get("time_snapshots", {})

                    # 严格校验：若未获取到 TDX 有效行情数据 (op <= 1.0) 且无真实时间线快照，判定为无效/未连线上线的脏数据，禁止持久化落盘污染账本！
                    if op <= 1.0 and not snapshots and not locked:
                        continue

                    # 消除脏数据残留：若 node_1 或 node_2 锁定了旧默认值，但当前已有真实 open_price (> 1.0)，自动修正对齐
                    if op > 1.0:
                        custom_params = state.get("node_custom_params", {})
                        if "node_1" in locked and abs(float(locked.get("node_1", 0.0)) - op) > 0.01:
                            if "node_1" not in custom_params and "node_1_auction" not in custom_params:
                                locked["node_1"] = op
                                locked["node_1_auction"] = op
                        if "node_2" in locked and float(locked.get("node_2", 0.0)) < op * 0.8:
                            if "node_2" not in custom_params and "node_2_first_wave" not in custom_params:
                                if snapshots and "09:40" in snapshots:
                                    locked["node_2"] = float(snapshots["09:40"].get("price", op))
                                    locked["node_2_first_wave"] = locked["node_2"]
                                    locked["node_2_first_attack"] = locked["node_2"]

                    sigs_serialized = []
                    for sig in state.get("signals", []):
                        sigs_serialized.append({
                            "code": getattr(sig, "code", c_clean),
                            "timestamp": getattr(sig, "timestamp", ""),
                            "signal_type": getattr(sig, "signal_type", SignalType.SELL).value if hasattr(getattr(sig, "signal_type", None), "value") else str(getattr(sig, "signal_type", "")),
                            "price": getattr(sig, "price", 0.0),
                            "reason": getattr(sig, "reason", ""),
                            "suggested_price": getattr(sig, "suggested_price", getattr(sig, "price", 0.0)),
                            "sell_ratio": getattr(sig, "sell_ratio", 0.0)
                        })

                    stocks_data[c_clean] = {
                        "open_price": op,
                        "max_price": state.get("max_price", 0.0),
                        "min_price": state.get("min_price", 0.0),
                        "high_am": state.get("high_am", 0.0),
                        "remaining_ratio": state.get("remaining_ratio", 1.0),
                        "triggered_rules": list(state.get("triggered_rules", set())),
                        "execution_logs": state.get("execution_logs", []),
                        "manual_scores": state.get("manual_scores", {}),
                        "node_custom_params": state.get("node_custom_params", {}),
                        "node_locked_params": locked,
                        "time_snapshots": snapshots,
                        "signals": sigs_serialized
                    }

                # 【⚡ 核心优化：内容哈希脏检查，无变动跳过物理写盘】
                data_str = json.dumps(stocks_data, sort_keys=True)
                current_hash = hashlib.md5(data_str.encode("utf-8")).hexdigest()
                if not force and current_hash == getattr(self, "_last_saved_hash", ""):
                    self._is_dirty = False
                    return True

                cache_data = {
                    "date": today_str,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "stocks": stocks_data
                }
                tmp_file = cache_file + f".tmp_{os.getpid()}_{threading.get_ident()}"
                try:
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
                    if os.path.exists(cache_file):
                        os.replace(tmp_file, cache_file)
                    else:
                        os.rename(tmp_file, cache_file)
                    self._last_saved_hash = current_hash
                    self._is_dirty = False
                    self._last_save_time = time.time()
                    return True
                finally:
                    if os.path.exists(tmp_file):
                        try:
                            os.remove(tmp_file)
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"❌ 保存分时策略持久化缓存异常: {e}")
                return False

    def load_config(self) -> bool:
        """从 JSON 加载策略配置并自动清洗无效垃圾策略"""
        if not os.path.exists(self.config_path):
            alt_path = os.path.join(get_app_root(), "config", "intraday_newstock_strategies.json")
            if os.path.exists(alt_path):
                self.config_path = alt_path
        if not os.path.exists(self.config_path):
            logger.warning(f"Strategy config file not found: {self.config_path}")
            return False
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.strategies = data.get("strategies", [])
            # 🧹 启动即时自动清洗不存在的垃圾/占位策略 (如 000000, 000123)
            self.clean_invalid_strategies()
            logger.info(f"✅ 成功加载并就绪 {len(self.strategies)} 套有效分时交易策略配置")
            return True
        except Exception as e:
            logger.error(f"❌ 加载分时策略配置失败: {e}")
            return False

    def clean_invalid_strategies(self) -> int:
        """
        【🧹 自动清洗】清理策略库中不存在的垃圾/占位标的策略（如 000000, 000123 等虚构占位代码）
        物理同步清理 config/intraday_newstock_strategies.json 磁盘文件
        返回清理掉的垃圾策略数量
        """
        invalid_patterns = {"000000", "000123", "标的_000000", "标的_000123", "个股_000123"}
        valid_strategies = []
        removed_count = 0

        with self._lock:
            for st in self.strategies:
                st_id = str(st.get("id", ""))
                st_name = str(st.get("name", ""))
                target_codes = [str(c).strip().zfill(6) for c in st.get("target_codes", [])]

                # 检查是否命中无效占位特征
                is_invalid = False
                if any(p in st_id for p in invalid_patterns) or any(p in st_name for p in invalid_patterns):
                    is_invalid = True
                elif target_codes and not any(is_valid_stock_code(c) for c in target_codes):
                    is_invalid = True

                if is_invalid:
                    removed_count += 1
                    logger.info(f"🧹 [IntradayStrategyEngine] 自动清洗并剔除垃圾无效策略: [{st_id}] {st_name}")
                else:
                    valid_strategies.append(st)

            if removed_count > 0:
                self.strategies = valid_strategies
                # 同步物理写盘更新
                try:
                    conf_path = self.config_path
                    if os.path.exists(conf_path):
                        with open(conf_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        data["strategies"] = valid_strategies
                        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        tmp_path = conf_path + ".tmp"
                        with open(tmp_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        os.replace(tmp_path, conf_path)
                        logger.info(f"💾 [IntradayStrategyEngine] 垃圾策略清理完毕，已同步物理落盘 (剔除 {removed_count} 套无效策略)")
                except Exception as e_save:
                    logger.error(f"❌ 垃圾策略清理写盘异常: {e_save}")

        return removed_count

    def save_config(self, data: Dict[str, Any]) -> bool:
        """保存自定制策略配置"""
        try:
            tmp_path = self.config_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.config_path)
            self.strategies = data.get("strategies", [])
            logger.info("✅ 策略配置文件更新落盘成功")
            return True
        except Exception as e:
            logger.error(f"❌ 保存策略配置文件失败: {e}")
            return False

    def get_stock_ladder_spec(self, code: Optional[str] = None) -> Dict[str, Any]:
        """
        获取证券阶梯规格配置（优先从 JSON 专属策略中读取，如 688826、688835、688836 等）
        """
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
        if c_clean:
            for st in self.strategies:
                target_codes = st.get("target_codes", [])
                target_code = st.get("target_code", "")
                tc_list = ["".join(filter(str.isdigit, str(x))).zfill(6) for x in target_codes if x and str(x).strip()]
                t_single = "".join(filter(str.isdigit, str(target_code))).zfill(6) if target_code else ""
                if (c_clean in tc_list or (t_single and c_clean == t_single)) and "stock_spec" in st:
                    return st["stock_spec"]

        # 1. 尝试从 NewStockFetcher 权威 IPO 日历中获取真实新股基础信息
        ipo_info = {}
        try:
            from ats.new_stock_fetcher import NewStockFetcher
            ipo_dict = NewStockFetcher.get_instance().fetch_ipo_calendar()
            if c_clean in ipo_dict:
                ipo_info = ipo_dict[c_clean]
        except Exception:
            pass

        stock_name = ipo_info.get("name") or resolve_stock_name(c_clean) or (f"标的_{c_clean}" if c_clean else "新股标的")
        real_issue_p = float(ipo_info.get("issue_price", 0.0) or 0.0)
        listing_d = str(ipo_info.get("listing_date", "") or "").split(" ")[0].strip()
        apply_d = str(ipo_info.get("apply_date", "") or "").split(" ")[0].strip()

        # 若权威 IPO 日历中有真实发行价，动态构建真实新股规格
        if real_issue_p > 0:
            float_shares_w = 2000.0
            float_mv = round(real_issue_p * float_shares_w * 10000 / 1e8, 2)
            ladder_gains = [100.0, 200.0, 300.0, 400.0, 500.0]
            price_ladder = [
                {
                    "name": f"+{int(g)}%",
                    "gain_pct": g,
                    "price": round(real_issue_p * (1.0 + g / 100.0), 2),
                    "meaning": "翻倍稳健基准" if g == 100.0 else ("强势基准" if g == 200.0 else "高频溢价")
                }
                for g in ladder_gains
            ]
            return {
                "code": c_clean,
                "name": stock_name,
                "issue_price": real_issue_p,
                "listing_date": listing_d or datetime.now().strftime("%Y-%m-%d"),
                "subscription_date": apply_d or "-",
                "float_shares_wan": float_shares_w,
                "float_mv_yi": float_mv,
                "lottery_rate": "0.02500%",
                "price_ladder": price_ladder,
                "turnover_ladder": [
                    {"level": "弱换手", "range": "<40%", "min": 0.0, "max": 40.0, "meaning": "关注度不足"},
                    {"level": "标准换手", "range": "50-70%", "min": 50.0, "max": 70.0, "meaning": "健康"},
                    {"level": "高换手", "range": "70-90%", "min": 70.0, "max": 90.0, "meaning": "充分交换"},
                    {"level": "极高换手", "range": ">90%", "min": 90.0, "max": 999.0, "meaning": "过热/分歧"}
                ],
                "intensity_benchmark": {
                    "metric": f"成交额/流通市值({float_mv:.1f}亿)",
                    "threshold": 2.5,
                    "meaning": "资金强度极高"
                }
            }

        # 2. 尝试从 TDX 实时/昨日快照获取昨收价作为常规股票基准价
        ref_p = 0.0
        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            fetcher = TDXRealtimeFetcher.get_instance()
            y_ohlc = fetcher.get_yesterday_ohlc(c_clean)
            if y_ohlc and float(y_ohlc.get("close", 0.0)) > 0:
                ref_p = float(y_ohlc.get("close", 0.0))
            if ref_p <= 0:
                snap = fetcher.fetch_stock_snapshot(c_clean)
                ref_p = float(snap.get("last_close", snap.get("price", 0.0)))
        except Exception:
            pass

        base_ref = ref_p if ref_p > 0 else 10.0
        return {
            "code": c_clean or "000000",
            "name": stock_name,
            "issue_price": base_ref,
            "reference_price": base_ref,
            "listing_date": listing_d or "",
            "float_shares_wan": 1000.0,
            "float_mv_yi": 15.0,
            "lottery_rate": "0.02000%",
            "price_ladder": [
                {"name": "+100%", "gain_pct": 100.0, "price": round(base_ref * 2.0, 2), "meaning": "翻倍"},
                {"name": "+200%", "gain_pct": 200.0, "price": round(base_ref * 3.0, 2), "meaning": "强势基准"},
                {"name": "+300%", "gain_pct": 300.0, "price": round(base_ref * 4.0, 2), "meaning": "高频发区间"},
                {"name": "+400%", "gain_pct": 400.0, "price": round(base_ref * 5.0, 2), "meaning": "强势上限"},
                {"name": "+500%", "gain_pct": 500.0, "price": round(base_ref * 6.0, 2), "meaning": "极端行情"}
            ],
            "turnover_ladder": [
                {"level": "弱换手", "range": "<40%", "min": 0.0, "max": 40.0, "meaning": "关注度不足"},
                {"level": "标准换手", "range": "50-70%", "min": 50.0, "max": 70.0, "meaning": "健康"},
                {"level": "高换手", "range": "70-90%", "min": 70.0, "max": 90.0, "meaning": "充分交换"},
                {"level": "极高换手", "range": ">90%", "min": 90.0, "max": 999.0, "meaning": "过热/分歧"}
            ],
            "intensity_benchmark": {
                "metric": "成交额/流通市值(15.0亿)",
                "threshold": 2.5,
                "meaning": "资金强度极高"
            }
        }

    def get_timeline_nodes_def(self, code: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取 7 节点标准时序定义列表"""
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else "688826"
        st = self.auto_select_strategy(0.0, code=c_clean)
        if st and "timeline_nodes" in st:
            return st["timeline_nodes"]

        # 默认回退 7 节点标准定义
        return [
            {
                "node_id": "node_1_auction",
                "node_num": "①",
                "time_str": "9:25",
                "time_range": "09:15~09:25",
                "name": "集合竞价定盘",
                "weight": 0.15,
                "focus": "开盘价/涨幅、买卖盘口厚度",
                "strong_signals": "高开+200%以上(>560.64元)；买一量>>卖一量；买单持续堆积",
                "risk_signals": "高开后买单快速撤单；卖盘压单沉重；开盘价远低于预期",
                "action_guide": "若高开>560元且买盘充沛，启动强势持有/冲高阶梯卖出；若远低于373元谨慎对待"
            },
            {
                "node_id": "node_2_first_wave",
                "node_num": "②",
                "time_str": "9:40",
                "time_range": "09:25~09:40",
                "name": "早盘第一波攻击",
                "weight": 0.15,
                "focus": "开盘后第一波放量方向",
                "strong_signals": "放量上攻突破开盘价；量价齐升；快速脱离成本区",
                "risk_signals": "放量砸盘跌破开盘价；高开低走；量增价跌",
                "action_guide": "冲高较开盘涨10%以上挂买一价*1.02卖出首批50%；跌破开盘价且无反弹果断减仓"
            },
            {
                "node_id": "node_3_turnover",
                "node_num": "③",
                "time_str": "10:00",
                "time_range": "09:40~10:00",
                "name": "换手质量检验",
                "weight": 0.20,
                "focus": "换手率进度、价格是否抬升",
                "strong_signals": "持续换手且价格抬升；10min换手>15%；低点不断抬高",
                "risk_signals": "巨量但价格不涨；放量滞涨；低点下移",
                "action_guide": "10:00前未触发冲高则10:00市价卖30%；若量缩价稳低点抬高则持有等待分歧承接"
            },
            {
                "node_id": "node_4_divergence",
                "node_num": "④",
                "time_str": "11:00",
                "time_range": "10:00~11:00",
                "name": "分歧承接测试",
                "weight": 0.15,
                "focus": "回落后承接力、是否破分时均价线",
                "strong_signals": "回落后快速收回；均价线向上；缩量回调后放量上攻",
                "risk_signals": "一路下跌不回头；破均价线无量承接；反弹无力",
                "action_guide": "均线不破且放量再起可持有博午后；破均线且反抽不过均线坚决离场"
            },
            {
                "node_id": "node_5_afternoon",
                "node_num": "⑤",
                "time_str": "14:00",
                "time_range": "13:00~14:00",
                "name": "午后突破验证",
                "weight": 0.10,
                "focus": "午后是否再创新高、板块联动",
                "strong_signals": "突破上午最高价；午后放量上涨；激光/半导体设备板块同步走强",
                "risk_signals": "午后弱势缩量；冲高回落；板块分化",
                "action_guide": "突破上午最高价继续持有；若冲高回落且板块走弱逢高派发剩余仓位"
            },
            {
                "node_id": "node_6_closing_rally",
                "node_num": "⑥",
                "time_str": "14:50",
                "time_range": "14:30~14:50",
                "name": "尾盘抢筹强度",
                "weight": 0.15,
                "focus": "尾盘方向、量能变化",
                "strong_signals": "放量创新高；尾盘抢筹；封板或逼近最高价",
                "risk_signals": "放量跳水；尾盘恐慌抛售；快速回落",
                "action_guide": "尾盘抢筹坚决且逼近最高准备保留过夜仓；若放量跳水尾盘市价清仓"
            },
            {
                "node_id": "node_7_closing_structure",
                "node_num": "⑦",
                "time_str": "15:00",
                "time_range": "14:50~15:00",
                "name": "收盘结构与锁仓",
                "weight": 0.10,
                "focus": "收盘价位置、收盘/最高价比例",
                "strong_signals": "收盘接近最高(收盘/最高>90%)；缩量横盘守住涨幅",
                "risk_signals": "收盘远低于最高(收盘/最高<80%)；放量跳水",
                "action_guide": "收盘/最高>90%且综合评分>=8.0可留10%~20%过夜，次日竞价关注；否则清仓"
            }
        ]

    def get_open_price_tier(self, open_price: float, code: Optional[str] = None) -> Tuple[str, str, str]:
        """
        开盘价档位速查判定（100% 动态自适应不同发行价的新股与策略）
        返回: (tier_name, default_strategy_id, action_mode)
        """
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
        st = None
        if c_clean:
            for s in self.strategies:
                tc = [str(x).zfill(6) for x in s.get("target_codes", []) if str(x).strip()]
                if c_clean in tc:
                    st = s
                    break

        st_id = st.get("id", "strategy_a_new_stock_batch_sell") if st else "strategy_a_new_stock_batch_sell"

        try:
            open_price = float(open_price)
        except (ValueError, TypeError):
            open_price = 0.0

        if st and "stock_spec" in st:
            spec = st["stock_spec"]
            issue_p = float(spec.get("issue_price", 0.0))
            if issue_p > 0:
                p_200 = issue_p * 3.0  # +200% 强势基准
                p_150 = issue_p * 2.5  # +150% 乐观下沿
                p_100 = issue_p * 2.0  # +100% 翻倍中性
                p_50 = issue_p * 1.5   # +50% 中性下沿

                if open_price >= p_200:
                    return ("乐观档(+200%基准)", st_id, "trend_hold")
                elif open_price >= p_150:
                    return ("乐观下沿(+150%)", st_id, "standard")
                elif open_price >= p_100:
                    return ("中性档(+100%翻倍)", st_id, "standard")
                elif open_price >= p_50:
                    return ("中性下沿(+50%)", st_id, "decelerated")
                else:
                    return ("保守档(<+50%)", st_id, "hold_rebound")

        # 对于通用日常个股策略，按日常标准档位执行
        if st and st.get("id") == "strategy_c_daily_surge_ladder":
            return ("日常标准档", st_id, "standard")

        # 通用新股/未指定发行价标准档位
        if open_price >= 467.0:
            return ("乐观档", "strategy_b_new_stock_trend_hold", "trend_hold")
        elif open_price >= 412.0:
            return ("乐观下沿", "strategy_a_new_stock_batch_sell", "standard")
        elif open_price >= 336.0:
            return ("中性档", "strategy_a_new_stock_batch_sell", "standard")
        elif open_price >= 280.0:
            return ("中性下沿", "strategy_a_new_stock_batch_sell", "decelerated")
        else:
            return ("保守档", "strategy_a_new_stock_batch_sell", "hold_rebound")

    def get_all_target_codes(self) -> List[str]:
        """获取所有 JSON 策略配置中指定的目标股票代码列表（去除重复与格式化）"""
        codes = []
        for st in self.strategies:
            t_codes = st.get("target_codes", [])
            t_code = st.get("target_code", "")
            if isinstance(t_codes, list):
                for tc in t_codes:
                    c_clean = "".join(filter(str.isdigit, str(tc))).zfill(6)
                    if c_clean and c_clean not in codes and c_clean != "000000":
                        codes.append(c_clean)
            if t_code:
                c_clean = "".join(filter(str.isdigit, str(t_code))).zfill(6)
                if c_clean and c_clean not in codes and c_clean != "000000":
                    codes.append(c_clean)
        if not codes:
            codes = ["688826"]
        return codes

    def get_code_strategy_map(self) -> Dict[str, Dict[str, Any]]:
        """获取全量代码与策略绑定映射字典 {code: strategy_dict}"""
        code_map = {}
        for c in self.get_all_target_codes():
            code_map[c] = self.auto_select_strategy(0.0, code=c)
        return code_map

    def get_default_target_code(self) -> Optional[str]:
        """获取首个目标股票代码，无则默认 688826"""
        all_codes = self.get_all_target_codes()
        return all_codes[0] if all_codes else "688826"

    def get_strategy_by_id(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """按 strategy_id 获取对应的策略字典 (支持向下兼容别名与标的代码)"""
        for st in self.strategies:
            if st.get("id") == strategy_id:
                return st
        digits = "".join(filter(str.isdigit, str(strategy_id)))
        if digits and len(digits) >= 6:
            for st in self.strategies:
                if digits in st.get("id", "") or any(digits == "".join(filter(str.isdigit, str(tc))).zfill(6) for tc in st.get("target_codes", [])):
                    return st
        if strategy_id in ("strategy_a_new_stock_batch_sell", "strategy_a"):
            for st in self.strategies:
                if "688826" in st.get("id", "") or "batch" in st.get("id", ""):
                    return st
        if strategy_id in ("strategy_b_new_stock_trend_hold", "strategy_b"):
            for st in self.strategies:
                if "hold" in st.get("id", "") or "688835" in st.get("id", ""):
                    return st
        return None

    def is_stock_first_listing_day(self, code: str) -> bool:
        """
        【100% 数据与每日自动更新新股上市表驱动】客观精准判定标的今日是否为【上市首日】：
        1. 权威新股上市表 (NewStockFetcher / new_stock_ipo_calendar.json)：
           - 严格从每日自动更新的新股上市表中获取官方 listing_date 与 status ('首日(N)', '前5日(C)', '次新', '已上市', '待上市')；
           - 若 status == '首日(N)' 或 listing_date == 今日 (today_str)：100% 判定为上市首日 (True)；
           - 若 status in ('前5日(C)', '次新', '已上市') 或 listing_date < 今日：100% 判定为非首日 (False)；
        2. TDX 真实日 K 线历史数据硬核核验：
           - 若日 K 线已产生 >= 2 根：已有多个历史交易日，100% 判定为非首日 (False)；
           - 若日 K 线仅有 1 根且日期为今日：今日首次产生日 K，100% 判定为上市首日 (True)；
           - 若日 K 最后一根日期早于今日：已有历史日 K，100% 判定为非首日 (False)；
        3. 昨日真实 OHLC 检验：
           - 若昨日有真实开盘/最高成交记录，100% 判定为非首日 (False)；
        4. 彻底摒弃任何基于股票名称字符串猜测（如 startswith('N')）的不可靠逻辑。
        """
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
        if not c_clean:
            return False

        if not hasattr(self, "_first_listing_day_cache"):
            self._first_listing_day_cache = {}

        now_ts = time.time()
        cached = self._first_listing_day_cache.get(c_clean)
        if cached and (now_ts - cached[1] < 30.0):
            return cached[0]

        today_str = datetime.now().strftime("%Y-%m-%d")
        res_first_day = None

        # 1. 【最高权威·每日自动更新的新股上市表】：直接从 NewStockFetcher 权威日历与状态判定
        try:
            from ats.new_stock_fetcher import NewStockFetcher
            ipo_fetcher = NewStockFetcher.get_instance()
            ipo_dict = getattr(ipo_fetcher, '_cached_ipo_dict', {})
            if c_clean in ipo_dict:
                ipo_info = ipo_dict[c_clean]
                ipo_list_date = str(ipo_info.get("listing_date", "")).strip()[:10]
                ipo_status = str(ipo_info.get("status", "")).strip()

                if ipo_status == "首日(N)" or (ipo_list_date and ipo_list_date == today_str):
                    res_first_day = True
                elif ipo_status in ("前5日(C)", "次新", "已上市") or (ipo_list_date and len(ipo_list_date) == 10 and ipo_list_date < today_str):
                    res_first_day = False
        except Exception as e_ipo:
            logger.debug(f"新股上市表校验异常: {e_ipo}")

        # 2. 【核心客观证据·TDX 真实日 K 线历史数量与日期检验】
        if res_first_day is None:
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                fetcher = TDXRealtimeFetcher.get_instance()
                df_daily = fetcher.fetch_kline_bars(c_clean, category="day", count=5)
                if df_daily is not None and not df_daily.empty:
                    last_row_date = str(df_daily.iloc[-1].get("datetime", df_daily.iloc[-1].get("time", "")))[:10]
                    if len(df_daily) >= 2:
                        res_first_day = False  # 已有 2 根及以上日 K 线，必非首日
                    elif len(df_daily) == 1:
                        if last_row_date == today_str:
                            res_first_day = True   # 仅有今天 1 根日 K 线且为今日，为首日
                        elif last_row_date < today_str:
                            res_first_day = False  # 日 K 属于历史过去交易日，必非首日
            except Exception:
                pass

        # 3. 【策略规格中的上市日期校验】
        if res_first_day is None:
            spec = self.get_stock_ladder_spec(c_clean)
            list_date = str(spec.get("listing_date", "")).strip()[:10]
            if list_date and len(list_date) == 10 and list_date != "-":
                if list_date == today_str:
                    res_first_day = True
                elif list_date < today_str:
                    res_first_day = False

        # 4. 【昨日真实走势校验】：若已有昨日 OHLC，必为非首日
        if res_first_day is None:
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                y_ohlc = TDXRealtimeFetcher.get_instance().get_yesterday_ohlc(c_clean)
                if y_ohlc and (float(y_ohlc.get("open", 0.0)) > 0 or float(y_ohlc.get("high", 0.0)) > 0):
                    res_first_day = False
            except Exception:
                pass

        # 5. 【历史收盘定盘记录校验】
        if res_first_day is None:
            closing_scorecards = self.load_listing_closing_scorecards()
            if c_clean in closing_scorecards:
                rec = closing_scorecards[c_clean]
                rec_date = str(rec.get("date", rec.get("listing_date", ""))).strip()[:10]
                if rec_date and rec_date < today_str:
                    res_first_day = False

        # 6. 【最终安全兜底】：未在 IPO 表中且无确凿首日证据的标的，一律判定为常规非首日股票
        if res_first_day is None:
            res_first_day = False

        self._first_listing_day_cache[c_clean] = (res_first_day, now_ts)
        return res_first_day

    def is_stock_unlisted(self, code: str) -> bool:
        """
        【100% 动态自适应数据驱动】权威检测标的是否处于【尚未上市/待挂牌/申购/发行中】状态：
        1. 权威 IPO 日历检验 (NewStockFetcher):
           - 若在 IPO 日历中，且 listing_date 为空/待定/未公布，或 listing_date > 今日 -> 100% 待上市 (True);
           - 若 status in ('待上市', '发行中', '待发行', '已发行待上市', '申购中') -> 100% 待上市 (True);
           - 若 listing_date 存在且 <= 今日 (历史上市老股) 且 status in ('首日(N)', '前5日(C)', '次新', '已上市') -> 进入 K 线复核;
        2. 策略与规格元数据检验 (spec):
           - 若 spec.get('is_unlisted') is True，或 spec.get('listing_date') in ('', '-', '待定') 且有 issue_price -> 待上市 (True);
        3. TDX 真实日 K 与演练测试脏数据动态过滤:
           - 过滤交易所周末/盘前撮合演练产生的 0.01元/1.08元 等伪测试日 K；
           - 只有存在 >=2 根 close > 0.10 且 amount > 50000 的真实历史日 K 时，才确认已上市；
        4. 价格倒挂自适应熔断:
           - 若开盘价/现价 <= 0.05 元，或与发行价倒挂严重 (>80% 跌幅且成交几乎为0)，自动自适应识别为待上市标的并拦截卖出。
        """
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
        if not c_clean or not is_valid_stock_code(c_clean):
            return False

        if not hasattr(self, "_unlisted_cache"):
            self._unlisted_cache = {}

        now_ts = time.time()
        cached = self._unlisted_cache.get(c_clean)
        if cached and (now_ts - cached[1] < 15.0):
            return cached[0]

        today_str = datetime.now().strftime("%Y-%m-%d")
        res_unlisted = None

        # 1. 权威新股上市表与 IPO 日历检验 (包含未公布上市日期的所有新股)
        try:
            from ats.new_stock_fetcher import NewStockFetcher
            ipo_fetcher = NewStockFetcher.get_instance()
            ipo_dict = getattr(ipo_fetcher, '_cached_ipo_dict', {})
            if c_clean in ipo_dict:
                ipo_info = ipo_dict[c_clean]
                ipo_status = str(ipo_info.get("status", "")).strip()
                ipo_list_date = str(ipo_info.get("listing_date", "")).strip()[:10]

                if ipo_status in ("待上市", "发行中", "待发行", "已发行待上市", "申购中"):
                    res_unlisted = True
                elif not ipo_list_date or ipo_list_date in ("-", "待定", "None", "null"):
                    # 尚未公布上市日期或已发行待挂牌，100% 属于待上市新股
                    res_unlisted = True
                elif len(ipo_list_date) == 10 and ipo_list_date > today_str:
                    res_unlisted = True
                elif len(ipo_list_date) == 10 and ipo_list_date == today_str:
                    # 今日上市首日
                    res_unlisted = False
                elif len(ipo_list_date) == 10 and ipo_list_date < today_str:
                    res_unlisted = False
        except Exception:
            pass

        # 2. 策略规格规格元数据检验
        if res_unlisted is None:
            spec = self.get_stock_ladder_spec(c_clean)
            if spec.get("is_unlisted") is True:
                res_unlisted = True
            else:
                list_d = str(spec.get("listing_date", "")).strip()[:10]
                issue_p = float(spec.get("issue_price", 0.0) or 0.0)
                if (not list_d or list_d in ("-", "待定")) and issue_p > 0:
                    res_unlisted = True
                elif list_d and len(list_d) == 10 and list_d > today_str:
                    res_unlisted = True

        # 3. TDX 真实日 K 与演练测试脏数据动态过滤
        if res_unlisted is None:
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                fetcher = TDXRealtimeFetcher.get_instance()
                df_daily = fetcher.fetch_kline_bars(c_clean, category="day", count=10)
                if df_daily is not None and not df_daily.empty:
                    # 严格过滤伪测试脏日 K (如 open <= 0.05 或 amount <= 1000)
                    valid_bars = df_daily[
                        (df_daily["close"] > 0.10) &
                        (df_daily["open"] > 0.10) &
                        ((df_daily["amount"] > 50000) | (df_daily["volume"] > 500))
                    ]
                    if len(valid_bars) >= 2:
                        res_unlisted = False  # 存在多日真实正常交易日 K 线，必已上市
                    elif len(valid_bars) == 1:
                        # 仅有 1 根有效日 K，检查是否为今日首日
                        bar_date = str(valid_bars.iloc[-1].get("datetime", ""))[:10]
                        if bar_date == today_str:
                            res_unlisted = False  # 今日上市首日
                        else:
                            res_unlisted = False
                    else:
                        # 真实日 K 为 0 根 (全是 0.01元 演练数据或空数据)
                        spec = self.get_stock_ladder_spec(c_clean)
                        issue_p = float(spec.get("issue_price", 0.0) or 0.0)
                        if issue_p > 0:
                            res_unlisted = True
                else:
                    spec = self.get_stock_ladder_spec(c_clean)
                    issue_p = float(spec.get("issue_price", 0.0) or 0.0)
                    if issue_p > 0:
                        res_unlisted = True
            except Exception:
                pass

        if res_unlisted is None:
            res_unlisted = False

        self._unlisted_cache[c_clean] = (res_unlisted, now_ts)
        return res_unlisted

    def auto_select_strategy(self, open_price: float, code: Optional[str] = None, is_b_conditions_met: bool = True) -> Dict[str, Any]:
        """
        根据股票代码 code 或开盘价与条件自动选择对应策略：
        - 待上市新股：优先匹配专属上市估价策略 (保留发行价与阶梯估价)
        - 上市首日当天：自动匹配该标的专属首日阶梯策略
        - 非首日已上市新股与全部常规日常个股：100% 自动匹配通用日常策略 (strategy_c_daily_surge_ladder)
        """
        if code:
            c_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
            if not is_valid_stock_code(c_clean):
                daily_strat = self.get_strategy_by_id("strategy_c_daily_surge_ladder")
                return daily_strat if daily_strat else (self.strategies[0] if self.strategies else {})

            is_unlisted = self.is_stock_unlisted(c_clean)
            is_first_day = self.is_stock_first_listing_day(c_clean)

            # 🛡️ 核心业务法则：仅在非待上市且非首日上市（即常规老股票/次新股）时，匹配日常通用策略！
            if not is_unlisted and not is_first_day:
                daily_strat = self.get_strategy_by_id("strategy_c_daily_surge_ladder")
                if daily_strat:
                    return daily_strat

            # 🆕 待上市或首日上市：优先匹配专属上市/首日策略
            for st in self.strategies:
                target_codes = st.get("target_codes", [])
                target_code = st.get("target_code", "")
                st_id = st.get("id", "")
                if isinstance(target_codes, list) and any(c_clean == "".join(filter(str.isdigit, str(tc))).zfill(6) for tc in target_codes if tc and str(tc).strip() not in ("", "000000")):
                    return st
                if target_code and c_clean == "".join(filter(str.isdigit, str(target_code))).zfill(6) and str(target_code).strip() not in ("", "000000"):
                    return st
                if c_clean in st_id and st_id != "strategy_c_daily_surge_ladder":
                    return st

            # 🚀 首日新股若尚无专属策略，尝试自动从权威 IPO 日历读取真实发行价生成专属策略并热重载
            try:
                from ats.new_stock_strategy_generator import NewStockStrategyGenerator
                from ats.new_stock_fetcher import NewStockFetcher
                generator = NewStockStrategyGenerator.get_instance()
                ipo_dict = NewStockFetcher.get_instance().fetch_ipo_calendar()
                ipo_info = ipo_dict.get(c_clean, {})
                stock_name = ipo_info.get("name") or resolve_stock_name(c_clean)
                real_issue_p = float(ipo_info.get("issue_price", 0.0) or 0.0)
                gen_payload = {
                    "code": c_clean,
                    "name": stock_name,
                    "price": open_price,
                    "issue_price": real_issue_p,
                    "listing_date": ipo_info.get("listing_date") or datetime.now().strftime("%Y-%m-%d"),
                    "apply_date": ipo_info.get("apply_date") or ""
                }
                gen_strat = generator.generate_strategy(gen_payload)
                if gen_strat:
                    generator.save_or_update_strategy(gen_strat)
                    self.load_config()
                    return gen_strat
            except Exception as e_gen:
                logger.debug(f"自动生成新股 {c_clean} 首日策略异常: {e_gen}")

            # 首日降级回退至新股通用 A/B 策略
            tier_name, strat_id, mode = self.get_open_price_tier(open_price, code=c_clean)
            if strat_id == "strategy_b_new_stock_trend_hold" and not is_b_conditions_met:
                strat_id = "strategy_a_new_stock_batch_sell"
            found = self.get_strategy_by_id(strat_id)
            if found:
                return found

        # 未传 code 时的开盘价档位判定 (针对新股)
        tier_name, strat_id, mode = self.get_open_price_tier(open_price, code=code)
        if strat_id == "strategy_b_new_stock_trend_hold" and not is_b_conditions_met:
            strat_id = "strategy_a_new_stock_batch_sell"

        found = self.get_strategy_by_id(strat_id)
        if found:
            return found

        daily_strat = self.get_strategy_by_id("strategy_c_daily_surge_ladder")
        if daily_strat:
            return daily_strat

        return self.strategies[0] if self.strategies else {}

    def get_current_phase(self, time_str: str, strategy: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        根据盘中时间 'HH:MM' 推算当前所属的时间轴阶段
        """
        if not strategy:
            return None, -1
        
        phases = strategy.get("phases", [])
        clean_t = time_str[-8:] if len(time_str) >= 8 else time_str
        if len(clean_t) > 5 and ":" in clean_t:
            clean_t = clean_t[:5]

        matched_phases = []
        for idx, ph in enumerate(phases):
            s_time = ph.get("start_time", "")
            e_time = ph.get("end_time", "")
            if not s_time or not e_time:
                tr = ph.get("time_range", "")
                if tr and ("-" in tr or "~" in tr):
                    parts = tr.replace("~", "-").split("-")
                    if len(parts) >= 2:
                        s_time = parts[0].strip()
                        e_time = parts[1].strip()
            s_time = s_time or "00:00"
            e_time = e_time or "23:59"

            if s_time <= clean_t <= e_time:
                try:
                    sh, sm = map(int, s_time.split(":"))
                    eh, em = map(int, e_time.split(":"))
                    span = (eh * 60 + em) - (sh * 60 + sm)
                except Exception:
                    span = 9999
                matched_phases.append((span, idx, ph))

        if matched_phases:
            matched_phases.sort(key=lambda x: x[0])
            best = matched_phases[0]
            return best[2], best[1]

        if clean_t < "09:25":
            return phases[0] if phases else None, 0
        elif clean_t >= "14:50":
            return phases[-1] if len(phases) >= 4 else phases[0], len(phases)-1
            
        return phases[1] if len(phases) >= 2 else None, 1

    def _get_stock_state(self, code: str, open_price: float) -> Dict[str, Any]:
        """获取或初始化某股票的策略运行与 7 节点评分状态机"""
        c_clean = str(code).zfill(6)
        if c_clean not in self.rule_state_map:
            self.rule_state_map[c_clean] = {
                "open_price": open_price if open_price > 1.0 else 0.0,
                "max_price": open_price if open_price > 1.0 else 0.0,
                "min_price": open_price if open_price > 1.0 else 0.0,
                "high_am": open_price if open_price > 1.0 else 0.0, # 上午最高价
                "remaining_ratio": 1.0,
                "triggered_rules": set(),
                "execution_logs": [],
                "signals": [],
                "manual_scores": {}, # node_id -> float (人工覆盖评分)
                "node_custom_params": {}, # node_id -> float (人工校准参数)
                "node_locked_params": {}, # node_id -> float (按时间锁死的历史节点参数)
                "time_snapshots": {}, # HH:MM -> snapshot dict
                "timeline_eval_cache": {} # 7 节点评估缓存
            }
        state = self.rule_state_map[c_clean]
        # 当获取到真实有效的开盘价时，动态实时更新对齐 open_price 与基准价
        if open_price > 1.0 and (state["open_price"] <= 1.0 or abs(state["open_price"] - open_price) > 0.001):
            state["open_price"] = open_price
            if state["max_price"] <= 1.0:
                state["max_price"] = open_price
            if state["min_price"] <= 1.0:
                state["min_price"] = open_price
        return state

    def set_manual_node_score(self, code: str, node_id_or_idx: Any, score: float):
        """设置某节点的人工打分覆盖并自动标记变动（由统一调度防抖持久化）"""
        c_clean = str(code).zfill(6)
        state = self._get_stock_state(c_clean, 0.0)
        state["manual_scores"][str(node_id_or_idx)] = float(score)
        self.mark_dirty()
        self.save_intraday_cache_throttled(interval_sec=5.0)

    def set_node_custom_param(self, code: str, node_id: str, value: float):
        """设置某节点的校准价格或换手率参数并自动标记变动（由统一调度防抖持久化）"""
        c_clean = str(code).zfill(6)
        state = self._get_stock_state(c_clean, 0.0)
        if "node_custom_params" not in state:
            state["node_custom_params"] = {}
        state["node_custom_params"][str(node_id)] = float(value)
        self.mark_dirty()
        self.save_intraday_cache_throttled(interval_sec=5.0)

    def reset_node_custom_params(self, code: str):
        """重置所有节点的校准参数、锁死参数与人工打分并自动标记变动"""
        c_clean = str(code).zfill(6)
        state = self._get_stock_state(c_clean, 0.0)
        state["node_custom_params"] = {}
        state["node_locked_params"] = {}
        state["manual_scores"] = {}
        self.mark_dirty()
        self.save_intraday_cache_throttled(interval_sec=5.0)

    def clear_stock_cache(self, code: str):
        """【🧹 彻底清理单股缓存】清除该标的内存中的节点锁死状态、手动参数、时间快照并同步持久化"""
        c_clean = str(code).zfill(6)
        if c_clean in self.rule_state_map:
            self.rule_state_map.pop(c_clean, None)
        if hasattr(self, "_first_listing_day_cache"):
            self._first_listing_day_cache.pop(c_clean, None)
        self.mark_dirty()
        self.save_intraday_cache(force=True)
        logger.info(f"🧹 [IntradayStrategyEngine] 已强力清除标的 [{c_clean}] 的盘中状态与磁盘缓存！")

    def _clean_time_str(self, time_str: str) -> str:
        """统一清洗时间字符串为 5 位 HH:MM 标准格式"""
        if not time_str:
            return "00:00"
        s = str(time_str).strip()
        if len(s) >= 8 and ":" in s:
            s = s[-8:]
        if ":" in s:
            parts = s.split(":")
            if len(parts) >= 2:
                try:
                    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                except Exception:
                    return s[:5]
        return s[:5]

    def hydrate_from_intraday_df(self, code: str, df_intraday: Optional[pd.DataFrame], open_price: Optional[float] = None) -> bool:
        """
        全自动解析分时 DataFrame (1分钟 K 线 / 盘中 Tick 历史)，将早盘至当前时刻的所有历史节点 (09:25, 09:40, 10:00, 11:00 等)
        完美补全并精准锁死到 node_locked_params 中，防止中途启动系统或过了早盘后丢失早盘历史数据！
        """
        if df_intraday is None or not isinstance(df_intraday, pd.DataFrame) or df_intraday.empty:
            return False

        c_clean = str(code).zfill(6)

        # 🛡️ 结构合法性校验：严格防范全市场截面 DataFrame (包含多股或 index 为股票代码) 被误传入
        if "code" in df_intraday.columns:
            unique_codes = df_intraday["code"].dropna().unique()
            if len(unique_codes) > 1:
                # 过滤出单只目标标的数据
                df_single = df_intraday[df_intraday["code"].astype(str).str.strip().str.zfill(6) == c_clean]
                if df_single.empty:
                    return False
                df_intraday = df_single

        # 校验 index 是否为纯股票代码（如 00089, 30130 等），若是截面表且无法提供分时时间序列，直接拒绝
        if not df_intraday.empty:
            sample_idx_str = str(df_intraday.index[0]).strip()
            if sample_idx_str.isdigit() and len(sample_idx_str) in (5, 6) and (sample_idx_str < "0915" or sample_idx_str > "1505"):
                return False

        state = self._get_stock_state(c_clean, open_price if open_price else 0.0)
        time_snapshots = state.setdefault("time_snapshots", {})
        node_locked_params = state.setdefault("node_locked_params", {})
        custom_params = state.get("node_custom_params", {})

        # 清除 time_snapshots 中非正常交易时间戳
        invalid_keys = [k for k in list(time_snapshots.keys()) if str(k).strip()[:5] < "09:15" or str(k).strip()[:5] > "15:05"]
        for k in invalid_keys:
            time_snapshots.pop(k, None)

        op = open_price if (open_price and open_price > 1.0) else 0.0
        if op <= 1.0 and not df_intraday.empty:
            first_bar_open = float(df_intraday.iloc[0].get("open", 0.0))
            if first_bar_open > 1.0:
                op = first_bar_open
        if op <= 1.0:
            op = state.get("open_price", 0.0)

        # 1. 纯净计算今日分时极值与遍历 df_intraday 的所有分钟行
        intraday_max = op
        intraday_min = op if op > 1.0 else 999999.0
        intraday_high_am = op

        for idx_row, (time_idx, row) in enumerate(df_intraday.iterrows()):
            clean_t = self._clean_time_str(str(time_idx))
            if clean_t < "09:15" or clean_t > "15:05":
                continue

            p = float(row.get("close", row.get("trade", row.get("price", 0.0))))
            if p <= 0:
                continue

            if op <= 1.0:
                op = float(row.get("open", p))
                if op > 1.0:
                    state["open_price"] = op

            to_val = float(row.get("turnover", row.get("turnover_rate", row.get("turnoverratio", 0.0))))
            vw_val = float(row.get("vwap", p))
            h_val = float(row.get("high", p))
            l_val = float(row.get("low", p))
            amt_val = float(row.get("amount", 0.0))

            time_snapshots[clean_t] = {
                "price": p,
                "turnover_rate": to_val,
                "vwap": vw_val,
                "high": h_val,
                "low": l_val,
                "amount": amt_val
            }

            intraday_max = max(intraday_max, h_val, p)
            if clean_t < "13:00":
                intraday_high_am = max(intraday_high_am, h_val, p)
            if l_val > 1.0 and (p <= 5.0 or l_val >= p * 0.1):
                intraday_min = min(intraday_min, l_val, p)

        if op > 1.0:
            state["open_price"] = op
            intraday_max = max(intraday_max, op)
            intraday_min = min(intraday_min, op)

        state["max_price"] = intraday_max
        state["min_price"] = intraday_min if intraday_min < 999998.0 else op
        state["high_am"] = intraday_high_am

        # 2. 如果 node_locked_params 未填充或存在默认遗留值，利用 time_snapshots 精准复原 09:25 / 09:40 / 10:00 / 11:00 等节点！
        def get_snapshot_at_or_before(target_t: str, field: str, default_val: float) -> float:
            target_5 = str(target_t).strip()[:5]
            if target_5 in time_snapshots and field in time_snapshots[target_5]:
                v = float(time_snapshots[target_5][field])
                if v > 0:
                    return v
            cands = [t for t in time_snapshots.keys() if str(t).strip()[:5] <= target_5]
            if cands:
                best_t = max(cands, key=lambda x: str(x).strip()[:5])
                v = float(time_snapshots[best_t].get(field, 0.0))
                if v > 0:
                    return v
            return default_val

        latest_time = max(time_snapshots.keys()) if time_snapshots else "00:00"

        if op > 1.0:
            node_locked_params["node_1"] = op
            node_locked_params["node_1_auction"] = op

        if latest_time >= "09:40":
            v_0940 = get_snapshot_at_or_before("09:40", "price", 0.0)
            if v_0940 > 0:
                node_locked_params["node_2"] = v_0940
                node_locked_params["node_2_first_wave"] = v_0940
                node_locked_params["node_2_first_attack"] = v_0940

        if latest_time >= "10:00":
            v_1000 = get_snapshot_at_or_before("10:00", "turnover_rate", 0.0)
            if v_1000 > 0:
                node_locked_params["node_3"] = v_1000
                node_locked_params["node_3_turnover"] = v_1000
                node_locked_params["node_3_turnover_check"] = v_1000

        if latest_time >= "11:00":
            v_1100 = get_snapshot_at_or_before("11:00", "price", 0.0)
            if v_1100 > 0:
                node_locked_params["node_4"] = v_1100
                node_locked_params["node_4_vwap_test"] = v_1100

        if latest_time >= "14:00":
            v_1400 = get_snapshot_at_or_before("14:00", "price", 0.0)
            if v_1400 > 0:
                node_locked_params["node_5"] = v_1400
                node_locked_params["node_5_afternoon_breakout"] = v_1400

        self.scan_and_evaluate_intraday_timeline(code, df_intraday)
        return True

    def scan_and_evaluate_intraday_timeline(self, code: str, df_intraday: pd.DataFrame) -> List[SignalPoint]:
        """
        根据全量 240 分钟分时 K 线，逐分钟反演扫描策略规则触发点，
        标记【实际成交价买卖点】与【预估不及预期降价修正平仓点】！
        """
        if df_intraday.empty:
            return []

        state = self._get_stock_state(code, 0.0)

        # 🛡️ 待上市新股安全防护：尚未正式上市交易，不触发实盘卖出反演
        if self.is_stock_unlisted(code):
            state["signals"] = []
            state["triggered_rules"] = set()
            state["remaining_ratio"] = 1.0
            state["remaining_position_ratio"] = 1.0
            state["execution_logs"] = []
            return []

        strategy = state.get("current_strategy") or self.auto_select_strategy(0.0, code=code)
        if not strategy:
            return []

        open_price = state.get("open_price", 0.0)
        if not df_intraday.empty:
            df_first_open = float(df_intraday.iloc[0].get("open", df_intraday.iloc[0].get("close", 0.0)))
            if df_first_open > 1.0 and (open_price <= 1.0 or open_price < df_first_open * 0.2 or open_price > df_first_open * 5.0):
                logger.info(f"🔄 [IntradayStrategyEngine] {code} 识别到陈旧错乱开盘价 ({open_price:.2f}元)，已自动强力对齐为分时 K 线真实开盘价 ({df_first_open:.2f}元)！")
                open_price = df_first_open
                state["open_price"] = open_price

        if open_price <= 1.0:
            return []

        signals: List[SignalPoint] = []
        execution_logs: List[str] = []
        triggered_rule_ids = set()
        rem_ratio = 1.0
        cum_high = open_price

        for idx_row, (t_idx, row) in enumerate(df_intraday.iterrows()):
            t_str = str(t_idx).strip()[-8:]
            t_5 = t_str[:5] if len(t_str) >= 5 else t_str

            p = float(row.get("close", row.get("price", 0.0)))
            if p <= 1.0:
                continue
            h_p = float(row.get("high", p))
            vw = float(row.get("vwap", p))

            # 🛡️ 异常价格毛刺脏数据强力清洗门禁 (例如 2048.93 元等由于行情错误推送导致的暴涨红针)
            if open_price > 10.0:
                max_allowed_p = open_price * 1.70
                if p > max_allowed_p or h_p > max_allowed_p:
                    logger.warning(f"⚠️ [IntradayStrategyEngine] 识别并强力过滤 K 线中 异常毛刺脏数据: t={t_5}, p={p:.2f}, h_p={h_p:.2f} (上限={max_allowed_p:.2f})")
                    continue

            cum_high = max(cum_high, h_p, p)

            # 获取当前分钟所在的策略阶段
            curr_phase, _ = self.get_current_phase(t_5, strategy)

            # ⚡ 全局阶梯临停检查 (若触及 +30% 且未触发过临停规则)
            cb_rules = strategy.get("circuit_breaker_rules", {})
            if (cb_rules or "stock_spec" in strategy) and "rule_halt_30_global" not in triggered_rule_ids:
                if cum_high >= open_price * 1.30 and open_price > 0:
                    triggered_rule_ids.add("rule_halt_30_global")
                    actual_sell = min(rem_ratio, 0.30)
                    if actual_sell > 0.001:
                        rem_ratio -= actual_sell
                        sugg_p = round(open_price * 1.28, 2)
                        sig_pt = SignalPoint(
                            code=code,
                            timestamp=t_5,
                            bar_index=idx_row,
                            price=max(p, open_price * 1.30),
                            signal_type=SignalType.SELL,
                            source=SignalSource.STRATEGY_ENGINE,
                            debug_info={"suggested_price": sugg_p, "sell_ratio": actual_sell},
                            reason=f"⚡ [临停复牌] 盘中触及较开盘价+30%临停 (挂单:{sugg_p:.2f}元, 卖出{actual_sell*100:.0f}%)"
                        )
                        sig_pt.suggested_price = sugg_p
                        sig_pt.sell_ratio = actual_sell
                        signals.append(sig_pt)
                        execution_logs.append(f"{t_5} [临停复牌] +30%达成 | 卖出{actual_sell*100:.0f}% 建议挂单:{sugg_p:.2f}")

            if not curr_phase:
                continue

            rules = curr_phase.get("rules", [])
            if not rules:
                default_strat = self.get_strategy_by_id("strategy_c_daily_surge_ladder")
                if default_strat:
                    d_phase, _ = self.get_current_phase(t_5, default_strat)
                    if d_phase:
                        rules = d_phase.get("rules", [])

            for r in rules:
                r_id = r.get("rule_id", "")
                if r_id in triggered_rule_ids:
                    continue

                sell_r = float(r.get("sell_ratio", 0.5))
                r_name = r.get("name", r_id)
                cond_expr = r.get("trigger_expr", "")

                triggered = False
                exec_price = p
                sugg_price = p
                reason_msg = ""

                # 1. 冲高达标 (如 +10% 或日常 +3%)
                if "open_price * 1.10" in cond_expr or "open_price * 1.03" in cond_expr or "surge" in r_id or "profit" in r_id or "D-1" in r_id:
                    trigger_target = open_price * 1.03 if "1.03" in cond_expr or "D-1" in r_id else open_price * 1.10
                    if h_p >= trigger_target:
                        triggered = True
                        exec_price = max(p, trigger_target)
                        sugg_price = round(trigger_target * 1.01, 2)
                        reason_msg = f"🔴 [冲高止盈] 触达目标价位 {trigger_target:.2f}元 (实际成交:{exec_price:.2f}元, 挂单:{sugg_price:.2f}元)"

                # 2. 临停复牌 (如 +30%)
                elif "open_price * 1.30" in cond_expr or "halt" in r_id or "circuit" in r_id:
                    if cum_high >= open_price * 1.30:
                        triggered = True
                        exec_price = max(p, open_price * 1.30)
                        sugg_price = round(open_price * 1.28, 2)
                        reason_msg = f"⚡ [临停复牌] +30%达成 (实际成交:{exec_price:.2f}元, 挂单:{sugg_price:.2f}元)"

                # 3. 预估不及预期修正 (如 10:00 攻势未达标降价清仓 / 破均线 VWAP 防守修正)
                elif "10:00" in cond_expr or "timeout" in r_id:
                    if t_5 >= "10:00" and rem_ratio > 0.5:
                        triggered = True
                        exec_price = p
                        sugg_price = p
                        reason_msg = f"⚠️ [不及预期修正] 10:00攻势未达标，降价市价卖出 (成交:{exec_price:.2f}元)"

                elif "vwap" in cond_expr.lower() or "break" in r_id:
                    if p < vw and t_5 >= "09:40":
                        triggered = True
                        exec_price = p
                        sugg_price = vw
                        reason_msg = f"🛡️ [均线防守修正] 跌破 VWAP 均线，止损修正平仓 (成交:{exec_price:.2f}元)"

                if triggered:
                    triggered_rule_ids.add(r_id)
                    actual_sell = min(rem_ratio, sell_r)
                    if actual_sell <= 0.001:
                        continue
                    rem_ratio -= actual_sell
                    sig_pt = SignalPoint(
                        code=code,
                        timestamp=t_5,
                        bar_index=idx_row,
                        price=exec_price,
                        signal_type=SignalType.SELL,
                        source=SignalSource.STRATEGY_ENGINE,
                        debug_info={"suggested_price": sugg_price, "sell_ratio": actual_sell},
                        reason=reason_msg
                    )
                    sig_pt.suggested_price = sugg_price
                    sig_pt.sell_ratio = actual_sell
                    signals.append(sig_pt)

                    log_entry = f"{t_5} [{r_name}] {reason_msg} | 卖出{actual_sell*100:.0f}% 建议挂单:{sugg_price:.2f}"
                    if log_entry not in execution_logs:
                        execution_logs.append(log_entry)

        state["signals"] = signals
        state["triggered_rules"] = triggered_rule_ids
        state["remaining_ratio"] = max(0.0, float(rem_ratio))
        state["remaining_position_ratio"] = max(0.0, float(rem_ratio))
        state["execution_logs"] = execution_logs
        return signals

    def evaluate_seven_nodes(
        self,
        code: str,
        current_time_str: str,
        open_price: float,
        price: float,
        high_price: float,
        low_price: float,
        vwap: float = 0.0,
        turnover_rate: float = 0.0,
        amount: float = 0.0, # 成交金额(元)
        bid1_price: float = 0.0,
        ask1_price: float = 0.0,
        sector_strengths: Optional[Dict[str, str]] = None,
        strategy_id: Optional[str] = None,
        last_close: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        全面评估 7 大时序节点，生成各节点观察值、强中弱判定、节点分(0-10)、加权得分、形态分类与实操建议。
        支持根据用户在表格中输入的校准价格/换手率全自动重新推导评分。
        全面适配【通用日常个股策略】与【新股上市策略】两种模式。
        """
        c_clean = str(code).zfill(6)
        spec = self.get_stock_ladder_spec(c_clean)
        nodes_def = self.get_timeline_nodes_def(c_clean)
        state = self._get_stock_state(c_clean, open_price)
        custom_params = state.setdefault("node_custom_params", {})

        # 判断当前策略归属：通用日常个股策略 vs 新股专属策略
        current_strat = self.get_strategy_by_id(strategy_id) if strategy_id else self.auto_select_strategy(open_price, code=c_clean)
        strat_id = current_strat.get("id", "") if current_strat else ""
        strat_type = current_strat.get("strategy_type", "") if current_strat else ""
        target_newstock_codes = self.get_all_target_codes()
        has_stock_spec = bool(current_strat and ("stock_spec" in current_strat or current_strat.get("schema_version") == "v1.0-unified"))
        
        # 只要当前策略含有 stock_spec 并且是新股标的，就属于新股上市专属时序评估
        if has_stock_spec and (c_clean in target_newstock_codes or "new_stock" in strat_id or strat_type == "new_stock" or "laser" in strat_id or "688826" in strat_id):
            is_daily_strategy = False
        elif strat_type in ("daily_surge", "general", "daily") or "strategy_c" in strat_id:
            is_daily_strategy = True
        else:
            is_daily_strategy = not has_stock_spec

        clean_t = self._clean_time_str(current_time_str)

        # 记录全天最高/最低与上午最高 (过滤低价异常噪声)
        if price > 0:
            state["max_price"] = max(state.get("max_price", price), high_price, price)
            cur_min = state.get("min_price", price)
            valid_lows = [p for p in (cur_min, low_price, price) if p > 1.0 and (price <= 5.0 or p >= price * 0.1)]
            if valid_lows:
                state["min_price"] = min(valid_lows)
            else:
                state["min_price"] = price
            if clean_t < "13:00":
                state["high_am"] = max(state.get("high_am", price), state["max_price"])

        max_p = state.get("max_price", high_price if high_price > 0 else price)
        min_p = state.get("min_price", low_price if low_price > 0 else price)
        high_am = state.get("high_am", max_p)
        vwap_val = vwap if vwap > 0 else (price if price > 0 else open_price)

        # 1. 保存当前时间点的行情快照 (时间线历史)
        time_snapshots = state.setdefault("time_snapshots", {})
        if price > 0:
            time_snapshots[clean_t] = {
                "price": price,
                "turnover_rate": turnover_rate,
                "vwap": vwap_val,
                "high": max_p,
                "low": min_p,
                "amount": amount
            }

        # 2. 7 节点锁定参数表 (node_locked_params)
        node_locked_params = state.setdefault("node_locked_params", {})

        def get_best_historical_val(target_time: str, key: str, fallback_val: float) -> float:
            """在历史快照中寻找目标时刻 (<= target_time) 最贴切的数据，无则回退到 fallback_val"""
            target_5 = str(target_time).strip()[:5]
            if target_5 in time_snapshots and key in time_snapshots[target_5]:
                v = float(time_snapshots[target_5][key])
                if v > 0:
                    return v
            candidates = [t for t in time_snapshots.keys() if str(t).strip()[:5] <= target_5]
            if candidates:
                best_t = max(candidates, key=lambda x: str(x).strip()[:5])
                v = float(time_snapshots[best_t].get(key, 0.0))
                if v > 0:
                    return v
            return fallback_val

        def get_snap_field(target_t: str, field: str, default_val: float) -> float:
            """在历史快照中按字段名安全提取数值"""
            target_5 = str(target_t).strip()[:5]
            if target_5 in time_snapshots and field in time_snapshots[target_5]:
                v = float(time_snapshots[target_5][field])
                if v > 0:
                    return v
            cands = [t for t in time_snapshots.keys() if str(t).strip()[:5] <= target_5]
            if cands:
                best_t = max(cands, key=lambda x: str(x).strip()[:5])
                v = float(time_snapshots[best_t].get(field, 0.0))
                if v > 0:
                    return v
            return default_val

        # 动态锁死已过节点参数，防止随后续实时行情浮动
        if clean_t >= "09:25" and open_price > 1.0:
            if ("node_1" not in node_locked_params or abs(node_locked_params.get("node_1", 0.0) - open_price) > 0.01) and "node_1" not in custom_params and "node_1_auction" not in custom_params:
                node_locked_params["node_1"] = open_price
                node_locked_params["node_1_auction"] = open_price

        if clean_t >= "09:40":
            v_0940 = get_best_historical_val("09:40", "price", price)
            if v_0940 > 0 and ("node_2" not in node_locked_params or ("09:40" in time_snapshots and abs(node_locked_params.get("node_2", 0.0) - v_0940) > 0.01)):
                node_locked_params["node_2"] = v_0940
                node_locked_params["node_2_first_attack"] = v_0940

        if clean_t >= "10:00":
            v_1000 = get_best_historical_val("10:00", "turnover_rate", turnover_rate)
            if v_1000 <= 0.0:
                v_1000 = get_snap_field("10:00", "turnover_rate", 0.0)
            if v_1000 <= 0.0 and turnover_rate > 0:
                v_1000 = turnover_rate
            if v_1000 > 0 and ("node_3" not in node_locked_params or ("10:00" in time_snapshots and abs(node_locked_params.get("node_3", 0.0) - v_1000) > 0.01)):
                node_locked_params["node_3"] = v_1000
                node_locked_params["node_3_turnover_check"] = v_1000

        if clean_t >= "11:00":
            v_1100 = get_best_historical_val("11:00", "price", price)
            if v_1100 > 0 and ("node_4" not in node_locked_params or ("11:00" in time_snapshots and abs(node_locked_params.get("node_4", 0.0) - v_1100) > 0.01)):
                node_locked_params["node_4"] = v_1100
                node_locked_params["node_4_vwap_test"] = v_1100

        if clean_t >= "14:00":
            v_1400 = get_best_historical_val("14:00", "price", price)
            if v_1400 > 0 and ("node_5" not in node_locked_params or ("14:00" in time_snapshots and abs(node_locked_params.get("node_5", 0.0) - v_1400) > 0.01)):
                node_locked_params["node_5"] = v_1400
                node_locked_params["node_5_afternoon_breakout"] = v_1400

        if clean_t >= "14:50":
            v_1450 = get_best_historical_val("14:50", "price", price)
            if v_1450 > 0 and ("node_6" not in node_locked_params or ("14:50" in time_snapshots and abs(node_locked_params.get("node_6", 0.0) - v_1450) > 0.01)):
                node_locked_params["node_6"] = v_1450
                node_locked_params["node_6_tail_buy"] = v_1450

        if clean_t >= "15:00":
            v_1500 = get_best_historical_val("15:00", "price", price)
            if v_1500 > 0 and ("node_7" not in node_locked_params or ("15:00" in time_snapshots and abs(node_locked_params.get("node_7", 0.0) - v_1500) > 0.01)):
                node_locked_params["node_7"] = v_1500
                node_locked_params["node_7_close_structure"] = v_1500

        issue_p = float(spec.get("issue_price", 0.0) or 0.0)
        if issue_p <= 0:
            try:
                from ats.new_stock_fetcher import NewStockFetcher
                ipo_dict = NewStockFetcher.get_instance().fetch_ipo_calendar()
                if c_clean in ipo_dict:
                    issue_p = float(ipo_dict[c_clean].get("issue_price", 0.0) or 0.0)
            except Exception:
                pass
        if issue_p <= 0:
            issue_p = last_close if (last_close and last_close > 0) else (open_price if open_price > 0 else (price if price > 0 else 10.0))

        float_mv_yi = float(spec.get("float_mv_yi", 0.0) or 0.0)
        if float_mv_yi <= 0:
            float_mv_yi = 15.0
        amount_yi = (amount / 1e8) if amount > 1e5 else (amount if amount > 0 else 0.0) # 转换为亿元
        intensity_ratio = (amount_yi / float_mv_yi) if (float_mv_yi > 0 and amount_yi > 0) else 1.0

        # 通用日常策略基准：以昨收价为核心参考基准
        ref_base_p = last_close if (last_close is not None and last_close > 0) else (open_price if open_price > 0 else (price if price > 0 else 10.0))

        gain_from_issue = ((price - issue_p) / issue_p * 100.0) if (issue_p > 0 and price > 0) else 0.0
        gain_from_open = ((price - open_price) / open_price * 100.0) if (open_price > 0 and price > 0) else 0.0
        gain_from_base = ((price - ref_base_p) / ref_base_p * 100.0) if (ref_base_p > 0 and price > 0) else 0.0
        close_high_ratio = (price / max_p) if max_p > 0 else 1.0

        node_results = []
        total_weighted_score = 0.0
        current_node_idx = 0
        current_node_info = None

        # 7 节点时间截点列表
        time_milestones = ["09:25", "09:40", "10:00", "11:00", "14:00", "14:50", "15:00"]

        for idx, nd in enumerate(nodes_def):
            n_id = nd.get("node_id", f"node_{idx+1}")
            n_name = nd.get("name", "")
            n_time = nd.get("time_str", time_milestones[idx] if idx < len(time_milestones) else "15:00")
            n_weight = float(nd.get("weight", 0.15))
            m_time = time_milestones[idx] if idx < len(time_milestones) else "15:00"

            # 判定节点活跃状态: 已过(completed)、当前(active)、待到达(pending)
            if idx == 0:
                is_active = (clean_t <= m_time)
                is_completed = (clean_t > m_time)
            else:
                prev_m = time_milestones[idx-1]
                is_active = (prev_m < clean_t <= m_time)
                is_completed = (clean_t > m_time)

            if is_active:
                current_node_idx = idx
                current_node_info = nd

            # 1. 提取/推算盘中实际观察值与校准参数 (优先级: 人工校准 > 时间锁定 > 动态实时)
            observed_val = ""
            judgment = "中" # 强 / 中 / 弱
            auto_score = 5.0 # 0 - 10
            remarks = ""
            input_val = 0.0
            input_unit = "元"

            time_snaps = state.get("time_snapshots", {})

            def get_resolved_val(primary_key: str, alt_key: str, default_val: float) -> float:
                try:
                    if primary_key in custom_params and float(custom_params[primary_key]) > 0:
                        return float(custom_params[primary_key])
                    if alt_key in custom_params and float(custom_params[alt_key]) > 0:
                        return float(custom_params[alt_key])
                    if primary_key in node_locked_params and float(node_locked_params[primary_key]) > 0:
                        return float(node_locked_params[primary_key])
                    if alt_key in node_locked_params and float(node_locked_params[alt_key]) > 0:
                        return float(node_locked_params[alt_key])
                except Exception:
                    pass
                try:
                    return float(default_val)
                except Exception:
                    return 0.0

            if idx == 0: # 9:25 集合竞价定盘 (校准开盘价)
                default_op = open_price if open_price > 0 else (price if price > 0 else ref_base_p)
                cur_op = get_resolved_val(n_id, "node_1", default_op)
                input_val = cur_op
                input_unit = "元"

                if is_daily_strategy:
                    # 通用日常策略：评估较昨收价高开/平开/低开幅度
                    open_pct = ((cur_op - ref_base_p) / ref_base_p * 100.0) if ref_base_p > 0 else 0.0
                    observed_val = f"开盘:{cur_op:.2f}元 (较昨收{open_pct:+.2f}%)"
                    if open_pct >= 2.0:
                        judgment = "强"
                        auto_score = 8.5
                        remarks = f"高开{open_pct:+.2f}%做多意愿积极，竞价承接强势"
                    elif open_pct >= -0.5:
                        judgment = "中"
                        auto_score = 6.5
                        remarks = f"平开至微幅震荡({open_pct:+.2f}%)，竞价平稳"
                    else:
                        judgment = "弱"
                        auto_score = 4.0
                        remarks = f"低开{open_pct:+.2f}%，早盘开盘承接偏弱"
                else:
                    # 新股专属策略：较发行价涨幅评估
                    open_gain_issue = ((cur_op - issue_p) / issue_p * 100.0) if (issue_p > 0 and cur_op > 0) else 0.0
                    observed_val = f"开盘:{cur_op:.2f}元 (较发行价{open_gain_issue:+.1f}%)"
                    strong_ref = issue_p * 3.0 # +200%
                    double_ref = issue_p * 2.0 # +100%
                    if cur_op >= strong_ref: # >= +200% 强势基准
                        judgment = "强"
                        auto_score = 9.0
                        remarks = f"高开>={open_gain_issue:+.0f}%超预期，做多意愿极强"
                    elif cur_op >= double_ref: # >= +100% 翻倍
                        judgment = "中"
                        auto_score = 7.0
                        remarks = "开盘落在+100%~+200%中性区间，量价正常"
                    else:
                        judgment = "弱"
                        auto_score = 4.0
                        remarks = "开盘低于翻倍线，关注度略显不足"

            elif idx == 1: # 9:40 早盘第一波攻击 (校准 9:40 现价)
                default_p1 = price if price > 0 else (cur_op * 1.03 if cur_op > 0 else ref_base_p)
                cur_p1 = get_resolved_val(n_id, "node_2", default_p1)
                input_val = cur_p1
                input_unit = "元"
                base_op_for_calc = cur_op if cur_op > 0 else open_price
                cur_gain_open = ((cur_p1 - base_op_for_calc) / base_op_for_calc * 100.0) if base_op_for_calc > 0 else 0.0
                observed_val = f"现价:{cur_p1:.2f}元 (较开盘{cur_gain_open:+.1f}%)"

                if is_daily_strategy:
                    # 通用日常策略：早盘冲高突破与站稳开盘价/VWAP
                    if cur_gain_open >= 3.0 or cur_p1 >= base_op_for_calc * 1.03:
                        judgment = "强"
                        auto_score = 9.0
                        remarks = "早盘放量冲高突破开盘价，多头攻击形态明确"
                    elif cur_p1 >= base_op_for_calc:
                        judgment = "中"
                        auto_score = 6.5
                        remarks = "维持在开盘价上方震荡蓄势，趋势良性"
                    else:
                        judgment = "弱"
                        auto_score = 3.5
                        remarks = "冲高回落跌破开盘价，早盘承接偏弱"
                else:
                    if cur_gain_open >= 10.0 or cur_p1 >= base_op_for_calc * 1.10:
                        judgment = "强"
                        auto_score = 9.0
                        remarks = "放量上攻突破开盘价并涨超10%，攻击迅猛"
                    elif cur_p1 >= base_op_for_calc:
                        judgment = "中"
                        auto_score = 6.5
                        remarks = "维持在开盘价上方震荡，等待方向选择"
                    else:
                        judgment = "弱"
                        auto_score = 3.5
                        remarks = "跌破开盘价走弱，出现分歧砸盘"

            elif idx == 2: # 10:00 换手质量检验 (校准 10:00 换手率)
                try:
                    to_num = float(turnover_rate)
                except Exception:
                    to_num = 0.0
                safe_to_val = to_num if (0.0 < to_num <= 100.0) else (5.0 if is_daily_strategy else 25.0)
                cur_to = get_resolved_val(n_id, "node_3", safe_to_val)
                if cur_to > 100.0 or cur_to < 0.0:
                    cur_to = min(100.0, max(0.0, safe_to_val))
                input_val = cur_to
                input_unit = "%"
                v_1000_amt = get_snap_field("10:00", "amount", 0.0)
                amt_1000_yi = (v_1000_amt / 1e8) if v_1000_amt > 0 else amount_yi
                observed_val = f"换手率:{cur_to:.1f}% 金额:{amt_1000_yi:.2f}亿"

                if is_daily_strategy:
                    # 通用日常个股：10:00 换手达到 3%~8% 为活跃健康
                    if cur_to >= 3.0 and price >= vwap_val:
                        judgment = "强"
                        auto_score = 8.5
                        remarks = "早盘换手充沛且站稳均线，资金承接活跃"
                    elif cur_to >= 1.0:
                        judgment = "中"
                        auto_score = 6.5
                        remarks = "换手温和推进，量价结构平稳"
                    else:
                        judgment = "弱"
                        auto_score = 4.0
                        remarks = "换手偏低无量横盘，警惕量能不济"
                else:
                    if cur_to >= 15.0 and price >= open_price:
                        judgment = "强"
                        auto_score = 8.5
                        remarks = "换手充沛且价格抬升，承接有力"
            elif idx == 3: # 11:00 分歧承接/均线测试 (校准 11:00 价格)
                default_p3 = price if price > 0 else (open_price if open_price > 0 else ref_base_p)
                cur_p3 = get_resolved_val(n_id, "node_4", default_p3)
                input_val = cur_p3
                input_unit = "元"
                vwap_diff = ((cur_p3 - vwap_val) / vwap_val * 100.0) if vwap_val > 0 else 0.0
                observed_val = f"现价:{cur_p3:.2f}元 (偏离均价{vwap_diff:+.1f}%)"

                if cur_p3 >= vwap_val and cur_p3 >= open_price:
                    judgment = "强"
                    auto_score = 8.5
                    remarks = "稳居分时均线之上，分时均线向上支撑坚挺"
                elif cur_p3 >= vwap_val * 0.98 or cur_p3 >= open_price * 0.98:
                    judgment = "中"
                    auto_score = 6.0
                    remarks = "贴近分时均线窄幅拉锯，承接尚在可控范围"
                else:
                    judgment = "弱"
                    auto_score = 3.5
                    remarks = "跌破分时均线且反抽无力，警惕破线阴跌"

            elif idx == 4: # 14:00 午后突破验证 (校准 14:00 价格)
                default_p4 = price if price > 0 else (open_price if open_price > 0 else ref_base_p)
                cur_p4 = get_resolved_val(n_id, "node_5", default_p4)
                input_val = cur_p4
                input_unit = "元"
                observed_val = f"现价:{cur_p4:.2f}元 / 上午最高:{high_am:.2f}元"

                if cur_p4 >= high_am and cur_p4 > vwap_val:
                    judgment = "强"
                    auto_score = 9.0
                    remarks = "午后放量突破上午高点，主升趋势延续"
                elif cur_p4 >= vwap_val or cur_p4 >= open_price * 0.95:
                    judgment = "中"
                    auto_score = 6.5
                    remarks = "午后震荡蓄势守住分时均线，未破关键支撑"
                else:
                    judgment = "弱"
                    auto_score = 4.0
                    remarks = "午后持续走弱重心下移，波段调整"

            elif idx == 5: # 14:50 尾盘抢筹强度 (校准 14:50 价格)
                default_p5 = price if price > 0 else (open_price if open_price > 0 else ref_base_p)
                cur_p5 = get_resolved_val(n_id, "node_6", default_p5)
                input_val = cur_p5
                input_unit = "元"
                cur_ch_ratio = (cur_p5 / max_p) if max_p > 0 else 1.0
                observed_val = f"现价:{cur_p5:.2f}元 (收盘/最高: {cur_ch_ratio*100:.1f}%)"

                if (cur_ch_ratio >= 0.92 or cur_p5 >= max_p * 0.95) and cur_p5 >= vwap_val:
                    judgment = "强"
                    auto_score = 9.5
                    remarks = "尾盘放量抢筹反弹上穿VWAP均线并逼近日内最高价，做多坚决"
                elif cur_ch_ratio >= 0.85 or cur_p5 >= vwap_val:
                    judgment = "中"
                    auto_score = 7.0
                    remarks = "尾盘平稳维持守住均线，走势良好，按计划管理持仓"
                else:
                    judgment = "弱"
                    auto_score = 3.5
                    remarks = "尾盘放量跳水破位，建议清仓规避隔夜风险"

            elif idx == 6: # 15:00 收盘结构与持仓管理 (校准收盘价)
                default_p6 = price if price > 0 else (open_price if open_price > 0 else ref_base_p)
                cur_p6 = get_resolved_val(n_id, "node_7", default_p6)
                input_val = cur_p6
                input_unit = "元"
                cur_ch_ratio = (cur_p6 / max_p) if max_p > 0 else 1.0
                observed_val = f"收盘:{cur_p6:.2f}元 相对日高:{cur_ch_ratio*100:.1f}%"

                if (cur_ch_ratio >= 0.90 or cur_p6 >= cur_op) and cur_p6 >= vwap_val:
                    judgment = "强"
                    auto_score = 9.5
                    remarks = "收盘站稳分时均线之上且逼近日高，低点抬升反弹结构健康"
                elif cur_ch_ratio >= 0.80 or cur_p6 >= vwap_val * 0.98:
                    judgment = "中"
                    auto_score = 7.0
                    remarks = "平稳收盘守住核心支撑区间，形态结构正常"
                else:
                    judgment = "弱"
                    auto_score = 3.5
                    remarks = "破位收阴跌破分时均线，防范次日低开风险"

            # 2. 检查是否有用户人工打分覆盖 (Manual Score Override)
            manual_score = None
            if str(n_id) in state.get("manual_scores", {}):
                manual_score = float(state["manual_scores"][str(n_id)])
            elif str(idx) in state.get("manual_scores", {}):
                manual_score = float(state["manual_scores"][str(idx)])

            final_score = manual_score if manual_score is not None else auto_score
            weighted_score = round(final_score * n_weight, 3)
            total_weighted_score += weighted_score

            raw_strong = nd.get("strong_signals", "")
            strong_str = "；".join(str(x) for x in raw_strong) if isinstance(raw_strong, (list, tuple, set)) else str(raw_strong)
            raw_risk = nd.get("risk_signals", "")
            risk_str = "；".join(str(x) for x in raw_risk) if isinstance(raw_risk, (list, tuple, set)) else str(raw_risk)
            raw_guide = nd.get("action_guide", "")
            guide_str = "；".join(str(x) for x in raw_guide) if isinstance(raw_guide, (list, tuple, set)) else str(raw_guide)

            node_results.append({
                "node_id": n_id,
                "node_num": nd.get("node_num", f"#{idx+1}"),
                "time_str": n_time,
                "name": n_name,
                "weight": n_weight,
                "weight_pct": f"{int(n_weight*100)}%",
                "focus": nd.get("focus", ""),
                "strong_signals": strong_str,
                "risk_signals": risk_str,
                "observed_val": observed_val,
                "judgment": judgment,
                "auto_score": auto_score,
                "final_score": round(final_score, 1),
                "input_val": input_val,
                "input_unit": input_unit,
                "weighted_score": weighted_score,
                "action_guide": guide_str,
                "remarks": remarks,
                "is_active": is_active,
                "is_completed": is_completed
            })

        total_score_rounded = round(total_weighted_score, 2)

        # 3. 动态根据策略中的 grade_levels 判定形态与 T+1 操作建议
        pattern = "未知形态"
        t1_advice = "--"
        pattern_color = "#ffffff"

        grade_levels = spec.get("scoring_rules", {}).get("grade_levels", [])
        if not grade_levels:
            st = self.auto_select_strategy(open_price, code=c_clean)
            if st and "scoring_rules" in st:
                grade_levels = st["scoring_rules"].get("grade_levels", [])

        if grade_levels:
            for gl in grade_levels:
                min_s = float(gl.get("min_score", 0.0))
                if total_score_rounded >= min_s:
                    pattern = gl.get("pattern", "未知形态")
                    t1_advice = gl.get("advice", "--")
                    pattern_color = gl.get("color", "#ffffff")
                    break
        else:
            if total_score_rounded >= 8.0:
                pattern = "A型·超强趋势"
                t1_advice = "★关注竞价接力，强势可参与"
                pattern_color = "#00ff88"
            elif total_score_rounded >= 6.5:
                pattern = "B型·强势换手"
                t1_advice = "★观察次日竞价，回踩不破可试"
                pattern_color = "#38bdf8"
            elif total_score_rounded >= 5.0:
                pattern = "C型·冲高兑现"
                t1_advice = "★谨慎，等二次确认"
                pattern_color = "#ffaa44"
            else:
                pattern = "D/E型·弱势或衰竭"
                t1_advice = "★回避，防回撤"
                pattern_color = "#ff4444"

        # 4. 当前阶段自动解析与实操指引 (Action Guidance Engine)
        if not current_node_info and nodes_def:
            current_node_info = nodes_def[min(current_node_idx, len(nodes_def)-1)]

        active_name = current_node_info.get("name", "盘中阶段") if current_node_info else "盘中监测"
        active_time = current_node_info.get("time_str", clean_t) if current_node_info else clean_t

        # 🛡️ 待上市新股安全防护与专属估价判定 (尚未正式挂牌交易)
        if self.is_stock_unlisted(c_clean):
            pattern = "【待上市估价】"
            t1_advice = f"★尚未正式上市交易，已载入发行基准价 ({issue_p:.2f}元)，估价模型推演就绪"
            pattern_color = "#38bdf8"
            current_status_diagnosis = f"⏱️ [{clean_t}] 【待上市新股】尚未正式挂牌上市交易，已为您自动载入发行基准价 ({issue_p:.2f}元)。"
            action_execution_text = f"【待上市估价推演】当前标的处于待上市阶段，系统已配置发行基准价 ({issue_p:.2f}元) 与阶梯估价模型。可在分时工作台中开启【💡 开启手动估价】自由推演 7 节点买卖点。"
        elif is_daily_strategy:
            # === 通用日常个股分时策略 实操指引体系 ===
            open_gain_val = ((open_price - last_close) / last_close * 100.0) if (last_close and last_close > 0) else 0.0
            cur_gain_val = ((price - last_close) / last_close * 100.0) if (last_close and last_close > 0) else gain_from_open

            if clean_t < "09:25":
                lc_desc = f"昨收 {last_close:.2f} 元" if (last_close and last_close > 0) else "待开盘"
                current_status_diagnosis = f"当前处于【集合竞价定盘阶段】。{lc_desc}，试盘价 {open_price:.2f} 元 ({open_gain_val:+.2f}%)，观察 9:25 最终撮合与竞价量比。"
                if open_gain_val >= 3.0:
                    action_execution_text = f"【操作建议 🚀 强势高开】高开幅度达 {open_gain_val:+.2f}%！若量比充足，开盘后关注冲高至 +5%~+7% 目标位分批止盈机会。"
                elif open_gain_val >= 0.0:
                    action_execution_text = "【操作建议 ⏳ 平开/微高开】开盘在昨收上方，盘初关注能否放量突破开盘价并稳健运行在分时均线上方。"
                else:
                    action_execution_text = "【操作建议 ⚠️ 低开防守】低开在昨收线下方，不盲目追单，观察开盘是否有放量拉升快速收复昨收价。"

            elif "09:25" <= clean_t < "09:40":
                current_status_diagnosis = f"当前处于【早盘快速冲高攻击阶段】。现价 {price:.2f} 元 (较昨收 {cur_gain_val:+.2f}% / 较开盘 {gain_from_open:+.2f}%)，日内高点 {max_p:.2f} 元。"
                if gain_from_open >= 3.0 or cur_gain_val >= 5.0:
                    action_execution_text = f"【操作建议 🔴 冲高分批止盈】早盘快速拉升已达预期冲高目标 (现价 {price:.2f}元)！建议按阶梯分批挂单止盈 30%~50%，锁定日内利润！"
                elif price >= open_price:
                    action_execution_text = f"【操作建议 ⏳ 沿均线持股】股价在开盘价上方稳健上行，未达减仓条件，继续沿分时均线持有盯盘。"
                else:
                    action_execution_text = f"【操作建议 ⚠️ 跌破开盘价】股价跌破开盘价 ({open_price:.2f}元)！若反抽无力且均线下行，需提高警惕控制仓位。"

            elif "09:40" <= clean_t < "10:00":
                current_status_diagnosis = f"当前处于【换手质量与量比检验阶段】。当前换手率 {turnover_rate:.2f}%，成交金额 {amount_yi:.2f} 亿元，分时低点 {min_p:.2f} 元。"
                if price >= vwap_val and turnover_rate >= 3.0:
                    action_execution_text = f"【操作建议 ✅ 量价健康】换手率 ({turnover_rate:.2f}%) 推进充分且股价运行在均价线 ({vwap_val:.2f}元) 上方，承接有力，持股观察。"
                elif price < vwap_val:
                    action_execution_text = f"【操作建议 ⚠️ 破线警惕】股价跌破分时均线 ({vwap_val:.2f}元)！若 10:00 前反抽无力，建议主动分批减仓防范日内调整。"
                else:
                    action_execution_text = f"【操作建议 ⏳ 观察承接】换手推进中，密切关注分时均线 ({vwap_val:.2f}元) 支撑力度。"

            elif "10:00" <= clean_t < "11:30" or "11:30" <= clean_t < "13:00":
                current_status_diagnosis = f"当前处于【分歧承接测试阶段】。现价 {price:.2f} 元，分时均价 VWAP 为 {vwap_val:.2f} 元。"
                if price >= vwap_val:
                    action_execution_text = f"【操作建议 🛡️ 守线持有】股价稳健运行在分时均线 ({vwap_val:.2f}元) 上方，承接良好，剩余仓位安心持有博弈午后突破；若盘中高点回撤 >= 3%~5% 则触发移动止盈。"
                else:
                    action_execution_text = f"【操作建议 ⚠️ 破线减仓】股价跌破分时均线 ({vwap_val:.2f}元)！若反抽无法收复均线，建议逢反弹高点主动减仓，规避阴跌回落。"

            elif "13:00" <= clean_t < "14:30":
                current_status_diagnosis = f"当前处于【午后波段方向选择阶段】。现价 {price:.2f} 元，上午最高价 {high_am:.2f} 元，VWAP {vwap_val:.2f} 元。"
                if price >= high_am:
                    action_execution_text = f"【操作建议 🔥 突破上午高点】午后放量突破上午最高价 ({high_am:.2f}元)！多头趋势强化，持股待涨并注意涨停板封板强度。"
                elif price >= vwap_val:
                    action_execution_text = f"【操作建议 ⏳ 震荡蓄势】午后维持在分时均线 ({vwap_val:.2f}元) 上方震荡，继续持仓观察，等待尾盘方向选择。"
                else:
                    action_execution_text = f"【操作建议 ⚠️ 破位减仓】午后走弱跌破分时均线 ({vwap_val:.2f}元)，建议主动降低仓位防范尾盘跳水。"

            elif "14:30" <= clean_t < "14:50":
                current_status_diagnosis = f"当前处于【尾盘承接与留仓评估阶段】。收盘/最高价比例为 {close_high_ratio*100:.1f}%，现价 {price:.2f} 元。"
                if close_high_ratio >= 0.95 and price >= vwap_val:
                    action_execution_text = f"【操作建议 🚀 尾盘强势】尾盘保持高位震荡 (>=95%高点)，分时形态健康，可评估保留仓位博弈次日溢价。"
                else:
                    action_execution_text = f"【操作建议 ⚠️ 冲高回落防守】尾盘回落或跌破分时均线，不满足强势留仓条件，建议在 14:50 后择机减仓或止盈。"

            else: # 14:50 ~ 15:00
                current_status_diagnosis = f"当前处于【收盘持仓决策阶段】。综合加权得分 {total_score_rounded:.2f} 分，形态判定【{pattern}】。"
                if (close_high_ratio >= 0.90 or price >= vwap_val) and (total_score_rounded >= 7.0 or price >= open_price):
                    action_execution_text = f"【操作建议 🌙 强势留仓】全天低点逐步抬升且尾盘放量反弹上穿VWAP均线，收盘稳健 (综合评分 {total_score_rounded:.2f}分 【{pattern}】)！建议保留底仓/过夜持股，关注次日溢价！"
                else:
                    action_execution_text = f"【操作建议 🚪 纪律防守】走势平淡或走弱 (评分 {total_score_rounded:.2f}分 < 7.0)，建议按交易纪律在收盘前降低仓位或锁定胜果。"

        else:
            # === 新股上市首日专属 实操指引体系 ===
            if clean_t < "09:25":
                current_status_diagnosis = f"当前处于【集合竞价定盘阶段】。发行价 {issue_p:.2f} 元，重点观察 9:25 最终撮合价格与盘口委买厚度。"
                p_strong = issue_p * 3.0
                p_double = issue_p * 2.0
                if open_price >= p_strong:
                    action_execution_text = f"【操作建议】高开达到 +200% 强势基准 (>={p_strong:.2f}元)！开盘后优先按强势模式持有观察或准备在较开盘涨10%处挂买一价*1.02卖出首批仓位。"
                elif open_price >= p_double:
                    action_execution_text = f"【操作建议】开盘落在翻倍区间 (+100%~+200%，{p_double:.2f}~{p_strong:.2f}元)。执行标准阶梯分批：早盘冲高+10%申报价格笼子卖出，若10:00前未冲高则10:00市价减仓30%。"
                else:
                    action_execution_text = f"【操作建议】开盘低于翻倍线 (<{p_double:.2f}元)，按保守档应对，不急于低位割肉，观察开盘是否有放量反弹拉升。"

            elif "09:25" <= clean_t < "09:40":
                current_status_diagnosis = f"当前处于【早盘第一波攻击阶段】。现价 {price:.2f} 元 (较开盘 {gain_from_open:+.1f}%)，最高 {max_p:.2f} 元。"
                if price >= open_price * 1.10:
                    action_execution_text = f"【操作建议 🔴 触发卖出】股价较开盘已冲高 >= 10% (目标价 {open_price*1.10:.2f}元)！立即按买一价*1.02限价申报卖出 50% 仓位锁定利润！"
                elif price >= open_price:
                    action_execution_text = f"【操作建议 ⏳ 监控冲高】股价在开盘价上方稳健上行，未达+10%卖点(目标 {open_price*1.10:.2f}元)，继续持股盯盘，勿提前抢跑。"
                else:
                    action_execution_text = f"【操作建议 ⚠️ 风险防范】股价跌破开盘价 {open_price:.2f} 元！若反抽无力或换手滞涨，需提高警惕准备在10:00执行减仓。"

            elif "09:40" <= clean_t < "10:00":
                current_status_diagnosis = f"当前处于【换手质量检验阶段】。当前换手率 {turnover_rate:.1f}%，成交金额 {amount_yi:.2f} 亿元，分时低点 {min_p:.2f} 元。"
                if clean_t >= "09:59":
                    action_execution_text = "【操作建议 🔔 10:00整兜底】若此前冲高50%未触发，在 10:00:00 整按市价果断卖出 30% 仓位执行纪律兜底！"
                elif turnover_rate >= 15.0 and price >= open_price:
                    action_execution_text = "【操作建议 ✅ 健康换手】10分钟换手超15%且价格稳步抬升，属于健康充分交换，剩余仓位继续持有等待分歧承接。"
                else:
                    action_execution_text = "【操作建议 ⚠️ 观察承接】换手推进中，若出现放量滞涨且低点下移，准备在 10:00 执行兜底减仓。"

            elif "10:00" <= clean_t < "11:30" or "11:30" <= clean_t < "13:00":
                current_status_diagnosis = f"当前处于【分歧承接测试阶段】。现价 {price:.2f} 元，分时均价 VWAP 为 {vwap_val:.2f} 元。"
                if price >= vwap_val:
                    action_execution_text = f"【操作建议 🛡️ 守线持有】股价稳稳运行在分时均线 ({vwap_val:.2f}元) 上方，承接良好，剩余仓位安心持有博弈午后突破；若盘中触及+30%临停复牌前挂 Open*1.28 限价单卖30%。"
                else:
                    action_execution_text = f"【操作建议 ⚠️ 破线警惕】股价跌破分时均线 ({vwap_val:.2f}元)！若反抽不过均线，建议逢反弹高点主动减仓，严防阴跌。"

            elif "13:00" <= clean_t < "14:30":
                current_status_diagnosis = f"当前处于【午后突破验证阶段】。现价 {price:.2f} 元，上午最高价 {high_am:.2f} 元。"
                if price >= high_am:
                    action_execution_text = f"【操作建议 🔥 突破新高】午后成功突破上午最高价 {high_am:.2f} 元！主力做多趋势强化，保持锁仓，关注激光/半导体板块协同性。"
                else:
                    action_execution_text = f"【操作建议 ⏳ 震荡观察】午后尚未突破上午高点 ({high_am:.2f}元)，若缩量横盘维持在均线上方可继续观察，破均线则分批派发。"

            elif "14:30" <= clean_t < "14:50":
                current_status_diagnosis = f"当前处于【尾盘抢筹强度检验阶段】。收盘/最高价比例为 {close_high_ratio*100:.1f}%。"
                if close_high_ratio >= 0.90:
                    action_execution_text = "【操作建议 🚀 尾盘抢筹】尾盘放量上攻逼近全天最高价！锁仓迹象明显，准备在 14:50 之后保留 10%~20% 底仓过夜博次日溢价。"
                else:
                    action_execution_text = "【操作建议 ⚠️ 准备清仓】尾盘回落且收盘/最高 < 90%，不满足留仓条件，准备在 14:50~14:57 尾盘全部市价清仓，不留隔夜仓。"

            else: # 14:50 ~ 15:00
                current_status_diagnosis = f"当前处于【收盘结构与锁仓结算阶段】。综合加权得分 {total_score_rounded:.2f} 分，形态判定【{pattern}】。"
                if close_high_ratio >= 0.90 and total_score_rounded >= 8.0:
                    action_execution_text = f"【操作建议 🌙 优质锁仓过夜】收盘/最高 {close_high_ratio*100:.1f}% >= 90% 且综合评分达 {total_score_rounded:.2f} 分(A型)！保留 10% 底仓过夜，次日开盘 9:25 关注竞价接力！"
                else:
                    action_execution_text = "【操作建议 🚪 尾盘市价清仓】未达成超强锁仓条件(或评分<8.0)，执行策略A纪律，在 14:57 前按买一价市价全部清仓，规避次日低开风险！"

        eval_result = {
            "code": c_clean,
            "name": spec.get("name", "频准激光"),
            "current_time": clean_t,
            "open_price": open_price,
            "price": price,
            "high_price": max_p,
            "low_price": min_p,
            "vwap": vwap_val,
            "turnover_rate": turnover_rate,
            "amount_yi": amount_yi,
            "intensity_ratio": round(intensity_ratio, 2),
            "close_high_ratio": round(close_high_ratio, 3),
            "gain_from_issue": round(gain_from_issue, 2),
            "gain_from_open": round(gain_from_open, 2),
            "node_results": node_results,
            "total_weighted_score": total_score_rounded,
            "pattern": pattern,
            "t1_advice": t1_advice,
            "pattern_color": pattern_color,
            "active_node_name": active_name,
            "active_node_time": active_time,
            "current_status_diagnosis": current_status_diagnosis,
            "action_execution_text": action_execution_text
        }

        state["timeline_eval_cache"] = eval_result
        if clean_t >= "14:55" and open_price > 1.0 and not is_daily_strategy:
            self.save_listing_closing_scorecard(code, eval_result)

        # 🕒 交易收盘后 (>=15:00) 统一持久化；盘中则启用 300 秒（5分钟）防抖低频节流持久化 (仅在 _is_dirty 时执行)
        if clean_t >= "15:00":
            self.save_intraday_cache(force=False)
        else:
            self.save_intraday_cache_throttled(interval_sec=300.0)

        return eval_result

    def evaluate_tick(
        self,
        code: str,
        tick_row: Dict[str, Any],
        open_price: float,
        current_time_str: str,
        bid1_price: float = 0.0,
        strategy: Optional[Dict[str, Any]] = None,
        is_b_conditions_met: bool = True,
        bar_index: int = 0
    ) -> List[SignalPoint]:
        """
        评估单个分时/Tick 节点，触发阶梯买卖规则并生成 SignalPoint
        """
        if open_price <= 0:
            return []

        c_clean = str(code).zfill(6)
        # 🛡️ 待上市新股安全防护：尚未正式挂牌交易，不触发任何实盘卖出信号
        if self.is_stock_unlisted(c_clean):
            return []

        state = self._get_stock_state(c_clean, open_price)
        
        # 1. 动态选择策略
        if strategy is None:
            strategy = self.auto_select_strategy(open_price, code=c_clean, is_b_conditions_met=is_b_conditions_met)

        tier_name, _, action_mode = self.get_open_price_tier(open_price, code=c_clean)
        
        # 保守档不卖出，等待反弹
        if action_mode == "hold_rebound":
            return []

        # 2. 提取当前价格与时间
        price = float(tick_row.get("trade", tick_row.get("close", 0.0)))
        if price <= 0:
            return []

        # 自动纠偏陈旧/错乱开盘价 (例如缓存为 24.95 元但现价为 892.78 元)
        if price > 10.0 and (open_price <= 1.0 or open_price < price * 0.2 or open_price > price * 5.0):
            logger.info(f"🔄 [IntradayStrategyEngine] {c_clean} 识别到陈旧错乱开盘价 ({open_price:.2f}元)，已自动强力对齐为现价基准 ({price:.2f}元)！")
            open_price = price
            state["open_price"] = open_price

        # 🛡️ 异常价格毛刺脏数据强力清洗门禁 (过滤由于 TDX 或行情错误推送引起的 2048.93 元等红针)
        if open_price > 10.0:
            max_allowed_p = open_price * 1.70
            if price > max_allowed_p:
                logger.warning(f"⚠️ [IntradayStrategyEngine] 识别到异常价格毛刺脏数据: 现价={price:.2f} (上限={max_allowed_p:.2f})，已强力压制过滤！")
                return []

        state["max_price"] = max(state["max_price"], price)
        state["min_price"] = min(state["min_price"], price) if state["min_price"] > 0 else price
        
        clean_time = current_time_str[-8:] if len(current_time_str) >= 8 else current_time_str
        if len(clean_time) > 5 and ":" in clean_time:
            clean_time = clean_time[:5]

        # 盘后非交易时间 (>= 15:05 或 < 09:15) 不再由实时 Timer 触发新规则与日志落盘
        if clean_time > "15:05" or clean_time < "09:15":
            return []

        phase, phase_idx = self.get_current_phase(clean_time, strategy)
        if not phase:
            return []

        generated_signals: List[SignalPoint] = []

        # ⚡ 检查全局临停与阶梯规则 (+30% 达成且未触发过临停)
        cb_rules = strategy.get("circuit_breaker_rules", {})
        if (cb_rules or "stock_spec" in strategy) and "rule_halt_30_global" not in state["triggered_rules"]:
            if state["max_price"] >= open_price * 1.30 and open_price > 0:
                state["triggered_rules"].add("rule_halt_30_global")
                actual_sell = min(state["remaining_ratio"], 0.30)
                if actual_sell > 0.001:
                    state["remaining_ratio"] = max(0.0, state["remaining_ratio"] - actual_sell)
                    state["remaining_position_ratio"] = state["remaining_ratio"]
                    sugg_p = round(open_price * 1.28, 2)
                    sig_pt = SignalPoint(
                        code=c_clean,
                        timestamp=clean_time,
                        bar_index=bar_index,
                        price=price,
                        signal_type=SignalType.SELL,
                        source=SignalSource.STRATEGY_ENGINE,
                        debug_info={"suggested_price": sugg_p, "sell_ratio": actual_sell},
                        reason=f"⚡ [临停复牌] 盘中触及较开盘价+30%临停 (挂单:{sugg_p:.2f}元, 卖出{actual_sell*100:.0f}%)"
                    )
                    sig_pt.suggested_price = sugg_p
                    sig_pt.sell_ratio = actual_sell
                    generated_signals.append(sig_pt)
                    state.setdefault("signals", []).append(sig_pt)
                    state.setdefault("execution_logs", []).append(f"{clean_time} [临停复牌] +30%达成 | 卖出{actual_sell*100:.0f}% 建议挂单:{sugg_p:.2f}")

        rules = phase.get("rules", [])
        if not rules:
            default_strat = self.get_strategy_by_id("strategy_c_daily_surge_ladder")
            if default_strat:
                d_phase, _ = self.get_current_phase(clean_time, default_strat)
                if d_phase:
                    rules = d_phase.get("rules", [])

        # 3. 逐条评估阶段内规则
        for rule in rules:
            rule_id = rule.get("rule_id", "")
            if rule_id in state["triggered_rules"]:
                continue

            cond_mode = rule.get("condition_mode", "all")
            if cond_mode not in ("all", action_mode, "standard", "") and action_mode != "trend_hold":
                continue

            is_triggered = False
            trigger_reason = ""
            
            # 规则条件匹配判断 (优先支持 trigger_expr 动态表达式求值，向下兼容既有硬编码 ID)
            trigger_expr = rule.get("trigger_expr", "")
            if trigger_expr:
                try:
                    vwap_val = float(tick_row.get("vwap", price))
                    to_val = float(tick_row.get("turnover", tick_row.get("turnover_rate", 0.0)))
                    amt_val = float(tick_row.get("amount", 0.0))
                    eval_scope = {
                        "price": price,
                        "close": price,
                        "trade": price,
                        "open_price": open_price,
                        "open": open_price,
                        "max_price": state["max_price"],
                        "high": state["max_price"],
                        "min_price": state["min_price"],
                        "low": state["min_price"],
                        "vwap": vwap_val,
                        "turnover_rate": to_val,
                        "turnover": to_val,
                        "amount": amt_val,
                        "gain_from_open": ((price - open_price) / open_price * 100.0) if open_price > 0 else 0.0,
                        "gain_pct": ((price - open_price) / open_price * 100.0) if open_price > 0 else 0.0,
                        "pct": ((price - open_price) / open_price * 100.0) if open_price > 0 else 0.0,
                        "percent": ((price - open_price) / open_price * 100.0) if open_price > 0 else 0.0,
                        "close_high_ratio": (price / state["max_price"]) if state["max_price"] > 0 else 1.0,
                        "current_time": clean_time,
                        "time": clean_time,
                        "remaining_ratio": state["remaining_ratio"]
                    }
                    for tr_id in state["triggered_rules"]:
                        eval_scope[f"{tr_id}_triggered"] = True
                    for r_sub in rules:
                        sub_id = r_sub.get("rule_id", "")
                        if sub_id and f"{sub_id}_triggered" not in eval_scope:
                            eval_scope[f"{sub_id}_triggered"] = False

                    if eval(trigger_expr, {"__builtins__": {}}, eval_scope):
                        is_triggered = True
                        trigger_reason = rule.get("description", f"满足触发条件 [{trigger_expr}]")
                except Exception as e_eval:
                    logger.debug(f"规则 {rule_id} 表达式求值异常: {e_eval}")

            if not is_triggered:
                if rule_id in ["rule_a1_surge", "rule_pz_surge_10"]:
                    if price >= open_price * 1.10:
                        is_triggered = True
                        trigger_reason = f"开盘冲高≥10% (现价:{price:.2f} >= 目标:{open_price*1.10:.2f})"
                elif rule_id == "rule_a1_surge_decelerated":
                    if price >= open_price * 1.05:
                        is_triggered = True
                        trigger_reason = f"中性下沿冲高≥5% (现价:{price:.2f} >= 目标:{open_price*1.05:.2f})"
                elif rule_id in ["rule_a1_timeout", "rule_pz_timeout"]:
                    if clean_time >= "10:00" and "rule_a1_surge" not in state["triggered_rules"] and "rule_pz_surge_10" not in state["triggered_rules"]:
                        is_triggered = True
                        trigger_reason = "10:00整冲高未触发兜底卖出30%"
                elif rule_id in ["rule_a2_halt_30", "rule_pz_halt_30"]:
                    if state["max_price"] >= open_price * 1.30:
                        is_triggered = True
                        trigger_reason = f"+30%临停复牌卖30% (最高:{state['max_price']:.2f} >= 临停阈值:{open_price*1.30:.2f})"
                elif rule_id in ["rule_a3_overnight_check", "rule_pz_overnight_check"]:
                    if clean_time >= "14:50" and price >= open_price * 1.20:
                        is_triggered = True
                        trigger_reason = f"14:50仍高出开盘20%(现价:{price:.2f})，保留10%过夜，清仓其余"
                elif rule_id in ["rule_a3_clear_all", "rule_pz_clear_all"]:
                    if clean_time >= "14:50" and "rule_a3_overnight_check" not in state["triggered_rules"] and "rule_pz_overnight_check" not in state["triggered_rules"]:
                        is_triggered = True
                        trigger_reason = "14:50~14:57 尾盘市价清仓剩余全部"
                elif rule_id == "rule_b1_surge":
                    if price >= open_price * 1.08:
                        is_triggered = True
                        trigger_reason = f"策略B开盘冲高≥8% (现价:{price:.2f} >= 目标:{open_price*1.08:.2f})"
                elif rule_id == "rule_b1_timeout":
                    if clean_time >= "10:00" and "rule_b1_surge" not in state["triggered_rules"]:
                        is_triggered = True
                        trigger_reason = "策略B 10:00整超时卖出20%"
                elif rule_id == "rule_b2_halt_60":
                    if state["max_price"] >= open_price * 1.60:
                        is_triggered = True
                        trigger_reason = f"+60%临停复牌未创新高再卖33% (最高:{state['max_price']:.2f})"
                elif rule_id == "rule_b3_trailing_stop":
                    high_t = state.get("high_t", state["max_price"])
                    if price <= high_t * 0.90:
                        is_triggered = True
                        trigger_reason = f"T日高点({high_t:.2f})回撤10%移动止盈清仓(现价:{price:.2f})"

            # 4. 触发动作与信号路由生成
            if is_triggered:
                sell_ratio = float(rule.get("sell_ratio", 0.30))
                order_type = rule.get("order_type", "market_price")
                price_offset_ratio = float(rule.get("price_offset_ratio", 1.02))
                
                # 计算建议挂单价格 (价格笼子限制: 买一价 * 1.02)
                suggested_limit_price = price
                if order_type == "limit_price_cage":
                    ref_bid = bid1_price if bid1_price > 0 else price
                    suggested_limit_price = round(ref_bid * price_offset_ratio, 2)
                elif order_type == "limit" and "limit_price_expr" in rule:
                    suggested_limit_price = round(open_price * 1.28, 2)

                # 标记规则已触发
                state["triggered_rules"].add(rule_id)
                actual_sell_ratio = min(sell_ratio, state["remaining_ratio"])
                if actual_sell_ratio <= 0.001:
                    continue
                state["remaining_ratio"] = max(0.0, state["remaining_ratio"] - actual_sell_ratio)
                state["remaining_position_ratio"] = state["remaining_ratio"]

                sig_msg = f"[{rule.get('name')}] {trigger_reason} | 卖出{actual_sell_ratio*100:.0f}% 建议挂单:{suggested_limit_price:.2f}"
                log_entry = f"{clean_time} {sig_msg}"
                if log_entry not in state["execution_logs"]:
                    state["execution_logs"].append(log_entry)
                    logger.info(f"⚡ [IntradayStrategyEngine] {c_clean} {log_entry}")

                sp = SignalPoint(
                    code=c_clean,
                    timestamp=clean_time,
                    bar_index=bar_index,
                    price=price,
                    signal_type=SignalType.SELL,
                    reason=f"[{rule_id}] {trigger_reason}",
                    source=SignalSource.STRATEGY_ENGINE
                )
                sp.sell_ratio = actual_sell_ratio
                sp.suggested_price = suggested_limit_price
                sp.order_type = order_type
                sp.rule_id = rule_id
                sp.phase_id = phase.get("phase_id")
                
                state["signals"].append(sp)
                generated_signals.append(sp)

        if generated_signals:
            self.mark_dirty()
            self.save_intraday_cache(force=False)

        return generated_signals

    def extract_market_snapshot_from_df(self, df: Optional[pd.DataFrame], code: str) -> Dict[str, Any]:
        """
        全自动从实时推送的 DataFrame 中解析当前股票的行情快照
        包含：open, price/trade, high, low, vwap, turnover_rate, amount, volume, buy/bid1, sell/ask1 等
        """
        c_clean = str(code).zfill(6)
        res = {
            "open_price": 0.0,
            "price": 0.0,
            "high_price": 0.0,
            "low_price": 0.0,
            "vwap": 0.0,
            "turnover_rate": 0.0,
            "amount": 0.0,
            "volume": 0.0,
            "bid1_price": 0.0,
            "ask1_price": 0.0,
            "time_str": datetime.now().strftime("%H:%M:%S")
        }

        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return res

        row = None
        # 1. 尝试从 Index 匹配
        if c_clean in df.index:
            row = df.loc[c_clean]
        elif str(code) in df.index:
            row = df.loc[str(code)]
        else:
            # 2. 尝试从 'code' 列匹配
            code_col = next((c for c in ('code', 'symbol', 'sec_code') if c in df.columns), None)
            if code_col:
                matched = df[df[code_col].astype(str).str.contains(c_clean)]
                if not matched.empty:
                    row = matched.iloc[0]

        if row is None:
            # 3. 兼容单股 1 分钟 K 线历史 DataFrame (以 time 为行，非多股大表)
            if 'close' in df.columns or 'open' in df.columns:
                try:
                    first_r = df.iloc[0]
                    last_r = df.iloc[-1]
                    op_val = float(first_r.get('open', last_r.get('close', 0.0)))
                    cl_val = float(last_r.get('close', op_val))
                    hi_val = float(df['high'].max()) if 'high' in df.columns else max(op_val, cl_val)
                    lo_val = float(df['low'].min()) if 'low' in df.columns else min(op_val, cl_val)
                    if lo_val <= 1.0 or (cl_val > 5.0 and lo_val < cl_val * 0.1):
                        lo_val = cl_val if cl_val > 0 else op_val
                    vw_val = float(last_r.get('vwap', cl_val)) if 'vwap' in last_r and float(last_r.get('vwap', 0.0)) > 0 else cl_val
                    to_val = float(last_r.get('turnover', 0.0)) if 'turnover' in last_r else 0.0
                    amt_val = float(df['amount'].sum()) if 'amount' in df.columns else 0.0
                    vol_val = float(df['volume'].sum()) if 'volume' in df.columns else 0.0

                    return {
                        "open_price": op_val,
                        "price": cl_val,
                        "high_price": hi_val,
                        "low_price": lo_val,
                        "vwap": vw_val,
                        "turnover_rate": to_val,
                        "amount": amt_val,
                        "volume": vol_val,
                        "bid1_price": cl_val,
                        "ask1_price": cl_val,
                        "last_close": op_val,
                        "time_str": str(last_r.get('time', datetime.now().strftime("%H:%M:%S")))
                    }
                except Exception:
                    pass
            return res

        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        try:
            # 开盘价
            res["open_price"] = float(row.get('open', row.get('open_price', row.get('Open', 0.0))))
            
            # 当前价/收盘价
            res["price"] = float(row.get('close', row.get('trade', row.get('price', row.get('Close', 0.0)))))
            
            # 最高价/最低价
            res["high_price"] = float(row.get('high', row.get('high_price', row.get('High', res['price']))))
            raw_low = float(row.get('low', row.get('low_price', row.get('Low', res['price']))))
            if raw_low <= 1.0 or (res['price'] > 5.0 and raw_low < res['price'] * 0.1):
                raw_low = res['price'] if res['price'] > 0 else (res['open_price'] if res['open_price'] > 0 else 10.0)
            res["low_price"] = raw_low
            
            # 昨收价 / 前收盘价
            res["last_close"] = float(row.get('last_close', row.get('llastp', row.get('pre_close', row.get('settlement', res['open_price'])))))
            
            # 成交金额 (元) — 兼容 amount / turnover(金额) / money
            raw_amt = float(row.get('amount', row.get('money', row.get('Amount', 0.0))))
            raw_to_col = float(row.get('turnover', 0.0))
            if raw_amt <= 0 and raw_to_col > 1e4:
                raw_amt = raw_to_col
            res["amount"] = raw_amt
            
            # 成交量 (股/手)
            res["volume"] = float(row.get('volume', row.get('vol', row.get('Volume', 0.0))))
            
            # 换手率 (%) — 优先读取 turnoverratio / turnover_rate / turnover_ratio
            raw_to_ratio = row.get('turnoverratio', row.get('turnover_rate', row.get('turnover_ratio', row.get('turnover_d', None))))
            if raw_to_ratio is not None and float(raw_to_ratio) > 0:
                res["turnover_rate"] = float(raw_to_ratio)
            elif raw_to_col > 0 and raw_to_col <= 100.0:
                res["turnover_rate"] = raw_to_col
            else:
                # 若无直接换手率字段，尝试从成交额/流通市值推导
                spec = self.get_stock_ladder_spec(c_clean)
                float_mv_yi = float(spec.get("float_mv_yi", 0.0))
                if float_mv_yi > 0 and res["amount"] > 0:
                    res["turnover_rate"] = round((res["amount"] / (float_mv_yi * 1e8)) * 100.0, 2)
            
            # 换手率合理边界保护 (0.0% ~ 100.0%)
            if res["turnover_rate"] > 100.0 or res["turnover_rate"] < 0:
                res["turnover_rate"] = min(100.0, max(0.0, res["turnover_rate"]))
            
            # 买一价 / 卖一价
            res["bid1_price"] = float(row.get('buy', row.get('bid1', row.get('buy1', res['price']))))
            res["ask1_price"] = float(row.get('sell', row.get('ask1', row.get('sell1', res['price']))))
            
            # 时间字段
            t_val = row.get('time', row.get('timestamp', row.get('datetime', '')))
            if t_val:
                res["time_str"] = str(t_val)[-8:] if len(str(t_val)) >= 8 else str(t_val)

            # 动态计算与提取 VWAP 均价线
            # 1. 优先提取显式均价字段
            explicit_vwap = float(row.get('vwap_price', row.get('vwap', row.get('avg_price', row.get('nclose', row.get('avg', 0.0))))))
            cur_p = res["price"] if res["price"] > 0 else res["open_price"]
            
            if explicit_vwap > 0 and cur_p > 0 and (cur_p * 0.5 <= explicit_vwap <= cur_p * 2.0):
                res["vwap"] = round(explicit_vwap, 2)
            elif res["amount"] > 0 and res["volume"] > 0 and cur_p > 0:
                # 2. 尝试从 amount / volume 计算 (考虑 volume 是手还是股)
                v_gu = res["volume"] * 100.0  # 假设 volume 是手
                v_raw = res["volume"]         # 假设 volume 是股
                
                vwap_from_gu = res["amount"] / v_gu if v_gu > 0 else 0.0
                vwap_from_raw = res["amount"] / v_raw if v_raw > 0 else 0.0
                
                if cur_p * 0.7 <= vwap_from_gu <= cur_p * 1.3:
                    res["vwap"] = round(vwap_from_gu, 2)
                elif cur_p * 0.7 <= vwap_from_raw <= cur_p * 1.3:
                    res["vwap"] = round(vwap_from_raw, 2)
                else:
                    # 回退到四价均值
                    res["vwap"] = round((res["open_price"] + res["price"] + res["high_price"] + res["low_price"]) / 4.0, 2) if res["open_price"] > 0 else cur_p
            else:
                if res["open_price"] > 0 and cur_p > 0:
                    res["vwap"] = round((res["open_price"] + res["price"] + res["high_price"] + res["low_price"]) / 4.0, 2)
                else:
                    res["vwap"] = cur_p

            # 最终极端值兜底保护
            if res["vwap"] <= 0 or (cur_p > 0 and (res["vwap"] > cur_p * 3.0 or res["vwap"] < cur_p * 0.3)):
                res["vwap"] = cur_p

        except Exception as e:
            logger.warning(f"Error parsing market row from DataFrame: {e}")

        return res

    def generate_scenario_intraday_df(self, scenario_type: str = "A_SUPER_TREND", code: str = "688826") -> pd.DataFrame:
        """
        生成全天分时模拟回测情景数据（9:15 到 15:00 精确时间对齐，共 241 根分时记录）
        100% 动态自适应任何股票代码及其专属发行价与流通盘！
        情景可选:
        - 'A_SUPER_TREND': A型·超强主升主线 (+336% 超强封板锁仓，得分 > 8.0)
        - 'B_STRONG_TURNOVER': B型·强势换手洗盘 (+189% 强势换手承接，得分 6.5~8.0)
        - 'C_SURGE_AND_CASH': C型·冲高兑现回落 (+105% 冲高回落走弱，得分 5.0~6.5)
        - 'D_WEAK_EXHAUSTION': D/E型·弱势衰竭走弱 (+60% 高开低走破位，得分 < 5.0)
        """
        c_clean = str(code).zfill(6) if code else "688826"
        spec = self.get_stock_ladder_spec(c_clean)
        issue_p = float(spec.get("issue_price", 100.0))
        float_shares_wan = float(spec.get("float_shares_wan", 1000.0))
        float_shares = float_shares_wan * 10000.0
        float_mv = float(spec.get("float_mv_yi", 15.0)) * 1e8

        times = []
        # 1. 集合竞价 09:15 ~ 09:25 (11 min)
        for m in range(15, 26):
            times.append(f"09:{m:02d}")
        # 2. 上午分时 09:30 ~ 11:30 (121 min)
        for h in range(9, 12):
            start_m = 30 if h == 9 else 0
            end_m = 31 if h == 11 else 60
            for m in range(start_m, end_m):
                times.append(f"{h:02d}:{m:02d}")
        # 3. 下午分时 13:00 ~ 15:00 (121 min)
        for h in range(13, 16):
            start_m = 0
            end_m = 1 if h == 15 else 60
            for m in range(start_m, end_m):
                times.append(f"{h:02d}:{m:02d}")

        n = len(times)
        records = []
        cum_volume = 0
        cum_amount = 0.0
        running_high = 0.0
        running_low = 999999.0

        if scenario_type == "A_SUPER_TREND":
            open_p = round(issue_p * 3.10, 2) # +210% 强势高开
            target_close = round(issue_p * 4.36, 2) # 冲高至 +336%
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:45":
                    p = open_p + (i - 11) * (open_p * 0.010) + np.sin(i)*1.5
                elif "09:45" < t <= "10:30":
                    p = open_p * 1.10 + np.sin(i*0.3)*(open_p * 0.01)
                elif "10:30" < t <= "11:30":
                    p = open_p * 1.17 + (i - 70) * (open_p * 0.002)
                elif "13:00" <= t <= "14:00":
                    p = open_p * 1.28 + (i - 130) * (open_p * 0.0015)
                elif "14:00" < t <= "14:50":
                    p = target_close * 0.98 + (i - 190) * (open_p * 0.001)
                else:
                    p = target_close - (i - 230) * (open_p * 0.0005)
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.65 / n * (1.5 if t < "10:00" or t > "14:30" else 0.8))
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        elif scenario_type == "B_STRONG_TURNOVER":
            open_p = round(issue_p * 2.62, 2) # +162% 乐观下沿
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:40":
                    p = open_p + (i - 11) * (open_p * 0.008)
                elif "09:40" < t <= "10:30":
                    p = open_p * 1.08 - (i - 21) * (open_p * 0.0012)
                elif "10:30" < t <= "11:30":
                    p = open_p * 1.04 + np.sin(i*0.2)*(open_p * 0.008)
                elif "13:00" <= t <= "14:30":
                    p = open_p * 1.07 + (i - 130) * (open_p * 0.0006)
                else:
                    p = round(open_p * 1.10 + np.sin(i)*(open_p * 0.004), 2)
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.62 / n)
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        elif scenario_type == "C_SURGE_AND_CASH":
            open_p = round(issue_p * 2.11, 2) # +111% 翻倍中性档
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:40":
                    p = open_p + (i - 11) * (open_p * 0.011)
                elif "09:40" < t <= "11:30":
                    p = open_p * 1.11 - (i - 21) * (open_p * 0.001)
                else:
                    p = open_p * 0.99 - (i - 130) * (open_p * 0.0003)
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.52 / n)
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        else: # D_WEAK_EXHAUSTION
            open_p = round(issue_p * 2.25, 2)
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:45":
                    p = open_p - (i - 11) * (open_p * 0.008)
                elif "09:45" < t <= "11:30":
                    p = open_p * 0.88 - (i - 26) * (open_p * 0.0012)
                else:
                    p = open_p * 0.78 - (i - 130) * (open_p * 0.0005)
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.42 / n)
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        df_res = pd.DataFrame(records)
        df_res.set_index("time", drop=False, inplace=True)
        return df_res

    def run_full_day_backtest(self, code: str, df_intraday: pd.DataFrame) -> Dict[str, Any]:
        """
        全天分时模拟回测运行器：输入分时 DataFrame，输出完整 7 节点评分演进、阶梯买卖点与最终形态
        """
        c_clean = str(code).zfill(6)
        self.reset_state(c_clean)
        
        all_signals = []
        timeline_history = []
        open_p = 0.0

        for idx, (t_str, row) in enumerate(df_intraday.iterrows()):
            if idx == 0 or open_p <= 0:
                open_p = float(row.get("open", row.get("close", 0.0)))
            
            p = float(row.get("trade", row.get("close", 0.0)))
            h = float(row.get("high", p))
            l = float(row.get("low", p))
            vw = float(row.get("vwap", p))
            to = float(row.get("turnover", 0.0))
            amt = float(row.get("amount", 0.0))
            b1 = float(row.get("buy", p))

            # 1. 评估阶梯交易信号
            sigs = self.evaluate_tick(
                code=c_clean,
                tick_row=row.to_dict(),
                open_price=open_p,
                current_time_str=t_str,
                bid1_price=b1,
                bar_index=idx
            )
            all_signals.extend(sigs)

            # 2. 评估 7 节点时序状态机
            eval_res = self.evaluate_seven_nodes(
                code=c_clean,
                current_time_str=t_str,
                open_price=open_p,
                price=p,
                high_price=h,
                low_price=l,
                vwap=vw,
                turnover_rate=to,
                amount=amt
            )

            timeline_history.append({
                "time": t_str,
                "price": p,
                "score": eval_res.get("total_weighted_score", 0.0),
                "pattern": eval_res.get("pattern", "--"),
                "remaining_ratio": self._get_stock_state(c_clean, open_p).get("remaining_ratio", 1.0)
            })

        state = self._get_stock_state(c_clean, open_p)
        final_eval = self.evaluate_seven_nodes(
            code=c_clean,
            current_time_str="15:00",
            open_price=open_p,
            price=df_intraday.iloc[-1]["close"],
            high_price=df_intraday["high"].max(),
            low_price=df_intraday["low"].min(),
            vwap=df_intraday.iloc[-1]["vwap"],
            turnover_rate=df_intraday.iloc[-1]["turnover"],
            amount=df_intraday.iloc[-1]["amount"]
        )

        return {
            "code": c_clean,
            "open_price": open_p,
            "total_bars": len(df_intraday),
            "signals": all_signals,
            "execution_logs": state.get("execution_logs", []),
            "final_evaluation": final_eval,
            "timeline_history": timeline_history,
            "remaining_ratio": state.get("remaining_ratio", 0.0)
        }

    def reset_state(self, code: Optional[str] = None):
        """重置股票判定状态"""
        if code:
            c_clean = str(code).zfill(6)
            if c_clean in self.rule_state_map:
                del self.rule_state_map[c_clean]
        else:
            self.rule_state_map.clear()

