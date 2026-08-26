import re
import pandas as pd
import numpy as np
from logger_utils import LoggerFactory
from typing import Optional, Any, Dict, Union

class PandasQueryEngine:
    """
    高级 Pandas 查询引擎工具 (V11-PRECISION)
    支持：
    - 精准解构：仅针对全行引号包裹的行执行隐式字符串合并，保护函数内部引号
    - 赋值容忍：自动剥离 assignment (=) 干扰
    - 深度组合：支持 (源码块) and (普通表达式) 混合模式
    - 备注裁剪：自动抑制中文标签/备注
    """
    
    def __init__(self, logger=None):
        self.logger = logger or LoggerFactory.getLogger("PandasQueryEngine")
        self.last_error = ""

    def set_logger(self, logger):
        self.logger = logger

    @staticmethod
    def _parse_placeholder_items(content: str) -> Optional[list[str]]:
        """解析占位符内容: 支持范围 {1-5}, {1..5}, 步长 {1-10:2}, 倒序 {5-1}, 列表 {5,10,20}"""
        content = content.strip()
        if not content: return None
        
        # 1. 范围与步长匹配: {start-end} 或 {start-end:step} 或 {start..end} 或 {start~end}
        m_range = re.match(r'^(-?\d+)\s*(?:[\-~]|\.\.)\s*(-?\d+)(?:\s*[:]\s*(-?\d+))?$', content)
        if m_range:
            start = int(m_range.group(1))
            end = int(m_range.group(2))
            step_group = m_range.group(3)
            step = int(step_group) if step_group else (1 if start <= end else -1)
            if step == 0: step = 1
            if start <= end:
                if step < 0: step = abs(step)
                nums = list(range(start, end + 1, step))
            else:
                if step > 0: step = -step
                nums = list(range(start, end - 1, step))
            return [str(x) for x in nums]
        
        # 2. 列表匹配: {val1,val2,val3}
        if ',' in content:
            items = [x.strip() for x in content.split(',') if x.strip()]
            if items: return items
            
        return None

    @classmethod
    def _expand_logical_blocks(cls, query_str: str) -> str:
        """解析并优先展开嵌套的 {or: ...} 与 {and: ...} 显式逻辑块"""
        if not query_str or '{' not in query_str: return query_str

        pattern_start = re.compile(r'\{\s*(or|and)\s*:', re.IGNORECASE)
        res_str = query_str
        
        while True:
            match = pattern_start.search(res_str)
            if not match: break
                
            start_idx = match.start()
            op = match.group(1).lower()
            colon_idx = match.end()
            
            # 向后进行 {} 大括号深度平衡扫描
            depth = 1
            end_idx = -1
            for i in range(start_idx + 1, len(res_str)):
                char = res_str[i]
                if char == '{': depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            
            if end_idx == -1: break
                
            inner_content = res_str[colon_idx:end_idx].strip()
            expanded_inner = cls._expand_simple_placeholders(inner_content, default_op=op)
            res_str = res_str[:start_idx] + expanded_inner + res_str[end_idx+1:]
            
        return res_str

    @classmethod
    def _expand_simple_placeholders(cls, clause: str, default_op: str = 'and') -> str:
        """对单个条件片段中的简单 {} 占位符进行自适应展开与组合"""
        clause_str = clause.strip()
        if not clause_str or '{' not in clause_str: return clause
        
        op = default_op
        m_op = re.match(r'^\{\s*(or|and)\s*:\s*(.*?)\s*\}$', clause_str, re.IGNORECASE)
        if m_op:
            op = m_op.group(1).lower()
            clause_str = m_op.group(2).strip()

        pattern = r'\{([^{}]+)\}'
        matches = list(re.finditer(pattern, clause_str))
        if not matches: return clause

        parsed_placeholders = []
        for m in matches:
            p_text = m.group(1)
            items = cls._parse_placeholder_items(p_text)
            if items is not None:
                parsed_placeholders.append((m.start(), m.end(), items))
            else:
                return clause

        if not parsed_placeholders: return clause

        item_lists = [p[2] for p in parsed_placeholders]
        lengths = [len(l) for l in item_lists]
        max_len = max(lengths)
        
        if all(l == max_len or l == 1 for l in lengths):
            count = max_len
            combined_series = []
            for i in range(count):
                cur_vals = [l[i if len(l) == count else 0] for l in item_lists]
                combined_series.append(cur_vals)
        else:
            import itertools
            combined_series = list(itertools.product(*item_lists))

        expanded_clauses = []
        for combination in combined_series:
            temp_clause = clause_str
            for (start, end, _), val in zip(reversed(parsed_placeholders), reversed(combination)):
                temp_clause = temp_clause[:start] + str(val) + temp_clause[end:]
            expanded_clauses.append(temp_clause)

        if not expanded_clauses: return clause
        if len(expanded_clauses) == 1: return expanded_clauses[0]

        join_str = f" {op} "
        return f"({join_str.join(expanded_clauses)})"

    def _expand_special_syntax(self, query_str: str) -> str:
        """自适应展开表达式中的重复与区间语法，例如: lastp{1-5}d > ma60{1-5}d 与 {or: per{1-3}d > 3.0}"""
        if not query_str or '{' not in query_str: return query_str
        
        # 1. 优先解构并替换所有 {or: ...} / {and: ...} 逻辑块
        expanded_blocks = self._expand_logical_blocks(query_str)
        if '{' not in expanded_blocks: return expanded_blocks

        # 2. 对剩余按逻辑分隔符(and, or, 括号)拆分后的 token 块提取包含 {} 的子句并独立展开
        tokens = re.split(r'(\b(?:and|or)\b|[\(\)\#\n])', expanded_blocks, flags=re.IGNORECASE)
        new_tokens = []
        for i, token in enumerate(tokens):
            if '{' in token and '}' in token:
                expanded = self._expand_simple_placeholders(token)
                if expanded.startswith('(') and new_tokens and not new_tokens[-1].endswith(' ') and not new_tokens[-1].endswith('('):
                    expanded = ' ' + expanded
                if expanded.endswith(')') and i + 1 < len(tokens) and not tokens[i+1].startswith(' ') and not tokens[i+1].startswith(')'):
                    expanded = expanded + ' '
                new_tokens.append(expanded)
            else:
                new_tokens.append(token)
        return "".join(new_tokens)


    @staticmethod
    def split_sub_conditions(expr: str) -> list[str]:
        if not expr: return []
        def _get_top_level_parts(s: str, delimiters: list[str]) -> list[str]:
            depths, d = [], 0
            for char in s:
                if char == '(': depths.append(d); d += 1
                elif char == ')': d -= 1; depths.append(d)
                else: depths.append(d)
            pattern = r'\b(' + '|'.join(delimiters) + r')\b'
            parts, last_idx = [], 0
            for match in re.finditer(pattern, s, re.IGNORECASE):
                start = match.start()
                if start < len(depths) and depths[start] == 0:
                    parts.append(s[last_idx:start].strip())
                    last_idx = match.end()
            parts.append(s[last_idx:].strip())
            return [p for p in parts if p]
        and_parts = _get_top_level_parts(expr, ['and'])
        final_parts = []
        for p in and_parts:
            curr = p
            modified = False
            while curr.startswith('(') and curr.endswith(')'):
                inner = curr[1:-1].strip()
                if PandasQueryEngine._is_balanced(inner):
                    curr = inner
                    modified = True
                else: break
            if modified:
                or_branches = _get_top_level_parts(curr, ['or'])
                if len(or_branches) > 1: final_parts.extend(or_branches)
                else: final_parts.append(p)
            else: final_parts.append(p)
        return [item for item in final_parts if item]

    @staticmethod
    def _is_balanced(s: str) -> bool:
        d = 0
        for char in s:
            if char == '(': d += 1
            elif char == ')': d -= 1
            if d < 0: return False
        return d == 0

    @staticmethod
    def _greatest(*args):
        if not args: return None
        try:
            res = np.maximum.reduce(args)
            for a in args:
                if isinstance(a, pd.Series): return pd.Series(res, index=a.index, name=a.name)
            return res
        except Exception:
            try: return pd.concat(args, axis=1).max(axis=1)
            except Exception: return None

    @staticmethod
    def _least(*args):
        if not args: return None
        try:
            res = np.minimum.reduce(args)
            for a in args:
                if isinstance(a, pd.Series): return pd.Series(res, index=a.index, name=a.name)
            return res
        except Exception:
            try: return pd.concat(args, axis=1).min(axis=1)
            except Exception: return None

    def _prepare_context(self, df: pd.DataFrame) -> Dict[str, Any]:
        ctx = {
            'df': df, 'pd': pd, 'np': np, 'result': None, 'signal': None,
            'GREATEST': self._greatest, 'LEAST': self._least, 'ABS': np.abs,
            'MAX': self._greatest, 'MIN': self._least,
            'greatest': self._greatest, 'least': self._least,
            'max': self._greatest, 'min': self._least, 'abs': np.abs
        }
        col_map = {
            'lastp0d': ['close', 'trade', 'now', 'lastp', 'lastp0d'],
            'lastp1d': ['lastp1d', 'lastp'], 'lastp2d': ['lastp2d'],
            'close': ['close', 'trade', 'now', 'lastp', 'lastp0d'],
            'open': ['open', 'lasto0d'],
            'now': ['now', 'trade', 'close', 'lastp0d'],
            'percent': ['perd', 'per1d', 'perc1d', 'percent', 'pct', 'per0d', 'perc0d'],
            'pct': ['perd', 'per1d', 'perc1d', 'pct', 'percent', 'per0d', 'perc0d'],
            'per0d': ['per0d', 'perc0d', 'percent', 'pct', 'perd'],
            'volume': ['lvol', 'vol', 'volume', 'lastv0d'],
            'lastv0d': ['lvol', 'vol', 'volume', 'lastv0d'],
            'lastv1d': ['lastv1d', 'lastv', 'lvol'], 'lastv2d': ['lastv2d'],
            'upper0d': ['upper', 'upper0d'], 'upper1d': ['upper1', 'upper1d'], 'upper2d': ['upper2', 'upper2d'],
            'lower0d': ['lower', 'lower0d'], 'lower1d': ['lower1', 'lower1d'], 'lower2d': ['lower2', 'lower2d'],
            'macd0d': ['macd', 'macd0d'], 'dif0d': ['macddif', 'dif', 'dif0d'], 'dea0d': ['macddea', 'dea', 'dea0d'],
            'macd': ['macd', 'macdlast1'],
            'dif': ['macddif', 'dif'], 'dea': ['macddea', 'dea'],
            'k': ['kdj_k', 'k', 'k0d'], 'd': ['kdj_d', 'd', 'd0d'], 'j': ['kdj_j', 'j', 'j0d'],
            'k0d': ['kdj_k', 'k', 'k0d'], 'd0d': ['kdj_d', 'd', 'd0d'], 'j0d': ['kdj_j', 'j', 'j0d'],
            'ma5d': ['ma5d', 'ma5', 'ma50d'], 'ma5': ['ma5d', 'ma5', 'ma50d'],
            'ma10d': ['ma10d', 'ma10', 'ma100d'], 'ma10': ['ma10d', 'ma10', 'ma100d'],
            'ma20d': ['ma20d', 'ma20', 'ma200d'], 'ma20': ['ma20d', 'ma20', 'ma200d'],
            'ma30d': ['ma30d', 'ma30', 'ma300d'], 'ma30': ['ma30d', 'ma30', 'ma300d'],
            'ma60d': ['ma60d', 'ma60', 'ma600d'], 'ma60': ['ma60d', 'ma60', 'ma600d'],
            'ma120d': ['ma120d', 'ma120', 'ma1200d'], 'ma120': ['ma120d', 'ma120', 'ma1200d'],
            'ma250d': ['ma250d', 'ma250', 'ma2500d'], 'ma250': ['ma250d', 'ma250', 'ma2500d'],
            'lastdu': ['lastdu4', 'lastdu1', 'lastdu'], 'lastld': ['lastld4', 'lastl1d', 'lastld1', 'lastld'],
            'resist': ['upper', 'high4', 'max5', 'resist'], 'support': ['lower', 'low4', 'min5', 'support'],
            'green': ['gren', 'green'], 'red': ['red'],
            # ===== 扩展趋势与结构定位指标安全映射 =====
            'ch_upper': ['ch_upper', 'channel_upper', 'ch_up'],
            'ch_mid': ['ch_mid', 'channel_mid', 'ch_middle'],
            'ch_lower': ['ch_lower', 'channel_lower', 'ch_dn'],
            'ch_slope': ['ch_slope', 'channel_slope'],
            'ch_slope_deg': ['ch_slope_deg', 'slope_deg', 'slope_angle'],
            'ch_pos': ['ch_pos', 'channel_pos', 'ch_pct'],
            'ch_dir': ['ch_dir', 'channel_dir'],
            'ch_width': ['ch_width', 'channel_width'],
            'fib_high': ['fib_high', 'fib_top'],
            'fib_low': ['fib_low', 'fib_bottom'],
            'fib_19': ['fib_19', 'fib19'],
            'fib_38': ['fib_38', 'fib38'],
            'fib_50': ['fib_50', 'fib50', 'fib_mid'],
            'fib_61': ['fib_61', 'fib61'],
            'fib_80': ['fib_80', 'fib80'],
            'trend_dir': ['trend_dir', 'trend_direction'],
            'sig_bottom': ['sig_bottom', 'bottom_signal'],
            'sig_top': ['sig_top', 'top_signal'],
            'sig_launch': ['sig_launch', 'launch_signal'],
            'sig_escape': ['sig_escape', 'escape_signal'],
            'sig_start': ['sig_start', 'start_signal'],
            'sk_val': ['sk_val'], 'sd_val': ['sd_val'], 'rsi6': ['rsi6'],
            'ch_anchor_high_price': ['ch_anchor_high_price', 'ch_high_price', 'ch_high_val'],
            'ch_anchor_low_price': ['ch_anchor_low_price', 'ch_low_price', 'ch_low_val'],
            'ch_tc2': ['ch_tc2', 'tc2', 'high_bars_ago'],
            'ch_bc2': ['ch_bc2', 'bc2', 'low_bars_ago'],
            'ch_nod': ['ch_nod', 'nod', 'extrema_bars'],
            'ch_pattern': ['ch_pattern', 'trend_pattern', 'channel_pattern'],
            'ch_supp_price': ['ch_supp_price', 'supp_price', 'support_price', 'ch_supp', 'supp', '支撑价', '支撑位'],
            'ch_supp_slope': ['ch_supp_slope', 'supp_slope', 'support_slope', '支撑斜率'],
            'ch_supp_slope_deg': ['ch_supp_slope_deg', 'supp_slope_deg', 'supp_deg', '支撑角度', '支撑倾角'],
            'ch_supp_pos': ['ch_supp_pos', 'supp_pos', 'supp_bias', 'ch_supp_bias', '支撑偏离', '支撑位置'],
            'ch_supp_days': ['ch_supp_days', 'supp_days', '支撑天数'],
            'reversal_line': ['reversal_line', 'reversal_price', 'rev_price', '反转价', '翻转价'],
            'ch_res_price': ['ch_res_price', 'res_price', 'resist_price', '压力价', '阻力价'],
            'ch_res_slope': ['ch_res_slope', 'res_slope', 'resist_slope', '压力斜率'],
            'ch_res_slope_deg': ['ch_res_slope_deg', 'res_slope_deg', 'resist_deg', '压力角度'],
            'strong_structure_score': ['strong_structure_score', 'structure_score', 'score'],
            'SWL': ['SWL', 'swl', 'ma5d'], 'SWS': ['SWS', 'sws', 'ma10d'],
            'hmax': ['hmax', 'lasth1d', 'high'], 'nlow': ['nlow', 'lastl1d', 'low'],
            'vwap_price': ['vwap_price', 'vwap', 'nclose', 'avg_price'],
            'nclose': ['nclose', 'vwap_price', 'vwap', 'lastp1d', 'close'], 'win': ['win', 'win_score'],
            'Rank': ['Rank', 'rank'], 'high4': ['high4', 'lasth1d', 'high'],
            'low4': ['low4', 'lastl1d', 'low'], 'td_sell': ['td_sell'], 'td_buy': ['td_buy'],
            'Trends': ['Trends', 'TrendS', 'trends', 'trend_score', 'trend_s', 'Trends_d'],
            'Trends_d': ['Trends_d', 'Trends', 'TrendS', 'trends', 'trend_score'],
            # ===== 扩展 5 日连续 VWAP 机构成本线同义词映射 =====
            'vwap_cum_2d': ['vwap_cum_2d', 'cum_vwap_2d', 'vwap_2d_cum', 'm_vwap2d', 'vwap2d_cum', 'vwap_cum_2d_d'],
            'vwap_cum_3d': ['vwap_cum_3d', 'cum_vwap_3d', 'vwap_3d_cum', 'm_vwap3d', 'vwap3d_cum', 'vwap_cum_3d_d'],
            'vwap_cum_4d': ['vwap_cum_4d', 'cum_vwap_4d', 'vwap_4d_cum', 'm_vwap4d', 'vwap4d_cum', 'vwap_cum_4d_d'],
            'vwap_cum_5d': ['vwap_cum_5d', 'cum_vwap_5d', 'vwap_5d_cum', 'm_vwap5d', 'vwap5d_cum', 'vwap_cum_5d_d', 'vwap_cum_5d_3d'],
            'vwap_cum_10d': ['vwap_cum_10d', 'cum_vwap_10d', 'vwap_10d_cum', 'm_vwap10d', 'vwap10d_cum'],
            'last_vwap_cum_2d': ['last_vwap_cum_2d', 'last_cum_vwap_2d', 'last_vwap_cum_2d_d'],
            'last_vwap_cum_3d': ['last_vwap_cum_3d', 'last_cum_vwap_3d', 'last_vwap_cum_3d_d'],
            'last_vwap': ['last_vwap', 'last_vwap1d', 'last_nclose', 'last_nclose1d'],
            'last_nclose1d': ['last_nclose1d', 'last_nclose', 'last_vwap1d', 'last_vwap', 'last_nclose1d_d', 'last_nclose1d_2d'],
            'last_nclose2d': ['last_nclose2d', 'last_vwap2d', 'nclose2d'],
            'last_nclose3d': ['last_nclose3d', 'last_vwap3d', 'nclose3d', 'last_nclose3d_d'],
            'last_nclose4d': ['last_nclose4d', 'last_vwap4d', 'nclose4d'],
            'last_nclose5d': ['last_nclose5d', 'last_vwap5d', 'nclose5d'],
            'nclose1d': ['nclose1d', 'last_nclose1d', 'last_vwap1d'],
            'nclose2d': ['nclose2d', 'last_nclose2d', 'last_vwap2d'],
            'nclose3d': ['nclose3d', 'last_nclose3d', 'last_vwap3d'],
            'nclose4d': ['nclose4d', 'last_nclose4d', 'last_vwap4d'],
            'nclose5d': ['nclose5d', 'last_nclose5d', 'last_vwap5d'],
        }
        for i in range(0, 10):
            last_macd_idx = min(max(i, 1), 6)
            col_map[f'macd{i}d'] = [f'macdlast{i}', f'macd{i}d', f'macd{i}', f'macdlast{last_macd_idx}']
            col_map[f'macd{i}'] = [f'macdlast{i}', f'macd{i}d', f'macd{i}', f'macdlast{last_macd_idx}']
            col_map[f'dif{i}d'] = [f'macddif{i}', f'dif{i}d', f'dif{i}', f'macddif{last_macd_idx}']
            col_map[f'dif{i}'] = [f'macddif{i}', f'dif{i}d', f'dif{i}', f'macddif{last_macd_idx}']
            col_map[f'dea{i}d'] = [f'macddea{i}', f'dea{i}d', f'dea{i}', f'macddea{last_macd_idx}']
            col_map[f'dea{i}'] = [f'macddea{i}', f'dea{i}d', f'dea{i}', f'macddea{last_macd_idx}']
            col_map[f'upper{i}d'] = [f'upper{i}', f'upper{i}d']
            col_map[f'upper{i}'] = [f'upper{i}', f'upper{i}d']
            col_map[f'lower{i}d'] = [f'lower{i}', f'lower{i}d']
            col_map[f'lower{i}'] = [f'lower{i}', f'lower{i}d']
            col_map[f'per{i}d'] = [f'per{i}d', f'perc{i}d', f'percent{i}d', 'percent', 'pct']
            col_map[f'perc{i}d'] = [f'perc{i}d', f'per{i}d', f'percent{i}d', 'percent', 'pct']
            col_map[f'ma5{i}d'] = [f'ma5{i}d', f'ma5_{i}d', f'ma5_d{i}d', 'ma51d', 'ma5d']
            col_map[f'ma10{i}d'] = [f'ma10{i}d', f'ma10_{i}d', f'ma10_d{i}d', 'ma101d', 'ma10d']
            col_map[f'ma20{i}d'] = [f'ma20{i}d', f'ma20_{i}d', f'ma20_d{i}d', 'ma201d', 'ma20d']
            col_map[f'ma60{i}d'] = [f'ma60{i}d', f'ma60_{i}d', f'ma60_d{i}d', 'ma601d', 'ma60d']
            col_map[f'ma120{i}d'] = [f'ma120{i}d', f'ma120_{i}d', f'ma120_d{i}d', 'ma1201d', 'ma120d']
            col_map[f'ma250{i}d'] = [f'ma250{i}d', f'ma250_{i}d', f'ma250_d{i}d', 'ma2501d', 'ma250d']
            col_map[f'ma60_{i}d'] = [f'ma60{i}d', f'ma60_{i}d', f'ma60_d{i}d', 'ma601d', 'ma60d']
            col_map[f'ma60_d{i}d'] = [f'ma60{i}d', f'ma60_{i}d', f'ma60_d{i}d', 'ma601d', 'ma60d']
            col_map[f'lastv{i}d'] = [f'lastv{i}d', 'lastv1d', 'lvol', 'vol', 'volume']
            col_map[f'lastp{i}d'] = [f'lastp{i}d', 'lastp1d', 'close']
            col_map[f'lasth{i}d'] = [f'lasth{i}d', 'lasth1d', 'high']
            col_map[f'lastl{i}d'] = [f'lastl{i}d', 'lastl1d', 'low']
            col_map[f'lasto{i}d'] = [f'lasto{i}d', 'lasto1d', 'open']
        # 构建全量指标同义词等价组 (Transitive Closure of Metric Synonyms)
        alias_groups = []
        for alias, targets in col_map.items():
            t_list = [targets] if isinstance(targets, str) else targets
            group = {alias} | set(t_list)
            merged = False
            for existing in alias_groups:
                if existing & group:
                    existing.update(group)
                    merged = True
                    break
            if not merged:
                alias_groups.append(group)
        metric_to_group = {}
        for g in alias_groups:
            for m in g:
                metric_to_group[m] = g

        supported_periods = ('d', '2d', '3d', 'w', 'm', '45d', '3M')
        is_multi = isinstance(df.columns, pd.MultiIndex)

        # 1. 优先物理列与 MultiIndex 直接挂载
        if is_multi:
            for (period, metric) in df.columns:
                alias1 = f"{period}_{metric}"
                alias2 = f"{metric}_{period}"
                if alias1 not in ctx: ctx[alias1] = df[(period, metric)]
                if alias2 not in ctx: ctx[alias2] = df[(period, metric)]
        else:
            for col in df.columns:
                if isinstance(col, str) and col not in ctx:
                    ctx[col] = df[col]

        # 2. 基于 df.columns 中真实拥有的所有列名，自适应交叉展开同义词及多周期后缀
        if not is_multi:
            for col in list(df.columns):
                if not isinstance(col, str): continue
                period_suf = ""
                base_m = col
                if col not in metric_to_group:
                    for p in supported_periods:
                        if col.endswith(f"_{p}"):
                            period_suf = f"_{p}"
                            base_m = col[:-len(p)-1]
                            break
                
                equiv_group = metric_to_group.get(base_m, {base_m})
                for eq in equiv_group:
                    if period_suf:
                        eq_with_suf = f"{eq}{period_suf}"
                        if eq_with_suf not in ctx or ctx[eq_with_suf] is None:
                            ctx[eq_with_suf] = df[col]
                        if period_suf == "_d" and (eq not in ctx or ctx[eq] is None):
                            ctx[eq] = df[col]
                    else:
                        if eq not in ctx or ctx[eq] is None:
                            ctx[eq] = df[col]

        # 动态标记与缺省指标兜底补全 (防止 exe 环境由于缺列抛出 NameError 导致 Hit 归零)
        default_fallbacks = {
            'strong_structure_score': 50.0,
            'win': 1, 'Rank': 100, 'td_sell': 0, 'td_buy': 0,
            'SWL': ctx.get('ma5d'), 'SWS': ctx.get('ma10d'),
            'hmax': ctx.get('high'), 'nlow': ctx.get('low'),
            'nclose': ctx.get('close'), 'high4': ctx.get('high'),
            'low4': ctx.get('low'), 'dff2': 0.0, 'dff3': 0.0,
            'Trends': 60.0, 'Trends_d': 60.0,
            'vwap_cum_2d': ctx.get('nclose'), 'vwap_cum_3d': ctx.get('nclose'),
            'vwap_cum_4d': ctx.get('nclose'), 'vwap_cum_5d': ctx.get('nclose'),
            'vwap_cum_10d': ctx.get('nclose'),
            'vwap_cum_2d_d': ctx.get('nclose'), 'vwap_cum_3d_d': ctx.get('nclose'),
            'vwap_cum_4d_d': ctx.get('nclose'), 'vwap_cum_5d_d': ctx.get('nclose'),
            'vwap_cum_5d_3d': ctx.get('nclose'),
            'last_vwap_cum_2d': ctx.get('close'), 'last_vwap_cum_3d': ctx.get('close'),
            'last_vwap_cum_2d_d': ctx.get('close'), 'last_vwap_cum_3d_d': ctx.get('close'),
            'last_nclose1d': ctx.get('close'), 'last_nclose2d': ctx.get('close'),
            'last_nclose3d': ctx.get('close'), 'last_nclose4d': ctx.get('close'),
            'last_nclose1d_d': ctx.get('close'), 'last_nclose1d_2d': ctx.get('close'),
            'last_nclose3d_d': ctx.get('close'),
        }
        for fb_key, fb_val in default_fallbacks.items():
            if fb_key not in ctx or ctx.get(fb_key) is None:
                if isinstance(fb_val, pd.Series):
                    ctx[fb_key] = fb_val
                elif fb_val is not None:
                    ctx[fb_key] = pd.Series(fb_val, index=df.index)
                else:
                    ctx[fb_key] = pd.Series(0, index=df.index)

        # 📌 _d 后缀别名兜底：将策略中 close_d / open_d / high_d 等写法自动映射至实际列
        # 消除二次过滤条件中因带 _d 后缀书写习惯导致的 NameError / Fallback 告警
        _d_suffix_map = {
            'close_d':   ctx.get('close'),
            'open_d':    ctx.get('open'),
            'high_d':    ctx.get('high'),
            'low_d':     ctx.get('low'),
            'volume_d':  ctx.get('volume'),
            'percent_d': ctx.get('percent'),
            'trade_d':   ctx.get('trade') if ctx.get('trade') is not None else ctx.get('close'),
            'ratio_d':   ctx.get('ratio'),
            'amount_d':  ctx.get('amount'),
            'turnover_d':ctx.get('turnover'),
            'price_d':   ctx.get('trade') if ctx.get('trade') is not None else ctx.get('close'),
            'Trends_d':  ctx.get('Trends') if ctx.get('Trends') is not None else 60.0,
            'vwap_cum_2d_d': ctx.get('vwap_cum_2d'),
            'vwap_cum_3d_d': ctx.get('vwap_cum_3d'),
            'vwap_cum_4d_d': ctx.get('vwap_cum_4d'),
            'vwap_cum_5d_d': ctx.get('vwap_cum_5d'),
            'last_vwap_cum_2d_d': ctx.get('last_vwap_cum_2d'),
            'last_vwap_cum_3d_d': ctx.get('last_vwap_cum_3d'),
            'last_nclose1d_d': ctx.get('last_nclose1d'),
            'last_nclose3d_d': ctx.get('last_nclose3d'),
            'lastp0d_d': ctx.get('lastp0d') if ctx.get('lastp0d') is not None else ctx.get('close'),
            'lastp1d_d': ctx.get('lastp1d') if ctx.get('lastp1d') is not None else ctx.get('close'),
            'lastp2d_d': ctx.get('lastp2d'),
            'ma5d_d':    ctx.get('ma5d'),
            'ma51d_d':   ctx.get('ma51d') if ctx.get('ma51d') is not None else ctx.get('ma5d'),
            'ma10d_d':   ctx.get('ma10d'),
            'ma20d_d':   ctx.get('ma20d'),
            'ma60d_d':   ctx.get('ma60d'),
            'lastv0d_d': ctx.get('lastv0d') if ctx.get('lastv0d') is not None else ctx.get('volume'),
            'lastv1d_d': ctx.get('lastv1d'),
            'lastv2d_d': ctx.get('lastv2d'),
            'lasth1d_d': ctx.get('lasth1d') if ctx.get('lasth1d') is not None else ctx.get('high'),
            'lastl1d_d': ctx.get('lastl1d') if ctx.get('lastl1d') is not None else ctx.get('low'),
            'lasto1d_d': ctx.get('lasto1d') if ctx.get('lasto1d') is not None else ctx.get('open'),
        }
        for alias, src in _d_suffix_map.items():
            if alias not in ctx or ctx.get(alias) is None:
                if isinstance(src, pd.Series):
                    ctx[alias] = src
                else:
                    ctx[alias] = pd.Series(0, index=df.index)

        if 'green' not in ctx or ctx.get('green') is None:
            if is_multi:
                p0 = df.columns.levels[0][0]
                if (p0, 'close') in df.columns and (p0, 'open') in df.columns:
                    ctx['green'] = df[(p0, 'close')] < df[(p0, 'open')]
            elif 'close' in df.columns and 'open' in df.columns: ctx['green'] = df['close'] < df['open']
        if 'red' not in ctx or ctx.get('red') is None:
            if is_multi:
                p0 = df.columns.levels[0][0]
                if (p0, 'close') in df.columns and (p0, 'open') in df.columns:
                    ctx['red'] = df[(p0, 'close')] > df[(p0, 'open')]
            elif 'close' in df.columns and 'open' in df.columns: ctx['red'] = df['close'] > df['open']
        return ctx

    def _preprocess_query(self, query_str: str) -> str:
        """精准预处理：智能脱敏多行/单行混杂的 # 注释，保护函数内部合法的引号，解构隐式字符串连接，并自动展开自适应重复语法"""
        raw_input = query_str.strip()
        if not raw_input: return ""

        # Step 1: 逐段与逐行智能脱敏 (深度支持多行脚本及被压扁为单行时混入的 # 注释)
        def _clean_segment(s_raw: str) -> str:
            s = s_raw.strip()
            if not s:
                return ''
                
            # 1. 物理移除行首赋值: var = (注意排除双等号 ==)
            s = re.sub(r'^\s*[a-zA-Z_]\w*\s*=(?!=)\s*', '', s)

            # 2. 保护单双引号内的字符串常量（如 '芯片', "PCB"）
            quotes_map = {}
            def _quote_repl(m):
                key = f'__QUOTE_{len(quotes_map)}__'
                quotes_map[key] = m.group(0)
                return key
                
            s_protected = re.sub(r'(?:\'[^\']*\'|\"[^\"]*\")', _quote_repl, s)
            
            # 3. 移除包含中文或说明性内容的括号 (如 (拒绝空头排列), (A: abs 振幅剧烈试盘 OR B: 极度缩量小步垫高成本))
            while True:
                s_new = re.sub(r'\([^\(\)]*[\u4e00-\u9fa5][^\(\)]*\)', ' ', s_protected)
                if s_new == s_protected:
                    break
                s_protected = s_new
                
            # 4. 剥离 # 开头的注释：跳过注释中文说明，精准提取随后的代码起点
            def _strip_comment_chunk(match):
                chunk = match.group(0)
                # 严格代码起点特征 (必须为操作符、逻辑占位符或带有操作符的变量，杜绝中文句子中提及变量名误判):
                code_start_pattern = r'(?<![\w\u4e00-\u9fa5])(?:\b(?:and|or|not)\b\s+(?:\(*\s*\{\s*(?:or|and)\s*:|\(*\s*[a-zA-Z_]\w*|\(*\s*[\d\.\-])|\(*\s*\{\s*(?:or|and)\s*:|\(*\s*[a-zA-Z_]\w*\s*(?:>=|<=|==|!=|>|<|\*|\/|\+|\-|\.|\bin\b|\bis\b))'
                m = re.search(code_start_pattern, chunk[1:], flags=re.IGNORECASE)
                if m:
                    code_cand = chunk[1 + m.start():].strip()
                    # 若提取内容仍然以中文字符结尾或主要是中文，说明纯为描述文字，直接丢弃
                    if not re.search(r'[\u4e00-\u9fa5]$', code_cand):
                        return ' ' + code_cand
                return ' '
                
            s_cleaned = re.sub(r'#[^#]*', _strip_comment_chunk, s_protected)
            
            # 5. 还原被保护的引号字符串
            for k, v in quotes_map.items():
                s_cleaned = s_cleaned.replace(k, v)
                
            return s_cleaned.strip()

        processed_lines = []
        for line in raw_input.splitlines():
            cleaned_line = _clean_segment(line)
            if not cleaned_line:
                continue
                
            # 精准识别 Implicit Concatenation 特征
            if re.match(r'^\s*[\(\s]*(["\']).*\1[\)\s]*$', cleaned_line):
                quotes = re.findall(r'(["\'])(.*?)\1', cleaned_line)
                if quotes:
                    inner_merged = "".join([q[1] for q in quotes])
                    shell = re.sub(r'(["\']).*?\1', ' {} ', cleaned_line)
                    reconstructed = shell.format(inner_merged)
                    processed_lines.append(reconstructed)
                else:
                    processed_lines.append(cleaned_line)
            else:
                processed_lines.append(cleaned_line)
        
        # Step 2: 空间转换与备注过滤
        res = " ".join(processed_lines).replace('df_all', 'df').strip()
        res = re.sub(r'^\s*\(([\u4e00-\u9fa5\-]+)\)\s*(?=\()', '', res) 
        res = re.sub(r'^\s*[\u4e00-\u9fa5\-]+\s*(?=\()', '', res)

        # Step 3: 自动展开自适应重复与区间语法 (例如: lastp{1-5}d > ma60{1-5}d 与 {OR: ...})
        if '{' in res and '}' in res:
            res = self._expand_special_syntax(res)
        
        # Step 4: 规范化 .str.contains 字符串搜索
        if '.str.contains(' in res:
            def _contains_repl(match):
                quote = match.group(1)
                content = match.group(2)
                has_regex_chars = any(char in content for char in ['|', '^', '$', '*', '+', '?'])
                regex_val = "True" if has_regex_chars else "False"
                return f'.str.contains({quote}{content}{quote}, case=False, regex={regex_val}, na=False)'
            res = re.sub(
                r'\.str\.contains\((["\'])(.*?)\1\s*\)',
                _contains_repl,
                res
            )
        
        return res.strip()

    def execute(self, df: pd.DataFrame, query_str: str) -> pd.DataFrame:
        """执行引擎：回归稳定链"""
        self.last_error = ""
        if df is None or df.empty or not query_str.strip(): return df
        cleaned_expr = self._preprocess_query(query_str)
        if not cleaned_expr: return df
        
        # 快捷拦截：平衡括号判定
        if not self._is_balanced(cleaned_expr):
            self.last_error = "Parentheses are not balanced"
            return df

        context = self._prepare_context(df)
        
        is_explicit = any(l.strip().startswith(('result =', 'signal =', 'import ', 'from ')) for l in query_str.splitlines())
        has_sql = bool(re.search(r'\b(GREATEST|LEAST|ABS|MAX|MIN)\b', cleaned_expr, re.IGNORECASE))
        
        try:
            if is_explicit:
                exec(re.sub(r'\bdf_all\b', 'df', query_str), context)
                return self._extract_result(df, context)

            local_scope = context.copy()
            mentioned = set(re.findall(r'\b[a-zA-Z_]\w*\b', cleaned_expr))
            for col in df.columns:
                if str(col) in mentioned: local_scope[str(col)] = df[col]
            
            # 使用 @ 前缀保护 Python 关键字与内置函数冲突
            pd_expr = cleaned_expr
            py_restricted = {'open', 'id', 'type', 'dir', 'sum', 'abs', 'max', 'min', 'in', 'is', 'from', 'import', 'as', 'with'}
            for var in py_restricted:
                if var in mentioned and var in local_scope and f"@{var}" not in pd_expr:
                    pd_expr = re.sub(r'\b' + var + r'\b', f'@{var}', pd_expr)

            try:
                if not has_sql:
                    try: return df.query(pd_expr, local_dict=local_scope, engine='python')
                    except Exception: pass
                # pd.eval 向量化执行
                res = pd.eval(cleaned_expr, engine='python', local_dict=local_scope)
                return self._wrap_result(df, res)
            except Exception:
                exec_expr = self._to_bit_logical_expr(cleaned_expr)
                res = pd.eval(exec_expr, engine='python', local_dict=local_scope)
                return self._wrap_result(df, res)
        except Exception as e:
            try:
                # 完善 Fallback: 自动使用 _to_bit_logical_expr 安全转换 and/or 为 &/|
                vec_expr = self._to_bit_logical_expr(cleaned_expr)
                res_series = eval(vec_expr, globals(), context)
                self.last_error = ""
                return self._wrap_result(df, res_series)
            except Exception as ex_fb:
                self.last_error = f"Query [{query_str}] parsing error: {ex_fb}"
                self.logger.warning(f"[QueryEngine] Fallback 回退执行告警: {ex_fb} | 触发Query原句: '{query_str}'")
                return df

    @staticmethod
    def _to_bit_logical_expr(expr_str: str) -> str:
        """安全将 and/or 替换为 &/|，同时保护二元比较运算两端的优先级，彻底防范 float | float 语法告警"""
        if not expr_str: return expr_str
        tokens = re.split(r'(\b(?:and|or)\b)', expr_str, flags=re.IGNORECASE)
        new_tokens = []
        for t in tokens:
            t_lower = t.lower()
            if t_lower == 'and':
                new_tokens.append('&')
            elif t_lower == 'or':
                new_tokens.append('|')
            else:
                sub = t.strip()
                if re.search(r'[><!]=?|==', sub) and not (sub.startswith('(') and sub.endswith(')')):
                    new_tokens.append(f"({sub})")
                else:
                    new_tokens.append(t)
        return "".join(new_tokens)

    def _wrap_result(self, df: pd.DataFrame, res: Any) -> pd.DataFrame:
        if res is None: return df
        if isinstance(res, pd.Series) and len(res) == len(df):
            if res.dtype == bool: return df[res]
        if isinstance(res, pd.DataFrame): return res
        if isinstance(res, (bool, np.bool_)): return df if res else df.iloc[:0]
        return df

    def _extract_result(self, df: pd.DataFrame, context: Dict) -> pd.DataFrame:
        if context.get('result') is not None: return context['result']
        if context.get('signal') is not None and isinstance(context['signal'], pd.Series):
            return df[context['signal']]
        return df

query_engine = PandasQueryEngine()
