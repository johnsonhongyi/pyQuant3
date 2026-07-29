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
            # ===== 趋势通道指标 (calc_trend_channel) =====
            'ch_upper': ['ch_upper', 'channel_upper', 'ch_up'],
            'ch_mid': ['ch_mid', 'channel_mid', 'ch_middle'],
            'ch_lower': ['ch_lower', 'channel_lower', 'ch_dn'],
            'ch_slope': ['ch_slope', 'channel_slope'],
            'ch_slope_deg': ['ch_slope_deg', 'slope_deg', 'slope_angle'],
            'ch_pos': ['ch_pos', 'channel_pos', 'ch_pct'],
            'ch_dir': ['ch_dir', 'channel_dir'],
            'ch_width': ['ch_width', 'channel_width'],
            # ===== Fibonacci 动态支撑阻力 =====
            'fib_high': ['fib_high', 'fib_top'],
            'fib_low': ['fib_low', 'fib_bottom'],
            'fib_19': ['fib_19', 'fib19'],
            'fib_38': ['fib_38', 'fib38'],
            'fib_50': ['fib_50', 'fib50', 'fib_mid'],
            'fib_61': ['fib_61', 'fib61'],
            'fib_80': ['fib_80', 'fib80'],
            # ===== 趋势信号 =====
            'trend_dir': ['trend_dir', 'trend_direction'],
            'sig_bottom': ['sig_bottom', 'bottom_signal'],
            'sig_top': ['sig_top', 'top_signal'],
            'sig_launch': ['sig_launch', 'launch_signal'],
            'sig_escape': ['sig_escape', 'escape_signal'],
            'sig_start': ['sig_start', 'start_signal'],
            'sk_val': ['sk_val'], 'sd_val': ['sd_val'], 'rsi6': ['rsi6'],
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

        # 动态标记补齐
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
        """精准预处理：解构隐式字符串连接的同时，保护函数内部合法的引号，并自动展开自适应重复语法"""
        raw_input = query_str.strip()
        if not raw_input: return ""

        # Step 0: 自动展开自适应重复与区间语法 (例如: lastp{1-5}d > ma60{1-5}d)
        if '{' in raw_input and '}' in raw_input:
            raw_input = self._expand_special_syntax(raw_input)

        # Step 1: 逐行扫描与智能脱敏
        processed_lines = []
        for line in raw_input.splitlines():
            # 1. 物理移除行首赋值: var = (注意排除双等号 ==)
            line_no_assign = re.sub(r'^\s*[a-zA-Z_]\w*\s*=(?!=)\s*', '', line)
            
            # 2. 剥离行内注释
            code = line_no_assign.split('#')[0].rstrip()
            if not code.strip(): continue
            
            # 3. [KEY FIX] 精准识别 Implicit Concatenation 特征
            if re.match(r'^\s*[\(\s]*(["\']).*\1[\)\s]*$', code):
                quotes = re.findall(r'(["\'])(.*?)\1', code)
                if quotes:
                    inner_merged = "".join([q[1] for q in quotes])
                    shell = re.sub(r'(["\']).*?\1', ' {} ', code)
                    reconstructed = shell.format(inner_merged)
                    processed_lines.append(reconstructed)
                else:
                    processed_lines.append(code)
            else:
                processed_lines.append(code)
        
        # Step 2: 空间转换与备注过滤
        res = " ".join(processed_lines).replace('df_all', 'df').strip()
        res = re.sub(r'^\s*\(([\u4e00-\u9fa5\-]+)\)\s*(?=\()', '', res) 
        res = re.sub(r'^\s*[\u4e00-\u9fa5\-]+\s*(?=\()', '', res)
        
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
                exec_expr = re.sub(r'\band\b', '&', cleaned_expr, flags=re.IGNORECASE)
                exec_expr = re.sub(r'\bor\b', '|', exec_expr, flags=re.IGNORECASE)
                res = pd.eval(exec_expr, engine='python', local_dict=local_scope)
                return self._wrap_result(df, res)
        except Exception as e:
            self.last_error = f"Query [{query_str}] parsing error: {e}"
            self.logger.warning(f"[QueryEngine] 表达式解析告警: {e} | 触发Query原句: '{query_str}' | 转换后Expr: '{cleaned_expr}'")
            try:
                # 完善 Fallback: 自动转换 and/or 为 &/| 避免 Series 条件歧义报错
                vec_expr = re.sub(r'\band\b', '&', cleaned_expr, flags=re.IGNORECASE)
                vec_expr = re.sub(r'\bor\b', '|', vec_expr, flags=re.IGNORECASE)
                res_series = eval(vec_expr, globals(), context)
                return self._wrap_result(df, res_series)
            except Exception as ex_fb:
                self.logger.warning(f"[QueryEngine] Fallback 回退执行告警: {ex_fb} | 触发Query原句: '{query_str}'")
                return df

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
