# -*- coding: utf-8 -*-
"""
ats/capital_dragon_engine.py — ATS 资金趋势与真龙辨识度核心量化引擎 (SSOT)
=============================================================================
职责定位：
1. 【资金流向与流动性深度度量】：
   - 全市场成交额分级：超大容量中军 (>=15亿/Top30)、主流活跃 (3~15亿)、微盘孤狼 (<1亿降权)；
   - 换手率、量比与主力资金沉淀度量；
2. 【主线板块资金集聚识别】：
   - 聚合板块总成交额、上涨比率、涨停梯队集聚度，甄别市场前 3 大核心增量主线；
3. 【真龙四维角色精准画像】：
   - 【👑 空间高度龙】：全市场连板最高、情绪风向标 (对接 LimitUpEngine)；
   - 【🛡️ 趋势容量中军】：大成交额容量龙头、自适应通道多头向上、机构游资合力底座；
   - 【🚀 主线板块先锋】：Top 核心主线最早涨停/拔起攻坚的领头羊；
   - 【💎 弱转强卡位龙】：分歧转一致、竞价/开盘放量逆袭的接力龙；
4. 【资金趋势买点决策与诱多铁壁拦截】：
   - 分歧低吸点 (VWAP/通道支撑)、放量突破确认点、中军缩量企稳点；
   - 识别并精准拦截【⚠️ 孤狼脉冲】与【⛔ 破位诱多】。
"""

import os
import time
import math
import logging
import threading
from typing import Dict, List, Tuple, Optional, Any, Set
import pandas as pd
import numpy as np

from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("CapitalDragonEngine")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "" or val == "-" or val == "--":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clean_code(c: Any) -> str:
    s = str(c).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(6) if digits else s


