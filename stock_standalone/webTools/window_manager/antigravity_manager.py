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
from datetime import datetime, timezone

logger = logging.getLogger("window_manager.antigravity")

# 1. 桌面独立客户端 Antigravity (App)
APP_DB_PATH = os.path.expandvars(r"%APPDATA%\Antigravity\User\globalStorage\state.vscdb")
APP_EXE_PATH = os.path.expandvars(r"%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe")
APP_NAME = "Antigravity 客户端"
APP_TITLE = "🚀 Antigravity (桌面端)"
APP_STORAGE_PATH = os.path.expandvars(r"%APPDATA%\Antigravity\app_storage.json")
APP_LOGIN_STORAGE_KEY = "jetski.onboarding.lastLoginUsername"
APP_PROFILE_LOGIN_KEY = "__app_last_login_username"

# Antigravity App 的真实 OAuth 会话由 Windows Credential Manager 提供给
# LanguageServer。JSON / state.vscdb 只是辅助状态，不能单独代表切换成功。
APP_CREDENTIAL_TARGET = "gemini:antigravity"
APP_PROFILE_CRED_BLOB_KEY = "__app_credential_dpapi_b64"
APP_PROFILE_CRED_USER_KEY = "__app_credential_username"
APP_PROFILE_CRED_PERSIST_KEY = "__app_credential_persist"
APP_PROFILE_VERIFIED_KEY = "__app_live_verified"

# 2. 编辑器集成环境 Antigravity IDE
IDE_DB_PATH = os.path.expandvars(r"%APPDATA%\Antigravity IDE\User\globalStorage\state.vscdb")
IDE_EXE_PATH = r"D:\JohnsonProgram\AntigravityIDE\Antigravity IDE.exe"
IDE_NAME = "Antigravity IDE"
IDE_TITLE = "💻 Antigravity IDE (开发环境)"

# 兼容既有全局常量引用
OLD_DB_PATH = APP_DB_PATH
NEW_DB_PATH = IDE_DB_PATH
ACCOUNTS_DIR = os.path.expandvars(r"%USERPROFILE%\.antigravity-agent\antigravity-accounts")

SYNC_KEYS = [
    'antigravityAuthStatus',
    'oauthToken',
    'userStatus',
    'antigravityOnboarding',
    'antigravityUnifiedStateSync.oauthToken',
    'antigravityUnifiedStateSync.userStatus',
]

# Antigravity 桌面客户端额外依赖 profileUrl；Antigravity IDE 继续严格使用
# 上面的 legacy SYNC_KEYS，不共享这个字段，避免两套实现互相污染。
APP_SYNC_KEYS = [
    'antigravity.profileUrl',
    *SYNC_KEYS,
    'antigravityUnifiedStateSync.modelCredits',
]


def _collect_sync_data(data: dict, keys) -> dict:
    if not data:
        return {}
    return {k: data[k] for k in keys if k in data and data[k] is not None}


def _read_app_storage() -> dict:
    if not os.path.exists(APP_STORAGE_PATH):
        return {}
    try:
        with open(APP_STORAGE_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"读取 Antigravity app_storage.json 失败: {e}")
        return {}


def _get_app_login_username() -> str:
    value = _read_app_storage().get(APP_LOGIN_STORAGE_KEY, "")
    return str(value or "").strip().lower()


def _write_app_login_username(email: str) -> bool:
    email = str(email or "").strip()
    if not email:
        return False
    data = _read_app_storage()
    data[APP_LOGIN_STORAGE_KEY] = email
    try:
        ensure_db_dir(APP_STORAGE_PATH)
        temp = APP_STORAGE_PATH + f".tmp_{int(time.time() * 1000)}"
        with open(temp, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)
        os.replace(temp, APP_STORAGE_PATH)
        return True
    except Exception as e:
        logger.error(f"写入 Antigravity app_storage.json 登录账号失败: {e}")
        return False


def _capture_app_credential_snapshot() -> dict:
    """读取当前 App 系统凭据并用当前 Windows 用户的 DPAPI 再加密保存。"""
    if sys.platform != "win32":
        return {}
    import base64
    import ctypes
    from ctypes import wintypes

    raw_bytes = None
    username = ""
    persist = 2

    # 1. 优先使用 Windows 原生 Advapi32.dll CredReadW (对 PyInstaller 打包环境 100% 免疫，无需任何外部依赖)
    try:
        advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)

        class CREDENTIALW_READ(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(CREDENTIALW_READ))
        ]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]

        pcred = ctypes.POINTER(CREDENTIALW_READ)()
        if advapi32.CredReadW(APP_CREDENTIAL_TARGET, 1, 0, ctypes.byref(pcred)):
            cred = pcred.contents
            raw_bytes = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            username = str(cred.UserName or "")
            persist = int(cred.Persist or 2)
            advapi32.CredFree(pcred)
        else:
            last_err = ctypes.get_last_error()
            logger.debug(f"Advapi32.CredReadW 返回 False (GetLastError={last_err})")
    except Exception as e:
        logger.debug(f"Advapi32.CredReadW 读取凭据异常: {e}")

    # 2. 备用路径：如果 ctypes 读取失败，尝试通过 win32cred 读取
    if not raw_bytes:
        try:
            import win32cred
            cred = win32cred.CredRead(
                APP_CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC, 0
            )
            blob = cred.get("CredentialBlob")
            if isinstance(blob, str):
                raw_bytes = blob.encode("utf-16-le")
            elif isinstance(blob, memoryview):
                raw_bytes = blob.tobytes()
            elif blob:
                raw_bytes = bytes(blob)
            username = str(cred.get("UserName") or "")
            persist = int(cred.get("Persist") or 2)
        except Exception as e:
            logger.debug(f"win32cred.CredRead 备用读取失败: {e}")

    if not raw_bytes:
        logger.warning(f"读取 Antigravity Windows 安全凭据失败: 未能从系统凭据管理器读取到 {APP_CREDENTIAL_TARGET}")
        return {}

    # 3. 使用 Windows 原生 Crypt32.dll CryptProtectData 进行 DPAPI 加密 (打包安全且无需 pywin32 模块依赖)
    protected_bytes = None
    try:
        crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        in_buf = (ctypes.c_byte * len(raw_bytes)).from_buffer_copy(raw_bytes)
        in_blob = DATA_BLOB(len(raw_bytes), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()

        if crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "Antigravity App account credential backup",
            None, None, None, 0,
            ctypes.byref(out_blob)
        ):
            protected_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            kernel32.LocalFree(out_blob.pbData)
        else:
            last_err = ctypes.get_last_error()
            logger.debug(f"Crypt32.CryptProtectData 返回 False (GetLastError={last_err})")
    except Exception as e:
        logger.debug(f"Crypt32.CryptProtectData 异常: {e}")

    # 4. 备用 DPAPI 加密：win32crypt
    if not protected_bytes:
        try:
            import win32crypt
            protected_bytes = win32crypt.CryptProtectData(
                raw_bytes,
                "Antigravity App account credential backup",
                None, None, None, 0,
            )
        except Exception as e:
            logger.debug(f"win32crypt.CryptProtectData 备用加密失败: {e}")

    if not protected_bytes:
        logger.warning("对 Antigravity 安全凭据执行 DPAPI 加密失败")
        return {}

    return {
        APP_PROFILE_CRED_BLOB_KEY: base64.b64encode(protected_bytes).decode("ascii"),
        APP_PROFILE_CRED_USER_KEY: username,
        APP_PROFILE_CRED_PERSIST_KEY: persist,
    }


