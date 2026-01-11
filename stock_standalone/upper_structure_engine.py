# upper_structure_auto_engine.py
# --------------------------------------------------
# 自动列名生成版 Upper Structure Engine + GUI
# --------------------------------------------------

import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import ttk

import json
import os
def load_display_columns(cfg_path='display_cols.json', key='current'):
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f'display cols config not found: {cfg_path}')

    with open(cfg_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cols = data.get(key, [])
    if not isinstance(cols, list):
        raise ValueError(f'display_cols[{key}] must be a list')

    return cols


# ==================================================
# 核心引擎
# ==================================================
class UpperStructureEngine:
    """
    自动生成 lasthXd / lastpXd 与 upperY 的结构扫描引擎
    """

    def __init__(
        self,
        last_prefix,       # 'lasth' or 'lastp'
        last_days,         # 5 -> lasth1d ... lasth5d
        upper_prefix,      # 'upper'
        upper_levels,      # 3 -> upper1, upper2, upper3
        suffix='d',
        windows=(3, 5),
        code_col='code',
        date_col='date',
        weights=None
    ):
        self.last_prefix = last_prefix
        self.last_days = int(last_days)
        self.upper_prefix = upper_prefix
        self.upper_levels = int(upper_levels)
        self.suffix = suffix
        self.windows = list(windows)
        self.code_col = code_col
        self.date_col = date_col

        # -------- 自动生成列名 --------
        self.last_cols = [
            f'{self.last_prefix}{i}{self.suffix}'
            for i in range(1, self.last_days + 1)
        ]

        self.upper_cols = [
            f'{self.upper_prefix}{i}'
            for i in range(1, self.upper_levels + 1)
        ]

        # -------- 权重 --------
        if weights is None:
            self.weights = {
                col: i + 1
                for i, col in enumerate(self.upper_cols)
            }
        else:
            self.weights = weights

    # ---------- rolling 工具 ----------

    @staticmethod
    def _rolling_sum(arr, n, codes):
        s = pd.Series(arr)
        return (
            s.groupby(codes)
             .rolling(n)
             .sum()
             .reset_index(level=0, drop=True)
             .values
        )

    # ---------- 主计算 ----------

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        # -------- 列存在性检查 --------
        missing = (
            set(self.last_cols + self.upper_cols)
            - set(df.columns)
        )
        if missing:
            raise ValueError(f'Missing columns: {sorted(missing)}')

        df = df.sort_values(
            [self.code_col, self.date_col]
        ).reset_index(drop=True)

        if 'code' in df.columns:
            codes = df[self.code_col].values
        else:
            codes = df.index.values

        lastp = df[self.last_cols].values      # (N, P)
        upper = df[self.upper_cols].values     # (N, U)

        # -------- 广播比较 --------
        # (N, P, U)
        above = lastp[:, :, None] > upper[:, None, :]

        # -------- upper_score --------
        weights = np.array(
            [self.weights[u] for u in self.upper_cols],
            dtype='int16'
        )

        # 每个 last 取最高 upper 层级，再在时间维度聚合
        score = (above * weights).max(axis=2).sum(axis=1)

        df['upper_score'] = score

        # -------- 稳定度 --------
        for n in self.windows:
            df[f'upper_score_{n}d'] = self._rolling_sum(
                score, n, codes
            )

        # 记录新增列
        self.new_cols_generated = ['upper_score'] + [f'upper_score_{w}d' for w in self.windows]

        return df


# ==================================================
# GUI 查看器
# ==================================================
class UpperStructureViewer(tk.Tk):
    def __init__(self, df, engine=None,title='Upper Structure Viewer',col_idx='power_idx'):
        super().__init__()
        self.df_all = df.copy()
        self.df = df.copy()
        self.title(title)
        self.geometry('1300x700')
        # ✅ 从 json 读取列配置

        # ✅ 保证 engine 存在
        self.engine = engine
        self.col_idx = col_idx
        # 从 engine 获取新增列
        if self.engine and hasattr(self.engine, 'new_cols_generated'):
            self.new_cols = [
                c for c in self.engine.new_cols_generated if c in self.df.columns
            ]
        else:
            self.new_cols = []

        self.display_cols = load_display_columns('display_cols.json', 'current')
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=5, pady=5)

        ttk.Label(top, text='Filter:').pack(side='left')
        # self.filter_entry = ttk.Entry(top, width=40)
        # self.filter_entry.pack(side='left', padx=5)
        self.search_entry = ttk.Entry(top, width=30)
        self.search_entry.pack(side='left', padx=5)
        self.search_entry.bind('<KeyRelease>', self._search)

        ttk.Button(top, text='Apply', command=self._apply).pack(side='left')
        ttk.Button(top, text='Reset', command=self._reset).pack(side='left')

        # # cols = list(self.df.columns)
        # # 只保留 df 中真实存在的列
        # cols = [c for c in self.display_cols if c in self.df.columns]

        # 基础列（JSON 配置）
        base_cols = [c for c in self.display_cols if c in self.df.columns]

        # 只显示 Engine 生成的新增列
        new_cols = [c for c in self.engine.new_cols_generated if c in self.df.columns]

        # # GUI 列 = base_cols + engine新增列
        # cols = base_cols + new_cols
        # 找 power_idx 的位置
        try:
            idx = base_cols.index(self.col_idx) + 1
        except ValueError:
            # 如果没有 power_idx，就放到末尾
            print(f'没有 power_idx，就放到末尾')
            idx = len(base_cols)

        # 在 power_idx 后插入 new_cols
        cols = base_cols[:idx] + new_cols + base_cols[idx:]


        # ---------- 表格容器 ----------
        table_frame = ttk.Frame(self)
        table_frame.pack(fill='both', expand=True)

        tree_frame = ttk.Frame(table_frame)
        tree_frame.pack(side='left', fill='both', expand=True)

        scroll_frame = ttk.Frame(table_frame)
        scroll_frame.pack(side='right', fill='y')

        self.tree = ttk.Treeview(
            tree_frame,
            columns=cols,
            show='headings'
        )

        vsb = ttk.Scrollbar(
            scroll_frame,
            orient='vertical',
            command=self.tree.yview
        )

        hsb = ttk.Scrollbar(
            tree_frame,
            orient='horizontal',
            command=self.tree.xview
        )

        self.tree.configure(
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )

        self.tree.pack(fill='both', expand=True)
        vsb.pack(fill='y')
        hsb.pack(fill='x')

        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self._sort(_c))
            self.tree.column(c, width=90, anchor='center', stretch=False)

        # ---------- 右键菜单 ----------
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label='复制 Code', command=self._copy_code)
        self.menu.add_command(label='只看该 Code', command=self._filter_code)
        self.menu.add_separator()
        self.menu.add_command(label='清空过滤', command=self._reset)

        self.tree.bind('<Button-3>', self._popup_menu)

        self.tree.tag_configure('strong', background='#ffe4b5')
        self.tree.tag_configure('mid', background='#f0f8ff')
        self.tree.tag_configure('weak', background='#ffffff')

        # stretch=False 是 避免右侧空白的关键参数。
        self._load(self.df)

    # def _load(self, df):
    #     self.tree.delete(*self.tree.get_children())
    #     for _, row in df.iterrows():
    #         self.tree.insert('', 'end', values=list(row))
    def _load(self, df):
        self.tree.delete(*self.tree.get_children())

        for _, row in df.iterrows():
            score = row.get('upper_score', 0)

            if score >= 10:
                tag = 'strong'
            elif score >= 4:
                tag = 'mid'
            else:
                tag = 'weak'

            self.tree.insert(
                '', 'end',
                # values=list(row),
                values = [row[c] for c in self.tree['columns']],
                tags=(tag,)
            )


    def _sort(self, col):
        asc = getattr(self, '_asc', True)
        self.df = self.df.sort_values(col, ascending=asc)
        self._asc = not asc
        self._load(self.df)

    def _apply(self):
        expr = self.filter_entry.get().strip()
        if not expr:
            return
        try:
            self.df = self.df_all.query(expr)
            self._load(self.df)
        except Exception as e:
            print('[FILTER ERROR]', e)

    def _reset(self):
        self.df = self.df_all.copy()
        self._load(self.df)

    def _popup_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.menu.post(event.x_root, event.y_root)

    def _copy_code(self):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], 'values')
        code = values[0]  # 默认 code 在第一列
        self.clipboard_clear()
        self.clipboard_append(code)

    def _filter_code(self):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], 'values')
        code = values[0]
        self.df = self.df_all[self.df_all['code'] == code]
        self._load(self.df)

    def _search(self, event=None):
        text = self.search_entry.get().strip()
        if not text:
            self.df = self.df_all.copy()
            self._load(self.df)
            return

        # 纯数字 / code 模糊
        if text.isdigit():
            self.df = self.df_all[
                self.df_all['code'].astype(str).str.contains(text)
            ]
            self._load(self.df)
            return

        # 尝试表达式
        try:
            self.df = self.df_all.query(text)
            self._load(self.df)
        except Exception:
            pass

