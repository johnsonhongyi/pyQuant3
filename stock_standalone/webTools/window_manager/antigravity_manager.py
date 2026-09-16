# -*- coding: utf-8 -*-
"""
Antigravity 账户管理与多 IDE 状态自动同步引擎
集成在桌面窗口管理器 (manage_window_layout) 架构下：
1. 本地多账户管理：识别当前激活账户、枚举本地账户配置、支持无损切换
2. 跨 IDE 双向同步：从 Antigravity 自动增量/全量同步至 Antigravity IDE
3. 后台守护线程：AntigravitySyncWorker 实时监听数据库与账户目录变动，自动同步
"""

import os
import sys
import time
import json
import glob
import sqlite3
import logging
import threading
from datetime import datetime

logger = logging.getLogger("window_manager.antigravity")

OLD_DB_PATH = os.path.expandvars(r"%APPDATA%\Antigravity\User\globalStorage\state.vscdb")
NEW_DB_PATH = os.path.expandvars(r"%APPDATA%\Antigravity IDE\User\globalStorage\state.vscdb")
ACCOUNTS_DIR = os.path.expandvars(r"%USERPROFILE%\.antigravity-agent\antigravity-accounts")

SYNC_KEYS = [
    'antigravityAuthStatus',
    'oauthToken',
    'userStatus',
    'antigravityOnboarding',
    'antigravityUnifiedStateSync.oauthToken',
    'antigravityUnifiedStateSync.userStatus',
]


def mask_email(email: str) -> str:
    """邮箱脱敏打码函数，保护隐私显示"""
    if not email or "@" not in email:
        return email or "None"
    parts = email.split("@")
    if len(parts) != 2:
        return email
    local, domain = parts[0], parts[1]
    if len(local) <= 1:
        return f"{local}*@{domain}"
    elif len(local) == 2:
        return f"{local[0]}*@{domain}"
    else:
        return f"{local[0]}***{local[-1]}@{domain}"


def ensure_db_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def read_db_data(db_path: str):
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ItemTable'")
        if not cur.fetchone():
            conn.close()
            return None
        cur.execute("SELECT key, value FROM ItemTable")
        data = {k: v for k, v in cur.fetchall()}
        conn.close()
        return data
    except Exception as e:
        logger.warning(f"读取数据库异常 ({db_path}): {e}")
        return None


def write_db_data(db_path: str, data_dict: dict) -> int:
    ensure_db_dir(db_path)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        updated = 0
        for k, v in data_dict.items():
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", (k, v))
            updated += 1
        conn.commit()
        conn.close()
        return updated
    except Exception as e:
        logger.error(f"写入数据库失败 ({db_path}): {e}")
        return 0


def extract_account_summary(auth_val) -> str:
    if not auth_val:
        return "None"
    try:
        d = json.loads(auth_val) if isinstance(auth_val, str) else auth_val
        email = d.get("email", "unknown_email")
        name = d.get("name", "unknown_name")
        return f"{name} ({email})"
    except Exception:
        return f"Token(len={len(str(auth_val))})"


def parse_account_detail(auth_val) -> dict:
    if not auth_val:
        return {}
    try:
        d = json.loads(auth_val) if isinstance(auth_val, str) else auth_val
        return {
            "email": d.get("email", ""),
            "name": d.get("name", ""),
            "has_api_key": bool(d.get("apiKey")),
            "raw": d
        }
    except Exception:
        return {}


def get_current_account(db_path: str = None) -> dict:
    """获取当前生效活跃账户"""
    paths_to_check = [db_path] if db_path else [OLD_DB_PATH, NEW_DB_PATH]
    for p in paths_to_check:
        if not p or not os.path.exists(p):
            continue
        data = read_db_data(p)
        if data and data.get("antigravityAuthStatus"):
            detail = parse_account_detail(data["antigravityAuthStatus"])
            if detail.get("email"):
                detail["source_db"] = p
                detail["summary"] = f"{detail.get('name', '')} ({detail.get('email', '')})".strip()
                detail["masked_email"] = mask_email(detail.get("email", ""))
                return detail
    return {"email": "", "name": "", "summary": "未登录/无有效账户", "masked_email": "", "source_db": ""}


