# -*- coding: utf-8 -*-
import os
import sys
import json
import shutil
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'webTools')))

from window_manager.antigravity_manager import (
    mask_email, extract_account_summary, parse_account_detail,
    read_db_data, write_db_data, list_accounts, get_current_account,
    backup_current_account, switch_account, do_sync,
    auto_backup_new_accounts_from_databases
)


def test_mask_email():
    assert mask_email('hongyi2008@gmail.com') == 'h***8@gmail.com'
    assert mask_email('a@b.com') == 'a*@b.com'
    assert mask_email('ab@c.com') == 'a*@c.com'
    assert mask_email('invalid') == 'invalid'
    assert mask_email('') == 'None'


def test_parse_account_detail():
    raw_auth = json.dumps({'name': 'Test User', 'email': 'test@example.com', 'apiKey': 'key123'})
    detail = parse_account_detail(raw_auth)
    assert detail['name'] == 'Test User'
    assert detail['email'] == 'test@example.com'
    assert detail['has_api_key'] is True

    summary = extract_account_summary(raw_auth)
    assert summary == 'Test User (test@example.com)'


def test_db_read_write_and_sync():
    local_temp = os.path.abspath(os.path.join(os.path.dirname(__file__), '_temp_ag_test'))
    if os.path.exists(local_temp):
        shutil.rmtree(local_temp, ignore_errors=True)
    os.makedirs(local_temp, exist_ok=True)

    try:
        old_db = os.path.join(local_temp, 'old_state.vscdb')
        new_db = os.path.join(local_temp, 'new_state.vscdb')
        acc_dir = os.path.join(local_temp, 'accounts')
        os.makedirs(acc_dir, exist_ok=True)

        # 1. 写入测试数据到 old_db
        test_auth_1 = json.dumps({'name': 'User One', 'email': 'one@example.com', 'apiKey': 'key1'})
        write_db_data(old_db, {
            'antigravityAuthStatus': test_auth_1,
            'oauthToken': 'token_1',
            'antigravityOnboarding': 'true'
        })

        # 验证读取
        d = read_db_data(old_db)
        assert d['oauthToken'] == 'token_1'

        # 2. 写入备份账户文件
        test_auth_2 = json.dumps({'name': 'User Two', 'email': 'two@example.com', 'apiKey': 'key2'})
        acc_file_2 = os.path.join(acc_dir, 'two@example.com.json')
        with open(acc_file_2, 'w', encoding='utf-8') as f:
            json.dump({
                'antigravityAuthStatus': test_auth_2,
                'antigravityUnifiedStateSync.oauthToken': 'token_2',
                'antigravityUnifiedStateSync.userStatus': 'status_2'
            }, f)

        # 3. 列出账户
        accs = list_accounts(acc_dir)
        assert len(accs) >= 1

        # 4. 测试备份当前账户
        import window_manager.antigravity_manager as agm
        orig_old = agm.OLD_DB_PATH
        orig_new = agm.NEW_DB_PATH
        orig_acc = agm.ACCOUNTS_DIR
        try:
            agm.OLD_DB_PATH = old_db
            agm.NEW_DB_PATH = new_db
            agm.ACCOUNTS_DIR = acc_dir

            ok, msg, path = backup_current_account(acc_dir)
            assert ok is True
            assert os.path.exists(os.path.join(acc_dir, 'one@example.com.json'))

            # 5. 测试切换到 User Two
            ok_sw, msg_sw = switch_account('two@example.com', acc_dir, auto_sync=True)
            assert ok_sw is True
            curr_after_sw = get_current_account(old_db)
            assert curr_after_sw['email'] == 'two@example.com'

            new_d = read_db_data(new_db)
            assert new_d is not None
            assert 'two@example.com' in new_d.get('antigravityAuthStatus', '')
        finally:
            agm.OLD_DB_PATH = orig_old
            agm.NEW_DB_PATH = orig_new
            agm.ACCOUNTS_DIR = orig_acc
    finally:
        shutil.rmtree(local_temp, ignore_errors=True)


