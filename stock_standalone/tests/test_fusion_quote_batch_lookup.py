from types import SimpleNamespace

import pandas as pd

from ats.ui.fusion_ladder_dialog import FusionLadderDialog


def test_quote_batch_lookup_keeps_first_duplicate_and_index_priority():
    frame = pd.DataFrame(
        {"code": ["000001", "000001", "000002"],
         "price": [10.0, 20.0, 30.0], "percent": [1.0, 2.0, 3.0]},
        index=["other", "000002", "third"],
    )
    dialog = SimpleNamespace(_py_parent=SimpleNamespace(current_df=frame))

    quotes = FusionLadderDialog._get_batch_quotes_snapshot(dialog, ["000001", "000002"])

    assert quotes["000001"]["price"] == 10.0
    assert quotes["000002"]["price"] == 20.0
    assert quotes["000002"]["day_pct"] == 2.0


def test_structure_filter_only_renders_visible_table(monkeypatch):
    from ats.ui import fusion_ladder_dialog as module

    monkeypatch.setattr(module, "save_config_node_async", lambda *args: None)
    calls = []
    dialog = SimpleNamespace(
        tabs=SimpleNamespace(currentIndex=lambda: 0),
        cmb_day=SimpleNamespace(currentText=lambda: "2026-11-02"),
        _tab_signatures={3: "old"}, _live_sig="old",
        _style_structure_only=lambda value: None,
        _queue_shadow_refresh=lambda index: calls.append("live" if index == 0 else "track"),
    )
    FusionLadderDialog._on_structure_only_toggled(dialog, True)
    assert calls == ["live"]
    assert dialog._live_sig is None and 3 not in dialog._tab_signatures

    calls.clear()
    dialog.tabs.currentIndex = lambda: 3
    FusionLadderDialog._on_structure_only_toggled(dialog, False)
    assert calls == ["track"]


def test_historical_track_does_not_fetch_current_quotes(monkeypatch):
    from ats.ui import fusion_ladder_dialog as module

    monkeypatch.setattr(module, "load_live_series", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "today_str", lambda: "2026-11-02")

    calls = []

    class Dialog:
        def _get_batch_quotes_snapshot(self, codes):
            calls.append(codes)
            return {}

    assert FusionLadderDialog._track_entries_from_shadow(Dialog(), "2026-10-30") == []
    assert calls == []


def test_custom_column_lookup_preserves_first_match_and_index_priority():
    frame = pd.DataFrame({"code": [1, 1, 2], "dff": [1.5, 2.5, 3.5]},
                         index=["other", "000002", "third"])
    lookup = FusionLadderDialog._custom_code_lookup(frame)
    for code in ("000001", "000002", "999999"):
        original = FusionLadderDialog._extract_stock_custom_val(None, frame, code, "dff")
        cached = FusionLadderDialog._extract_stock_custom_val(None, frame, code, "dff", lookup)
        assert cached == original
