import os
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime

from strategy_interface import IStrategy, StrategyConfig, StrategyMode
from signal_types import SignalPoint, SignalType, SignalSource
from signal_message_queue import SignalMessageQueue, SignalMessage

logger = logging.getLogger(__name__)

class StrongConsolidationStrategy(IStrategy):
    """
    强势整理突破策略 (301348模式)
    
    逻辑:
    1. 寻找最近一次中阳突破布林上轨 (Breakout Day)
    2. 检查自Breakout Day以来, 收盘价从未有效跌破 Breakout Day 的收盘价 (Strong Consolidation)
    3. 检查最近2日是否呈现攻击形态 (每日新高, 量能配合)
    """
    
    def __init__(self, config: Optional[StrategyConfig] = None, executor: Optional[Any] = None):
        super().__init__(config)
        self.executor = executor # 🚀 [NEW] 持有外部注入的线程池
        if not self._config.description:
            self._config.description = "捕捉强势整理后再次突破的个股 (如301348模式)"
        
        # 内部使用 SignalMessageQueue 推送信号
        try:
            from signal_message_queue import SignalMessageQueue
            self.queue = SignalMessageQueue()
        except:
            self.queue = None

    def evaluate_historical(self, code: str, day_df: pd.DataFrame) -> List[SignalPoint]:
        # 本策略主要用于实时监控和即时选股, 历史回测暂返回空或仅作为验证
        # 为简化, 这里暂不实现全历史回测逻辑, 仅对最后一天进行评估
        points = []
        if day_df is None or len(day_df) < 20: 
            return points
            
        # 模拟实时评估最后一行
        # last_row = day_df.iloc[-1].to_dict()
        # snapshot = {
        #     'trade': last_row['close'],
        #     'high': last_row['high'],
        #     'low': last_row['low'],
        #     'open': last_row['open'],
        #     'volume': last_row['volume']
        # }
        
        # 需要传入完整DF进行计算
        sig = self._detect_pattern(code, day_df)
        if sig:
            points.append(sig)
            
            # --- 增强: 实时推送逻辑 (支持手动切换股票触发) ---
            # 如果信号是"今天"(最后一行)触发的, 推送到消息队列
            try:
                # 简单判断: 信号时间是数据最后一行的时间
                if str(sig.timestamp) == str(day_df.index[-1]) and self.queue:
                    # 避免重复推送? SignalMessageQueue未去重, 但UI显示有限制
                    # 构造消息
                    msg = SignalMessage(
                        priority=20, 
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        code=code,
                        name=str(day_df.iloc[-1].get('name', '')), 
                        signal_type='CONSOLIDATION',
                        source='STRATEGY',
                        reason=sig.reason,
                        score=90
                    )
                    self.queue.push(msg)
            except Exception as e:
                logger.error(f"Failed to push signal in evaluate_historical: {e}")
            
        return points

    def evaluate_realtime(self, code: str, row_data: Dict[str, Any], 
                          snapshot: Dict[str, Any]) -> Optional[SignalPoint]:
        """实时评估"""
        # 注意: 实时评估通常只拿到当前tick, 需要历史数据配合
        # 此处假设调用方会提供足够的历史数据上下文, 或者我们在内部维护/获取
        # 实际上 StrategyController 调用 evaluate_realtime 时通常是 Tick 级
        # 对于形态策略, 我们更倾向于在 on_dataframe_updated (分钟/日线更新) 时触发
        # 但遵循接口, 我们可以做简单的判读, 或者依赖外部传入的 day_df (如果接口支持)
        
        # 修正: 标准接口 evaluate_realtime 只有 row_data/snapshot
        # 严格来说无法做基于历史形态的复杂判断. 
        # 本策略更适合作为 "选股器" 运行, 或在 StrategyController 获取到新K线时运行.
        # 
        # 暂时返回 None, 逻辑主要实现在 evaluate_historical (被周期性调用) 
        # 或通过外部独立调用检测.
        return None
        
    def detect_and_push(self, code: str, df: pd.DataFrame) -> bool:
        """
        主动检测并推送信号 (供外部周期性调用)
        """
        sig_point = self._detect_pattern(code, df)
        if sig_point:
            # 推送到消息队列
            if self.queue:
                msg = SignalMessage(
                    priority=20, # 较高优先级
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    code=code,
                    name=str(df.iloc[-1].get('name', '')), # 尝试获取名称
                    signal_type='CONSOLIDATION',
                    source='STRATEGY',
                    reason=sig_point.reason,
                    score=90
                )
                self.queue.push(msg)
                return True
        return False

    def execute_scan(self, df_all: pd.DataFrame, resample: str = 'd', parallel: bool = True) -> List[Dict[str, Any]]:
        """
        全市场批量扫描符合强势整理模式的个股
        :param df_all: 如果是实时数据，通常是 indexed by code 的 DataFrame；如果是历史数据，可能是 MultiIndex (date, code)
        :param resample: 周期
        :param parallel: 是否开启并行加速
        :return: 扫描结果列表
        """
        results = []
        # 注意: 这里的 df_all 假设包含了一定历史深度的K线数据 (MultiIndex 或者按代码分片的列表)
        # 如果 df_all 仅是单行快照，则无法进行形态识别
        
        # 为了演示和接口对齐，我们假设 df_all 是按代码分片的字典，或者我们可以按代码分组处理
        if not isinstance(df_all, pd.DataFrame) or df_all.empty:
            return []

        # 获取所有代码
        if 'code' in df_all.columns:
            codes = df_all['code'].unique()
        elif isinstance(df_all.index, pd.MultiIndex):
            codes = df_all.index.get_level_values('code').unique()
        else:
            # 假设 index 就是 code (TDX 常见格式)
            codes = df_all.index.unique()

        logger.info(f"🚀 Starting Strong Consolidation scan for {len(codes)} stocks (resample={resample}, parallel={parallel})...")

        if parallel and len(codes) > 10:
            # 🚀 [OPTIMIZATION] 优先使用注入的全局线程池
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            # 如果没有注入 executor，则使用本地池 (降级)
            if self.executor is None:
                logger.warning(f"[StrongConsolidation] No shared executor found. Falling back to local pool.")
                local_pool = ThreadPoolExecutor(max_workers=int(os.cpu_count()/2) or 4)
            else:
                local_pool = self.executor

            try:
                # 预切片
                def _get_sub_df(c):
                    if isinstance(df_all.index, pd.MultiIndex):
                        if 'code' in df_all.index.names:
                            return df_all.xs(c, level='code')
                        else:
                            return df_all.loc[(slice(None), c)]
                    else:
                        if 'code' in df_all.columns:
                            return df_all[df_all['code'] == c]
                        else:
                            return df_all[df_all.index == c]

                futures = {local_pool.submit(self._detect_pattern, str(c), _get_sub_df(c)): c for c in codes}
                for future in as_completed(futures):
                    code = futures[future]
                    try:
                        sig = future.result()
                        if sig:
                            sub_df = _get_sub_df(code)
                            results.append({
                                'code': sig.code,
                                'name': str(sub_df.get('name', '')) if not isinstance(sub_df.index, pd.MultiIndex) else str(sub_df['name'].iloc[-1]),
                                'score': 90,
                                'resample': resample,
                                'reason': sig.reason,
                                'price': sig.price,
                                'timestamp': sig.timestamp
                            })
                    except Exception as e:
                        logger.error(f"Scan failed for {code}: {e}")
            finally:
                # 🛑 只有本地创建的池子才需要关闭，共享池禁止关闭
                if self.executor is None and 'local_pool' in locals():
                    local_pool.shutdown(wait=False)
        else:
            for code in codes:
                try:
                    # 简单分片逻辑
                    if isinstance(df_all.index, pd.MultiIndex):
                        if 'code' in df_all.index.names:
                            sub_df = df_all.xs(code, level='code')
                        else:
                            sub_df = df_all.loc[(slice(None), code)]
                    else:
                        if 'code' in df_all.columns:
                            sub_df = df_all[df_all['code'] == code]
                        else:
                            sub_df = df_all[df_all.index == code]
                        
                    sig = self._detect_pattern(str(code), sub_df)
                    if sig:
                        results.append({
                            'code': sig.code,
                            'name': str(sub_df.get('name', '')) if not isinstance(sub_df.index, pd.MultiIndex) else str(sub_df['name'].iloc[-1]),
                            'score': 90,
                            'resample': resample,
                            'reason': sig.reason,
                            'price': sig.price,
                            'timestamp': sig.timestamp
                        })
                except Exception as e:
                    logger.debug(f"Scan skip for {code}: {e}")

        logger.info(f"✅ Scan completed. Found {len(results)} matches.")
        return results

    def _detect_pattern(self, code: str, df: pd.DataFrame) -> Optional[SignalPoint]:
        """
        核心形态检测逻辑 (优化版)
        结合 启动强度(Breakout) + 支撑验证(MA Support) + 蓄势形态(Doji/Volume)
        """
        if df is None or len(df) < 30: return None
        
        try:
            # 1. 确保必要指标计算 (优先使用已有的)
            df = df.copy()
            close_s = pd.to_numeric(df['close'], errors='coerce')
            
            if 'ma5' not in df.columns: df['ma5'] = close_s.rolling(5).mean()
            if 'ma10' not in df.columns: df['ma10'] = close_s.rolling(10).mean()
            if 'ma20' not in df.columns: df['ma20'] = close_s.rolling(20).mean()
            if 'upper' not in df.columns:
                ma20 = close_s.rolling(20).mean()
                std20 = close_s.rolling(20).std()
                df['upper'] = ma20 + 2 * std20
            
            vol_s = pd.to_numeric(df['volume'], errors='coerce')
            df['vol_ma5'] = vol_s.rolling(5).mean()
            df['vol_ma20'] = vol_s.rolling(20).mean()

            # 2. 寻找最近的启动日 (Breakout Day) - 过去3到20天内
            # 启动特征: 突破布林上轨, 且不是放天量的高开低走
            recent_search_count = min(len(df), 30)
            recent_search = df.iloc[-recent_search_count:-2].copy() # 搜索范围: 3天前到最近30天内
            if recent_search.empty: 
                logger.debug(f"{code}: No recent search data (min 30 days)")
                return None

            # 启动特征: 突破布林上轨, 且收阳, 涨幅>3%
            recent_search['is_breakout'] = (recent_search['close'] > recent_search['upper']) & \
                                           (recent_search['close'] > recent_search['open']) & \
                                           (recent_search['percent'] > 3)
            
            # 如果有 high4, max, hmax 指标，增加突破判定
            if 'high4' in recent_search.columns:
                recent_search['is_breakout'] |= (recent_search['high'] > recent_search['high4'])
            if 'max' in recent_search.columns:
                recent_search['is_breakout'] |= (recent_search['high'] > recent_search['max'])
            
            # 过滤 breakout
            recent_search = recent_search[recent_search['is_breakout']]
            if recent_search.empty: 
                logger.debug(f"{code}: No breakout found in recent search")
                return None

            # 获取最近的一个有效启动日
            breakout_row = recent_search.iloc[-1]
            breakout_date = breakout_row.name
            breakout_close = float(breakout_row['close'])
            breakout_vol = float(breakout_row['volume'])

            # 3. 验证自启动以来的整理质量 (Consolidation)
            consolidation_df = df.loc[breakout_date:].iloc[1:]
            if len(consolidation_df) < 2: 
                logger.debug(f"{code}: Consolidation period too short (<2 days)")
                return None
            
            # A. 空间支撑: 收盘价不应大幅跌破启动日收盘价 (允许3%浮动)
            min_close = pd.to_numeric(consolidation_df['close'], errors='coerce').min()
            if min_close < breakout_close * 0.97:
                logger.debug(f"{code}: Price drop too deep ({min_close} < {breakout_close * 0.97})")
                return None
            
            # B. 趋势性验证: "每日新高" 或 "Win连阳"
            # 检查是否有 win 指标 (cct 处理后的)
            if 'win' in consolidation_df.columns:
                recent_win = consolidation_df['win'].iloc[-3:]
                is_win_trend = (recent_win > 0).all() # 最近3日温和上涨
            else:
                # 手动判定: 最近3日高点没有大幅回落, 且有尝试创高
                is_win_trend = (float(df.iloc[-1]['high']) > float(df.iloc[-3]['high']))

            # C. 均线支撑: 最近1-2日低点应触及或接近 MA10/MA20
            last_row = df.iloc[-1]
            ma10_val = float(last_row['ma10'])
            ma20_val = float(last_row['ma20'])
            ma5_val = float(last_row['ma5'])
            curr_low = float(last_row['low'])
            curr_close = float(last_row['close'])
            
            # 支撑判定: 低点接近10/20日线 (2.5%范围内), 且收盘站在5日线上方
            is_ma_supported = (curr_low < ma10_val * 1.025) or (curr_low < ma20_val * 1.025)
            # 必须站稳5日线
            if curr_close < ma5_val * 0.995: 
                logger.debug(f"{code}: Close below MA5 ({curr_close} < {ma5_val * 0.995})")
                return None
            
            if not is_ma_supported:
                # 如果没触及大均线, 检查是否是极强势横盘 (一直在布林上轨附近)
                if not (curr_close > last_row['upper'] * 0.98):
                    logger.debug(f"{code}: Not touching MA support and not super strong ({curr_close} < {last_row['upper'] * 0.98})")
                    return None

            # 4. 蓄势形态判定 (Setup Pattern)
            # A. 缩量: 当前成交量显著低于启动量 (成交量萎缩是重点)
            vol_curr = float(last_row['volume'])
            vol_ma5 = float(last_row['vol_ma5'])
            
            # 成交量必须小于启动日的 80% 且小于5日均量
            is_shrinking = (vol_curr < breakout_vol * 0.8) and (vol_curr < vol_ma5 * 1.2)
            if not is_shrinking:
                logger.debug(f"{code}: Volume not shrinking enough ({vol_curr} vs {breakout_vol*0.8})")
                return None
            
            # B. K线形态: 十字星或小阳/小阴 (整理中)
            # 实体较小 或 涨跌幅绝对值 < 2.5%
            body_abs = abs(curr_close - float(last_row['open']))
            is_small_k = (body_abs / curr_close < 0.025) or (abs(float(last_row['percent'])) < 2.5)
            
            if not (is_small_k and is_win_trend):
                logger.debug(f"{code}: K-Pattern mismatch (SmallK:{is_small_k}, WinTrend:{is_win_trend})")
                return None

            # 5. 额外过滤: 排除加速赶顶
            # 如果最近3日累计涨幅过大，可能是突破后的二波已经走完了
            recent_3_pct = consolidation_df['percent'].iloc[-3:].sum()
            if recent_3_pct > 15: 
                logger.debug(f"{code}: Accelerated too fast ({recent_3_pct} > 15)")
                return None

            return SignalPoint(
                code=code,
                signal_type=SignalType.BUY,
                timestamp=df.index[-1],
                bar_index=len(df)-1,
                price=curr_close,
                source=SignalSource.STRATEGY_ENGINE,
                reason=f"强势缩量回踩: {breakout_date if isinstance(breakout_date, str) else breakout_date.strftime('%m-%d')}启动, 现缩量触及均线支撑"
            )
        except Exception as e:
            logger.debug(f"Pattern detect error for {code}: {e}")
            return None

