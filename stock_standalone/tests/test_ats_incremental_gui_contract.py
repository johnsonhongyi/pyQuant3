"""Real Qt item ownership and interaction checks without external transport."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def test_swing_incremental_refresh_preserves_items_and_interactions(monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from ats.ui import swing_table as module
    from ats.ui.base_table import BaseATSTableWidget
    from global_favorites import GlobalFavoriteManager
    import sys_utils

    app = QApplication.instance() or QApplication(['incremental-contract'])
    monkeypatch.setattr(sys_utils, 'get_app_root', lambda: str(tmp_path))
    monkeypatch.setattr(module, 'load_config_node', lambda key, default=None: default)
    monkeypatch.setattr(module, 'auto_fit_columns_once', lambda *a, **k: None)
    monkeypatch.setattr(module, 'get_ats_extra_cols', lambda: [])
    monkeypatch.setattr(BaseATSTableWidget, 'setup_persistence', lambda *a, **k: None)
    monkeypatch.setattr(module.SwingStateTable, 'load_mock_data', lambda self: None)
    monkeypatch.setattr(module.SwingStateTable, '_load_show_favorite_config', lambda self: False)
    monkeypatch.setattr(module.SwingStateTable, '_apply_favorite_filter', lambda self: None)
    monkeypatch.setattr(GlobalFavoriteManager, 'get_favorite_stocks', lambda self: [])
    widget = module.SwingStateTable()
    table = widget.table
    def row(code, price):
        return (code, code, str(price), 'WATCH') + ('0',) * 11 + ('reason',)
    rows = [row('600001', 10), row('600002', 20), row('600003', 30)]
    widget.update_data_list(rows)
    table.sortItems(2, Qt.SortOrder.DescendingOrder)
    original = {table.item(i, 0).text(): table.item(i, 0) for i in range(3)}
    table.setCurrentItem(original['600002'])
    table.setColumnWidth(1, 177)
    widget.hide()
    changed = [rows[0], row('600002', 40), rows[2]]
    widget.update_data_list(changed)
    app.processEvents()
    assert [table.item(i, 0).text() for i in range(3)] == ['600002', '600003', '600001']
    assert table.currentItem().text() == '600002'
    assert table.columnWidth(1) == 177
    assert all(table.item(i, 0) is original[table.item(i, 0).text()] for i in range(3))
    identities = [table.item(i, 0) for i in range(3)]
    widget.update_data_list(changed)
    assert all(table.item(i, 0) is identities[i] for i in range(3))
    table._copy_to_clipboard('600002')
    assert app.clipboard().text() == '600002'
    widget.close()
