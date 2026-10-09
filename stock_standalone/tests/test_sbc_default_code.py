"""Default SBC code persistence and real context-menu wiring only."""
import os
import subprocess
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QInputDialog, QMessageBox

from ats.ui.sbc_preferences import get_sbc_default_code, set_sbc_default_code


def test_default_code_survives_restart_and_layout_removal(monkeypatch, tmp_path):
    layout = tmp_path / 'layout.json'
    monkeypatch.setenv('SBC_LAYOUT_CONFIG_PATH', str(layout))
    assert get_sbc_default_code() == '600733'
    layout.write_text('{broken layout', encoding='utf-8')
    set_sbc_default_code(' 000001 ')
    assert layout.read_text(encoding='utf-8') == '{broken layout'
    layout.unlink()
    assert get_sbc_default_code() == '000001'
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c',
                             'from ats.ui.sbc_preferences import get_sbc_default_code; print(get_sbc_default_code())'],
                            env=dict(os.environ), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == '000001'
    for code in ('000000', '1', '1234567', 'abc123', '６００７３３'):
        with pytest.raises(ValueError):
            set_sbc_default_code(code)
        assert get_sbc_default_code() == '000001'
    assert not list(tmp_path.glob('*.tmp'))


def test_context_menu_saves_default_and_cancel_or_invalid_keeps_previous(monkeypatch, tmp_path):
    from ats.ui.intraday_strategy_dialog import SBCChartCanvas, SBCIntradayChartDialog
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('SBC_LAYOUT_CONFIG_PATH', str(tmp_path / 'layout.json'))
    class Window(QWidget):
        _on_set_default_code = SBCIntradayChartDialog._on_set_default_code
    window = Window()
    canvas = SBCChartCanvas(window)
    inputs = iter([('300750', True), ('bad', True), ('000001', False)])
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: next(inputs))
    info, warnings = [], []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: info.append(args))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args))
    canvas._show_custom_context_menu()
    menu = canvas.findChildren(QMenu)[-1]
    action = next(a for a in menu.actions() if '设置默认股票代码' in a.text())
    assert '600733' in action.text()
    action.trigger()
    assert get_sbc_default_code() == '300750' and len(info) == 1
    action.trigger()
    action.trigger()
    assert get_sbc_default_code() == '300750' and len(warnings) == 1 and len(info) == 1
    canvas._show_custom_context_menu()
    assert any('300750' in a.text() for a in canvas.findChildren(QMenu)[-1].actions())
    window.close()
    window.deleteLater()
    app.processEvents()