def test_auto_discover_and_healing_from_target_db():
    local_temp = os.path.abspath(os.path.join(os.path.dirname(__file__), '_temp_ag_heal_test'))
    if os.path.exists(local_temp):
        shutil.rmtree(local_temp, ignore_errors=True)

    non_existent_acc_dir = os.path.join(local_temp, 'lost_accounts_dir')
    corrupted_old_db = os.path.join(local_temp, 'missing_old_state.vscdb')
    active_target_new_db = os.path.join(local_temp, 'active_ide_state.vscdb')

    # 在目标数据库中注入一个新登录的账户
    new_trader_auth = json.dumps({'name': 'Alpha Trader', 'email': 'alpha.trader@fund.com', 'apiKey': 'fund_key_888'})
    write_db_data(active_target_new_db, {
        'antigravityAuthStatus': new_trader_auth,
        'antigravityUnifiedStateSync.oauthToken': 'fund_token_999',
        'antigravityUnifiedStateSync.userStatus': 'fund_status_vip',
        'antigravityOnboarding': 'true'
    })

    import window_manager.antigravity_manager as agm
    orig_old = agm.OLD_DB_PATH
    orig_new = agm.NEW_DB_PATH
    orig_acc = agm.ACCOUNTS_DIR

    try:
        agm.OLD_DB_PATH = corrupted_old_db
        agm.NEW_DB_PATH = active_target_new_db
        agm.ACCOUNTS_DIR = non_existent_acc_dir

        assert not os.path.exists(non_existent_acc_dir)
        assert not os.path.exists(corrupted_old_db)

        # 执行自愈与同步
        changed, msg = do_sync(auto_persist_to_file=True)
        assert changed is True

        # 验证 1: 自动创建了账户目录
        assert os.path.exists(non_existent_acc_dir)

        # 验证 2: 自动生成了该新账户的备份配置文件
        expected_json = os.path.join(non_existent_acc_dir, 'alpha.trader@fund.com.json')
        assert os.path.exists(expected_json)
        with open(expected_json, 'r', encoding='utf-8') as fp:
            saved_json = json.load(fp)
            assert 'alpha.trader@fund.com' in saved_json.get('antigravityAuthStatus', '')
            assert saved_json.get('antigravityUnifiedStateSync.oauthToken') == 'fund_token_999'

        # 验证 3: 自动从目标库自愈恢复了源数据库
        assert os.path.exists(corrupted_old_db)
        healed_data = read_db_data(corrupted_old_db)
        assert 'alpha.trader@fund.com' in healed_data.get('antigravityAuthStatus', '')

        # 验证 4: list_accounts 正确返回该自愈新账户
        accs = list_accounts(non_existent_acc_dir)
        assert len(accs) == 1
        assert accs[0]['email'] == 'alpha.trader@fund.com'
        assert accs[0]['name'] == 'Alpha Trader'
    finally:
        agm.OLD_DB_PATH = orig_old
        agm.NEW_DB_PATH = orig_new
        agm.ACCOUNTS_DIR = orig_acc
        shutil.rmtree(local_temp, ignore_errors=True)


def test_ui_tray_methods():
    from window_manager.ui import WindowPosManagerUI
    from PyQt6.QtWidgets import QApplication, QMenu
    app = QApplication.instance() or QApplication([])

    menu = QMenu()
    sub_menu = menu.addMenu('Antigravity')

    class DummyUI:
        def __init__(self):
            self.ag_sub_menu = sub_menu
            self.logs = []
        def log(self, text):
            self.logs.append(text)
        def _trigger_ag_sync_from_tray(self):
            pass
        def _trigger_ag_backup_from_tray(self):
            pass
        def _open_ag_accounts_dir(self):
            pass
        def _on_switch_ag_account_from_tray(self, email):
            pass
        def open_antigravity_account_manager(self):
            pass

    dummy = DummyUI()
    WindowPosManagerUI._update_ag_tray_submenu(dummy)
    actions = sub_menu.actions()
    assert len(actions) >= 4
    action_texts = [a.text() for a in actions]
    assert any('当前' in t or 'Current' in t for t in action_texts)
    assert any('同步' in t or 'Sync' in t for t in action_texts)
    assert any('备份' in t or 'Backup' in t for t in action_texts)
    assert any('账户与配额' in t for t in action_texts)

    # 验证隐私保护：所有带邮箱的菜单项必须经过脱敏打码 (含有 *)
    for t in action_texts:
        if "@" in t:
            assert "*" in t, f"右键菜单中发现未脱敏邮箱暴露: {t}"