def _write_generic_credential_blob(target: str, username: str, blob: bytes, persist: int = 2) -> bool:
    """通过 Win32 CredWriteW 写回不透明凭据 blob；不解析、不输出凭据内容。"""
    if sys.platform != "win32" or not target or not blob:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        blob_buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = CREDENTIALW()
        credential.Flags = 0
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.Comment = None
        credential.LastWritten = wintypes.FILETIME(0, 0)
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(
            blob_buffer, ctypes.POINTER(ctypes.c_ubyte)
        )
        credential.Persist = int(persist or 2)
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = str(username or "")

        advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
        advapi32.CredWriteW.restype = wintypes.BOOL
        if advapi32.CredWriteW(ctypes.byref(credential), 0):
            return True
        last_err = ctypes.get_last_error()
        logger.warning(f"Advapi32.CredWriteW 返回 False (GetLastError={last_err})")
    except Exception as e:
        logger.debug(f"Advapi32.CredWriteW 写回异常: {e}")

    # 备用路径：win32cred
    try:
        import win32cred
        cred_dict = {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target,
            "UserName": str(username or ""),
            "CredentialBlob": blob,
            "Persist": int(persist or win32cred.CRED_PERSIST_LOCAL_MACHINE),
        }
        win32cred.CredWrite(cred_dict, 0)
        return True
    except Exception as e:
        logger.error(f"恢复 Antigravity Windows 安全凭据失败: {e}")
        return False


def _restore_app_credential_snapshot(profile: dict) -> bool:
    if not profile or not profile.get(APP_PROFILE_CRED_BLOB_KEY):
        return False
    import base64
    try:
        protected = base64.b64decode(profile[APP_PROFILE_CRED_BLOB_KEY])
    except Exception as e:
        logger.error(f"Base64 解码安全凭据快照失败: {e}")
        return False

    blob = None

    # 1. 优先使用 Windows 原生 Crypt32.dll CryptUnprotectData (零外部模块依赖，打包最稳)
    try:
        import ctypes
        from ctypes import wintypes
        crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        in_buf = (ctypes.c_byte * len(protected)).from_buffer_copy(protected)
        in_blob = DATA_BLOB(len(protected), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()

        if crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None, None, None, None, 0,
            ctypes.byref(out_blob)
        ):
            blob = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            kernel32.LocalFree(out_blob.pbData)
    except Exception as e:
        logger.debug(f"Crypt32.CryptUnprotectData 解密异常: {e}")

    # 2. 备用解密路径：win32crypt
    if not blob:
        try:
            import win32crypt
            _, blob = win32crypt.CryptUnprotectData(
                protected, None, None, None, 0
            )
        except Exception as e:
            logger.debug(f"win32crypt.CryptUnprotectData 备用解密失败: {e}")

    if not blob:
        logger.error("解密 Antigravity App 安全凭据失败: DPAPI 未能解密数据")
        return False

    return _write_generic_credential_blob(
        APP_CREDENTIAL_TARGET,
        profile.get(APP_PROFILE_CRED_USER_KEY, ""),
        blob,
        int(profile.get(APP_PROFILE_CRED_PERSIST_KEY, 2) or 2),
    )


def _has_app_credential_snapshot(profile: dict) -> bool:
    return bool(
        profile
        and profile.get(APP_PROFILE_VERIFIED_KEY)
        and profile.get(APP_PROFILE_CRED_BLOB_KEY)
    )


APP_PROFILES_DIRNAME = "app_profiles"


def _app_profile_path(email: str, accounts_dir: str = ACCOUNTS_DIR) -> str:
    return os.path.join(accounts_dir, APP_PROFILES_DIRNAME, f"{email}.json")


