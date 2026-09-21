from datetime import date, timedelta
import gzip

from trading_kernel.observability.reconciliation_rotation import ReconciliationLogRotator


def test_reconciliation_rotation_compresses_files_after_30_days(tmp_path):
    today = date(2026, 9, 21)
    old_day = today - timedelta(days=30)
    active_day = today - timedelta(days=29)
    old_file = tmp_path / f"reconciliation_{old_day:%Y%m%d}.jsonl"
    active_file = tmp_path / f"reconciliation_{active_day:%Y%m%d}.jsonl"
    old_file.write_text('{"snapshot":"old"}\n', encoding="utf-8")
    active_file.write_text('{"snapshot":"active"}\n', encoding="utf-8")

    result = ReconciliationLogRotator().rotate(tmp_path, today=today)

    archive = tmp_path / "archive" / f"{old_file.name}.gz"
    assert result.archived == (archive.name,)
    assert not old_file.exists()
    assert active_file.exists()
    with gzip.open(archive, "rt", encoding="utf-8") as reader:
        assert reader.read() == '{"snapshot":"old"}\n'


def test_reconciliation_rotation_removes_expired_compressed_archives(tmp_path):
    today = date(2026, 9, 21)
    expired_day = today - timedelta(days=365)
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    expired = archive_root / f"reconciliation_{expired_day:%Y%m%d}.jsonl.gz"
    with gzip.open(expired, "wt", encoding="utf-8") as writer:
        writer.write('{"snapshot":"expired"}\n')

    result = ReconciliationLogRotator().rotate(tmp_path, today=today)

    assert result.removed == (expired.name,)
    assert not expired.exists()
