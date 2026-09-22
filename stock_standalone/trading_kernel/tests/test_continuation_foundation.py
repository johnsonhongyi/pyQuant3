from pathlib import Path

import pytest

from trading_kernel.build_fingerprint import (
    DEFAULT_OUTPUT_PATH,
    DirtyWorkingTreeError,
    build_fingerprint,
    main,
    write_build_fingerprint,
)
from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.engine.signal_canonicalizer import canonicalize_decision_queue_item
from trading_kernel.execution.paper_adapter import AccountSnapshot, PaperExecutionAdapter


def test_request_id_reaches_canonical_signal():
    signal = canonicalize_decision_queue_item({
        "code": "000001",
        "created_at": "2026-09-21 10:00:00",
        "current_price": 10.0,
        "request_id": "req-001",
        "source": "ATS",
    })
    assert signal.features["request_id"] == "req-001"
    assert signal.source == "ATS"


def test_paper_order_retry_is_idempotent():
    adapter = PaperExecutionAdapter(initial_capital=100000.0)
    adapter._is_test = True
    adapter.account = AccountSnapshot(cash=100000.0, initial_capital=100000.0)
    adapter.orders = []
    order = ApprovedOrder(
        order_id="order-001",
        code="000001",
        action="BUY",
        size_pct=0.10,
        price=10.0,
        stop_price=9.5,
        request_id="req-001",
    )

    assert adapter.submit_order(order) is True
    cash_after_first = adapter.account.cash
    volume_after_first = adapter.account.positions["000001"].volume

    assert adapter.submit_order(order) is True
    assert len(adapter.orders) == 1
    assert adapter.account.cash == cash_after_first
    assert adapter.account.positions["000001"].volume == volume_after_first
    assert adapter.orders[0]["request_id"] == "req-001"


def test_build_fingerprint_contains_version_and_git_fields(tmp_path):
    output = tmp_path / "fingerprint.json"
    payload = write_build_fingerprint(
        output,
        repo_root=Path(__file__).resolve().parents[2],
    )

    assert output.exists()
    assert payload["api_version"] == "1.0"
    assert payload["kernel_version"]
    assert "git_commit" in payload
    assert "git_dirty" in payload
    assert "release_ready" in payload
    assert payload["generated_at_utc"]


def test_build_fingerprint_clean_tree_is_release_ready(tmp_path):
    output = tmp_path / "clean_fingerprint.json"
    payload = write_build_fingerprint(
        output,
        repo_root=Path(__file__).resolve().parents[2],
        git_commit="abcdef1234567890",
        git_dirty=False,
        require_clean=True,
    )
    assert output.exists()
    assert payload["release_ready"] is True
    assert payload["git_dirty"] is False
    assert payload["git_commit"] == "abcdef1234567890"


def test_build_fingerprint_dirty_tree_blocks_release_mode(tmp_path):
    output = tmp_path / "dirty_fingerprint.json"
    with pytest.raises(DirtyWorkingTreeError):
        write_build_fingerprint(
            output,
            repo_root=Path(__file__).resolve().parents[2],
            git_commit="abcdef1234567890",
            git_dirty=True,
            require_clean=True,
        )
    assert not output.exists()


def test_build_fingerprint_default_output_path_in_agent_hub(tmp_path):
    assert DEFAULT_OUTPUT_PATH == Path(".agent_hub") / "artifacts" / "BUILD_FINGERPRINT.json"
    payload = write_build_fingerprint(
        repo_root=tmp_path,
        git_commit="fedcba0987654321",
        git_dirty=False,
    )
    expected_file = tmp_path / ".agent_hub" / "artifacts" / "BUILD_FINGERPRINT.json"
    assert expected_file.exists()
    assert payload["release_ready"] is True


def test_build_fingerprint_cli_dirty_release_returns_nonzero(capsys):
    ret = main(["--release", "--git-dirty", "true", "--git-commit", "deadbeef"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Cannot generate release build fingerprint" in captured.err


def test_build_fingerprint_cli_clean_release_succeeds(tmp_path, capsys):
    target = tmp_path / "cli_clean.json"
    ret = main([
        "--output", str(target),
        "--release",
        "--git-dirty", "false",
        "--git-commit", "c0ffee123456",
    ])
    assert ret == 0
    assert target.exists()
    captured = capsys.readouterr()
    assert "c0ffee123456" in captured.out