class CapitalDragonEngine:
    """
    资金趋势与主线龙头核心量化引擎 (单例)
    """
    _instance: Optional['CapitalDragonEngine'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'CapitalDragonEngine':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._cached_report: Dict[str, Any] = {}
        self._cached_time: float = 0.0
        self._cache_lock = threading.RLock()
        self._dragon_codes_set: Set[str] = set()
        self._trap_codes_set: Set[str] = set()

    def _get_virtual_vol_ratio(self, df: pd.DataFrame) -> pd.Series:
        """
        获取或计算全市场的虚拟量比序列 (SSOT)
        支持：
        1. 直接从 df 的 vol_ratio 列提取；
        2. 若 volume 列存在且中位数/均值在 0~20 之间（已被 calc_compute_volume 转换为虚拟量比强度），直接复用；
        3. 若有原始成交量 (vol/volume) 与昨量 (lastv1d/last6vol)，结合 cct.get_work_time_ratio 实时按交易进度投影放大计算；
        4. 兜底返回 1.0。
        """
        if df is None or df.empty:
            return pd.Series(1.0, index=df.index if df is not None else [])

        # 优先 1: 直接读取 vol_ratio / vr
        for col in ('vol_ratio', 'vr', 'volume_ratio'):
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce').fillna(1.0)
                if (s > 0).any():
                    return s.round(2)

        # 优先 2: 检查 volume 列是否已是虚拟量比（系统 data_utils.calc_compute_volume 注入特征：数值通常在 0.1 ~ 30 之间）
        if 'volume' in df.columns:
            s_vol = pd.to_numeric(df['volume'], errors='coerce').fillna(0.0)
            if 0 < s_vol.max() <= 50.0 and s_vol.quantile(0.9) <= 15.0:
                return s_vol.replace(0.0, 1.0).round(2)

        # 优先 3: 结合日内交易时间比例进行向量化动态投影
        try:
            from JohnsonUtil import commonTips as cct
            ratio_t = float(cct.get_work_time_ratio(resample='d'))
        except Exception:
            ratio_t = 1.0
        ratio_t = max(0.05, min(ratio_t, 1.0))

        raw_vol = None
        for v_col in ('vol', 'volume', 'trade_vol'):
            if v_col in df.columns:
                cand = pd.to_numeric(df[v_col], errors='coerce').fillna(0.0)
                if (cand > 0).any():
                    raw_vol = cand
                    break

        base_vol = None
        for b_col in ('lastv1d', 'last6vol', 'l6vol', 'prev_vol', 'vol_ma5'):
            if b_col in df.columns:
                cand = pd.to_numeric(df[b_col], errors='coerce').fillna(0.0)
                if (cand > 0).any():
                    base_vol = cand.replace(0.0, np.nan)
                    break

        if raw_vol is not None and base_vol is not None:
            proj_vol = raw_vol / ratio_t
            vr = (proj_vol / base_vol).fillna(1.0).clip(0.1, 50.0).round(2)
            return vr

        return pd.Series(1.0, index=df.index)

    def analyze_capital_dragon_universe(
        self,
        df_all: Optional[pd.DataFrame],
        sh_pct: float = 0.0,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        全量分析全市场资金分布、核心主线、龙头角色画像与资金趋势买点。
        带 1.0 秒轻量防抖缓存，避免高频 IPC 广播下重复沉重运算。
        """
        if df_all is None or df_all.empty:
            with self._cache_lock:
                return dict(self._cached_report)

        now = time.time()
        if not force and (now - self._cached_time < 1.0) and self._cached_report:
            with self._cache_lock:
                return dict(self._cached_report)

        t0 = time.time()

        # 1. 规范化提取基础字段 (向量化处理，超高速)
        df = df_all.copy(deep=False)
        close_col = 'close' if 'close' in df.columns else ('price' if 'price' in df.columns else None)
        pct_col = 'percent' if 'percent' in df.columns else ('pct' if 'pct' in df.columns else None)
        amt_col = 'amount' if 'amount' in df.columns else ('turnover' if 'turnover' in df.columns else None)

        if not close_col or not pct_col:
            return {}

        # 提取连板天梯数据
        ladder_dict = {}
        try:
            from ats.limit_up_engine import LimitUpEngine
            lue = LimitUpEngine.get_instance()
            radar_recs = lue.get_intraday_radar_records(current_df=df)
            for r in radar_recs:
                c = _clean_code(r.get("code", ""))
                if c:
                    ladder_dict[c] = r
        except Exception as e_lue:
            logger.debug(f"[CapitalDragonEngine] Load limit up records error: {e_lue}")

        # 2. 向量化预计算资金与涨幅指标
        codes_series = pd.Series([_clean_code(c) for c in df.index], index=df.index)
        prices = pd.to_numeric(df[close_col], errors='coerce').fillna(0.0)
        pcts = pd.to_numeric(df[pct_col], errors='coerce').fillna(0.0)
        
        # 成交金额转换 (统一转为亿元)
        amts_yi = pd.Series(0.0, index=df.index)
        if amt_col:
            raw_amt = pd.to_numeric(df[amt_col], errors='coerce').fillna(0.0)
            # 若原始值已经小于 10000 说明已经是亿元或万元单位，根据均值自适应判断
            if raw_amt.max() > 1e7:
                amts_yi = raw_amt / 1e8
            elif raw_amt.max() > 1000:
                amts_yi = raw_amt / 10000.0
            else:
                amts_yi = raw_amt

        # 换手率
        turnover_s = pd.Series(0.0, index=df.index)
        for t_col in ('turnover_rate', 'turnover', 'hsl', 'ratio'):
            if t_col in df.columns:
                cand = pd.to_numeric(df[t_col], errors='coerce').fillna(0.0)
                if 0.0 < cand.max() <= 100.0:
                    turnover_s = cand
                    break

        # 板块分类列
        sec_col = next((c for c in ('category', 'industry', 'concept') if c in df.columns), None)
        sectors = df[sec_col].astype(str).str.strip() if sec_col else pd.Series('', index=df.index)

        # 多周期特征
        def _get_series(col_names):
            for c in col_names:
                if c in df.columns:
                    return pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            return pd.Series(0.0, index=df.index)

        dff_s = _get_series(['dff', 'DFF'])
        dff2_s = _get_series(['dff2', 'DFF2'])
        dff3_s = _get_series(['dff3', 'DFF3'])
        ch_supp_s = _get_series(['ch_supp', 'ch_lower'])
        ma20_s = _get_series(['ma20d', 'ma20', 'MA20'])

        # 提取全市场系统的虚拟量比序列 (SSOT)
        vol_ratio_s = self._get_virtual_vol_ratio(df)
        try:
            from JohnsonUtil import commonTips as cct
            ratio_t = float(cct.get_work_time_ratio(resample='d'))
        except Exception:
            ratio_t = 1.0
        ratio_t = max(0.05, min(ratio_t, 1.0))

        # 3. 统计主线板块资金集聚度
        sector_stats = {}
        valid_mask = (prices > 0.0) & (~codes_series.isin(['000001', '399001', '399006', 'sh000001', 'sz399001']))
        
        for idx in df[valid_mask].index:
            sec = sectors.loc[idx]
            if not sec or sec in ('--', 'nan', '未知', '其它', '其他', '0', '0.0', 'None'):
                continue
            amt = float(amts_yi.loc[idx])
            p_val = float(pcts.loc[idx])
            vr_val = float(vol_ratio_s.loc[idx]) if idx in vol_ratio_s.index else 1.0
            
            # 分割复合板块名 (如 "软件服务;人工智能;大数据")
            sub_secs = [s.strip() for s in sec.replace(';', ',').replace('、', ',').split(',') if s.strip()]
            for s_name in sub_secs[:2]: # 仅取最核心的前2个概念
                if len(s_name) < 2:
                    continue
                if s_name not in sector_stats:
                    sector_stats[s_name] = {
                        "name": s_name,
                        "total_amt_yi": 0.0,
                        "up_count": 0,
                        "limit_up_count": 0,
                        "total_count": 0,
                        "avg_pct": 0.0,
                        "sum_pct": 0.0,
                        "sum_vr_weighted": 0.0,
                        "sum_vr": 0.0,
                        "vol_ratio": 1.0,
                        "proj_amt_yi": 0.0,
                        "leader_code": "",
                        "leader_name": "",
                        "leader_pct": -99.0,
                        "leader_amt_yi": 0.0
                    }
                st = sector_stats[s_name]
                st["total_amt_yi"] += amt
                st["total_count"] += 1
                st["sum_pct"] += p_val
                st["sum_vr_weighted"] += amt * vr_val
                st["sum_vr"] += vr_val
                if p_val > 0.0:
                    st["up_count"] += 1
                if p_val >= 9.5: # 涨停门槛
                    st["limit_up_count"] += 1
                
                # 记录板块领涨先锋
                if p_val > st["leader_pct"]:
                    st["leader_pct"] = p_val
                    st["leader_code"] = codes_series.loc[idx]
                    st["leader_name"] = str(df.loc[idx, 'name']) if 'name' in df.columns else ""
                    st["leader_amt_yi"] = amt

        # 计算板块综合资金强度得分
        top_sectors = []
        for s_name, st in sector_stats.items():
            if st["total_count"] < 3:
                continue
            st["avg_pct"] = round(st["sum_pct"] / st["total_count"], 2)
            up_ratio = st["up_count"] / st["total_count"]

            # 板块虚拟量比：成交额加权虚拟量比（资金权重优先），无成交额时使用算术平均
            if st["total_amt_yi"] > 0:
                sec_vr = st["sum_vr_weighted"] / st["total_amt_yi"]
            else:
                sec_vr = st["sum_vr"] / max(1, st["total_count"])
            st["vol_ratio"] = round(float(sec_vr), 2)
            st["proj_amt_yi"] = round(float(st["total_amt_yi"] / ratio_t), 1)
            
            # 板块资金强度 = 成交额(亿)*0.15 + 涨停数*15 + 平均涨幅*4 + 上涨占比*20 + 虚拟量比加速加分(最高15分)
            vr_bonus = min(15.0, max(0.0, (st["vol_ratio"] - 1.0) * 8.0))
            strength_score = (
                min(40.0, st["total_amt_yi"] * 0.15) +
                st["limit_up_count"] * 15.0 +
                max(0.0, st["avg_pct"]) * 4.0 +
                up_ratio * 20.0 +
                vr_bonus
            )
            st["strength_score"] = round(strength_score, 1)
            
            # 主线评级
            if st["limit_up_count"] >= 3 or (st["strength_score"] >= 65 and st["total_amt_yi"] >= 50.0):
                st["grade"] = "👑 核心主线"
            elif st["limit_up_count"] >= 1 or st["strength_score"] >= 45:
                st["grade"] = "🚀 活跃赛道"
            else:
                st["grade"] = "🟡 轮动分支"
                
            top_sectors.append(st)

        # 按资金强度降序排列，取 Top 5 核心主线
        top_sectors.sort(key=lambda x: x["strength_score"], reverse=True)

        # 4. 全市场龙头多维角色精准画像 (True Dragon Hierarchy)
        dragon_records = []
        dragon_codes_set = set()
        trap_codes_set = set()

        # 计算全市场成交额排名前 60 (容量中军候选池)
        top_amt_df = df[valid_mask].sort_values(by=amt_col, ascending=False) if amt_col else df[valid_mask]
        top_50_amt_codes = set(codes_series.loc[top_amt_df.index[:60]])

        for idx in df[valid_mask].index:
            code_str = codes_series.loc[idx]
            name_str = str(df.loc[idx, 'name']) if 'name' in df.columns else code_str
            price_val = float(prices.loc[idx])
            pct_val = float(pcts.loc[idx])
            amt_yi = float(amts_yi.loc[idx])
            turnover_val = float(turnover_s.loc[idx])
            sec_str = str(sectors.loc[idx])
            
            dff = float(dff_s.loc[idx])
            dff2 = float(dff2_s.loc[idx])
            dff3 = float(dff3_s.loc[idx])
            ch_supp = float(ch_supp_s.loc[idx])
            ma20_val = float(ma20_s.loc[idx])

            # 是否属于 Top 核心主线板块
            matched_main_sec = ""
            for ts in top_sectors[:5]:
                if ts["name"] in sec_str:
                    matched_main_sec = ts["name"]
                    break

            # 提取连板信息
            ladder_info = ladder_dict.get(code_str, {})
            l_days = int(ladder_info.get("limit_days", 0))
            is_limit_up = bool(ladder_info.get("is_limit_up", False) or pct_val >= 9.5)
            bid_amt_yi = float(ladder_info.get("bid_amount_yi", 0.0))
            is_first_limit = bool(ladder_info.get("is_first_board", False) or (is_limit_up and l_days <= 1))

            # 趋势通道状态判决
            has_channel_base = (dff2 > 0.0 or dff3 > 0.0 or (ma20_val > 0 and price_val >= ma20_val * 0.98))
            is_channel_down = (dff2 < -5.0 and dff3 < -5.0 and ma20_val > 0 and price_val < ma20_val * 0.95)

            # ── 💡 铁壁拦截：孤狼脉冲与破位诱多 ──
            if is_channel_down and not matched_main_sec and not is_limit_up:
                trap_codes_set.add(code_str)
                continue  # 破位诱多，彻底剔除

            if amt_yi < 0.8 and not is_limit_up and (not matched_main_sec or pct_val < 3.0):
                # 成交额不足 8000 万且无板块无涨停的边缘杂毛
                trap_codes_set.add(code_str)
                continue

            # ── 💡 四维真龙画像定位 ──
            dragon_role = ""
            role_priority = 0
            action_type = ""
            action_tip = ""
            buy_zone = ""
            stop_loss = round(price_val * 0.95, 2)
            reason = ""

            # 1. 【👑 空间高度龙】：市场连板天梯标杆 (3板及以上，或全市场最高板)
            if l_days >= 3 or (is_limit_up and l_days >= 2 and l_days == max((r.get('limit_days', 0) for r in ladder_dict.values()), default=0)):
                dragon_role = "👑 空间高度龙"
                role_priority = 100
                if is_limit_up:
                    action_type = "🔒 锁仓/巨量换手板"
                    buy_zone = f"{price_val:.2f}"
                    action_tip = "情绪空间总龙头，开板可关注分歧换手回封机会"
                    reason = f"市场最高连板梯队 ({l_days}连板), 情绪总标杆, 巨资封单{bid_amt_yi:.2f}亿"
                else:
                    action_type = "💎 高位分歧低吸"
                    buy_zone = f"{round(price_val * 0.97, 2)} ~ {price_val:.2f}"
                    action_tip = "高位分歧承接，关注首阴或日内分时均线低吸机会"
                    reason = f"空间高度龙盘中分歧 ({l_days}板预期), 资金换手承接充分"

            # 2. 【🛡️ 趋势容量中军】：成交额 Top 50 且通道多头向上的机构游资合力大票
            elif (code_str in top_50_amt_codes or amt_yi >= 12.0) and has_channel_base:
                dragon_role = "🛡️ 趋势容量中军"
                role_priority = 90
                supp_ref = max(ch_supp, ma20_val) if ch_supp > 0 else (ma20_val if ma20_val > 0 else round(price_val * 0.95, 2))
                stop_loss = round(supp_ref * 0.97, 2)
                
                if pct_val >= 4.0:
                    action_type = "🚀 主升趋势加速"
                    buy_zone = f"{round(price_val * 0.98, 2)} ~ {price_val:.2f}"
                    action_tip = "容量大票放量主升，顺势持股或回踩分时均线加仓"
                    reason = f"全市场成交额巨量排头 (成交{amt_yi:.1f}亿), 多头通道稳健向上 (DFF2={dff2:.1f})"
                else:
                    action_type = "🎯 通道支撑企稳"
                    buy_zone = f"{supp_ref:.2f} ~ {round(supp_ref * 1.02, 2)}"
                    action_tip = "大票缩量回踩通道中轨/支撑位，低吸性价比极高"
                    reason = f"百亿级别容量中军 (成交{amt_yi:.1f}亿) 回踩多头支撑位 ({supp_ref:.2f}元), 机构承接有力"

            # 3. 【🚀 主线板块先锋】：Top 3 核心主线最早拔起或涨停的领跑者
            elif matched_main_sec and (is_limit_up or (pct_val >= 5.0 and code_str == top_sectors[0]["leader_code"])):
                dragon_role = "🚀 主线板块先锋"
                role_priority = 85
                buy_zone = f"{price_val:.2f}" if is_limit_up else f"{round(price_val * 0.98, 2)} ~ {price_val:.2f}"
                stop_loss = round(price_val * 0.96, 2)
                action_type = "⚡ 主线率先冲关"
                action_tip = "核心主线带队大哥，享受板块助攻溢价"
                reason = f"所属【{matched_main_sec}】核心主线率先拔起封板 (+{pct_val:.1f}%), 带动整个赛道爆发"

            # 4. 【💎 弱转强/分歧转一致】：主线内强势换手首板或跳空拔起
            elif is_limit_up and is_first_limit and amt_yi >= 2.0:
                dragon_role = "💎 强势换手首板"
                role_priority = 80
                buy_zone = f"{price_val:.2f}"
                stop_loss = round(price_val * 0.95, 2)
                action_type = "🔥 启动首板封死"
                action_tip = "量价结构健康的首板标的，次日关注接力一进二"
                reason = f"成交额达标 (成交{amt_yi:.1f}亿/换手{turnover_val:.1f}%), 封板坚决"

            # 5. 【📈 核心主线高辨识度标的】：主线涨幅前列且成交活跃
            elif matched_main_sec and pct_val >= 4.0 and amt_yi >= 2.5:
                dragon_role = "📈 主线共振中坚"
                role_priority = 70
                buy_zone = f"{round(price_val * 0.98, 2)} ~ {price_val:.2f}"
                stop_loss = round(price_val * 0.96, 2)
                action_type = "🌊 顺应主线共振"
                action_tip = "跟随核心主线放量上攻，注意高抛低吸"
                reason = f"所属【{matched_main_sec}】主流赛道放量走强 (成交{amt_yi:.1f}亿, 涨幅+{pct_val:.1f}%)"

            if dragon_role:
                dragon_codes_set.add(code_str)
                vr_val = float(vol_ratio_s.loc[idx]) if idx in vol_ratio_s.index else 1.0
                dragon_records.append({
                    "code": code_str,
                    "name": name_str,
                    "role": dragon_role,
                    "priority": role_priority,
                    "sector": matched_main_sec or sec_str.split(';')[0].split(',')[0],
                    "price": price_val,
                    "pct": pct_val,
                    "amount_yi": round(amt_yi, 2),
                    "vol_ratio": round(vr_val, 2),
                    "turnover": round(turnover_val, 2),
                    "action_type": action_type,
                    "action_tip": action_tip,
                    "buy_zone": buy_zone,
                    "stop_loss": stop_loss,
                    "reason": reason if vr_val < 2.0 else f"{reason}, 虚拟量比加速({vr_val:.1f}x)",
                    "dff": dff,
                    "dff2": dff2,
                    "dff3": dff3,
                    "limit_days": l_days,
                    "is_limit_up": is_limit_up
                })

        # 排序：优先按角色优先级降序，再按成交额与涨幅
        dragon_records.sort(key=lambda x: (x["priority"], x["amount_yi"], x["pct"]), reverse=True)

        report = {
            "timestamp": now,
            "calc_cost_ms": round((time.time() - t0) * 1000, 1),
            "top_sectors": top_sectors[:5],
            "dragon_records": dragon_records,
            "dragon_codes_set": dragon_codes_set,
            "trap_codes_set": trap_codes_set,
            "space_dragon_count": sum(1 for r in dragon_records if "空间" in r["role"]),
            "midcap_dragon_count": sum(1 for r in dragon_records if "容量" in r["role"]),
            "pioneer_dragon_count": sum(1 for r in dragon_records if "先锋" in r["role"])
        }

        with self._cache_lock:
            self._cached_report = report
            self._cached_time = now
            self._dragon_codes_set = dragon_codes_set
            self._trap_codes_set = trap_codes_set

        logger.debug(
            f"[CapitalDragonEngine] Completed analysis in {report['calc_cost_ms']}ms: "
            f"TopSectors={len(top_sectors[:5])}, Dragons={len(dragon_records)} "
            f"(Space={report['space_dragon_count']}, Mid={report['midcap_dragon_count']}, Pioneer={report['pioneer_dragon_count']})"
        )
        return report

    def get_dragon_codes(self) -> Set[str]:
        with self._cache_lock:
            return set(self._dragon_codes_set)

    def is_true_dragon(self, code: str) -> bool:
        c = _clean_code(code)
        with self._cache_lock:
            return c in self._dragon_codes_set

    def is_isolated_trap(self, code: str) -> bool:
        c = _clean_code(code)
        with self._cache_lock:
            return c in self._trap_codes_set

    def get_dragon_info(self, code: str) -> Optional[Dict[str, Any]]:
        c = _clean_code(code)
        with self._cache_lock:
            recs = self._cached_report.get("dragon_records", [])
            for r in recs:
                if r["code"] == c:
                    return dict(r)
        return None
