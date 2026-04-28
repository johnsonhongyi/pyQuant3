import re
import pandas as pd
import numpy as np
import logging
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
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.last_error = ""

    def set_logger(self, logger: logging.Logger):
        self.logger = logger

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
            'lastp0d': ['close', 'trade', 'now', 'lastp0d'], 'lastp1d': ['lastp1d', 'lastp'], 'lastp2d': ['lastp2d'],
            'close': ['close', 'trade', 'now', 'lastp0d'], 'now': ['now', 'trade', 'close', 'lastp0d'],
            'percent': ['percent', 'pct', 'per1d'], 'pct': ['pct', 'percent', 'per1d'],
            'lastdu': ['lastdu4', 'lastdu1', 'lastdu'], 'lastld': ['lastld4', 'lastl1d', 'lastld1', 'lastld'],
            'resist': ['upper', 'high4', 'max5', 'resist'], 'support': ['lower', 'low4', 'min5', 'support'],
            'green': ['gren', 'green'], 'red': ['red']
        }
        is_multi = isinstance(df.columns, pd.MultiIndex)
        if is_multi:
            for (period, metric) in df.columns:
                alias = f"{period}_{metric}"
                if alias not in ctx: ctx[alias] = df[(period, metric)]
        for alias, targets in col_map.items():
            if not is_multi and alias in df.columns and (alias not in ctx or ctx[alias] is None):
                ctx[alias] = df[alias]
                continue
            for target in ([targets] if isinstance(targets, str) else targets):
                if is_multi:
                    found = False
                    for period in df.columns.levels[0]:
                        if (period, target) in df.columns:
                            ctx[alias] = df[(period, target)]
                            found = True; break
                    if found: break
                else:
                    if target in df.columns: ctx[alias] = df[target]; break

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
        """精准预处理：解构隐式字符串连接的同时，保护函数内部合法的引号"""
        raw_input = query_str.strip()
        if not raw_input: return ""

        # Step 1: 逐行扫描与智能脱敏
        processed_lines = []
        for line in raw_input.splitlines():
            # 1. 物理移除行首赋值: var = 
            line_no_assign = re.sub(r'^\s*[a-zA-Z_]\w*\s*=\s*', '', line)
            
            # 2. 剥离行内注释
            code = line_no_assign.split('#')[0].rstrip()
            if not code.strip(): continue
            
            # 3. [KEY FIX] 精准识别 Implicit Concatenation 特征
            # 如果全行被引号包裹（允许首尾有括号），则执行解构
            # 模式：^ (可选括号) "内容" "内容" (可选括号) $
            if re.match(r'^\s*[\(\s]*(["\']).*\1[\)\s]*$', code):
                # 提取所有引号内的字面量
                quotes = re.findall(r'(["\'])(.*?)\1', code)
                if quotes:
                    # 将引号内的内容取出，并保留引号外的括号
                    inner_merged = "".join([q[1] for q in quotes])
                    # 恢复该行原本的括号结构 (简单处理：提取 code 中所有非引号内容)
                    shell = re.sub(r'(["\']).*?\1', ' {} ', code)
                    reconstructed = shell.format(inner_merged)
                    processed_lines.append(reconstructed)
                else:
                    processed_lines.append(code)
            else:
                # 含有函数调用（如 contains("X")）或原始逻辑的行，保持原样（保护引号）
                processed_lines.append(code)
        
        # Step 2: 空间转换与备注过滤
        res = " ".join(processed_lines).replace('df_all', 'df').strip()
        # 情况 A: (中文字符标签) (逻辑) -> (逻辑)
        res = re.sub(r'^\s*\(([\u4e00-\u9fa5\-]+)\)\s*(?=\()', '', res) 
        # 情况 B: 中文字符标签 (逻辑) -> (逻辑)
        res = re.sub(r'^\s*[\u4e00-\u9fa5\-]+\s*(?=\()', '', res)
        
        return res.strip()

    def execute(self, df: pd.DataFrame, query_str: str) -> pd.DataFrame:
        """执行引擎：回归稳定链"""
        self.last_error = ""
        if df is None or df.empty or not query_str.strip(): return df
        cleaned_expr = self._preprocess_query(query_str)
        if not cleaned_expr: return df
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
            
            # 使用 @ 前缀保护关键字
            pd_expr = cleaned_expr
            py_restricted = {'open', 'id', 'type', 'dir', 'sum', 'abs', 'max', 'min'}
            for var in py_restricted:
                if var in mentioned and var in local_scope:
                    pd_expr = re.sub(r'\b' + var + r'\b', f'@{var}', pd_expr)

            try:
                if not has_sql:
                    try: return df.query(pd_expr, local_dict=local_scope, engine='python')
                    except: pass
                # pd.eval 向量化执行
                res = pd.eval(cleaned_expr, engine='python', local_dict=local_scope)
                return self._wrap_result(df, res)
            except:
                exec_expr = re.sub(r'\band\b', '&', cleaned_expr, flags=re.IGNORECASE)
                exec_expr = re.sub(r'\bor\b', '|', exec_expr, flags=re.IGNORECASE)
                res = pd.eval(exec_expr, engine='python', local_dict=local_scope)
                return self._wrap_result(df, res)
        except Exception as e:
            self.last_error = str(e)
            self.logger.warning(f"Query Error: {e}")
            try:
                exec(re.sub(r'\bdf_all\b', 'df', query_str), context)
                return self._extract_result(df, context)
            except: return df

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
