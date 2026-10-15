import ast
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
from unittest.mock import Mock

import pytest


def load_mixin():
    source = Path(__file__).parents[1] / 'tk_gui_modules' / 'window_mixin.py'
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'WindowMixin')
    methods = {'collect_all_open_windows', 'save_all_windows_snapshot', 'restore_all_windows_snapshot'}
    original.body = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in methods]
    namespace = dict(Any=Any, Optional=Optional, os=os, json=json, logger=logging.getLogger(__name__),
                     clamp_window_to_screens=lambda x, y, width, height: (x, y))
    exec(compile(ast.Module(body=[original], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['WindowMixin']


class Rect:
    def __init__(self, x, y, width, height):
        self.values = (x, y, width, height)

    def x(self):
        return self.values[0]

    def y(self):
        return self.values[1]

    def width(self):
        return self.values[2]

    def height(self):
        return self.values[3]


@pytest.mark.parametrize('edge,expanded,collapsed', [
    ('left', (-1920, 100, 800, 600), (-2715, 100, 800, 600)),
    ('right', (1120, 100, 800, 600), (1915, 100, 800, 600)),
    ('top', (100, 0, 800, 600), (100, -595, 800, 600)),
    (None, (200, 100, 800, 600), (200, 100, 800, 600)),
])
@pytest.mark.parametrize('scale', [1, 1.5])
@pytest.mark.parametrize('hover_active', [False, True])
def test_snapshot_round_trip(tmp_path, edge, expanded, collapsed, scale, hover_active):
    panel = Mock(spec=['geometry', 'windowHandle', 'normal_geometry', 'anchor_edge', 'is_hidden_state',
                       'isVisible', 'setGeometry', 'setWindowOpacity', 'snap_timer',
                       'hover_timer', 'anim_group'])
    panel.geometry.return_value = Rect(*collapsed)
    panel.normal_geometry = Rect(*expanded) if edge else None
    panel.anchor_edge = edge
    panel.is_hidden_state = bool(edge)
    panel._in_snap_action = True
    panel.isVisible.return_value = True
    panel.hover_timer.isActive.return_value = hover_active
    app = load_mixin()()
    app._signal_dashboard_win = panel
    app._get_dpi_scale_factor = lambda: scale
    app._get_config_file_path = lambda path, dpi: path
    config = str(tmp_path / 'windows.json')
    assert app.collect_all_open_windows() == {'signal_dashboard_panel': panel}
    app.save_all_windows_snapshot(slot=2, file_path=config)
    saved = json.loads(Path(config).read_text(encoding='utf-8'))['manual_snapshot_2']['windows']['signal_dashboard_panel']
    assert saved['x'] == int(expanded[0] / scale)
    assert saved['anchor_edge'] == edge
    panel.anchor_edge = 'top'
    count, names = app.restore_all_windows_snapshot(slot=2, file_path=config)
    expected = tuple(int(saved[key] * scale) for key in ('x', 'y', 'width', 'height'))
    assert (count, names) == (1, ['signal_dashboard_panel'])
    panel.setGeometry.assert_called_once_with(*expected)
    assert panel.normal_geometry.values == expected
    assert panel.anchor_edge == edge
    assert panel.is_hidden_state is False
    assert panel._in_snap_action is False
    assert panel._is_dragging is False
    panel.anim_group.stop.assert_called_once()
    panel.snap_timer.stop.assert_called_once()
    panel.setWindowOpacity.assert_called_once_with(1.0)
    assert panel._has_hovered_since_show is True
    assert panel.hover_timer.start.call_count == bool(edge or hover_active)
