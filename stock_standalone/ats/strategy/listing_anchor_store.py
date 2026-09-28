"""Immutable first-session IPO anchor persistence and dual-anchor checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import math
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager
from threading import RLock
from typing import Dict, Iterator, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ANCHOR_SCHEMA_VERSION = "1"


def _valid_price(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


@dataclass(frozen=True)
class ListingAnchors:
    code: str
    listing_date: str
    listing_open: float
    listing_high: float
    listing_low: float
    listing_close: float
    listing_vwap: float
    listing_anchored_vwap: float
    first_30m_vwap: float
    close_location: float
    first_day_turnover: float
    source_id: str = ""
    source_version: str = ""
    source_timezone: str = ""
    as_of_time: str = ""
    available_at: str = ""
    configuration_hash: str = ""
    data_contract_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("listing anchor code 缺失")
        try:
            date.fromisoformat(self.listing_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("listing_date 必须为 ISO 日期") from exc
        price_fields = (
            "listing_open", "listing_high", "listing_low", "listing_close",
            "listing_vwap", "listing_anchored_vwap", "first_30m_vwap",
        )
        if any(not _valid_price(getattr(self, field)) for field in price_fields):
            raise ValueError("首日价格锚点必须为正有限数值")
        if not (self.listing_low <= self.listing_open <= self.listing_high):
            raise ValueError("首日开盘价必须位于首日高低价范围内")
        if not (self.listing_low <= self.listing_close <= self.listing_high):
            raise ValueError("首日收盘价必须位于首日高低价范围内")
        if (
            isinstance(self.close_location, bool)
            or not isinstance(self.close_location, (int, float))
            or not math.isfinite(self.close_location)
            or not 0.0 <= self.close_location <= 1.0
        ):
            raise ValueError("首日 close_location 必须在 [0, 1]")
        if (
            isinstance(self.first_day_turnover, bool)
            or not isinstance(self.first_day_turnover, (int, float))
            or not math.isfinite(self.first_day_turnover)
            or self.first_day_turnover < 0
        ):
            raise ValueError("首日换手率必须为非负有限数值")
        provenance = (
            self.source_id, self.source_version, self.source_timezone,
            self.as_of_time, self.available_at, self.configuration_hash,
            self.data_contract_hash,
        )
        if any(provenance):
            if any(not isinstance(value, str) or not value.strip() for value in provenance):
                raise ValueError("首日锚点来源与哈希元数据必须完整")
            try:
                ZoneInfo(self.source_timezone)
                as_of = datetime.fromisoformat(self.as_of_time.replace("Z", "+00:00"))
                available = datetime.fromisoformat(self.available_at.replace("Z", "+00:00"))
            except (ValueError, ZoneInfoNotFoundError) as exc:
                raise ValueError("首日锚点时区或时间格式无效") from exc
            if as_of.tzinfo is None or available.tzinfo is None or as_of > available:
                raise ValueError("首日锚点来源时间必须带时区且不晚于采集时间")
            for digest in (self.configuration_hash, self.data_contract_hash):
                if len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
                    raise ValueError("首日锚点配置哈希格式无效")

    def matches_contract(
        self, configuration_hash: str, data_contract_hash: str,
        source_timezone: str = "Asia/Shanghai",
    ) -> bool:
        return bool(
            isinstance(configuration_hash, str)
            and isinstance(data_contract_hash, str)
            and isinstance(source_timezone, str)
            and self.source_timezone == source_timezone
            and self.configuration_hash.lower() == configuration_hash.lower()
            and self.data_contract_hash.lower() == data_contract_hash.lower()
        )


class ListingAnchorStore:
    """Persist anchors by code/date; a conflicting second freeze is rejected."""

    STORE_PATH = Path("config/listing_anchors.json")

    def __init__(self, store_path: Optional[os.PathLike[str] | str] = None) -> None:
        self.store_path = Path(store_path) if store_path is not None else self.STORE_PATH
        self._lock = RLock()

    @contextmanager
    def _process_lock(self) -> Iterator[None]:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.store_path.with_name(self.store_path.name + ".lock")
        with lock_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _load(self) -> Dict[str, ListingAnchors]:
        if not self.store_path.exists():
            return {}
        try:
            with self.store_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("listing anchors 存储损坏或不可读") from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != ANCHOR_SCHEMA_VERSION:
            raise ValueError("listing anchors schema_version 无效")
        raw_anchors = payload.get("anchors")
        if not isinstance(raw_anchors, Mapping):
            raise ValueError("listing anchors anchors 必须为映射")
        anchors: Dict[str, ListingAnchors] = {}
        for key, item in raw_anchors.items():
            if not isinstance(key, str) or not isinstance(item, Mapping):
                raise ValueError("listing anchor 条目格式无效")
            try:
                anchor = ListingAnchors(**item)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"listing anchor {key!r} 内容无效") from exc
            if key != self._key(anchor.code, anchor.listing_date):
                raise ValueError("listing anchor 键与标的/日期不一致")
            anchors[key] = anchor
        return anchors

    @staticmethod
    def _key(code: str, listing_date: str) -> str:
        return f"{code.strip()}@{listing_date}"

    def get(self, code: str, listing_date: str) -> Optional[ListingAnchors]:
        if not isinstance(code, str) or not code.strip():
            return None
        try:
            date.fromisoformat(listing_date)
        except (TypeError, ValueError):
            return None
        with self._lock:
            return self._load().get(self._key(code, listing_date))

    def latest_by_code(self) -> Dict[str, ListingAnchors]:
        """Read each symbol's newest immutable anchor without modifying the store."""
        with self._lock:
            anchors = self._load().values()
            latest: Dict[str, ListingAnchors] = {}
            for anchor in anchors:
                current = latest.get(anchor.code)
                if current is None or anchor.listing_date > current.listing_date:
                    latest[anchor.code] = anchor
            return latest

    def freeze(self, anchors: ListingAnchors) -> ListingAnchors:
        if not isinstance(anchors, ListingAnchors):
            raise ValueError("只能冻结通过校验的 ListingAnchors")
        key = self._key(anchors.code, anchors.listing_date)
        with self._lock, self._process_lock():
            records = self._load()
            existing = records.get(key)
            if existing is not None:
                if existing != anchors:
                    raise ValueError(f"首日锚点已冻结，拒绝覆盖: {key}")
                return existing
            records[key] = anchors
            payload = {
                "schema_version": ANCHOR_SCHEMA_VERSION,
                "anchors": {
                    item_key: asdict(value)
                    for item_key, value in sorted(records.items())
                },
            }
            encoded = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=self.store_path.parent, prefix=f"{self.store_path.name}.",
                    suffix=".tmp", delete=False,
                ) as stream:
                    temp_path = Path(stream.name)
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_path, self.store_path)
            except OSError as exc:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise ValueError("首日锚点持久化失败") from exc
            return anchors

    def check_dual_anchor_failure(
        self,
        anchors: ListingAnchors,
        intraday_low: float,
        current_price: float,
    ) -> Tuple[bool, str]:
        if not isinstance(anchors, ListingAnchors):
            return True, "双锚失守检查阻断: 首日锚点缺失/无效"
        if not _valid_price(intraday_low) or not _valid_price(current_price):
            return True, "双锚失守检查阻断: 日内最低价或现价缺失/无效"
        open_anchor = anchors.listing_open
        low_anchor = anchors.listing_low
        low_breached = intraday_low < open_anchor and intraday_low < low_anchor
        current_breached = current_price < open_anchor and current_price < low_anchor
        if low_breached or current_breached:
            return True, (
                f"双锚失守(日内最低 {intraday_low:.2f} / 现价 {current_price:.2f} "
                f"击穿首日开盘 {open_anchor:.2f} 与首日最低 {low_anchor:.2f})"
            )
        return False, ""
