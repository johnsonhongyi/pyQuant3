# -*- coding:utf-8 -*-
"""
Market Pulse Logic Engine
Aggregates data, generates action plans, and handles persistence.
File: market_pulse_engine.py
"""
from JohnsonUtil import LoggerFactory
from datetime import datetime
import json
import numpy as np
import market_pulse_db
from JohnsonUtil import commonTips as cct
from JSONData.sina_data import Sina

class DailyPulseEngine:
    def __init__(self, stock_selector=None):
        self.selector = stock_selector
        self.logger = LoggerFactory.getLogger("DailyPulseEngine")

    def analyze_opportunity(self, stock_data, snapshot):
        """
        Generate actionable advice based on technical indicators.
        :param stock_data: dict from monitored_stocks
        :param snapshot: dict containing 'win', 'score', 'ma5d', etc.
        :return: str Action Plan
        """
        plans = []
        score = snapshot.get('score', 0)
        win = snapshot.get('win', 0)
        reason = str(snapshot.get('reason', ''))
        
        # 0. Data Extraction
        price = snapshot.get('create_price', 0)
        upper = snapshot.get('upper', 0)
        ma5 = snapshot.get('ma5d', 0)
        
        # 1. Main Wave & Acceleration Logic (User Defined)
        # Definition: Continuous Positive (连阳) + Highs > Prev Highs + Lows > Prev Lows
        is_main_wave = "主升" in reason or "连阳" in reason or win >= 3
        is_accelerating = "加速" in reason or (upper > 0 and price > upper)
        
        if is_accelerating:
             plans.append("【加速结构】: 股价站上Upper线，进入主升急涨段。")
             plans.append("操作建议: 只要不破昨日收盘价或5日线，严禁下车。")
        elif is_main_wave:
             plans.append(f"【主升浪{win}连阳】: 结构完整(新高无新低)。")
             plans.append("操作建议: 趋势未变，缩量回调至分时均线/5日线是低吸机会。")
             
        # 2. Volume Logic
        if "倍量" in reason:
             plans.append("量能异动: 倍量攻击，主力资金介入明显。")

        # 3. Sector / Leader Logic
        if "龙头" in reason or score > 90:
            plans.append("板块核心: 享有高溢价，板块未退潮前缩量即买点。")
            
        # 4. Rebound / Oversold
        if "超跌" in reason:
            plans.append("超跌反弹: 短线博弈，遇阻力位(MA20/缺口)果断止盈，不恋战。")
            
        # Default Plan
        if not plans:
            if score > 80:
                plans.append("强势观察: 沿5日线趋势操作。")
            else:
                plans.append("普通关注: 等待放量突破信号。")
                
        return "\n".join(plans)

    def _get_market_breadth(self):
        """Calculate market-wide gainer/loser counts and ratio."""
        if not self.selector:
            return None
            
        df = None
        if hasattr(self.selector, 'df_all_realtime') and self.selector.df_all_realtime is not None:
             df = self.selector.df_all_realtime
        else:
             try:
                 df = self.selector.get_candidates_df() # Fallback
             except: pass
             
        if df is None or df.empty:
            return None
            
        # Filter valid percentages
        valid_df = df[df['percent'].notna()]
        up_count = int((valid_df['percent'] > 0).sum())
        down_count = int((valid_df['percent'] < 0).sum())
        flat_count = int((valid_df['percent'] == 0).sum())
        total = up_count + down_count + flat_count
        
        up_ratio = up_count / total if total > 0 else 0.5
        
        return {
            'up': up_count,
            'down': down_count,
            'flat': flat_count,
            'total': total,
            'up_ratio': round(up_ratio, 3)
        }

    def _get_index_status(self):
        """Fetch major indices status (SH, SZ, CYB)."""
        try:
            sina = Sina()
            # sh000001 (SSE), sz399001 (SZSE), sz399006 (ChiNext)
            index_codes = ['sh000001', 'sz399001', 'sz399006']
            # Sina class handles mapping internally if structured correctly
            # But let's use the explicit method to be safe
            df = sina.get_stock_code_data(index_codes)
            
            indices = []
            if df is not None and not df.empty:
                for code in index_codes:
                    if code in df.index:
                        row = df.loc[code]
                        name = row.get('name', code)
                        price = row.get('now', 0)
                        prev_close = row.get('llastp', 0)
                        pct = 0.0
                        if prev_close > 0:
                            pct = (price - prev_close) / prev_close * 100
                        indices.append({
                            'code': code,
                            'name': name,
                            'price': price,
                            'percent': round(pct, 2)
                        })
            return indices
        except Exception as e:
            self.logger.error(f"Failed to get index status: {e}")
            return []

    def generate_daily_report(self, monitored_stocks, force_date=None):
        """
        Aggregate current data into a Daily Report.
        :param monitored_stocks: self._monitored_stocks from Strategy
        :param force_date: Optional date string
        """
        today = force_date or datetime.now().strftime("%Y-%m-%d")
        
        # 1. Get Hot Sectors
        hot_sectors = []
        if self.selector:
            try:
                # [(name, avg_pct), ...]
                raw_sectors = self.selector.get_market_hotspots() 
                # Convert tuples to list of lists [name, pct] for JSON
                hot_sectors = [[s[0], round(s[1], 2)] for s in raw_sectors]
            except Exception as e:
                self.logger.error(f"Failed to get hot sectors: {e}")
        else:
            self.logger.error(f'self.selector is None')
        # 2. Analyze Stocks
        processed_stocks = []
        high_score_count = 0
        
        # Merge input monitored stocks with selector candidates if needed
        # This solves the "Empty Action Radar" issue when no live monitor is active
        combined_stocks = monitored_stocks.copy()
        if len(combined_stocks) < 10 and self.selector:
            try:
                candidates_df = self.selector.get_candidates_df()
                if candidates_df is not None and not candidates_df.empty:
                    # Filter for high quality candidates (score > 80)
                    high_quality = candidates_df[candidates_df['score'] > 80].head(30)
                    for code, row in high_quality.iterrows():
                        if code not in combined_stocks:
                            # Construct minimal data dummy
                            combined_stocks[code] = {
                                'name': row.get('name', ''),
                                'price': row.get('trade', row.get('price', 0)),
                                'create_price': 0, # Not joined yet
                                'snapshot': row.to_dict()
                            }
            except Exception as e:
                self.logger.error(f"Failed to merge candidates: {e}")

        # Get period from selector if available, default to 'd'
        current_period = 'd'
        if self.selector and hasattr(self.selector, 'resample'):
             current_period = 'd'
        if self.selector and hasattr(self.selector, 'resample'):
            current_period = self.selector.resample
            
        for code, data in combined_stocks.items():
            snapshot = data.get('snapshot', {})
            score = snapshot.get('score', 0)
            win_rate = snapshot.get('win_rate', 0)
            
            # Helper to get value from selector df (realtime) if not in snapshot
            # This ensures we get the latest 'Rank', 'topR' (Gap)
            rank = snapshot.get('Rank', 0)
            gap = snapshot.get('topR', 0)
            sector = snapshot.get('category', '')
            reason = snapshot.get('reason', '')
            
            # Additional P/L Logic
            create_price = data.get('create_price', 0)
            price = data.get('price', 0)
            if price == 0 and 'current_price' in data: # Try fallback
                 price = data.get('current_price', 0)
                 
            profit = 0.0
            if create_price > 0 and price > 0:
                profit = (price - create_price) / create_price * 100

            # Merge with Selector Data if available
            if self.selector and hasattr(self.selector, 'df_all_realtime'):
                df_all = self.selector.df_all_realtime
                if df_all is not None and not df_all.empty:
                    # [FIX] Robust Lookup with Normalization
                    # 1. Try exact match
                    rec = None
                    if code in df_all.index:
                        rec = df_all.loc[code]
                    else:
                        # 2. Try normalized (6-digit string)
                        norm_code = str(code).replace('sh', '').replace('sz', '').replace('.', '').zfill(6)
                        if norm_code in df_all.index:
                            rec = df_all.loc[norm_code]
                        else:
                            # 3. Try int
                            try:
                                int_code = int(norm_code)
                                if int_code in df_all.index:
                                    rec = df_all.loc[int_code]
                            except: pass
                    # snapshot = df_all.loc[code]   <-- Removed dangerous unconditional access
                    if rec is not None:
                        snapshot = rec
                        # Extract with priorities
                        if rank == 0: 
                             rank = rec.get('Rank', rec.get('rank', 0))
                        
                        if gap == 0: 
                             gap = rec.get('topR', rec.get('gap', 0))
                        
                        if not sector: 
                             # Try multiple keys for sector
                             sector = rec.get('category', rec.get('industry', rec.get('blockname', '')))
                        
                        if not reason:
                             reason = rec.get('reason', rec.get('user_reason', ''))

                        # Extract technicals for action plan
                        if 'ma5d' not in snapshot and 'ma5' in rec: snapshot['ma5d'] = rec['ma5']
                        if 'upper' not in snapshot and 'upper' in rec: snapshot['upper'] = rec['upper']
                        if 'win' not in snapshot and 'win' in rec: snapshot['win'] = rec['win']

                        # Update price from real-time source if snapshot has no live price
                        # This facilitates "Real-time reading" requirement
                        rt_price = rec.get('trade', rec.get('price', 0))
                        if rt_price > 0:
                             price = rt_price
                        
                        # Re-calculate profit with latest price
                        if create_price > 0:
                             profit = (price - create_price) / create_price * 100
                    win_rate = snapshot.get('sum_perc', 0)
                    score = snapshot.get('score', 0)
            # Generate Action Plan
            action_plan = self.analyze_opportunity(data, snapshot)
            
            # Status for DB (Extending with new fields)
            status = {
                'price': price,                   # Current Price
                'add_price': create_price,        # Join Price
                'profit': profit,                 # P/L %
                'win': snapshot.get('win', 0),    # 连阳
                'topR': gap,                      # Gap
                'score': score,
                'rank': rank,                     # Rank
                'period': current_period,         # Period
                'win_rate': win_rate              # Placeholder
            }
            
            stock_entry = {
                'code': code,
                'name': data.get('name', ''),
                'sector': sector,
                'reason': reason,
                'score': score,
                'action_plan': action_plan,
                'status': status
            }
            processed_stocks.append(stock_entry)
            
            if score > 85:
                high_score_count += 1

        # 3. Calculate Market Temperature
        # Heuristic: Combination of Breadth, Index Performance, and Hot Sector Sentiment
        breadth = self._get_market_breadth()
        indices = self._get_index_status()
        
        # Base from stock sentiment (max weight reduction to avoid inflation)
        # Instead of absolute count, use relative ready count
        ready_pct = (high_score_count / len(processed_stocks) * 100) if processed_stocks else 0
        sector_heat = sum([s[1] for s in hot_sectors[:5]]) / 5 if hot_sectors else 0
        
        # Base from stock sentiment (max weight reduction to avoid inflation)
        temperature, summary = self.calculate_professional_temperature(ready_pct, sector_heat, breadth, indices)
        
        if temperature > 80:
            summary = "市场情绪火热，赚钱效应极佳，主线力量强劲。"
        elif temperature > 60:
            summary = "市场温和向好，局部机会活跃，适合积极博弈。"
        elif temperature > 40:
            summary = "市场震荡分化，赚钱效应一般，控制仓位防守。"
        elif temperature > 20:
            summary = "市场持续低迷，空头占据核心，保持谨慎避险。"
        else:
            summary = "市场冰冷到极点，风险溢出显著，建议空仓观望。"
            
        summary_data = {
            'temperature': round(temperature, 1),
            'summary': summary,
            'hot_sectors': hot_sectors,
            'breadth': breadth,     # Added
            'indices': indices,      # Added
            'notes': ''
        }
        
        # 4. Save to DB
        market_pulse_db.save_daily_pulse(today, summary_data, processed_stocks)
        
        return summary_data, processed_stocks


    @staticmethod
    def calculate_professional_temperature(ready_pct, sector_heat, breadth, indices):
        """Standalone reusable temperature calculation."""
        import numpy as np
        # 3.1 Index Impact (Average of major indices)
        avg_index_pct = np.mean([idx['percent'] for idx in indices]) if indices else 0.0
        
        # 3.2 Breadth Impact
        up_ratio = breadth.get('up_ratio', 0.5) if breadth else 0.5
        
        # PROFESSIONAL FORMULA:
        # Base: (High Score Pct * 0.4) + (Sector Heat * 3) + 35
        # Adjustment: Index_Pct * 12 + (Up_Ratio - 0.5) * 60
        base_temp = (ready_pct * 0.4) + (sector_heat * 3) + 35
        correction = (avg_index_pct * 12) + (up_ratio - 0.5) * 60
        
        temperature = min(100, max(0, base_temp + correction))
        
        summary = ""
        if temperature > 80:
            summary = "市场火热"
        elif temperature > 60:
            summary = "市场活跃"
        elif temperature > 40:
            summary = "市场平淡"
        elif temperature > 20:
            summary = "市场低迷"
        else:
            summary = "市场冰点"
            
        return float(temperature), summary

    def get_history(self, date_str):
        """Retrieve historical report."""
        return market_pulse_db.get_report_by_date(date_str)

    def update_notes(self, date_str, notes):
        return market_pulse_db.update_user_notes(date_str, notes)