def _load_app_profile(email: str, accounts_dir: str = ACCOUNTS_DIR) -> dict:
    path = _app_profile_path(email, accounts_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {}


def _save_app_profile(
    email: str,
    data: dict,
    accounts_dir: str = ACCOUNTS_DIR,
    credential_snapshot: dict = None,
    live_verified: bool = None,
) -> str:
    profile_dir = os.path.join(accounts_dir, APP_PROFILES_DIRNAME)
    os.makedirs(profile_dir, exist_ok=True)
    path = _app_profile_path(email, accounts_dir)
    temp = path + f".tmp_{int(time.time() * 1000)}"

    # 保留已有安全凭据快照；普通状态刷新不能把它覆盖掉。
    snapshot = _load_app_profile(email, accounts_dir)
    for key, value in _collect_sync_data(data, APP_SYNC_KEYS).items():
        snapshot[key] = value
    snapshot[APP_PROFILE_LOGIN_KEY] = str(email or "").strip().lower()

    if credential_snapshot:
        snapshot.update(credential_snapshot)
    if live_verified is not None:
        snapshot[APP_PROFILE_VERIFIED_KEY] = bool(live_verified)

    with open(temp, "w", encoding="utf-8") as fp:
        json.dump(snapshot, fp, indent=2, ensure_ascii=False)
    os.replace(temp, path)
    return path


def _find_saved_account_without_autosync(target: str, accounts_dir: str = ACCOUNTS_DIR):
    """App 专用账户查找：只读共享 JSON，绝不触发 list_accounts() 的跨库自愈。"""
    target_clean = (target or "").strip().lower()
    for fpath in glob.glob(os.path.join(accounts_dir, "*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            detail = parse_account_detail(data.get("antigravityAuthStatus"))
            email = (detail.get("email") or "").strip()
            name = (detail.get("name") or "").strip()
            if (
                os.path.normpath(fpath).lower() == os.path.normpath(target).lower()
                or email.lower() == target_clean
                or target_clean in email.lower()
                or target_clean in name.lower()
            ):
                return {
                    "email": email,
                    "name": name,
                    "file_path": fpath,
                    "filename": os.path.basename(fpath),
                    "data": data,
                    "masked_summary": f"{name} <{mask_email(email)}>".strip(),
                }
        except Exception:
            continue
    return None


def _pid_belongs_to_app(pid: int) -> bool:
    """判断 LanguageServer/子进程是否属于桌面 App，而不是 Antigravity IDE。"""
    try:
        import psutil
        proc = psutil.Process(int(pid))
        app_exe = os.path.normcase(os.path.normpath(APP_EXE_PATH))
        ide_exe = os.path.normcase(os.path.normpath(IDE_EXE_PATH))
        for _ in range(12):
            try:
                name = (proc.name() or "").lower()
                exe = proc.exe() or ""
            except Exception:
                name, exe = "", ""
            exe_norm = os.path.normcase(os.path.normpath(exe)) if exe else ""
            if exe_norm == ide_exe or "antigravity ide" in name:
                return False
            if exe_norm == app_exe or name == "antigravity.exe":
                return True
            parent = proc.parent()
            if parent is None:
                break
            proc = parent
    except Exception:
        pass
    return False


def _probe_app_live_email(timeout: float = 0.5) -> str:
    """从 App 自己的 LanguageServer GetUserStatus 回读真实在线邮箱。"""
    try:
        result = fetch_antigravity_quotas(target_email="", timeout=timeout)
        discovered = result.get("all_accounts_quotas") or {}
        for email, info in discovered.items():
            pid = info.get("target_pid")
            if pid and _pid_belongs_to_app(pid):
                return str(email or "").strip().lower()
        pid = result.get("target_pid")
        if result.get("success") and pid and _pid_belongs_to_app(pid):
            return str(result.get("account_email") or "").strip().lower()
    except Exception as e:
        logger.debug(f"App 在线账户探针失败: {type(e).__name__}")
    return ""


def _get_app_processes() -> list:
    try:
        import psutil
        result = []
        app_exe = os.path.normcase(os.path.normpath(APP_EXE_PATH))
        ide_exe = os.path.normcase(os.path.normpath(IDE_EXE_PATH))
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = (proc.info.get("name") or "").lower()
                exe = proc.info.get("exe") or ""
                exe_norm = os.path.normcase(os.path.normpath(exe)) if exe else ""
                if exe_norm == ide_exe or "antigravity ide" in name:
                    continue
                if exe_norm == app_exe or name == "antigravity.exe":
                    result.append(proc)
            except Exception:
                continue
        return result
    except Exception:
        return []


def _is_antigravity_app_running() -> bool:
    """快速判断桌面 Antigravity App 是否仍有主进程存活。"""
    return bool(_get_antigravity_running_flags()[0])


def _wait_for_antigravity_app_stopped(timeout: float = 7.0) -> bool:
    """等待旧 App 完全退出；切换账户时禁止旧实例未退净就启动新实例。"""
    deadline = time.monotonic() + max(0.5, float(timeout))
    while time.monotonic() < deadline:
        if not _is_antigravity_app_running():
            # Electron/文件锁释放留一个很短的稳定窗口。
            time.sleep(0.12)
            return not _is_antigravity_app_running()
        time.sleep(0.10)
    return not _is_antigravity_app_running()


def _stop_antigravity_app(timeout: float = 5.0) -> bool:
    """仅关闭桌面 App 进程树，并确认 Antigravity.exe 已完全退出。"""
    try:
        import psutil
        roots = _get_app_processes()

        # 正常路径：按已识别的 Electron 根进程及其子树优雅结束。
        if roots:
            targets = {}
            for root in roots:
                targets[root.pid] = root
                try:
                    for child in root.children(recursive=True):
                        targets[child.pid] = child
                except Exception:
                    pass
            procs = list(targets.values())
            for proc in reversed(procs):
                try:
                    proc.terminate()
                except Exception:
                    pass
            _, alive = psutil.wait_procs(procs, timeout=max(0.5, timeout))
            for proc in alive:
                try:
                    proc.kill()
                except Exception:
                    pass
            if alive:
                psutil.wait_procs(alive, timeout=2.0)

        # 容灾路径：原生检测仍显示 App 存活，但 psutil 没拿到对象时，
        # 用精确镜像名强制结束 Antigravity.exe；不会匹配 Antigravity IDE.exe。
        if _is_antigravity_app_running():
            try:
                import subprocess
                subprocess.run(
                    ["taskkill", "/IM", "Antigravity.exe", "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3.0,
                    check=False,
                )
            except Exception:
                pass

        return _wait_for_antigravity_app_stopped(timeout=max(2.0, timeout))
    except Exception as e:
        logger.error(f"关闭 Antigravity App 失败: {type(e).__name__}")
        return False


def _launch_antigravity_app() -> bool:
    if not os.path.exists(APP_EXE_PATH):
        logger.error(f"未找到 Antigravity App: {APP_EXE_PATH}")
        return False
    try:
        import subprocess
        subprocess.Popen(
            [APP_EXE_PATH],
            cwd=os.path.dirname(APP_EXE_PATH) or None,
            close_fds=True,
        )
        return True
    except Exception as e:
        logger.error(f"启动 Antigravity App 失败: {type(e).__name__}")
        return False


def _wait_for_app_live_email(expected_email: str, timeout: float = 10.0) -> str:
    expected = str(expected_email or "").strip().lower()
    deadline = time.monotonic() + max(1.0, timeout)
    last_email = ""
    while time.monotonic() < deadline:
        last_email = _probe_app_live_email(timeout=0.45)
        if last_email and (not expected or last_email == expected):
            return last_email
        time.sleep(0.4)
    return last_email


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


def _replace_app_sync_state(db_path: str, data_dict: dict) -> int:
    """仅替换 App 固定账户字段；不碰 IDE，也不清理其它命名空间。"""
    state = _collect_sync_data(data_dict, APP_SYNC_KEYS)
    ensure_db_dir(db_path)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        placeholders = ",".join("?" for _ in APP_SYNC_KEYS)
        cur.execute(
            f"DELETE FROM ItemTable WHERE key IN ({placeholders})",
            tuple(APP_SYNC_KEYS),
        )
        for k, v in state.items():
            cur.execute(
                "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                (k, v),
            )
        conn.commit()
        conn.close()
        return len(state)
    except Exception as e:
        logger.error(f"替换 Antigravity App 账户状态失败 ({db_path}): {e}")
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


def get_dual_target_active_accounts(probe_live: bool = True) -> tuple:
    """
    独立获取 Antigravity 独立客户端与 Antigravity IDE 当前分别在使用的账户邮箱。
    返回: (app_active_email, ide_active_email)
    """
    app_email = ""
    ide_email = ""

    # 1. 独立客户端当前账户：运行时以 LanguageServer 回读为最高权威。
    # app_storage / state.vscdb 只用于 App 离线时显示“上次配置”，不能证明切换成功。
    app_email = ""
    if probe_live and _get_app_processes():
        app_email = _probe_app_live_email(timeout=0.35)
    if not app_email:
        app_email = _get_app_login_username()
    if not app_email:
        target_app_db = OLD_DB_PATH
        if os.path.exists(target_app_db):
            app_d = read_db_data(target_app_db)
            if app_d and app_d.get("antigravityAuthStatus"):
                app_acc = parse_account_detail(app_d["antigravityAuthStatus"])
                app_email = (app_acc.get("email") or "").strip().lower()

    # 2. IDE 当前账户
    target_ide_db = NEW_DB_PATH
    if os.path.exists(target_ide_db):
        ide_d = read_db_data(target_ide_db)
        if ide_d and ide_d.get("antigravityAuthStatus"):
            ide_acc = parse_account_detail(ide_d["antigravityAuthStatus"])
            ide_email = (ide_acc.get("email") or "").strip().lower()

    return app_email, ide_email


def list_accounts(
    accounts_dir: str = ACCOUNTS_DIR,
    auto_discover: bool = True,
    active_accounts: tuple = None,
) -> list:
    """扫描账户；可复用调用方已取得的活跃账户快照，避免重复在线探针。"""
    if auto_discover:
        auto_backup_new_accounts_from_databases(accounts_dir)

    if not os.path.exists(accounts_dir):
        return []

    account_files = glob.glob(os.path.join(accounts_dir, "*.json"))
    if active_accounts is None:
        app_active_email, ide_active_email = get_dual_target_active_accounts()
    else:
        app_active_email, ide_active_email = active_accounts

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

            email_clean = email.lower()
            is_app_active = bool(app_active_email and email_clean == app_active_email)
            is_ide_active = bool(ide_active_email and email_clean == ide_active_email)
            is_current = is_app_active or is_ide_active

            app_profile = _load_app_profile(email, accounts_dir)
            app_ready = _has_app_credential_snapshot(app_profile)

            if is_app_active and is_ide_active:
                active_role = "both"
                active_role_desc = "🟢 双端均在使用"
            elif is_app_active:
                active_role = "app"
                active_role_desc = "🚀 客户端使用中"
            elif is_ide_active:
                active_role = "ide"
                active_role_desc = "💻 IDE 使用中"
            else:
                active_role = "none"
                active_role_desc = "⚪ 备用账户"

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
                "is_app_active": is_app_active,
                "is_ide_active": is_ide_active,
                "app_ready": app_ready,
                "app_profile_verified": bool(app_profile.get(APP_PROFILE_VERIFIED_KEY)),
                "active_role": active_role,
                "active_role_desc": active_role_desc,
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
    """手动备份当前活跃账户（legacy：保持 IDE 原业务逻辑不变）。"""
    return persist_active_account_to_file(accounts_dir=accounts_dir, force=True)


def backup_current_app_account(accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """备份真实在线 App 账户，并绑定 Windows Credential Manager 安全凭据。"""
    os.makedirs(accounts_dir, exist_ok=True)

    live_email = _probe_app_live_email(timeout=0.7)
    if not live_email:
        return False, (
            "未检测到 Antigravity App 的真实在线账户。请先启动 App、确认已登录，"
            "再执行“备份客户端当前”；离线 JSON 不再作为成功依据。"
        ), None

    email = live_email.strip().lower()
    app_login_email = _get_app_login_username()
    db_data = read_db_data(OLD_DB_PATH) if os.path.exists(OLD_DB_PATH) else {}
    db_detail = parse_account_detail(db_data.get("antigravityAuthStatus"))
    db_email = (db_detail.get("email") or "").strip().lower()

    source_data = {}
    if db_email == email and db_data.get("antigravityAuthStatus"):
        source_data = dict(db_data)
    else:
        matched = _find_saved_account_without_autosync(email, accounts_dir)
        if matched and matched.get("data", {}).get("antigravityAuthStatus"):
            source_data = dict(matched["data"])
        existing_profile = _load_app_profile(email, accounts_dir)
        for key, value in existing_profile.items():
            if key in APP_SYNC_KEYS and value is not None:
                source_data[key] = value

    if not source_data.get("antigravityAuthStatus"):
        return False, (
            f"已在线确认 App 当前账户为 {mask_email(email)}，但缺少该账户基础认证快照；"
            "请保持登录后刷新一次账户状态。"
        ), None

    credential_snapshot = _capture_app_credential_snapshot()
    if not credential_snapshot:
        return False, (
            f"已在线确认 {mask_email(email)}，但未能读取系统安全凭据 "
            f"{APP_CREDENTIAL_TARGET}，因此不能建立可恢复的 App Profile。"
        ), None

    try:
        # 只在真实在线邮箱已确认后修正 app_storage，避免历史假切换污染。
        if app_login_email != email:
            _write_app_login_username(email)

        profile_path = _save_app_profile(
            email,
            source_data,
            accounts_dir,
            credential_snapshot=credential_snapshot,
            live_verified=True,
        )

        # 共享 JSON 仍保持 IDE legacy 结构，不写入 App 的系统凭据。
        legacy_file = os.path.join(accounts_dir, f"{email}.json")
        if not os.path.exists(legacy_file):
            temp_file = legacy_file + f".tmp_{int(time.time() * 1000)}"
            with open(temp_file, "w", encoding="utf-8") as fp:
                json.dump(_collect_sync_data(source_data, SYNC_KEYS), fp, indent=2, ensure_ascii=False)
            os.replace(temp_file, legacy_file)

        msg = (
            f"成功备份并在线验证 Antigravity App 账户 {mask_email(email)}；"
            "Windows 安全凭据已使用 DPAPI 加密绑定到该 App Profile。"
        )
        logger.info(msg)
        return True, msg, profile_path
    except Exception as e:
        logger.error(f"备份 Antigravity 客户端账户失败 ({email}): {e}")
        return False, f"备份 Antigravity 客户端账户失败: {e}", None


def _get_antigravity_running_flags() -> tuple:
    """轻量检测 App/IDE 是否运行；Windows 主路径避免 psutil 全进程枚举开销。"""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            TH32CS_SNAPPROCESS = 0x00000002
            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

            class PROCESSENTRY32W(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260),
                ]

            kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
            kernel32.CreateToolhelp32Snapshot.argtypes = [
                wintypes.DWORD, wintypes.DWORD
            ]
            kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            kernel32.Process32FirstW.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)
            ]
            kernel32.Process32FirstW.restype = wintypes.BOOL
            kernel32.Process32NextW.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)
            ]
            kernel32.Process32NextW.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

            handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if handle == INVALID_HANDLE_VALUE:
                raise OSError(ctypes.get_last_error())

            app_running = False
            ide_running = False
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            try:
                ok = kernel32.Process32FirstW(handle, ctypes.byref(entry))
                while ok:
                    name = (entry.szExeFile or "").lower()
                    if "antigravity ide" in name:
                        ide_running = True
                    elif name == "antigravity.exe":
                        app_running = True
                    if app_running and ide_running:
                        break
                    ok = kernel32.Process32NextW(handle, ctypes.byref(entry))
            finally:
                kernel32.CloseHandle(handle)
            return app_running, ide_running
        except Exception as e:
            logger.debug(f"Toolhelp 运行态探测失败，回退 psutil: {e}")

    try:
        import psutil
        app_running = False
        ide_running = False
        for p in psutil.process_iter(["name"]):
            try:
                name = (p.info.get("name") or "").lower()
                if "antigravity ide" in name:
                    ide_running = True
                elif name == "antigravity.exe":
                    app_running = True
            except Exception:
                pass
        return app_running, ide_running
    except Exception as e:
        logger.debug(f"运行态进程探测失败: {e}")
        return False, False


