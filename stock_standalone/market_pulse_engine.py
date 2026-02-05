# -*- coding:utf-8 -*-
"""
Market Pulse Logic Engine
Aggregates data, generates action plans, and handles persistence.
File: market_pulse_engine.py
"""
from JohnsonUtil import LoggerFactory
from datetime import datetime
import json
import market_pulse_db
from JohnsonUtil import commonTips as cct

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
        
        # Get period from selector if available, default to 'd'
        current_period = 'd'
        if self.selector and hasattr(self.selector, 'resample'):
             current_period = 'd'
        if self.selector and hasattr(self.selector, 'resample'):
            current_period = self.selector.resample
        for code, data in monitored_stocks.items():
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
        # Simple heuristic: Number of High Score Stocks + Hot Sectors Avg Pct
        sector_heat = sum([s[1] for s in hot_sectors[:5]]) / 5 if hot_sectors else 0
        temperature = min(100, (high_score_count * 2) + (sector_heat * 10) + 50)
        
        if temperature > 80:
            summary = "市场情绪火热，主线清晰，适合重仓参与龙头。"
        elif temperature > 60:
            summary = "市场温和向好，局部赚钱效应明显，精选前排。"
        elif temperature > 40:
            summary = "市场震荡分化，注意高低切换，防守为主。"
        else:
            summary = "市场情绪冰点，观望为主，等待新周期启动。"
            
        summary_data = {
            'temperature': round(temperature, 1),
            'summary': summary,
            'hot_sectors': hot_sectors,
            'notes': '' # User can edit later
        }
        
        # 4. Save to DB
        market_pulse_db.save_daily_pulse(today, summary_data, processed_stocks)
        
        return summary_data, processed_stocks

    def get_history(self, date_str):
        """Retrieve historical report."""
        return market_pulse_db.get_report_by_date(date_str)

    def update_notes(self, date_str, notes):
        return market_pulse_db.update_user_notes(date_str, notes)
