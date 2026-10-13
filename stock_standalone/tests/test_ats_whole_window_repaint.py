from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMainWindow

from ats.ui.styles import DARK_THEME_QSS, apply_dark_theme, apply_dark_tooltip_palette
from ats.ui.heatmap_widget import SectorHeatmapWidget


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def flush(app):
    for _ in range(6):
        app.processEvents()


class PaintProbe(QMainWindow):
    def __init__(self):
        super().__init__()
        self.paints = []
        self.palette_changes = 0

    def event(self, event):
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self.palette_changes += 1
        return super().event(event)

    def paintEvent(self, event):
        self.paints.append(event.region().boundingRect())
        super().paintEvent(event)


def test_dialog_theme_does_not_repaint_host_or_change_app_palette(qapp):
    original = QPalette(qapp.palette())
    palette = QPalette(original)
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor('#223344'))
    qapp.setPalette(palette)
    host = PaintProbe()
    host.resize(800, 600)
    host.setStyleSheet(DARK_THEME_QSS)
    host.setCentralWidget(QLabel('unchanged market data'))
    host.show()
    dialog = QDialog(host)
    try:
        flush(qapp)
        host.paints.clear()
        host.palette_changes = 0
        apply_dark_theme(dialog)
        flush(qapp)
        assert qapp.palette() == palette
        assert dialog.palette().color(QPalette.ColorRole.ToolTipBase).name() == '#1a1a24'
        assert host.palette_changes == 0
        assert not host.paints
        apply_dark_theme(dialog)
        flush(qapp)
        assert not host.paints
    finally:
        dialog.close()
        host.close()
        qapp.setPalette(original)


def test_explicit_app_palette_initialization_is_idempotent(qapp):
    original = QPalette(qapp.palette())
    try:
        apply_dark_tooltip_palette(qapp)
        palette = QPalette(qapp.palette())
        assert palette.color(QPalette.ColorRole.ToolTipBase).name() == '#1a1a24'
        cache_key = palette.cacheKey()
        apply_dark_tooltip_palette(qapp)
        assert qapp.palette().cacheKey() == cache_key
    finally:
        qapp.setPalette(original)


@pytest.fixture
def heatmap(qapp, monkeypatch):
    monkeypatch.setattr('ats.ui.styles.load_config_node', lambda *a, **k: 0)
    monkeypatch.setattr('global_favorites.GlobalFavoriteManager', lambda: SimpleNamespace(get_favorite_sectors=lambda: set()))
    monkeypatch.setattr(SectorHeatmapWidget, 'load_live_sectors', lambda *a, **k: None)
    widget = SectorHeatmapWidget()
    widget.resize(800, 600)
    widget.sectors = [('半导体', 10, '+1.00%', 3), ('白酒概念', 9, '+0.80%', 2)]
    widget.sector_to_codes = {'半导体': ['600000'], '白酒概念': ['600001']}
    widget.render_grid()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    yield widget
    widget.close()


def test_rank_swap_reuses_cards_moves_positions_and_keeps_click_targets(heatmap):
    first, second = heatmap._grid_cards
    received = []
    heatmap.sector_selected_with_codes.connect(lambda name, codes: received.append((name, codes)))
    heatmap.sectors.reverse()
    heatmap.render_grid()
    assert heatmap._grid_cards == [second, first]
    assert heatmap.grid_layout.itemAtPosition(0, 0).widget() is second[0]
    assert heatmap.grid_layout.itemAtPosition(0, 1).widget() is first[0]
    second[0].click()
    assert received == [('白酒概念', ['600001'])]


def test_add_remove_resize_and_force_do_not_recreate_survivors(heatmap):
    survivor = heatmap._grid_cards[0]
    removed = heatmap._grid_cards[1][0]
    heatmap.sectors = [heatmap.sectors[0], ('煤炭概念', 8, '+0.30%', 4)]
    heatmap.render_grid()
    assert heatmap._grid_cards[0] is survivor
    assert heatmap.grid_layout.indexOf(removed) == -1
    assert removed.isHidden()
    heatmap.resize(250, 600)
    heatmap.render_grid(force=True)
    assert heatmap._grid_cards[0] is survivor
    assert heatmap.grid_layout.count() == 2


def test_same_state_has_no_grid_layout_mutation(heatmap):
    original = list(heatmap._grid_cards)
    heatmap.render_grid(force=True)
    assert heatmap._grid_cards == original
    assert heatmap.grid_layout.count() == 2


def test_repeated_rank_and_value_updates_do_not_accumulate_widgets_or_connections(heatmap):
    from PyQt6.QtWidgets import QPushButton
    originals = {name: widgets[0] for name, widgets in zip(
        [item[0] for item in heatmap.sectors], heatmap._grid_cards)}
    received = []
    heatmap.sector_selected.connect(received.append)
    for index in range(100):
        heatmap.sectors.reverse()
        name, _, pct, count = heatmap.sectors[0]
        heatmap.sectors[0] = (name, index, pct, count)
        heatmap.render_grid()
    assert len(heatmap.grid_container.findChildren(QPushButton)) == 2
    assert all(widgets[0] is originals[item[0]] for item, widgets in zip(heatmap.sectors, heatmap._grid_cards))
    heatmap._grid_cards[0][0].click()
    assert received == [heatmap.sectors[0][0]]


def test_removing_card_releases_qt_object(heatmap, qapp):
    from PyQt6 import sip
    removed = heatmap._grid_cards[1][0]
    heatmap.sectors = heatmap.sectors[:1]
    heatmap.render_grid()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(removed)
    assert len(heatmap._grid_cards) == heatmap.grid_layout.count() == 1