def get_runtime_app_status(probe_live: bool = True) -> dict:
    """
    实时检测当前系统正在运行的是 Antigravity 客户端 还是 Antigravity IDE。
    返回两端运行状态、活跃标识、数据库账户等全景信息。
    """
    app_running, ide_running = _get_antigravity_running_flags()

    # 读取两端数据库信息
    app_acc = None
    app_mtime = 0
    if os.path.exists(APP_DB_PATH):
        app_mtime = os.path.getmtime(APP_DB_PATH)
        d = read_db_data(APP_DB_PATH)
        if d and d.get("antigravityAuthStatus"):
            app_acc = parse_account_detail(d["antigravityAuthStatus"])

    live_app_email = (
        _probe_app_live_email(timeout=0.35)
        if (probe_live and app_running)
        else ""
    )
    app_login = _get_app_login_username()
    app_db_email = ((app_acc or {}).get("email") or "").strip().lower()
    if live_app_email:
        matched = _find_saved_account_without_autosync(live_app_email, ACCOUNTS_DIR)
        app_acc = {
            "email": live_app_email,
            "name": (matched or {}).get("name", ""),
            "source": "language_server",
        }
    elif app_login and app_login != app_db_email:
        matched = _find_saved_account_without_autosync(app_login, ACCOUNTS_DIR)
        app_acc = {
            "email": app_login,
            "name": (matched or {}).get("name", ""),
            "source": "app_storage_offline",
        }

    ide_acc = None
    ide_mtime = 0
    if os.path.exists(IDE_DB_PATH):
        ide_mtime = os.path.getmtime(IDE_DB_PATH)
        d = read_db_data(IDE_DB_PATH)
        if d and d.get("antigravityAuthStatus"):
            ide_acc = parse_account_detail(d["antigravityAuthStatus"])

    # 确定主要活跃目标
    if app_running and not ide_running:
        active_target = "app"
        status_text = "🚀 Antigravity 客户端运行中"
        status_badge = "🟢 正在使用: Antigravity 客户端"
    elif ide_running and not app_running:
        active_target = "ide"
        status_text = "💻 Antigravity IDE 运行中"
        status_badge = "🟢 正在使用: Antigravity IDE"
    elif app_running and ide_running:
        active_target = "both"
        status_text = "🚀 Antigravity 与 💻 IDE 均在运行"
        status_badge = "🟢 正在使用: 两者同时运行"
    else:
        if app_mtime >= ide_mtime:
            active_target = "app"
            status_badge = "⚪ 离线 (上次使用: Antigravity 客户端)"
        else:
            active_target = "ide"
            status_badge = "⚪ 离线 (上次使用: Antigravity IDE)"
        status_text = "⚪ 两端均未运行"

    return {
        "app_running": app_running,
        "ide_running": ide_running,
        "active_target": active_target,
        "status_text": status_text,
        "status_badge": status_badge,
        "app": {
            "name": APP_NAME,
            "title": APP_TITLE,
            "db_path": APP_DB_PATH,
            "exe_path": APP_EXE_PATH,
            "running": app_running,
            "mtime": app_mtime,
            "account": app_acc
        },
        "ide": {
            "name": IDE_NAME,
            "title": IDE_TITLE,
            "db_path": IDE_DB_PATH,
            "exe_path": IDE_EXE_PATH,
            "running": ide_running,
            "mtime": ide_mtime,
            "account": ide_acc
        }
    }