def list_accounts(accounts_dir: str = ACCOUNTS_DIR) -> list:
    """扫描并列出所有已配置/备份的账户"""
    if not os.path.exists(accounts_dir):
        return []

    account_files = glob.glob(os.path.join(accounts_dir, "*.json"))
    curr = get_current_account()
    curr_email = curr.get("email", "").lower()

    results = []
    for fpath in account_files:
        fname = os.path.basename(fpath)
        if fname.endswith(".old") or fname.endswith(".bak"):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            auth_str = data.get("antigravityAuthStatus")
            detail = parse_account_detail(auth_str)
            email = detail.get("email") or fname[:-5]
            name = detail.get("name") or "Antigravity User"
            mtime = os.path.getmtime(fpath)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

            is_current = bool(curr_email and email.lower() == curr_email)

            results.append({
                "email": email,
                "name": name,
                "summary": f"{name} ({email})",
                "masked_email": mask_email(email),
                "file_path": fpath,
                "filename": fname,
                "mtime": mtime,
                "mtime_str": mtime_str,
                "is_current": is_current,
                "data": data,
            })
        except Exception as e:
            logger.warning(f"读取账户备份失败 {fname}: {e}")

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def backup_current_account(accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """将当前活跃账户从数据库备份到 accounts_dir"""
    os.makedirs(accounts_dir, exist_ok=True)
    data = read_db_data(OLD_DB_PATH) or read_db_data(NEW_DB_PATH)
    if not data or not data.get("antigravityAuthStatus"):
        return False, "当前数据库中未找到活跃的 Antigravity 账户信息", None

    detail = parse_account_detail(data.get("antigravityAuthStatus"))
    email = detail.get("email")
    if not email:
        return False, "未能从认证信息中提取有效邮箱", None

    backup_path = os.path.join(accounts_dir, f"{email}.json")
    
    content_map = {}
    for k in [
        'antigravityAuthStatus',
        'antigravityUnifiedStateSync.oauthToken',
        'antigravityUnifiedStateSync.userStatus',
        'oauthToken',
        'userStatus',
        'antigravityOnboarding',
    ]:
        if k in data and data[k] is not None:
            content_map[k] = data[k]

    try:
        with open(backup_path, "w", encoding="utf-8") as fp:
            json.dump(content_map, fp, indent=2, ensure_ascii=False)
        msg = f"成功备份当前账户 [{detail.get('name', '')} ({email})] 至 {backup_path}"
        logger.info(msg)
        return True, msg, backup_path
    except Exception as e:
        msg = f"备份账户文件失败: {e}"
        logger.error(msg)
        return False, msg, None


def switch_account(target: str, accounts_dir: str = ACCOUNTS_DIR, auto_sync: bool = True) -> tuple:
    """
    切换到指定账户并同步到数据库
    target 可以是邮箱、部分名称或完整 json 文件路径
    """
    ok_b, msg_b, _ = backup_current_account(accounts_dir)
    if ok_b:
        logger.info(f"切换前自动留存: {msg_b}")

    all_accs = list_accounts(accounts_dir)
    if not all_accs:
        return False, f"在 {accounts_dir} 中未找到任何已保存的账户"

    matched = None
    target_clean = target.strip().lower()

    for acc in all_accs:
        if os.path.normpath(acc["file_path"]).lower() == os.path.normpath(target).lower():
            matched = acc
            break

    if not matched:
        for acc in all_accs:
            if acc["email"].lower() == target_clean:
                matched = acc
                break

    if not matched:
        for acc in all_accs:
            if target_clean in acc["email"].lower() or target_clean in acc["name"].lower():
                matched = acc
                break

    if not matched:
        available = ", ".join([a["email"] for a in all_accs])
        return False, f"未匹配到账户 '{target}'。可用账户列表: {available}"

    acc_data = matched.get("data") or {}
    if not acc_data.get("antigravityAuthStatus"):
        return False, f"目标账户文件 {matched['filename']} 缺失 antigravityAuthStatus 认证字段"

    keys_to_write = {}
    for k in SYNC_KEYS:
        if k in acc_data and acc_data[k] is not None:
            keys_to_write[k] = acc_data[k]

    if 'antigravityOnboarding' not in keys_to_write:
        keys_to_write['antigravityOnboarding'] = 'true'

    count_old = write_db_data(OLD_DB_PATH, keys_to_write)
    count_new = write_db_data(NEW_DB_PATH, keys_to_write)

    for p in [OLD_DB_PATH, NEW_DB_PATH]:
        backup_db = p + ".backup"
        if os.path.exists(backup_db):
            write_db_data(backup_db, keys_to_write)

    user_summary = matched["summary"]
    logger.info(f"✅ 成功切换至账户: {user_summary} (写入项: 源={count_old}, 目标={count_new})")

    if auto_sync:
        do_sync()

    return True, f"已成功切换账户至 {user_summary}"


def do_sync() -> tuple:
    """执行从源数据库到目标数据库的单次同步，返回 (changed, message)"""
    old_data = read_db_data(OLD_DB_PATH)
    if not old_data:
        msg = f"源数据库暂不可用或不存在: {OLD_DB_PATH}"
        logger.warning(msg)
        return False, msg

    new_data = read_db_data(NEW_DB_PATH) or {}

    keys_to_update = {}
    for k in SYNC_KEYS:
        if k in old_data and old_data[k] != new_data.get(k):
            keys_to_update[k] = old_data[k]

    old_user = extract_account_summary(old_data.get('antigravityAuthStatus'))
    new_user = extract_account_summary(new_data.get('antigravityAuthStatus'))

    if not keys_to_update:
        msg = f"数据已是最新，两边保持一致: {old_user}"
        logger.debug(msg)
        return False, msg

    msg = f"检测到变动: 源账号[{old_user}] -> 目标原账号[{new_user}]，同步 {len(keys_to_update)} 项"
    logger.info(msg)

    count = write_db_data(NEW_DB_PATH, keys_to_update)
    if count > 0:
        res_msg = f"成功同步 {count} 项配置到 Antigravity IDE！当前生效: {old_user}"
        logger.info(res_msg)
        return True, res_msg
    return False, "写入目标数据库失败"


def open_accounts_directory():
    """打开本地账户配置所在的物理文件夹"""
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    try:
        if sys.platform == 'win32':
            os.startfile(ACCOUNTS_DIR)
        else:
            import subprocess
            subprocess.Popen(['xdg-open', ACCOUNTS_DIR])
        return True, "已打开账户配置目录"
    except Exception as e:
        return False, f"打开账户配置目录失败: {e}"


class AntigravitySyncWorker(threading.Thread):
    """后台持续监控 Antigravity 变动并自动同步到 IDE 的工作线程"""

    def __init__(self, check_interval_sec: float = 1.0, on_sync_callback=None):
        super().__init__(name="AntigravitySyncWorker", daemon=True)
        self.check_interval_sec = check_interval_sec
        self.on_sync_callback = on_sync_callback
        self._running = False
        self._stop_event = threading.Event()

    def stop(self):
        self._running = False
        self._stop_event.set()

    def run(self):
        self._running = True
        logger.info("[AntigravitySyncWorker] 自动同步守护线程已启动")

        # 启动时执行一次同步
        try:
            changed, msg = do_sync()
            if changed and self.on_sync_callback:
                self.on_sync_callback(msg)
        except Exception as e:
            logger.error(f"初次同步异常: {e}")

        last_mtime_old = os.path.getmtime(OLD_DB_PATH) if os.path.exists(OLD_DB_PATH) else 0
        last_mtime_acc = os.path.getmtime(ACCOUNTS_DIR) if os.path.exists(ACCOUNTS_DIR) else 0

        while self._running and not self._stop_event.is_set():
            try:
                mtime_old = os.path.getmtime(OLD_DB_PATH) if os.path.exists(OLD_DB_PATH) else 0
                mtime_acc = os.path.getmtime(ACCOUNTS_DIR) if os.path.exists(ACCOUNTS_DIR) else 0

                if mtime_old != last_mtime_old or mtime_acc != last_mtime_acc:
                    last_mtime_old = mtime_old
                    last_mtime_acc = mtime_acc
                    time.sleep(0.5)  # 等待写入冲刷完成
                    changed, msg = do_sync()
                    if changed and self.on_sync_callback:
                        self.on_sync_callback(msg)

                self._stop_event.wait(self.check_interval_sec)
            except Exception as e:
                logger.error(f"[AntigravitySyncWorker] 循环巡检异常: {e}")
                self._stop_event.wait(2.0)

        logger.info("[AntigravitySyncWorker] 守护线程已退出")
