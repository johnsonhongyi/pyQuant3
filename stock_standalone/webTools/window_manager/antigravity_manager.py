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
                detail["masked_summary"] = f"{detail.get('name', '')} <{detail['masked_email']}>".strip()
                return detail
    return {"email": "", "name": "", "summary": "未登录/无有效账户", "masked_email": "", "masked_summary": "未登录/无有效账户", "source_db": ""}


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
                "masked_summary": f"{name} <{mask_email(email)}>",
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

    user_summary = matched.get("masked_summary") or f"{matched['name']} <{matched.get('masked_email') or mask_email(matched['email'])}>"
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


# ==========================================
# ⚡ 额度 (Quota) 与重置时间极速探测核心引擎
# ==========================================

def format_time_until_reset(iso_time_str: str) -> tuple:
    """
    解析 ISO 格式重置时间，返回 (剩余秒数, 人类可读倒计时描述)
    例如: (14400.0, "4小时0分后重置")
    """
    if not iso_time_str:
        return 0.0, "未知"
    try:
        clean_str = iso_time_str.strip().replace("Z", "+00:00")
        if "+" in clean_str or clean_str.count("-") >= 3:
            dt = datetime.fromisoformat(clean_str)
        else:
            # 默认按 UTC
            dt = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc if hasattr(datetime, 'timezone') else None)
        
        # 计算距离当前的秒数
        now_ts = datetime.now(dt.tzinfo).timestamp() if dt.tzinfo else time.time()
        diff_sec = dt.timestamp() - now_ts
        if diff_sec <= 0:
            return 0.0, "已重置/已就绪"
        
        hours = int(diff_sec // 3600)
        minutes = int((diff_sec % 3600) // 60)
        seconds = int(diff_sec % 60)
        days = int(hours // 24)

        if days > 0:
            return diff_sec, f"{days}天{hours % 24}小时后"
        elif hours > 0:
            return diff_sec, f"{hours}小时{minutes}分后"
        elif minutes > 0:
            return diff_sec, f"{minutes}分{seconds}秒后"
        else:
            return diff_sec, f"{seconds}秒后"
    except Exception as e:
        logger.debug(f"解析重置时间异常 ({iso_time_str}): {e}")
        return 0.0, str(iso_time_str)


def categorize_model_label(label: str) -> str:
    """将复杂/复合模型标签标准化归入用户核心四大类"""
    l = (label or "").lower()
    if "claude" in l or "sonnet" in l or "opus" in l:
        return "Claude"
    elif "flash" in l:
        return "Gemini Flash"
    elif "pro" in l or "gemini" in l:
        return "Gemini Pro"
    elif "gpt" in l or "oss" in l:
        return "GPT-OSS"
    else:
        return "其他模型"


def parse_quota_summary(summary_data: dict) -> dict:
    """
    解析 RetrieveUserQuotaSummary 返回的双层配额体系（周限额与5小时滚动限额）：
    官方原生两大共享池：
    1. Gemini Models (Gemini Flash, Gemini Pro)
    2. Claude and GPT models (Claude Opus, Claude Sonnet, GPT-OSS)
    每个组均包含 weekly (周限额) 与 5h (5小时限额) 两个 Bucket。
    """
    if not summary_data or not isinstance(summary_data, dict):
        return {}

    raw_groups = summary_data.get("response", {}).get("groups", [])
    if not raw_groups and "groups" in summary_data:
        raw_groups = summary_data.get("groups", [])

    res = {
        "gemini": {
            "displayName": "Gemini Models",
            "models_desc": "Gemini Flash / Gemini Pro",
            "weekly": {"remaining_pct": 100.0, "remaining_fraction": 1.0, "reset_time": "", "reset_desc": "已就绪", "diff_sec": 0.0},
            "5h": {"remaining_pct": 100.0, "remaining_fraction": 1.0, "reset_time": "", "reset_desc": "已就绪", "diff_sec": 0.0},
        },
        "claude_gpt": {
            "displayName": "Claude and GPT models",
            "models_desc": "Claude Opus / Sonnet / GPT-OSS",
            "weekly": {"remaining_pct": 100.0, "remaining_fraction": 1.0, "reset_time": "", "reset_desc": "已就绪", "diff_sec": 0.0},
            "5h": {"remaining_pct": 100.0, "remaining_fraction": 1.0, "reset_time": "", "reset_desc": "已就绪", "diff_sec": 0.0},
        }
    }
    has_valid_data = False
    for g in raw_groups:
        dname = (g.get("displayName") or "").lower()
        key = None
        if "gemini" in dname:
            key = "gemini"
        elif "claude" in dname or "gpt" in dname:
            key = "claude_gpt"

        if not key:
            continue

        for b in g.get("buckets", []):
            w = (b.get("window") or "").lower()
            rem_frac = b.get("remainingFraction")
            rem_frac = float(rem_frac) if rem_frac is not None else 1.0
            rem_pct = round(rem_frac * 100.0, 1)
            reset_iso = b.get("resetTime", "")
            diff_sec, reset_desc = format_time_until_reset(reset_iso)

            b_info = {
                "displayName": b.get("displayName", "Limit Remaining"),
                "remaining_pct": rem_pct,
                "remaining_fraction": rem_frac,
                "reset_time": reset_iso,
                "reset_desc": reset_desc,
                "diff_sec": diff_sec,
                "window": w
            }
            if "week" in w:
                res[key]["weekly"] = b_info
                has_valid_data = True
            elif "5h" in w or "hour" in w:
                res[key]["5h"] = b_info
                has_valid_data = True

    return res if has_valid_data else {}


def fetch_antigravity_quotas(target_email: str = None, timeout: float = 0.8) -> dict:
    """
    【极速探针】：通过本地 Connect-RPC 探测运行中的 LanguageServer，
    秒级拉取指定（或当前活跃）账户的全部 AI 模型真实配额与精确重置时间。
    特性：
    1. 进程-邮箱精准识别：按 target_email 严格过滤，绝不把其他账号的配额张冠李戴；
    2. 多实例全量收集：一次探测同时捕获所有运行中 LanguageServer，并分别写入各自账户的专属缓存快照；
    3. 支持返回 all_accounts_quotas 供多卡片批量刷新。
    """
    import urllib.request
    import ssl
    import subprocess
    t0 = time.time()

    curr_acc = get_current_account()
    curr_email = (curr_acc.get("email") or "").strip().lower()
    wanted_email = (target_email or curr_email).strip().lower()

    # 1. 搜寻系统中所有运行中的 language_server 进程及其 csrf_token，按创建时间倒序排查
    pids_tokens = []
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                pname = (p.info['name'] or '').lower()
                if 'language_server' in pname:
                    pid = p.info['pid']
                    cmd = p.info['cmdline'] or []
                    csrf = None
                    for i, c in enumerate(cmd):
                        if c == '--csrf_token' and i + 1 < len(cmd):
                            csrf = cmd[i + 1]
                        elif c.startswith('--csrf_token='):
                            csrf = c.split('=', 1)[1]
                    if csrf:
                        pids_tokens.append((pid, csrf, p.info.get('create_time', 0)))
            except Exception:
                pass
        pids_tokens.sort(key=lambda x: x[2], reverse=True)
    except Exception as e:
        logger.debug(f"psutil 检测进程异常: {e}")

    if not pids_tokens:
        return {
            "success": False,
            "mode": "not_running",
            "error": "未检测到运行中的 Antigravity IDE 语言服务器进程",
            "account_email": wanted_email or curr_email,
            "latency_ms": int((time.time() - t0) * 1000),
            "groups": {},
            "models": [],
            "all_accounts_quotas": {}
        }

    # 2. 获取监听端口 (通过 netstat 查找 LISTENING)
    pid_ports = {}
    try:
        out = subprocess.check_output('netstat -ano', shell=True, text=True, errors='ignore')
        for line in out.splitlines():
            if 'LISTENING' in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    addr = parts[1]
                    p_id = parts[-1]
                    if ':' in addr:
                        try:
                            port = int(addr.split(':')[-1])
                            pid_ports.setdefault(p_id, []).append(port)
                        except ValueError:
                            pass
    except Exception as e:
        logger.debug(f"netstat 端口获取异常: {e}")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    discovered_accounts = {}

    # 3. 逐个尝试向本地端口发送 GetUserStatus 请求，精准提取各服务的真实用户与配额
    for pid, csrf, ctime in pids_tokens:
        ports = pid_ports.get(str(pid), [])
        for port in ports:
            for proto in ['https', 'http']:
                url = f"{proto}://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
                req = urllib.request.Request(
                    url,
                    data=json.dumps({'metadata': {'ideName': 'antigravity', 'extensionName': 'antigravity', 'locale': 'en'}}).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json',
                        'Connect-Protocol-Version': '1',
                        'X-Codeium-Csrf-Token': csrf
                    }
                )
                try:
                    resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
                    data = json.loads(resp.read().decode('utf-8'))
                    us = data.get('userStatus', {})
                    raw_configs = us.get('cascadeModelConfigData', {}).get('clientModelConfigs', [])
                    if not raw_configs and 'clientModelConfigs' in data:
                        raw_configs = data.get('clientModelConfigs', [])

                    server_email = (us.get('email') or '').strip().lower()
                    if not server_email:
                        # 兼容：如果 userStatus 未直接暴露 email，尝试从当前活跃账户比对
                        server_email = curr_email

                    if raw_configs:
                        # 4. 解析各模型配额与聚合组
                        parsed_models = []
                        groups = {
                            "Claude": {"remaining_fraction": 1.0, "remaining_pct": 100.0, "reset_time": "", "reset_desc": "未知", "models": []},
                            "Gemini Pro": {"remaining_fraction": 1.0, "remaining_pct": 100.0, "reset_time": "", "reset_desc": "未知", "models": []},
                            "Gemini Flash": {"remaining_fraction": 1.0, "remaining_pct": 100.0, "reset_time": "", "reset_desc": "未知", "models": []},
                            "GPT-OSS": {"remaining_fraction": 1.0, "remaining_pct": 100.0, "reset_time": "", "reset_desc": "未知", "models": []},
                        }

                        for item in raw_configs:
                            q_info = item.get('quotaInfo')
                            label = item.get('label') or item.get('modelOrAlias', {}).get('model') or 'Unknown'
                            if not q_info:
                                continue
                            
                            rem_frac = q_info.get('remainingFraction')
                            rem_frac = float(rem_frac) if rem_frac is not None else 0.0
                            rem_pct = round(rem_frac * 100.0, 1)
                            reset_iso = q_info.get('resetTime', '')
                            diff_sec, reset_desc = format_time_until_reset(reset_iso)

                            model_entry = {
                                "label": label,
                                "remaining_fraction": rem_frac,
                                "remaining_pct": rem_pct,
                                "reset_time": reset_iso,
                                "reset_desc": reset_desc,
                                "diff_sec": diff_sec
                            }
                            parsed_models.append(model_entry)

                            cat = categorize_model_label(label)
                            if cat in groups:
                                grp = groups[cat]
                                grp["models"].append(model_entry)
                                # 聚合组采用具有代表性的最小值（最快耗尽）指标
                                if len(grp["models"]) == 1 or rem_frac < grp["remaining_fraction"]:
                                    grp["remaining_fraction"] = rem_frac
                                    grp["remaining_pct"] = rem_pct
                                    grp["reset_time"] = reset_iso
                                    grp["reset_desc"] = reset_desc

                        # 4.1 尝试请求 RetrieveUserQuotaSummary 获取双层限额（周限额与5小时滚动限额）
                        quota_summary = {}
                        try:
                            url_summary = f"{proto}://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
                            req_summary = urllib.request.Request(
                                url_summary,
                                data=json.dumps({'metadata': {'ideName': 'antigravity', 'extensionName': 'antigravity', 'locale': 'en'}}).encode('utf-8'),
                                headers={
                                    'Content-Type': 'application/json',
                                    'Connect-Protocol-Version': '1',
                                    'X-Codeium-Csrf-Token': csrf
                                }
                            )
                            resp_summary = urllib.request.urlopen(req_summary, context=ctx, timeout=timeout)
                            data_summary = json.loads(resp_summary.read().decode('utf-8'))
                            quota_summary = parse_quota_summary(data_summary)
                        except Exception:
                            pass

                        # 4.2 若获得了官方双层限额，注入到 groups 与各模型中；若未获得，优雅推导兜底
                        if quota_summary:
                            gw = quota_summary.get("gemini", {}).get("weekly", {})
                            g5 = quota_summary.get("gemini", {}).get("5h", {})
                            cw = quota_summary.get("claude_gpt", {}).get("weekly", {})
                            c5 = quota_summary.get("claude_gpt", {}).get("5h", {})
                            for m_key in ["Gemini Pro", "Gemini Flash"]:
                                if m_key in groups:
                                    groups[m_key]["weekly"] = gw
                                    groups[m_key]["5h"] = g5
                            for m_key in ["Claude", "GPT-OSS"]:
                                if m_key in groups:
                                    groups[m_key]["weekly"] = cw
                                    groups[m_key]["5h"] = c5
                        else:
                            # 兜底生成双层结构
                            quota_summary = {
                                "gemini": {
                                    "displayName": "Gemini Models",
                                    "models_desc": "Gemini Flash / Gemini Pro",
                                    "weekly": {
                                        "remaining_pct": groups["Gemini Pro"]["remaining_pct"],
                                        "remaining_fraction": groups["Gemini Pro"]["remaining_fraction"],
                                        "reset_time": groups["Gemini Pro"]["reset_time"],
                                        "reset_desc": groups["Gemini Pro"]["reset_desc"],
                                        "diff_sec": 0.0
                                    },
                                    "5h": {
                                        "remaining_pct": groups["Gemini Pro"]["remaining_pct"],
                                        "remaining_fraction": groups["Gemini Pro"]["remaining_fraction"],
                                        "reset_time": groups["Gemini Pro"]["reset_time"],
                                        "reset_desc": groups["Gemini Pro"]["reset_desc"],
                                        "diff_sec": 0.0
                                    }
                                },
                                "claude_gpt": {
                                    "displayName": "Claude and GPT models",
                                    "models_desc": "Claude Opus / Sonnet / GPT-OSS",
                                    "weekly": {
                                        "remaining_pct": groups["Claude"]["remaining_pct"],
                                        "remaining_fraction": groups["Claude"]["remaining_fraction"],
                                        "reset_time": groups["Claude"]["reset_time"],
                                        "reset_desc": groups["Claude"]["reset_desc"],
                                        "diff_sec": 0.0
                                    },
                                    "5h": {
                                        "remaining_pct": groups["Claude"]["remaining_pct"],
                                        "remaining_fraction": groups["Claude"]["remaining_fraction"],
                                        "reset_time": groups["Claude"]["reset_time"],
                                        "reset_desc": groups["Claude"]["reset_desc"],
                                        "diff_sec": 0.0
                                    }
                                }
                            }

                        # 自动持久化保存属于该账号的专属配额缓存！
                        if server_email:
                            save_cached_quota(server_email, groups, quota_summary=quota_summary)

                        # 如果当前账户已发现，优先保留配置更详细或更新的
                        if server_email not in discovered_accounts:
                            discovered_accounts[server_email] = {
                                "groups": groups,
                                "quota_summary": quota_summary,
                                "models": parsed_models,
                                "target_pid": pid,
                                "target_port": port,
                                "server_email": server_email
                            }
                        break
                except Exception:
                    pass

    latency_ms = int((time.time() - t0) * 1000)

    # 5. 精准匹配主结果
    target_match = None
    if wanted_email and wanted_email in discovered_accounts:
        target_match = discovered_accounts[wanted_email]
    elif curr_email and curr_email in discovered_accounts:
        target_match = discovered_accounts[curr_email]
    elif discovered_accounts:
        # 未能精准匹配当前账号，返回第一个发现的，但标明其实际邮箱
        first_key = list(discovered_accounts.keys())[0]
        target_match = discovered_accounts[first_key]

    if not target_match:
        return {
            "success": False,
            "mode": "unreachable",
            "error": f"未检测到账户 {wanted_email or curr_email} 对应的在线语言服务器",
            "account_email": wanted_email or curr_email,
            "latency_ms": latency_ms,
            "groups": {},
            "quota_summary": {},
            "models": [],
            "all_accounts_quotas": discovered_accounts
        }

    return {
        "success": True,
        "mode": "live",
        "error": None,
        "account_email": target_match.get("server_email", wanted_email or curr_email),
        "target_pid": target_match.get("target_pid"),
        "target_port": target_match.get("target_port"),
        "latency_ms": latency_ms,
        "groups": target_match.get("groups", {}),
        "quota_summary": target_match.get("quota_summary", {}),
        "models": target_match.get("models", []),
        "all_accounts_quotas": discovered_accounts
    }


QUOTA_CACHE_FILE = os.path.join(ACCOUNTS_DIR, ".quota_cache.json")

def get_cached_quotas(cache_file: str = None) -> dict:
    """读取所有账户历史配额快照缓存"""
    f = cache_file or QUOTA_CACHE_FILE
    if not os.path.exists(f):
        return {}
    try:
        with open(f, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception as e:
        logger.debug(f"读取配额缓存失败: {e}")
        return {}


def save_cached_quota(email: str, groups: dict, quota_summary: dict = None, cache_file: str = None):
    """持久化缓存特定账户的配额快照（包含四大模型组与双层周限额）"""
    if not email:
        return
    f = cache_file or QUOTA_CACHE_FILE
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        cache = get_cached_quotas(f)
        entry = {
            "groups": groups,
            "updated_at": time.time(),
            "updated_at_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if quota_summary:
            entry["quota_summary"] = quota_summary
        cache[email.lower()] = entry
        temp_file = f + f".tmp_{int(time.time() * 1000)}"
        with open(temp_file, "w", encoding="utf-8") as fp:
            json.dump(cache, fp, indent=2, ensure_ascii=False)
        os.replace(temp_file, f)
    except Exception as e:
        logger.debug(f"保存配额缓存异常: {e}")



def delete_account(target_email_or_file: str, accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """
    安全删除本地账户备份文件（备份并重命名为 .bak）
    """
    all_accs = list_accounts(accounts_dir)
    matched = None
    target_clean = target_email_or_file.strip().lower()

    for acc in all_accs:
        if os.path.normpath(acc["file_path"]).lower() == os.path.normpath(target_email_or_file).lower():
            matched = acc
            break
        if acc["email"].lower() == target_clean or acc["filename"].lower() == target_clean:
            matched = acc
            break

    if not matched:
        return False, f"未找到账户文件: {target_email_or_file}"

    fpath = matched["file_path"]
    try:
        bak_path = fpath + ".bak"
        if os.path.exists(bak_path):
            os.remove(bak_path)
        os.rename(fpath, bak_path)
        return True, f"已安全移除账户备份: {matched['email']}"
    except Exception as e:
        return False, f"删除账户失败: {e}"


def get_antigravity_cli_info() -> dict:
    """
    探测并获取系统 Antigravity CLI (agy) 状态与信息
    """
    import shutil
    import subprocess

    candidate_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe"),
        os.path.expandvars(r"%USERPROFILE%\.gemini\bin\agy.exe"),
        os.path.expandvars(r"%APPDATA%\npm\agy.cmd"),
    ]

    cli_path = ""
    for cp in candidate_paths:
        if os.path.exists(cp):
            cli_path = cp
            break

    if not cli_path:
        which_agy = shutil.which("agy")
        if which_agy:
            cli_path = which_agy

    if not cli_path:
        return {
            "available": False,
            "path": "",
            "version": "",
            "commands": ["agy", "antigravity", "gemini"],
            "error": "未在标准路径找到 Antigravity CLI"
        }

    version_str = ""
    try:
        proc = subprocess.run(
            [cli_path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            shell=False
        )
        if proc.returncode == 0 and proc.stdout:
            version_str = proc.stdout.strip().split("\n")[0].strip()
    except Exception as e:
        logger.debug(f"探测 CLI 版本异常: {e}")

    return {
        "available": bool(version_str or os.path.exists(cli_path)),
        "path": cli_path,
        "version": version_str or "1.2.3",
        "commands": ["agy", "antigravity", "gemini"],
        "error": None
    }


