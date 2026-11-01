# -*- coding: utf-8 -*-
"""只读已归档换手和量比，严格按交易日前截取；不参与交易评分。"""
from __future__ import annotations

import math
from pathlib import Path


class DailyLiquidityHistory:
    def __init__(self, path=None):
        self.path = str(path or "")
        self.status = "unavailable"
        self.error = ""
        self._rows = {}
        try:
            if not self.path:
                from JSONData.multiday_feature_store import get_multiday_store_path
                self.path = str(get_multiday_store_path())
            if not Path(self.path).is_file():
                self.error = "历史特征文件不存在"
                return
            import pandas as pd
            from ats.fusion.context import _H5_LOCK
            with _H5_LOCK:
                frame = pd.read_hdf(self.path, key="/daily_multiday_ratio")
            if not {"code", "date", "ratio", "vol_ratio"}.issubset(frame.columns):
                raise ValueError("历史特征缺少必要字段")
            frame = frame.copy()
            frame["code"] = frame["code"].astype(str).str.strip().str.zfill(6)
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            frame = frame[frame["code"].str.fullmatch(r"\d{6}") & frame["date"].notna()]
            if frame.duplicated(["code", "date"]).any():
                raise ValueError("历史特征存在重复代码日期，未自动选取")
            frame = frame.sort_values(["code", "date"])
            for code, group in frame.groupby("code", sort=False):
                self._rows[code] = [(row.date, row.ratio, row.vol_ratio) for row in group.itertuples(index=False)]
            self.status = "ready" if self._rows else "unavailable"
            if not self._rows:
                self.error = "历史特征没有有效记录"
        except (OSError, ValueError, TypeError, KeyError, ImportError, RuntimeError, AttributeError) as exc:
            self.error = str(exc)
            self._rows = {}

    @staticmethod
    def _number(value, upper):
        try:
            number = float(value)
            return number if math.isfinite(number) and 0 < number <= upper else None
        except (TypeError, ValueError, OverflowError):
            return None

    def asof(self, code, day, limit=5):
        """返回 day 之前的真实归档日期；未知/默认值不冒充当前行情。"""
        if self.status != "ready":
            return {"status": self.status, "source": self.path, "history": [], "error": self.error}
        try:
            from datetime import date
            cutoff = date.fromisoformat(str(day)).isoformat()
        except (ValueError, TypeError):
            return {"status": "invalid_date", "source": self.path, "history": []}
        code = str(code).split(".")[0].zfill(6)
        available = [row for row in self._rows.get(code, ()) if row[0] < cutoff]
        history = []
        for trade_day, ratio, vol_ratio in reversed(available[-max(0, limit):] if limit > 0 else []):
            value = self._number(vol_ratio, 50)
            history.append({"date": trade_day, "turnover_pct": self._number(ratio, 100),
                            "volume_ratio": value, "volume_ratio_may_be_default": value == 1.0})
        return {"status": "archived" if history else "missing", "source": self.path, "history": history,
                "availability": "历史归档未保留逐行写入时间，不能证明当时已可获得"}