def test_quota_formatting_and_categorization():
    from window_manager.antigravity_manager import format_time_until_reset, categorize_model_label
    import datetime

    # 1. 过期时间测试
    past_iso = "2020-01-01T00:00:00Z"
    diff_sec, desc = format_time_until_reset(past_iso)
    assert diff_sec == 0.0
    assert "已重置" in desc or "已就绪" in desc

    # 2. 未来时间测试 (加 2 小时)
    future_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2, minutes=15)
    future_iso = future_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    diff_sec, desc = format_time_until_reset(future_iso)
    assert diff_sec > 7000
    assert "小时" in desc

    # 3. 异常与空保护
    assert format_time_until_reset("")[1] == "未知"
    assert format_time_until_reset("invalid_date")[0] == 0.0

    # 4. 标签分类测试
    assert categorize_model_label("Claude Opus 4.6 (Thinking)") == "Claude"
    assert categorize_model_label("Claude Sonnet 4.6 (Thinking)") == "Claude"
    assert categorize_model_label("Gemini 3.1 Pro (High)") == "Gemini Pro"
    assert categorize_model_label("Gemini 3.8 Flash (Medium)") == "Gemini Flash"
    assert categorize_model_label("GPT-OSS 120B (Medium)") == "GPT-OSS"
    assert categorize_model_label("custom-model-x") == "其他模型"


def test_delete_account_and_backup():
    import window_manager.antigravity_manager as agm
    from window_manager.antigravity_manager import delete_account, list_accounts
    local_temp = os.path.abspath(os.path.join(os.path.dirname(__file__), '_temp_del_test'))
    if os.path.exists(local_temp):
        shutil.rmtree(local_temp, ignore_errors=True)
    os.makedirs(local_temp, exist_ok=True)

    try:
        # 创建待删除文件
        acc_file = os.path.join(local_temp, "delete_me@test.com.json")
        with open(acc_file, "w", encoding="utf-8") as f:
            json.dump({"antigravityAuthStatus": json.dumps({"email": "delete_me@test.com"})}, f)

        # 验证删除
        ok, msg = delete_account("delete_me@test.com", accounts_dir=local_temp)
        assert ok is True
        assert not os.path.exists(acc_file)
        assert os.path.exists(acc_file + ".bak")

        # 再次删除应失败
        ok2, msg2 = delete_account("non_existent@test.com", accounts_dir=local_temp)
        assert ok2 is False
    finally:
        shutil.rmtree(local_temp, ignore_errors=True)


