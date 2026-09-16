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

    dummy = DummyUI()
    WindowPosManagerUI._update_ag_tray_submenu(dummy)
    actions = sub_menu.actions()
    assert len(actions) >= 4
    action_texts = [a.text() for a in actions]
    assert any('当前' in t or 'Current' in t for t in action_texts)
    assert any('同步' in t or 'Sync' in t for t in action_texts)
    assert any('备份' in t or 'Backup' in t for t in action_texts)