def _sync_to_app(source_account: str = None, accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """App 入口：当前账号只做真实备份；指定账号统一走事务式切换。"""
    if source_account:
        return _switch_app_account(source_account, accounts_dir=accounts_dir)

    ok, msg, _ = backup_current_app_account(accounts_dir=accounts_dir)
    return ok, msg


def sync_to_target(target: str = "app", source_account: str = None, accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """App 使用独立实现；IDE/both 精确委托修复前 legacy 实现。"""
    target_norm = (target or "app").strip().lower()
    if target_norm == "app":
        return _sync_to_app(source_account=source_account, accounts_dir=accounts_dir)
    return _legacy_sync_to_target(
        target=target_norm,
        source_account=source_account,
        accounts_dir=accounts_dir,
    )


def _legacy_sync_to_target(target: str = "app", source_account: str = None, accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """
    定向同步核心函数：
    target: "app" -> 明确同步至 Antigravity 桌面客户端 (APP_DB_PATH)
            "ide" -> 明确同步至 Antigravity IDE (IDE_DB_PATH)
            "both" -> 智能双向对齐同步至两者
    source_account: 可选指定的邮箱/文件，默认从最新活跃配置或最新文件提取
    """
    os.makedirs(accounts_dir, exist_ok=True)
    auto_backup_new_accounts_from_databases(accounts_dir=accounts_dir)

    target = (target or "app").strip().lower()

    if target == "both":
        return do_sync(auto_persist_to_file=True)

    # 确定目标数据库与名称 (兼容既有测试与新调用)
    if target == "app":
        dest_db = OLD_DB_PATH
        dest_title = APP_TITLE
        peer_db = NEW_DB_PATH
        peer_title = IDE_TITLE
    elif target == "ide":
        dest_db = NEW_DB_PATH
        dest_title = IDE_TITLE
        peer_db = OLD_DB_PATH
        peer_title = APP_TITLE
    else:
        return False, f"未知的同步目标: {target} (仅支持 'app', 'ide', 'both')"

    keys_to_write = {}
    source_desc = ""

    if source_account:
        all_accs = list_accounts(accounts_dir)
        matched = None
        s_clean = source_account.strip().lower()
        for a in all_accs:
            if a["email"].lower() == s_clean or s_clean in a["name"].lower() or s_clean == os.path.normpath(a["file_path"]).lower():
                matched = a
                break
        if matched and matched.get("data"):
            for k in SYNC_KEYS:
                if k in matched["data"] and matched["data"][k] is not None:
                    keys_to_write[k] = matched["data"][k]
            source_desc = matched.get("masked_summary") or matched["email"]

    if not keys_to_write:
        curr = get_current_account()
        curr_email = curr.get("email")
        if curr_email:
            acc_file = os.path.join(accounts_dir, f"{curr_email}.json")
            if os.path.exists(acc_file):
                try:
                    with open(acc_file, "r", encoding="utf-8") as fp:
                        adata = json.load(fp)
                    for k in SYNC_KEYS:
                        if k in adata and adata[k] is not None:
                            keys_to_write[k] = adata[k]
                    source_desc = curr.get("masked_summary") or curr_email
                except Exception:
                    pass

        if not keys_to_write and os.path.exists(peer_db):
            peer_data = read_db_data(peer_db)
            if peer_data and peer_data.get("antigravityAuthStatus"):
                for k in SYNC_KEYS:
                    if k in peer_data and peer_data[k] is not None:
                        keys_to_write[k] = peer_data[k]
                source_desc = f"来自 {peer_title} 最新状态"

    if not keys_to_write:
        return False, "未获取到可用于同步的有效账户认证数据"

    if 'antigravityOnboarding' not in keys_to_write:
        keys_to_write['antigravityOnboarding'] = 'true'

    count = write_db_data(dest_db, keys_to_write)
    backup_db = dest_db + ".backup"
    if os.path.exists(backup_db):
        write_db_data(backup_db, keys_to_write)

    persist_active_account_to_file(accounts_dir)

    msg = f"✅ 成功将配置同步至 [{dest_title}] (写入 {count} 项)！当前生效: {source_desc}"
    logger.info(msg)
    return True, msg

def _switch_app_account(target: str, accounts_dir: str = ACCOUNTS_DIR) -> tuple:
    """事务式切换 App：恢复状态+系统凭据，重启后必须在线回读目标邮箱。"""
    matched = _find_saved_account_without_autosync(target, accounts_dir)
    if not matched:
        return False, f"未匹配到 Antigravity 客户端账户 '{target}'"

    email = (matched.get("email") or "").strip().lower()
    if not email:
        return False, "目标账户缺少有效邮箱"

    app_running_before = _is_antigravity_app_running()
    live_before = (
        _probe_app_live_email(timeout=0.45)
        if app_running_before
        else ""
    )
    profile = _load_app_profile(email, accounts_dir)

    # 当前真实在线账户可以就地补建 App Profile；其它账户必须已有安全凭据快照。
    if live_before == email and not _has_app_credential_snapshot(profile):
        ok, msg, _ = backup_current_app_account(accounts_dir=accounts_dir)
        return ok, msg
    if live_before == email and _has_app_credential_snapshot(profile):
        return True, f"{mask_email(email)} 已是 Antigravity App 当前真实在线账户"

    if not _has_app_credential_snapshot(profile):
        return False, (
            f"{mask_email(email)} 尚未建立可恢复的 Antigravity App 安全凭据。"
            "该账号需要先在 Antigravity App 中真实登录一次，然后点击“备份客户端当前”。"
            "仅有 IDE/历史 JSON 不能完成 App 切换。"
        )

    merged = dict(matched.get("data") or {})
    for key, value in profile.items():
        if key in APP_SYNC_KEYS and value is not None:
            merged[key] = value
    app_keys = _collect_sync_data(merged, APP_SYNC_KEYS)
    if not app_keys.get("antigravityAuthStatus"):
        return False, f"{mask_email(email)} 的 App Profile 缺少基础认证状态"

    auth_email = (
        parse_account_detail(app_keys.get("antigravityAuthStatus")).get("email") or ""
    ).strip().lower()
    if auth_email and auth_email != email:
        return False, (
            f"App Profile 账户身份不一致：目标 {mask_email(email)}，"
            f"认证快照属于 {mask_email(auth_email)}"
        )

    # 回滚必须也能恢复当前 Windows 凭据，否则不执行风险切换。
    previous_credential = _capture_app_credential_snapshot()
    if not previous_credential:
        return False, (
            "当前 gemini:antigravity 系统凭据无法安全备份，已取消切换；"
            "未对 App 或 IDE 做任何修改。"
        )

    # 切换前重新确认运行态：已打开则必须先完整退出；未打开则直接准备新状态。
    was_running = _is_antigravity_app_running()
    if was_running:
        logger.info("检测到 Antigravity App 已运行，切换账户前先完整关闭旧实例")
        if not _stop_antigravity_app():
            return False, "检测到 Antigravity App 已打开，但无法完整关闭旧实例，已取消切换"
        if not _wait_for_antigravity_app_stopped(timeout=5.0):
            return False, "Antigravity App 旧实例未完全退出，已取消启动新账户实例"
    else:
        logger.info("Antigravity App 当前未运行，直接准备目标账户后启动")

    import shutil
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    db_existed = os.path.exists(OLD_DB_PATH)
    storage_existed = os.path.exists(APP_STORAGE_PATH)
    db_rescue = OLD_DB_PATH + f".switch_rescue_{stamp}"
    storage_rescue = APP_STORAGE_PATH + f".switch_rescue_{stamp}"
    rescue_meta = os.path.join(
        accounts_dir, APP_PROFILES_DIRNAME, f".switch_rescue_{stamp}.json"
    )
    os.makedirs(os.path.dirname(rescue_meta), exist_ok=True)

    try:
        if db_existed:
            shutil.copy2(OLD_DB_PATH, db_rescue)
        if storage_existed:
            shutil.copy2(APP_STORAGE_PATH, storage_rescue)
        with open(rescue_meta, "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "previous_credential": previous_credential,
                    "previous_login": _get_app_login_username(),
                    "was_running": was_running,
                },
                fp,
                indent=2,
                ensure_ascii=False,
            )

        count = _replace_app_sync_state(OLD_DB_PATH, app_keys)
        if count <= 0:
            raise RuntimeError("App state.vscdb 写入失败")
        if not _write_app_login_username(email):
            raise RuntimeError("app_storage 登录身份写入失败")
        if not _restore_app_credential_snapshot(profile):
            raise RuntimeError("Windows Credential Manager 凭据恢复失败")

        # 启动前最后一道硬门：旧 Antigravity.exe 必须已经完全退出。
        if _is_antigravity_app_running():
            raise RuntimeError("旧 Antigravity App 实例仍在运行，拒绝启动第二个实例")

        if not _launch_antigravity_app():
            raise RuntimeError("Antigravity App 启动失败")

        live_after = _wait_for_app_live_email(email, timeout=10.0)
        if live_after != email:
            actual = mask_email(live_after) if live_after else "未检测到在线账户"
            raise RuntimeError(
                f"LanguageServer 在线校验未通过，实际: {actual}"
            )

        written = read_db_data(OLD_DB_PATH) or {}
        _save_app_profile(email, written, accounts_dir, live_verified=True)

        for rescue in (db_rescue, storage_rescue, rescue_meta):
            try:
                if os.path.exists(rescue):
                    os.remove(rescue)
            except Exception:
                pass

        user_summary = matched.get("masked_summary") or mask_email(email)
        msg = (
            f"已真实切换 Antigravity App 至 {user_summary}；"
            f"LanguageServer 在线回读验证通过（写入 {count} 项 App 状态）。"
        )
        logger.info(f"✅ {msg}")
        return True, msg

    except Exception as e:
        logger.error(f"Antigravity App 切换失败，开始自动回滚: {e}")
        _stop_antigravity_app()

        rollback_ok = True
        try:
            if db_existed and os.path.exists(db_rescue):
                shutil.copy2(db_rescue, OLD_DB_PATH)
            elif not db_existed and os.path.exists(OLD_DB_PATH):
                os.remove(OLD_DB_PATH)
        except Exception:
            rollback_ok = False

        try:
            if storage_existed and os.path.exists(storage_rescue):
                shutil.copy2(storage_rescue, APP_STORAGE_PATH)
            elif not storage_existed and os.path.exists(APP_STORAGE_PATH):
                os.remove(APP_STORAGE_PATH)
        except Exception:
            rollback_ok = False

        if not _restore_app_credential_snapshot(previous_credential):
            rollback_ok = False

        if was_running:
            _launch_antigravity_app()

        if rollback_ok:
            for rescue in (db_rescue, storage_rescue, rescue_meta):
                try:
                    if os.path.exists(rescue):
                        os.remove(rescue)
                except Exception:
                    pass

        suffix = "已自动恢复原账户状态。" if rollback_ok else (
            f"自动回滚未完全成功，请保留救援文件: {rescue_meta}"
        )
        return False, f"Antigravity App 实际切换失败：{e}；{suffix}"


def switch_account(target: str, accounts_dir: str = ACCOUNTS_DIR, auto_sync: bool = True, sync_target: str = "both") -> tuple:
    """App 使用独立实现；IDE/both 精确委托修复前 legacy 实现。"""
    target_norm = (sync_target or "both").lower()
    if target_norm == "app":
        return _switch_app_account(target, accounts_dir=accounts_dir)
    return _legacy_switch_account(
        target,
        accounts_dir=accounts_dir,
        auto_sync=auto_sync,
        sync_target=target_norm,
    )


def _legacy_switch_account(target: str, accounts_dir: str = ACCOUNTS_DIR, auto_sync: bool = True, sync_target: str = "both") -> tuple:
    """
    切换到指定账户：
    sync_target: "both" (同时更新客户端与IDE)
                 "app" (仅更新 Antigravity 客户端)
                 "ide" (仅更新 Antigravity IDE)
    """
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

    sync_target = (sync_target or "both").lower()
    targets_written = []

    target_app_db = OLD_DB_PATH
    target_ide_db = NEW_DB_PATH

    if sync_target in ("both", "app"):
        count_app = write_db_data(target_app_db, keys_to_write)
        backup_app = target_app_db + ".backup"
        if os.path.exists(backup_app):
            write_db_data(backup_app, keys_to_write)
        targets_written.append(f"客户端({count_app}项)")

    if sync_target in ("both", "ide"):
        count_ide = write_db_data(target_ide_db, keys_to_write)
        backup_ide = target_ide_db + ".backup"
        if os.path.exists(backup_ide):
            write_db_data(backup_ide, keys_to_write)
        targets_written.append(f"IDE({count_ide}项)")

    user_summary = matched.get("masked_summary") or f"{matched['name']} <{matched.get('masked_email') or mask_email(matched['email'])}>"
    logger.info(f"✅ 成功切换至账户: {user_summary} (目标: {', '.join(targets_written)})")

    if auto_sync and sync_target == "both":
        do_sync(auto_persist_to_file=True)

    dest_name = APP_TITLE if sync_target == "app" else (IDE_TITLE if sync_target == "ide" else "两端应用(客户端 & IDE)")
    return True, f"已成功切换账户至 {user_summary} [目标: {dest_name}]"

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
    根据真实系统当前时钟实时动态计算，绝不死板使用缓存旧时间。
    例如: (14400.0, "4小时0分后") 或 (0.0, "已重置/已就绪")
    """
    if not iso_time_str:
        return 0.0, "已就绪"
    try:
        clean_str = str(iso_time_str).strip()
        if not clean_str:
            return 0.0, "已就绪"
        # 统一处理 Z 为 +00:00 (UTC)
        clean_str = clean_str.replace("Z", "+00:00")
        
        # 兼容纳秒：若小数秒部分超过 6 位，安全截断至 6 位 (微秒)
        if "." in clean_str:
            base, rest = clean_str.split(".", 1)
            tz_part = ""
            if "+" in rest:
                sub_sec, tz_part = rest.split("+", 1)
                tz_part = "+" + tz_part
            elif "-" in rest and rest.count("-") == 1:
                sub_sec, tz_part = rest.split("-", 1)
                tz_part = "-" + tz_part
            else:
                sub_sec = rest
            sub_sec = sub_sec[:6]
            clean_str = f"{base}.{sub_sec}{tz_part}"

        dt = None
        try:
            dt = datetime.fromisoformat(clean_str)
        except Exception:
            pass

        if dt is None:
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(clean_str, fmt)
                    break
                except Exception:
                    pass

        if dt is None:
            return 0.0, str(iso_time_str)

        # 统一转换为 UTC 时间戳计算当前剩余秒数
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        now_ts = datetime.now(timezone.utc).timestamp()
        diff_sec = dt.timestamp() - now_ts
        if diff_sec <= 0:
            return 0.0, "已重置/已就绪"
        
        hours = int(diff_sec // 3600)
        minutes = int((diff_sec % 3600) // 60)
        seconds = int(diff_sec % 60)
        days = int(hours // 24)

        if days > 0:
            return diff_sec, f"{days}天{hours % 24}小时{minutes}分后"
        elif hours > 0:
            return diff_sec, f"{hours}小时{minutes}分后"
        elif minutes > 0:
            return diff_sec, f"{minutes}分{seconds}秒后"
        else:
            return diff_sec, f"{seconds}秒后"
    except Exception as e:
        logger.debug(f"解析重置时间异常 ({iso_time_str}): {e}")
        return 0.0, str(iso_time_str)


def resolve_quota_reset_desc(quota_entry: dict, fallback_updated_at: float = None) -> tuple:
    """
    动态解析特定配额项当前的真实剩余倒计时：
    优先基于绝对 reset_time 结合当前系统时钟进行实时计算；
    若缺少 reset_time 但有旧 diff_sec 与更新时间戳，则根据时间流逝衰减计算；
    返回值: (diff_sec: float, reset_desc: str)
    """
    if not quota_entry or not isinstance(quota_entry, dict):
        return 0.0, "已就绪"
    
    reset_time = quota_entry.get("reset_time")
    if reset_time:
        diff_sec, desc = format_time_until_reset(reset_time)
        return diff_sec, desc
    
    # 备用方案：基于 diff_sec 与更新时间流逝递减
    orig_diff = quota_entry.get("diff_sec")
    if orig_diff is not None:
        try:
            orig_diff = float(orig_diff)
            ref_time = fallback_updated_at or quota_entry.get("updated_at")
            if ref_time:
                elapsed = max(0.0, time.time() - float(ref_time))
                cur_diff = max(0.0, orig_diff - elapsed)
            else:
                cur_diff = orig_diff
            
            if cur_diff <= 0:
                return 0.0, "已重置/已就绪"
            hours = int(cur_diff // 3600)
            minutes = int((cur_diff % 3600) // 60)
            seconds = int(cur_diff % 60)
            days = int(hours // 24)
            if days > 0:
                return cur_diff, f"{days}天{hours % 24}小时{minutes}分后"
            elif hours > 0:
                return cur_diff, f"{hours}小时{minutes}分后"
            elif minutes > 0:
                return cur_diff, f"{minutes}分{seconds}秒后"
            else:
                return cur_diff, f"{seconds}秒后"
        except Exception:
            pass

    desc = quota_entry.get("reset_desc", "")
    return 0.0, desc or "已就绪"



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
    explicit_target = bool(str(target_email or "").strip())
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

    # 5. 精准匹配主结果。显式请求某个邮箱时必须严格命中；
    # 禁止退回旧账号/第一个 LanguageServer，否则切换后刷新会重新识别成旧账户。
    target_match = None
    if wanted_email and wanted_email in discovered_accounts:
        target_match = discovered_accounts[wanted_email]
    elif not explicit_target and curr_email and curr_email in discovered_accounts:
        target_match = discovered_accounts[curr_email]
    elif not explicit_target and discovered_accounts:
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