def test_antigravity_account_manager_dialog_ui():
    from PyQt6.QtWidgets import QApplication
    from window_manager.ui import AntigravityAccountManagerDialog, WindowPosManagerUI
    app = QApplication.instance() or QApplication([])

    dialog = AntigravityAccountManagerDialog(auto_fetch=False)
    assert "Antigravity" in dialog.windowTitle()
    assert hasattr(dialog, "scroll_area")
    assert hasattr(dialog, "account_cards")
    assert "Claude" in dialog.card_widgets
    assert "Gemini Pro" in dialog.card_widgets
    assert "Gemini Flash" in dialog.card_widgets
    assert "GPT-OSS" in dialog.card_widgets

    # 测试明细折叠切换 (窗口未 show 前通过 isHidden 检验控件自身显隐意图)
    assert dialog.tbl_details.isHidden()
    dialog._toggle_details_view()
    assert not dialog.tbl_details.isHidden()
    dialog._toggle_details_view()
    assert dialog.tbl_details.isHidden()

    # 测试接收配额数据并更新进度条与倒计时
    mock_quota_data = {
        "success": True,
        "mode": "live",
        "latency_ms": 15,
        "target_port": 4975,
        "groups": {
            "Claude": {"remaining_pct": 85.5, "reset_desc": "4小时后重置"},
            "Gemini Pro": {"remaining_pct": 96.0, "reset_desc": "2小时后重置"},
            "Gemini Flash": {"remaining_pct": 72.0, "reset_desc": "1小时后重置"},
            "GPT-OSS": {"remaining_pct": 100.0, "reset_desc": "已就绪"},
        },
        "models": [
            {"label": "Claude Sonnet 4.6", "remaining_pct": 85.5, "reset_time": "2026-09-19T18:00:00Z", "reset_desc": "4小时后重置"}
        ]
    }
    dialog._on_quotas_received(mock_quota_data)
    assert "85.5%" in dialog.card_widgets["Claude"]["lbl_pct"].text()
    assert dialog.card_widgets["Claude"]["bar"].value() == 85
    assert "4小时后重置" in dialog.card_widgets["Claude"]["lbl_reset"].text()
    assert dialog.tbl_details.rowCount() == 1
    dialog.close()


def test_window_pos_manager_ui_antigravity_button():
    from window_manager.ui import WindowPosManagerUI, AntigravityAccountManagerDialog
    # 验证关键方法与弹窗类存在
    assert hasattr(WindowPosManagerUI, 'open_antigravity_account_manager')
    assert hasattr(WindowPosManagerUI, '_update_ag_tray_submenu')
    assert AntigravityAccountManagerDialog is not None

    # 验证 ui.py 源码中定义了 btn_ag_manager 并挂载到 open_antigravity_account_manager
    ui_py = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'webTools', 'window_manager', 'ui.py'))
    with open(ui_py, 'r', encoding='utf-8') as f:
        src = f.read()
    assert 'self.btn_ag_manager = QPushButton("🚀 Antigravity 账户")' in src
    assert 'self.btn_ag_manager.clicked.connect(self.open_antigravity_account_manager)' in src