# ==================================================
# 示例 main
# ==================================================
if __name__ == '__main__':
    # 示例数据
    rows = []
    # for code in ['000001', '000002']:
    #     for i in range(40):
    #         rows.append({
    #             'code': code,
    #             'date': pd.Timestamp('2025-01-01') + pd.Timedelta(days=i),
    #             'lasth1d': 10 + np.random.randn(),
    #             'lasth2d': 10 + np.random.randn(),
    #             'lasth3d': 10 + np.random.randn(),
    #             'lasth4d': 10 + np.random.randn(),
    #             'lasth5d': 10 + np.random.randn(),
    #             'upper1': 9.8,
    #             'upper2': 10.2,
    #             'upper3': 10.6,
    #         })

    # df = pd.DataFrame(rows)


    # from JSONData import tdx_data_Day as tdd
    # from JohnsonUtil import johnson_cons as ct
    from JohnsonUtil.commonTips import timed_ctx
    from JohnsonUtil import commonTips as cct
    from data_utils import (
                get_all_fetch_df
            )

    # market = 'all'
    # resample= 'd'
    # detect_val = False

    # with timed_ctx(f"fetch_market:{market} {resample}", warn_ms=800):
    #     top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)

    #     df, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[resample], 
    #                                                resample=resample, detect_calc_support=detect_val)

    df = get_all_fetch_df()

    with timed_ctx(f"UpperStructureEngine", warn_ms=800):
        engine = UpperStructureEngine(
            last_prefix='lasth',
            last_days=5,
            upper_prefix='upper',
            upper_levels=3,
            windows=[3, 5]
        )

    df_out = engine.run(df)
    cct.print_timing_summary()
    latest = df_out['date'].max()
    view_df = df_out[df_out['date'] == latest].sort_values(
        'upper_score_5d', ascending=False
    )

    app = UpperStructureViewer(view_df, engine=engine)
    app.mainloop()
