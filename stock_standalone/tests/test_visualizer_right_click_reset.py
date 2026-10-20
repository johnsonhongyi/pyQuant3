import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from PyQt6.QtCore import Qt


def handler():
    path="trade_visualizer_qt6.py"
    tree=ast.parse(Path(path).read_text(encoding="utf-8"))
    node=next(n for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body
              if isinstance(n,ast.FunctionDef) and n.name=="_handle_kline_reset_click")
    namespace={"Qt":Qt}
    exec(compile(ast.Module(body=[node],type_ignores=[]),path,"exec"),namespace)
    return namespace[node.name]


def test_right_click_restores_default_view_and_detail_follow_without_reloading():
    obj=SimpleNamespace(_manual_view_lock=True,kline_detail_win=SimpleNamespace(auto_close_disabled=True,reset_to_auto_follow=Mock()),_reset_kline_view=Mock())
    event=Mock();event.button.return_value=Qt.MouseButton.RightButton;event.modifiers.return_value=Qt.KeyboardModifier.NoModifier
    assert handler()(obj,event)
    assert obj._manual_view_lock is False
    obj._reset_kline_view.assert_called_once_with(force=True)
    obj.kline_detail_win.reset_to_auto_follow.assert_called_once()
    event.accept.assert_called_once()


def test_left_and_shift_right_are_left_to_existing_chart_handlers():
    for button,mod in ((Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier),(Qt.MouseButton.RightButton,Qt.KeyboardModifier.ShiftModifier)):
        obj=SimpleNamespace(_manual_view_lock=True,_reset_kline_view=Mock())
        event=Mock();event.button.return_value=button;event.modifiers.return_value=mod
        assert not handler()(obj,event)
        obj._reset_kline_view.assert_not_called();event.accept.assert_not_called()
        assert obj._manual_view_lock