def test_antigravity_cards_grid_dedup_and_rendering(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from window_manager.ui import AntigravityAccountManagerDialog
    from window_manager import antigravity_manager
    app = QApplication.instance() or QApplication([])

    mock_curr = {
        "name": "Alpha Trader",
        "email": "alpha.trader@quant.com",
        "masked_email": "a***r@quant.com",
        "masked_summary": "Alpha Trader <a***r@quant.com>"
    }
    mock_accounts = [
        {
            "name": "Alpha Trader",
            "email": "alpha.trader@quant.com",
            "masked_email": "a***r@quant.com",
            "mtime": 1000
        },
        {
            "name": "Beta Quant",
            "email": "beta.quant@gmail.com",
            "masked_email": "b***t@gmail.com",
            "mtime": 2000
        },
        {
            "name": "Gamma AI",
            "email": "gamma.ai@deepmind.com",
            "masked_email": "g***i@deepmind.com",
            "mtime": 1500
        }
    ]
    mock_cached = {
        "beta.quant@gmail.com": {
            "groups": {
                "Gemini Pro": {"remaining_pct": 60.0, "reset_desc": "3小时后重置"},
                "Claude": {"remaining_pct": 40.0, "reset_desc": "1小时后重置"}
            }
        }
    }

    monkeypatch.setattr(antigravity_manager, "get_current_account", lambda: mock_curr)
    monkeypatch.setattr(antigravity_manager, "list_accounts", lambda: mock_accounts)
    monkeypatch.setattr(antigravity_manager, "get_cached_quotas", lambda: mock_cached)

    dialog = AntigravityAccountManagerDialog(auto_fetch=False)
    
    # 验证去重后的卡片数量完全匹配账户数量
    assert len(dialog.account_cards) == 3
    assert "alpha.trader@quant.com" in dialog.account_cards
    assert "beta.quant@gmail.com" in dialog.account_cards
    assert "gamma.ai@deepmind.com" in dialog.account_cards

    # 验证当前活跃账户卡片
    curr_card = dialog.account_cards["alpha.trader@quant.com"]
    assert curr_card["is_active"] is True
    assert curr_card["btn_use"].text() == "✔ 当前生效"
    assert not curr_card["btn_use"].isEnabled()

    # 验证备用账户卡片及缓存配额呈现
    beta_card = dialog.account_cards["beta.quant@gmail.com"]
    assert beta_card["is_active"] is False
    assert beta_card["btn_use"].text() == "⇋ 切换 (Use)"
    assert beta_card["btn_use"].isEnabled()
    # 验证缓存的配额已正确注入进卡片
    assert "60.0%" in beta_card["models"]["Gemini Pro"]["lbl"].text()
    assert "3小时后重置" in beta_card["models"]["Gemini Pro"]["lbl"].text()
    assert beta_card["models"]["Gemini Pro"]["bar"].value() == 60

    # 验证无缓存备用账户显示提示
    gamma_card = dialog.account_cards["gamma.ai@deepmind.com"]
    assert "⚪ 切换激活" in gamma_card["models"]["Claude"]["lbl"].text()

    dialog.close()


def test_window_pos_manager_ui_compact_bottom_bar_and_tools_menu(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from window_manager.ui import WindowPosManagerUI
    from window_manager import core
    app = QApplication.instance() or QApplication([])

    # Mock screen, autostart, hotkey and tray to avoid OS-level conflicts during pytest
    monkeypatch.setattr(core, "is_autostart_enabled_for_current_app", lambda: False)
    monkeypatch.setattr(core, "check_and_add_route", lambda cfg: (True, "OK"))
    monkeypatch.setattr(WindowPosManagerUI, "bind_hotkey", lambda self, hk: True)
    monkeypatch.setattr(WindowPosManagerUI, "setup_tray_icon", lambda self: None)

    ui = WindowPosManagerUI()
    
    # 1. 验证日志控制台恢复原版协调高度 (默认 110px 比例，告别 48px 过扁问题)
    assert ui.log_group.height() == 110
    assert hasattr(ui, "btn_log_compact")
    assert hasattr(ui, "btn_log_normal")
    assert hasattr(ui, "btn_log_expand")

    # 验证日志高度动态调节与持久化
    ui.set_log_panel_height(65)
    assert ui.log_group.height() == 65
    assert ui.config_manager.config_data.get("log_panel_height") == 65

    ui.set_log_panel_height(160)
    assert ui.log_group.height() == 160
    assert ui.config_manager.config_data.get("log_panel_height") == 160

    # 2. 验证底栏【🛠️ 扩展工具】下拉菜单按钮存在且文本无多余重复箭头
    assert hasattr(ui, "btn_tools_menu")
    assert "扩展工具" in ui.btn_tools_menu.text()
    assert "▼" not in ui.btn_tools_menu.text() # 杜绝重复箭头
    assert not ui.btn_tools_menu.isHidden()

    # 3. 验证开机自启复选框紧随左侧热键组，且默认显示
    assert hasattr(ui, "chk_autostart")
    assert not ui.chk_autostart.isHidden()

    # 4. 验证默认收纳模式：5个辅助工具按钮与收纳按钮默认隐藏收纳
    tools_btns = [ui.btn_open_perf, ui.btn_route_settings, ui.btn_acer_perf, ui.btn_ramdisk_sync, ui.btn_ag_manager]
    for b in tools_btns:
        assert b.isHidden()
    assert ui.btn_collapse_tools.isHidden()
    
    # 5. 验证平铺模式切换：调用 toggle_tools_expand_mode
    ui.toggle_tools_expand_mode()
    assert ui.btn_tools_menu.isHidden()
    assert not ui.btn_collapse_tools.isHidden()
    for b in tools_btns:
        assert not b.isHidden()
    # 验证持久化状态为 True
    assert ui.config_manager.config_data.get("tools_expanded_mode") is True

    # 6. 验证通过【⇋ 收纳】按钮一键切回收纳模式
    ui.btn_collapse_tools.click() # 模拟操盘手点击收纳按钮
    assert not ui.btn_tools_menu.isHidden()
    assert ui.btn_collapse_tools.isHidden()
    for b in tools_btns:
        assert b.isHidden()
    # 验证持久化状态恢复为 False
    assert ui.config_manager.config_data.get("tools_expanded_mode") is False

    # 释放后台守护线程，避免影响其他测试
    if getattr(ui, '_hotkey_thread', None):
        ui._hotkey_thread.stop()
    if hasattr(ui, 'ramdisk_sync_worker') and ui.ramdisk_sync_worker:
        ui.ramdisk_sync_worker.stop()
    if hasattr(ui, 'single_instance_server') and ui.single_instance_server:
        ui.single_instance_server.close()

    ui.close()


def test_acer_performance_dialog_and_route_dialog_decoupling(monkeypatch):
    """验证 Acer 性能控制从路由设置中彻底独立解耦"""
    from PyQt6.QtWidgets import QApplication
    from window_manager.ui import RouteConfigDialog, AcerPerformanceDialog
    from window_manager.core import ConfigManager
    import tempfile

    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_cfg_path = os.path.join(tmpdir, "test_config.json")
        with open(tmp_cfg_path, "w", encoding="utf-8") as f:
            json.dump({
                "routing_config": {"enabled": True, "destination": "192.168.1.0", "mask": "255.255.255.0", "gateway": "192.168.1.1"},
                "magnetic_keywords": ["同花顺", "通达信"],
                "acer_performance": {"overclock_mode": "Extreme", "coolboost": True, "fan_mode": "Max", "post_action": "hide"}
            }, f)

        cfg_mgr = ConfigManager(tmp_cfg_path)

        # 1. 验证 RouteConfigDialog 仅包含 2 个 Tab (静态路由 + 磁吸窗口)，不再包含 Acer 性能控制
        route_dlg = RouteConfigDialog(cfg_mgr)
        assert route_dlg.tab_widget.count() == 2
        assert "静态路由" in route_dlg.tab_widget.tabText(0)
        assert "磁吸窗口" in route_dlg.tab_widget.tabText(1)
        assert not hasattr(route_dlg, "acer_controller")
        route_dlg.close()

        # 2. 验证 AcerPerformanceDialog 独立对话框
        acer_dlg = AcerPerformanceDialog(cfg_mgr)
        assert acer_dlg.windowTitle() == "🚀 Acer 笔记本性能与散热控制中心"
        assert hasattr(acer_dlg, "rad_oc_default")
        assert hasattr(acer_dlg, "rad_oc_fast")
        assert hasattr(acer_dlg, "rad_oc_extreme")
        assert hasattr(acer_dlg, "chk_coolboost")
        assert hasattr(acer_dlg, "rad_fan_auto")
        assert hasattr(acer_dlg, "rad_fan_max")
        assert hasattr(acer_dlg, "rad_fan_custom")
        assert hasattr(acer_dlg, "spn_startup_delay")

        # 验证读取到的初始配置
        assert acer_dlg.rad_oc_extreme.isChecked()
        assert acer_dlg.chk_coolboost.isChecked()
        assert acer_dlg.rad_fan_max.isChecked()
        assert acer_dlg.rad_post_hide.isChecked()

        # 切换选项并保存
        acer_dlg.rad_oc_fast.setChecked(True)
        acer_dlg.rad_fan_auto.setChecked(True)
        acer_dlg.save_settings()

        saved_acer_cfg = cfg_mgr.get_acer_performance_config()
        assert saved_acer_cfg.get("overclock_mode") == "Fast"
        assert saved_acer_cfg.get("fan_mode") == "Auto"
        acer_dlg.close()





