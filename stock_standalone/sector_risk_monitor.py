# -*- coding: utf-8 -*-
"""
板块系统性风险监控器
"""
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class SectorRiskMonitor:
    """
    板块系统性风险监控器
    
    核心功能:
    1. 追踪 Top5 热点板块的实时健康度
    2. 检测板块龙头回撤（龙头涨幅 vs 板块均值）
    3. 检测板块整体拉升信号（板块涨幅 > 阈值）
    4. 输出系统性风险等级和跟单建议
    """
    
    def __init__(self, pullback_threshold=0.03, rally_threshold=0.03):
        """
        Args:
            pullback_threshold: 龙头回撤阈值（相对板块，默认 3%）
            rally_threshold: 板块拉升阈值（默认 3%）
        """
        self.pullback_threshold = pullback_threshold
        self.rally_threshold = rally_threshold
        self._sector_cache = {}  # {sector_name: {leader_code, leader_pct, avg_pct, ...}}
        self._risk_level = 0.0  # 0-1 系统性风险等级
        self._last_update_time = 0
        
    def update(self, df_all: pd.DataFrame, concept_top5: list) -> dict:
        """
        每轮行情数据更新板块状态
        
        Returns:
            {
                "risk_level": float,  # 0-1 系统性风险等级
                "pullback_alerts": [(sector, leader_code, pullback_pct), ...],
                "rally_signals": [(sector, avg_pct, leader_code), ...],
                "sector_stats": {sector_name: {...}}
            }
        """
        if df_all is None or df_all.empty or not concept_top5:
            return {}

        current_stats = {}
        risk_score = 0.0
        pullback_alerts = []
        rally_signals = []
        
        # 提取板块名称
        top_concepts = []
        for item in concept_top5:
            if isinstance(item, (list, tuple)):
                # concept_top5 格式可能是 [('板块名', ...), ...]
                top_concepts.append(str(item[0]))
            else:
                top_concepts.append(str(item))
                
        if not top_concepts:
            return {}

        # 遍历每个热点板块
        for sector in top_concepts:
            # 1. 筛选板块内的股票
            # 假设 df_all 有 'category' 列包含板块信息
            if 'category' not in df_all.columns:
                continue
                
            # 模糊匹配板块
            # 注意：全量扫描可能较慢，建议优化或限制范围。
            # 这里为了性能，应该依赖上游已经筛选好的板块对应关系，或者使用 pandas 的 str.contains
            # 但 str.contains 在大数据量下较慢。
            # 为了简便，我们假设 process_data 已经做了一定的预处理，或者我们只关心已经在 snapshot 里的?
            # 不，df_all 是全量。为了性能，必须优化。
            # 暂时: 简单粗暴遍历在 df_all 中属于该板块的股票
            
            # 优化方案: 预先构建 sector_map (在 service 层做更好，这里先简易实现)
            # 实际上 category 格式如 "行业;概念;..."
            # 我们可以只计算 df_all 中涨幅前列的股票来估算板块强度，或者依赖外部传入的 concept_top5 数据(如果有详情)
            
            # 这里采用“快速采样”法：只看 df_all 中 volume > 0 的活跃股
            # 且只计算涨幅 Top 和 Bottom 的部分来评估？不准确。
            
            # 妥协方案：只计算当前监控列表 + 涨幅榜 Top50 中的相关股票
            # 或者，假设 concept_top5 本身带有板块指数的数据？(目前看代码是没有的，只是名字)
            
            # --- 真正实现 ---
            sector_stocks = df_all[df_all['category'].astype(str).str.contains(sector, regex=False, na=False)]
            
            if sector_stocks.empty:
                continue
                
            # 计算板块均值
            avg_pct = sector_stocks['percent'].mean()
            
            # 寻找龙头 (涨幅最大且量能充沛)
            # 排序：涨幅降序
            sorted_stocks = sector_stocks.sort_values(by='percent', ascending=False)
            if sorted_stocks.empty:
                continue
                
            leader = sorted_stocks.iloc[0]
            leader_code = leader.name # index is code
            leader_pct = leader['percent']
            leader_name = leader['name']
            
            # check if leader is pullback
            # 龙头回撤定义：龙头当前涨幅 距离 其今日最高涨幅 回撤较大？
            # 或者 龙头涨幅 < 板块均值 (被反超) ? 
            # 通常系统性风险是：早盘龙一涨停，下午炸板跳水，带动板块下杀。
            
            # 我们需要 leader 的 high_percent (最高涨幅)。 df_all 只有 high (价格)。
            leader_open = float(leader['open'])
            leader_high = float(leader['high'])
            leader_trade = float(leader['trade'])
            leader_pre_close = float(leader.get('last_close', leader_trade / (1 + leader_pct/100))) # 估算

            if leader_pre_close > 0:
                leader_high_pct = (leader_high - leader_pre_close) / leader_pre_close * 100
                pullback = leader_high_pct - leader_pct
                
                # 风险检测 1: 龙头大幅回撤 (比如炸板)
                if pullback > 3.0: # 从高点回撤 3%
                    pullback_alerts.append((sector, leader_code, pullback))
                    risk_score += 0.2
                    logger.info(f"⚠️ 板块 {sector} 龙头 {leader_name} 回撤 {pullback:.1f}%")
            
            # 机会检测 1: 板块整体拉升 (均值 > 3% 且 龙头涨停或接近涨停)
            if avg_pct > self.rally_threshold: # 板块均涨 > 3%
                if leader_pct > 5.0: # 龙头 > 5%
                    rally_signals.append((sector, avg_pct, leader_code))
                    
            current_stats[sector] = {
                'avg_pct': avg_pct,
                'leader_name': leader_name,
                'leader_code': leader_code,
                'leader_pct': leader_pct
            }

        # 归一化风险分 (简单累加，最大 1.0)
        self._risk_level = min(risk_score, 1.0)
        
        return {
            "risk_level": self._risk_level,
            "pullback_alerts": pullback_alerts,
            "rally_signals": rally_signals,
            "sector_stats": current_stats
        }

    def get_leader_pullback(self, sector_name: str) -> dict:
        """获取指定板块龙头回撤信息"""
        # 需在 update 中保存状态
        # 暂未持久化所有板块的回撤信息，仅在 alert 中返回
        # 简单的实现: 
        return None 
