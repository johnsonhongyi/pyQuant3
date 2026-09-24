"""Content fingerprints for TK market frames.

None means the frame cannot be hashed safely and must be processed.
"""

import pandas as pd
import hashlib
import pickle
from datetime import datetime


def frame_fingerprint(df):
    if df is None:
        return None
    try:
        values = pd.util.hash_pandas_object(df, index=True).to_numpy().tobytes()
        schema = (tuple(df.columns), tuple(str(dtype) for dtype in df.dtypes))
        return hash((schema, values))
    except Exception:
        return None


def send_content_fingerprint(df):
    """Hash even object columns that pandas cannot hash, for send deduplication."""
    result = frame_fingerprint(df)
    if result is not None:
        return result
    try:
        return hashlib.blake2b(pickle.dumps(df, protocol=5), digest_size=16).digest()
    except Exception:
        return None


def same_fingerprint(previous, current):
    return current is not None and previous == current


def has_sync_consumer(vis_enabled, subscribers, temporary_ports):
    """Static port configuration alone does not constitute a subscription."""
    return bool(vis_enabled or temporary_ports or any(
        info.get('subscribed', False) for info in subscribers.values()
    ))


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
