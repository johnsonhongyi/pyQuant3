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

    @staticmethod
    def _greatest(*args):
        if not args: return None
        # 使用 numpy 原生规约，比 pd.concat([].max(axis=1)) 快几个数量级
        return np.maximum.reduce(args)

    @staticmethod
    def _least(*args):
        if not args: return None
        return np.minimum.reduce(args)

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
        # 别名支持：lastp0d -> close (行情系统常见别名)
        if 'lastp0d' not in df.columns and 'close' in df.columns:
            ctx['lastp0d'] = df['close']
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
            self.logger.warning(f"Query Execution Error: {e}")
            # 最后一级兜底：全文 exec
            try:
                exec(re.sub(r'\bdf_all\b', 'df', query_str), context)
                return self._extract_result(df, context)
            except Exception:
                return df

    def _wrap_result(self, df: pd.DataFrame, res: Any) -> pd.DataFrame:
        """统一包装计算结果"""
        if isinstance(res, pd.Series) and len(res) == len(df):
            if res.dtype == bool:
                return df[res]
        if isinstance(res, pd.DataFrame):
            return res
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
