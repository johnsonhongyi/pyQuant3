# -*- coding: utf-8 -*-
"""
Antigravity 账户管理与多 IDE 状态自动同步引擎
集成在桌面窗口管理器 (manage_window_layout) 架构下：
1. 本地多账户管理：识别当前激活账户、枚举本地账户配置、支持无损切换
2. 跨 IDE 双向智能同步：根据变动时序与数据新鲜度，自动双向对齐 Antigravity 与 Antigravity IDE
3. 配置文件自动持续保鲜：随着 IDE 运行产生的新 Token / UserStatus，自动同步持久化更新回本地账户 JSON 文件
4. 容灾自愈与新账户自动建档：当账户目录丢失或在任一 IDE 发现新登录账户时，全自动自愈备份并对齐数据库
5. 后台守护线程：AntigravitySyncWorker 实时监听数据库与账户目录变动，自动保鲜与对齐
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


def auto_backup_new_accounts_from_databases(accounts_dir: str = ACCOUNTS_DIR) -> list:
    """
    【容灾与新账户自愈核心】：
    当本地账户目录缺失、文件损坏，或者用户在 Antigravity / Antigravity IDE 中新登录了任何账户，
    系统自动扫描目标数据库和源数据库，识别未收录的新账户并自动在账户库中创建备份，
    同时在单边数据库损坏或丢失时实现跨数据库自愈恢复！
    """
    os.makedirs(accounts_dir, exist_ok=True)
    discovered = []

    # 优先检查目标库(Antigravity IDE)，再检查源库(Antigravity)
    db_candidates = [
        ("Antigravity IDE (目标库)", NEW_DB_PATH, OLD_DB_PATH),
        ("Antigravity (源库)", OLD_DB_PATH, NEW_DB_PATH)
    ]

    for db_desc, db_path, peer_db_path in db_candidates:
        if not os.path.exists(db_path):
            continue
        data = read_db_data(db_path)
        if not data or not data.get("antigravityAuthStatus"):
            continue

        detail = parse_account_detail(data.get("antigravityAuthStatus"))
        email = detail.get("email")
        if not email:
            continue

        acc_file = os.path.join(accounts_dir, f"{email}.json")
        # 1. 如果账户文件在本地账户库中不存在，自动建立新账户备份！
        if not os.path.exists(acc_file):
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
                temp_file = acc_file + f".tmp_{int(time.time() * 1000)}"
                with open(temp_file, "w", encoding="utf-8") as fp:
                    json.dump(content_map, fp, indent=2, ensure_ascii=False)
                os.replace(temp_file, acc_file)

                name = detail.get("name") or "Antigravity User"
                msg = f"【容灾自愈】从 {db_desc} 自动识别新账户 [{name} ({email})] 并建立本地备份！"
                logger.info(msg)
                discovered.append((email, name, acc_file, msg))
            except Exception as e:
                logger.error(f"自动备份新账户失败 ({email}): {e}")

        # 2. 如果对方数据库不存在或严重损坏，执行跨库自愈同步
        peer_data = read_db_data(peer_db_path) if os.path.exists(peer_db_path) else None
        if not peer_data or not peer_data.get("antigravityAuthStatus"):
            try:
                keys_to_heal = {k: data[k] for k in SYNC_KEYS if k in data and data[k] is not None}
                if keys_to_heal:
                    write_db_data(peer_db_path, keys_to_heal)
                    logger.info(f"【数据库自愈】成功从 {db_desc} 自愈恢复另一侧损坏/丢失的数据库: {peer_db_path}")
            except Exception as e:
                logger.error(f"数据库自愈恢复异常: {e}")

    return discovered


def get_current_account(db_path: str = None) -> dict:
    """获取当前生效活跃账户（优先从最新修改且有效的库读取）"""
    if db_path:
        paths_to_check = [db_path]
    else:
        cands = [NEW_DB_PATH, OLD_DB_PATH]
        # 按修改时间与存在性排序
        paths_to_check = sorted(cands, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)

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
    """扫描并列出所有已配置/备份的账户（包含自动自愈新账户能力）"""
    # 前置自动自愈：若目录不存在或数据库有未备份新账户，全自动建档
    auto_backup_new_accounts_from_databases(accounts_dir)

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


def persist_active_account_to_file(accounts_dir: str = ACCOUNTS_DIR, force: bool = False) -> tuple:
    """
    核心保鲜机制：将 IDE 当前运行产生的最新 Token / UserStatus 自动回写更新到本地账户配置文件中。
    随着 IDE 运行时间推移，Token 刷新与状态更新将被全自动持久化保留。
    """
    os.makedirs(accounts_dir, exist_ok=True)
    
    cands = [NEW_DB_PATH, OLD_DB_PATH]
    valid_paths = [p for p in cands if os.path.exists(p)]
    if not valid_paths:
        return False, "未找到任何可用的 Antigravity 数据库", None

    sorted_paths = sorted(valid_paths, key=lambda p: os.path.getmtime(p), reverse=True)
    latest_db = sorted_paths[0]
    data = read_db_data(latest_db)
    if not data or not data.get("antigravityAuthStatus"):
        if len(sorted_paths) > 1:
            latest_db = sorted_paths[1]
            data = read_db_data(latest_db)

    if not data or not data.get("antigravityAuthStatus"):
        return False, "数据库中未找到活跃的账户认证数据", None

    detail = parse_account_detail(data.get("antigravityAuthStatus"))
    email = detail.get("email")
    if not email:
        return False, "未能从当前认证信息中解析有效邮箱", None

    account_file = os.path.join(accounts_dir, f"{email}.json")

    new_content = {}
    for k in [
        'antigravityAuthStatus',
        'antigravityUnifiedStateSync.oauthToken',
        'antigravityUnifiedStateSync.userStatus',
        'oauthToken',
        'userStatus',
        'antigravityOnboarding',
    ]:
        if k in data and data[k] is not None:
            new_content[k] = data[k]

    has_changed = True
    if os.path.exists(account_file) and not force:
        try:
            with open(account_file, "r", encoding="utf-8") as fp:
                old_json = json.load(fp)
            changed_keys = [k for k in new_content if new_content[k] != old_json.get(k)]
            if not changed_keys:
                has_changed = False
        except Exception:
            has_changed = True

    if not has_changed:
        return False, f"账户配置文件已是最新 ({email})", account_file

    temp_file = account_file + f".tmp_{int(time.time() * 1000)}"
    try:
        with open(temp_file, "w", encoding="utf-8") as fp:
            json.dump(new_content, fp, indent=2, ensure_ascii=False)
        if os.path.exists(account_file):
            try:
                os.replace(temp_file, account_file)
            except Exception:
                os.remove(account_file)
                os.rename(temp_file, account_file)
        else:
            os.rename(temp_file, account_file)

        msg = f"成功将 IDE 最新认证凭据自动同步更新至配置文件: {os.path.basename(account_file)}"
        logger.info(msg)
        return True, msg, account_file
    except Exception as e:
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except Exception: pass
        msg = f"持久化账户配置文件失败 ({email}): {e}"
        logger.error(msg)
        return False, msg, None


def backup_current_account(accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """手动备份当前活跃账户"""
    return persist_active_account_to_file(accounts_dir=accounts_dir, force=True)


def switch_account(target: str, accounts_dir: str = ACCOUNTS_DIR, auto_sync: bool = True) -> tuple:
    """切换到指定账户并在切换时执行一次完整的自检、保鲜与同步"""
    persist_active_account_to_file(accounts_dir=accounts_dir)
    auto_backup_new_accounts_from_databases(accounts_dir=accounts_dir)

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
        do_sync(auto_persist_to_file=True)

    return True, f"已成功切换账户至 {user_summary}"


def do_sync(auto_persist_to_file: bool = True) -> tuple:
    """
    双向智能对齐同步 + 账户文件保鲜 + 缺失自愈：
    1. 自动执行容灾检测，若数据库有未建档账户立即自动备份；
    2. 智能识别最新源数据库，双向同步对齐；
    3. 持续将最新 Token 与状态持久化回配置文件。
    """
    # 0. 容灾检测：若有新登录账号或目录缺失，全自动建档
    new_accs = auto_backup_new_accounts_from_databases(ACCOUNTS_DIR)

    exists_old = os.path.exists(OLD_DB_PATH)
    exists_new = os.path.exists(NEW_DB_PATH)

    if not exists_old and not exists_new:
        return False, "未找到任何 Antigravity 数据库"

    old_data = read_db_data(OLD_DB_PATH) if exists_old else {}
    new_data = read_db_data(NEW_DB_PATH) if exists_new else {}

    mtime_old = os.path.getmtime(OLD_DB_PATH) if exists_old else 0
    mtime_new = os.path.getmtime(NEW_DB_PATH) if exists_new else 0

    is_new_fresher = (mtime_new > mtime_old + 0.5) and bool(new_data and new_data.get('antigravityAuthStatus'))

    source_data = new_data if is_new_fresher else old_data
    target_data = old_data if is_new_fresher else new_data
    source_name = "Antigravity IDE (目标库)" if is_new_fresher else "Antigravity (源库)"
    target_db_path = OLD_DB_PATH if is_new_fresher else NEW_DB_PATH

    if not source_data:
        return False, "源数据库暂不可用或为空"

    keys_to_update = {}
    for k in SYNC_KEYS:
        if k in source_data and source_data[k] != target_data.get(k):
            keys_to_update[k] = source_data[k]

    db_updated = False
    source_user = extract_account_summary(source_data.get('antigravityAuthStatus'))
    
    if keys_to_update:
        count = write_db_data(target_db_path, keys_to_update)
        if count > 0:
            db_updated = True
            logger.info(f"成功从 {source_name} 同步 {count} 项配置至另一端数据库！当前账号: {source_user}")

    file_updated = False
    file_msg = ""
    if auto_persist_to_file:
        f_ok, f_msg, _ = persist_active_account_to_file(ACCOUNTS_DIR)
        if f_ok:
            file_updated = True
            file_msg = f_msg

    if new_accs:
        acc_names = ", ".join([f"{a[1]} <{a[0]}>" for a in new_accs])
        return True, f"已自动从数据库备份新账户 [{acc_names}] 并完成同步！"
    elif db_updated and file_updated:
        return True, f"已双向同步更新数据库与本地配置文件: {source_user}"
    elif db_updated:
        return True, f"已同步最新配置至数据库: {source_user}"
    elif file_updated:
        return True, file_msg
    else:
        return False, f"数据已是最新，两边与本地配置均保持一致: {source_user}"


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
    """后台持续监控 Antigravity 变动并自动同步与保鲜配置的工作线程"""

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
        logger.info("[AntigravitySyncWorker] 自动同步与保鲜守护线程已启动")

        try:
            changed, msg = do_sync(auto_persist_to_file=True)
            if changed and self.on_sync_callback:
                self.on_sync_callback(msg)
        except Exception as e:
            logger.error(f"初次同步异常: {e}")

        last_mtime_old = os.path.getmtime(OLD_DB_PATH) if os.path.exists(OLD_DB_PATH) else 0
        last_mtime_new = os.path.getmtime(NEW_DB_PATH) if os.path.exists(NEW_DB_PATH) else 0
        last_mtime_acc = os.path.getmtime(ACCOUNTS_DIR) if os.path.exists(ACCOUNTS_DIR) else 0

        while self._running and not self._stop_event.is_set():
            try:
                mtime_old = os.path.getmtime(OLD_DB_PATH) if os.path.exists(OLD_DB_PATH) else 0
                mtime_new = os.path.getmtime(NEW_DB_PATH) if os.path.exists(NEW_DB_PATH) else 0
                mtime_acc = os.path.getmtime(ACCOUNTS_DIR) if os.path.exists(ACCOUNTS_DIR) else 0

                if mtime_old != last_mtime_old or mtime_new != last_mtime_new or mtime_acc != last_mtime_acc:
                    last_mtime_old = mtime_old
                    last_mtime_new = mtime_new
                    last_mtime_acc = mtime_acc
                    time.sleep(0.5)
                    changed, msg = do_sync(auto_persist_to_file=True)
                    if changed and self.on_sync_callback:
                        self.on_sync_callback(msg)

                self._stop_event.wait(self.check_interval_sec)
            except Exception as e:
                logger.error(f"[AntigravitySyncWorker] 循环巡检异常: {e}")
                self._stop_event.wait(2.0)

        logger.info("[AntigravitySyncWorker] 守护线程已退出")
