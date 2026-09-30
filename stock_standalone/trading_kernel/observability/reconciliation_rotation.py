# -*- coding: utf-8 -*-
"""Small, deterministic archive rotation for daily reconciliation snapshots."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


_ACTIVE_NAME = re.compile(r"^reconciliation_(\d{8})\.jsonl$")
_ARCHIVE_NAME = re.compile(r"^reconciliation_(\d{8})\.jsonl\.gz$")


@dataclass(frozen=True)
class ReconciliationRotationResult:
    archived: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


class ReconciliationLogRotator:
    """Archive closed daily files without touching the current audit log."""

    def __init__(
        self,
        archive_after_days: int = 1,
        archive_retention_days: int | None = 365,
    ) -> None:
        self.archive_after_days = max(1, int(archive_after_days))
        self.archive_retention_days = (
            None if archive_retention_days is None
            else max(self.archive_after_days, int(archive_retention_days))
        )

    @staticmethod
    def _file_date(filename: str, pattern: re.Pattern[str]) -> date | None:
        match = pattern.match(filename)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            return None

    def rotate(self, directory: str | os.PathLike[str], *, today: date | None = None) -> ReconciliationRotationResult:
        """Compress aged daily files then remove aged compressed archives.

        Compressed bytes are verified before removing a closed source file.
        """
        root = Path(directory)
        if not root.is_dir():
            return ReconciliationRotationResult()
        today = today or date.today()
        archive_root = root / "archive"
        archived: list[str] = []
        removed: list[str] = []

        for source in root.iterdir():
            source_date = self._file_date(source.name, _ACTIVE_NAME)
            if source_date is None or (today - source_date).days < self.archive_after_days:
                continue
            archive_root.mkdir(exist_ok=True)
            target = archive_root / f"{source.name}.gz"
            try:
                from ats.storage_archive import archive_verified
                archive_verified(source, target)
            except OSError:
                continue
            try:
                source.unlink()
                archived.append(target.name)
            except OSError:
                pass

        if self.archive_retention_days is not None and archive_root.is_dir():
            for archive in archive_root.iterdir():
                archive_date = self._file_date(archive.name, _ARCHIVE_NAME)
                if archive_date is None or (today - archive_date).days < self.archive_retention_days:
                    continue
                try:
                    archive.unlink()
                    removed.append(archive.name)
                except OSError:
                    pass
        from ats.storage_archive import remove_expired_reconciliation_segments
        removed.extend(remove_expired_reconciliation_segments(root, self.archive_retention_days, today))
        return ReconciliationRotationResult(tuple(archived), tuple(removed))
