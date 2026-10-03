"""Pure market projections and cold archive preparation outside the GUI thread."""
import os
import shutil

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal


def distribution_projection(frame):
    if "percent" not in frame.columns:
        return None
    pcts = frame["percent"].dropna()
    bins = [-999, -8, -6, -4, -2, 0, 2, 4, 6, 8, 999]
    counts = pd.cut(pcts, bins=bins).value_counts().sort_index().tolist()
    up, down, flat = int((pcts > 0).sum()), int((pcts < 0).sum()), int((pcts == 0).sum())
    total = up + down + flat
    return counts, {"up": up, "down": down, "flat": flat,
                    "avg": float(pcts.mean()) if total else 0.0,
                    "temp": up / total * 100.0 if total else 0.0}


class DistributionWorker(QThread):
    ready = pyqtSignal(object, object)

    def __init__(self, frame):
        super().__init__()
        self.frame = frame

    def run(self):
        try:
            self.ready.emit(self.frame, distribution_projection(self.frame))
        except Exception:
            self.ready.emit(self.frame, None)


class AlphaHistoryWorker(QThread):
    ready = pyqtSignal(str, object, str)

    def __init__(self, day, root):
        super().__init__()
        self.day, self.root = day, root

    def run(self):
        try:
            from ats.bounded_evaluation_store import evaluation_store
            data_dir = os.path.join(self.root, "datacsv")
            old_dir = os.path.join(self.root, "data")
            os.makedirs(data_dir, exist_ok=True)
            if os.path.isdir(old_dir) and old_dir != data_dir:
                for name in os.listdir(old_dir):
                    if name.startswith("ats_alpha_tracker_") and name.endswith(".json"):
                        target = os.path.join(data_dir, name)
                        if not os.path.exists(target):
                            shutil.copy2(os.path.join(old_dir, name), target)
            path = os.path.join(data_dir, f"ats_alpha_tracker_{self.day}.json")
            records = evaluation_store.read(path, None)
            self.ready.emit(self.day, records if isinstance(records, list) else [], "")
        except Exception as exc:
            self.ready.emit(self.day, [], str(exc))
