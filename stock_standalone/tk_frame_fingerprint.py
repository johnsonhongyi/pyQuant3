"""Content fingerprints for TK market frames.

None means the frame cannot be hashed safely and must be processed.
"""

import pandas as pd
import hashlib
import pickle
from datetime import datetime
from contextlib import nullcontext


def frame_fingerprint(df):
    if df is None:
        return None
    try:
        values = pd.util.hash_pandas_object(df, index=True).to_numpy().tobytes()
        schema = (tuple(df.columns), tuple(str(dtype) for dtype in df.dtypes))
        return hash((schema, values))
    except Exception:
        return None


class _DigestWriter:
    def __init__(self, digest):
        self.digest = digest

    def write(self, data):
        self.digest.update(data)
        return memoryview(data).nbytes


def send_content_fingerprint(df):
    """对传输内容做二进制摘要，避免 pandas 对大型 object 单元格生成字符串。"""
    if df is None:
        return None
    try:
        digest = hashlib.blake2b(digest_size=16)
        pickle.Pickler(_DigestWriter(digest), protocol=5).dump(df)
        return digest.digest()
    except Exception:
        return None


def same_fingerprint(previous, current):
    return current is not None and previous == current


def has_sync_consumer(vis_enabled, subscribers, temporary_ports):
    """Static port configuration alone does not constitute a subscription."""
    return bool(vis_enabled or temporary_ports or any(
        info.get('subscribed', False) for info in subscribers.values()
    ))


def request_immediate_ipc_sync(owner):
    """One-shot refresh; subscriber ownership and market baselines remain unchanged."""
    with getattr(owner, '_ipc_sync_state_lock', nullcontext()):
        owner._force_full_sync_pending = True
        deferred = getattr(owner, '_deferred_port_sync', None)
        for port, info in list(getattr(owner, '_stream_subscribers', {}).items()):
            if info.get('subscribed', False):
                setattr(owner, f'_force_sync_{port}', True)
                setattr(owner, f'_force_sync_blocked_{port}', False)
                setattr(owner, f'_awaiting_full_ack_{port}', None)
                setattr(owner, f'_last_full_try_{port}', 0.0)
                if isinstance(deferred, set):
                    deferred.discard(port)
        event = getattr(owner, '_send_df_wake_event', None)
        if event is not None:
            event.set()



def recover_blocked_sync_ports(owner, now, is_work_time):
    """Rearm subscribed ports after bounded ACK/connect backoff, independently of Vis."""
    with getattr(owner, '_ipc_sync_state_lock', nullcontext()):
        if not is_work_time:
            return []
        recovered = []
        for port, info in list(getattr(owner, '_stream_subscribers', {}).items()):
            if not (info.get('subscribed', False) and getattr(owner, f'_force_sync_{port}', False)
                    and getattr(owner, f'_force_sync_blocked_{port}', False)):
                continue
            last_try = getattr(owner, f'_last_full_try_{port}', info.get('last_try', 0.0))
            failures = max(0, min(3, int(info.get('fail_count', 0))))
            delay = min(300.0, 60.0 * (2 ** failures))
            if now - last_try < delay:
                continue
            # Expired ACKs must not release the newly rearmed full baseline request.
            setattr(owner, f'_awaiting_full_ack_{port}', None)
            setattr(owner, f'_force_sync_blocked_{port}', False)
            recovered.append(port)
        return recovered



def acknowledge_full_sync(owner, feedback):
    """Serialize ACK acceptance against new explicit refresh requests."""
    with getattr(owner, '_ipc_sync_state_lock', nullcontext()):
        port = feedback.get('port')
        expected = getattr(owner, f'_awaiting_full_ack_{port}', None)
        # A legacy ACK cannot confirm a refresh which has not even been sent yet.
        pending_unsent = expected is None and getattr(owner, f'_force_sync_{port}', False)
        matched = not pending_unsent and full_ack_matches(feedback, expected, getattr(owner, '_last_vis_bus_version', None))
        if matched:
            setattr(owner, f'_force_sync_{port}', False)
            setattr(owner, f'_force_sync_blocked_{port}', False)
            setattr(owner, f'_awaiting_full_ack_{port}', None)
        return matched, expected


def content_requires_send(previous, current, explicit_request=False):
    """Only changed content or a new request can enter serialization."""
    return bool(explicit_request or current is None or previous != current)


def is_new_trade_snapshot(last_trade_date, today, is_trade_day, snapshot_time,
                          version, last_version, previous_fingerprint, current_fingerprint):
    """Only a fresh, changed market frame on a new trading day rolls the baseline."""
    if not last_trade_date or last_trade_date == today or not is_trade_day:
        return False
    if not snapshot_time or datetime.fromtimestamp(snapshot_time).strftime('%Y-%m-%d') != today:
        return False
    if version <= last_version or previous_fingerprint is None or current_fingerprint is None:
        return False
    return previous_fingerprint != current_fingerprint


def needs_full_for_null_or_rows(previous, current):
    """Detect baseline changes that the legacy diff receiver cannot apply."""
    if previous is None or current is None or previous.empty:
        return False
    if current.empty:
        return True
    if not previous.index.equals(current.index):
        return True
    common = previous.columns.intersection(current.columns)
    if common.empty:
        return False
    return ((~previous[common].isna()) & current[common].isna()).to_numpy().any()


def full_ack_matches(feedback, expected, current_version=None):
    """
    校验全量同步确认（ATS_RECEIVED）是否有效：
    1. 基础门禁：必须是合法的 dict 对象且包含 port 字段；
    2. 新版客户端协议闭环：若 feedback 携带了 sync_session 与 source_version，
       必须与当前期望确认的 (sync_session, version) 完全一致，
       以此精准过滤陈旧/延迟的旧确认，防止旧确认误清除新触发的重试标记；
       （注：发包后主线版本可能会随时推进，因此不强制要求 feedback 版本必须等于最新 current_version，
       只要确认版本与当前发出的 expected 完全吻合即为合法确认）；
    3. 旧版客户端协议兼容：若 feedback 未携带版本号（如已打包的老版本 ATS_Terminal、MultiPeriodTester 等），
       则优雅兼容放行，清除 force_sync 标记，彻底杜绝老版本客户端陷入每 10 秒全量包重推死锁。
    """
    if not isinstance(feedback, dict) or feedback.get('port') is None:
        return False

    fb_session = feedback.get('sync_session')
    fb_version = feedback.get('source_version')

    # 新版协议客户端：严格核对会话与期望确认的版本（防止旧确认误清除新版本重试）
    if fb_session is not None and fb_version is not None:
        return expected is not None and (fb_session, fb_version) == expected

    # 旧版协议客户端（未传版本号）：向前兼容放行
    return True
