import re
import pandas as pd
import numpy as np
import logging
from typing import Optional, Any, Dict, Union

class PandasQueryEngine:
    """
    高级 Pandas 查询引擎工具
    支持：
    - SQL 风格函数映射 (greatest, least, abs, max, min)
    - 多级智能执行链 (df.query -> df.eval -> pd.eval -> exec)
    - 脚本模式 (支持 result = ... 或 signal = ... 赋值)
    - 智能列注入 (仅注入表达式中提到的列)
    - 鲁棒的预处理 (剥离注释、处理三引号赋值)
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.last_error = ""

    def set_logger(self, logger: logging.Logger):
        """支持主程序注入一致的 logger"""
        self.logger = logger

    @staticmethod
    def _greatest(*args):
        if not args: return None
        # 使用 numpy 原生规约
        try:
            res = np.maximum.reduce(args)
            # 如果输入中有 Series，确保返回 Series 以保持索引对齐，防止 "cannot evaluate scalar only bool ops"
            for a in args:
                if isinstance(a, pd.Series):
                    return pd.Series(res, index=a.index, name=a.name)
            return res
        except Exception:
            # 兜底方案：使用 pandas 缓慢但兼容性强的方法
            try:
                return pd.concat(args, axis=1).max(axis=1)
            except Exception:
                return None

    @staticmethod
    def _least(*args):
        if not args: return None
        try:
            res = np.minimum.reduce(args)
            for a in args:
                if isinstance(a, pd.Series):
                    return pd.Series(res, index=a.index, name=a.name)
            return res
        except Exception:
            try:
                return pd.concat(args, axis=1).min(axis=1)
            except Exception:
                return None

    def _prepare_context(self, df: pd.DataFrame) -> Dict[str, Any]:
        """构建基础执行上下文"""
        ctx = {
            'df': df,
            'pd': pd,
            'np': np,
            'result': None,
            'signal': None,
            'GREATEST': self._greatest,
            'LEAST': self._least,
            'ABS': np.abs,
            'MAX': self._greatest,
            'MIN': self._least,
            'greatest': self._greatest,
            'least': self._least,
            'max': self._greatest,
            'min': self._least,
            'abs': np.abs
        }
        # 别名映射与智能注入
        col_map = {
            'lastp0d': ['close', 'lastp0d'],
            'lastp1d': ['lastp1d', 'lastp'],
            'lastp2d': ['lastp2d'],
            'lastdu': ['lastdu4', 'lastdu1', 'lastdu'],
            'lastld': ['lastld4', 'lastl1d', 'lastld1', 'lastld'],
            'resist': ['upper', 'high4', 'max5', 'resist'],
            'support': ['lower', 'low4', 'min5', 'support'],
            'green': ['gren', 'green'],
            'red': ['red']
        }
        
        # 处理 MultiIndex 情况 (多周期联合)
        is_multi = isinstance(df.columns, pd.MultiIndex)
        
        if is_multi:
            # 自动解构二级索引：Level 0 为 Period, Level 1 为 Metric
            # 生成 D_close, W_ma5 等变量
            for (period, metric) in df.columns:
                alias = f"{period}_{metric}"
                if alias not in ctx:
                    ctx[alias] = df[(period, metric)]
            self.logger.info(f" [QueryEngine] MultiIndex detected. Injected {len(df.columns)} period-prefixed aliases.")

        for alias, targets in col_map.items():
            # 1. 优先尝试直接匹配 (如果是 MultiIndex，则不直接映射基础别名，除非主表已对齐)
            if not is_multi and alias in df.columns and (alias not in ctx or ctx[alias] is None):
                ctx[alias] = df[alias]
                self.logger.debug(f" [QueryEngine] Column '{alias}' injected directly.")
                continue
            
            # 2. 尝试从目标列表中找到第一个存在的列
            target_list = [targets] if isinstance(targets, str) else targets
            for target in target_list:
                if is_multi:
                    # MultiIndex 下优先找第一个周期中的目标列
                    found = False
                    for period in df.columns.levels[0]:
                        if (period, target) in df.columns:
                            ctx[alias] = df[(period, target)]
                            self.logger.debug(f" [QueryEngine] MultiIndex Alias: '{alias}' -> ('{period}', '{target}')")
                            found = True
                            break
                    if found: break
                else:
                    if target in df.columns:
                        ctx[alias] = df[target]
                        self.logger.debug(f" [QueryEngine] Alias Map: '{alias}' -> '{target}'")
                        break
        
        # 3. 动态计算特殊标记 (green/red)
        if 'green' not in ctx or ctx.get('green') is None:
            # MultiIndex 下寻找第一个周期的 close/open
            if is_multi:
                p0 = df.columns.levels[0][0]
                if (p0, 'close') in df.columns and (p0, 'open') in df.columns:
                    ctx['green'] = df[(p0, 'close')] < df[(p0, 'open')]
            elif 'close' in df.columns and 'open' in df.columns:
                ctx['green'] = df['close'] < df['open']
        
        if 'red' not in ctx or ctx.get('red') is None:
            if is_multi:
                p0 = df.columns.levels[0][0]
                if (p0, 'close') in df.columns and (p0, 'open') in df.columns:
                    ctx['red'] = df[(p0, 'close')] > df[(p0, 'open')]
            elif 'close' in df.columns and 'open' in df.columns:
                ctx['red'] = df['close'] > df['open']
            
        return ctx
            
        # 兜底注入：如果 query 中提到了某些常见别名但没映射上，且 df 中有类似列，尝试自动映射
        # (这部分通常由 execute 中的 mentioned_words 处理，但这里可以做显式映射)
        
        return ctx

    def _preprocess_query(self, query_str: str) -> str:
        """剥离注释并提取核心表达式"""
        raw_input = query_str.strip()
        
        # 1. 提取赋值右侧内容 (例如 final_query = """ ... """)
        triple_match = re.search(r'^\s*\w+\s*=\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', raw_input, re.DOTALL | re.MULTILINE)
        assign_match = re.search(r'^\s*(\w+)\s*=\s*(.*)', raw_input, re.DOTALL | re.MULTILINE)
        
        process_content = raw_input
        if triple_match:
            process_content = triple_match.group(1)
        elif assign_match and assign_match.group(1).lower() not in ('result', 'signal', 'import', 'from'):
            process_content = assign_match.group(2)

        # 2. 清洗注释与换行
        lines = []
        for line in process_content.splitlines():
            code_part = line.split('#')[0].strip()
            if code_part:
                lines.append(code_part)
        
        return " ".join(lines).replace('df_all', 'df')

    def execute(self, df: pd.DataFrame, query_str: str) -> pd.DataFrame:
        """执行查询的核心入口"""
        self.last_error = ""
        if df is None or df.empty or not query_str.strip():
            return df

        cleaned_expr = self._preprocess_query(query_str)
        context = self._prepare_context(df)
        
        # 探测是否为显式脚本
        lines = query_str.strip().splitlines()
        is_explicit_script = any(line.strip().startswith(('result =', 'signal =', 'import ', 'from ')) for line in lines)
        has_sql_func = bool(re.search(r'\b(GREATEST|LEAST|ABS|MAX|MIN)\b', cleaned_expr, re.IGNORECASE))
        
        try:
            if is_explicit_script:
                exec(re.sub(r'\bdf_all\b', 'df', query_str), context)
                return self._extract_result(df, context)

            # 智能尝试链：df.query -> df.eval -> pd.eval (Stage 3)
            pd_expr = re.sub(r'\bdf\b', '@df', cleaned_expr)
            
            # 阶段 1 & 2 (仅在无复杂 SQL 函数时尝试)
            if not has_sql_func:
                try:
                    return df.query(pd_expr, local_dict=context, engine='python')
                except Exception:
                    try:
                        res = df.eval(pd_expr, engine='python', local_dict=context)
                        if isinstance(res, (pd.Series, pd.DataFrame)):
                            return self._wrap_result(df, res)
                    except Exception:
                        pass
            
            # 终极阶段：注入列名运行向量化计算
            local_scope = context.copy()
            # 动态检测并注入提及的列 (优化内存占用)
            mentioned_words = set(re.findall(r'\b[a-zA-Z_]\w*\b', cleaned_expr))
            for col in df.columns:
                if str(col) in mentioned_words:
                    local_scope[str(col)] = df[col]
            
            # 转换为位运算符并执行
            exec_expr = re.sub(r'\band\b', '&', cleaned_expr)
            exec_expr = re.sub(r'\bor\b', '|', exec_expr)
            engine = 'python' if has_sql_func else 'numexpr'
            
            res = pd.eval(exec_expr, engine=engine, local_dict=local_scope)
            return self._wrap_result(df, res)

        except Exception as e:
            self.last_error = str(e)
            self.logger.warning(f"Query Execution Error: {e} | Query: {query_str}")
            # 最后一级兜底：全文 exec
            try:
                exec(re.sub(r'\bdf_all\b', 'df', query_str), context)
                return self._extract_result(df, context)
            except Exception:
                return df

    def _wrap_result(self, df: pd.DataFrame, res: Any) -> pd.DataFrame:
        """统一包装计算结果"""
        if res is None:
            return df
        if isinstance(res, pd.Series) and len(res) == len(df):
            if res.dtype == bool:
                return df[res]
        if isinstance(res, pd.DataFrame):
            return res
        # 如果返回的是 scalar bool，且为 False，返回空 DataFrame
        if isinstance(res, (bool, np.bool_)):
            return df if res else df.iloc[:0]
        return df

    def _extract_result(self, df: pd.DataFrame, context: Dict) -> pd.DataFrame:
        """从上下文中提取变量"""
        if context.get('result') is not None:
            return context['result']
        if context.get('signal') is not None and isinstance(context['signal'], pd.Series):
            return df[context['signal']]
        return df

# 单例或快速访问实例
query_engine = PandasQueryEngine()
