import json
import os
import tempfile
import pytest

from trading_kernel.core.signal import StrategySignal
from trading_kernel.engine.state_manager import StateManager
from trading_kernel.kernel_service import TradingKernelService
from trading_kernel.observability.replay import ReplayRunner
from trading_kernel.execution.paper_adapter import PaperExecutionAdapter


@pytest.fixture
def replay_service(tmp_path, monkeypatch):
    # Journal replay consumes frozen features, never live HDF/TDX history.
    monkeypatch.setattr(TradingKernelService, "_auto_warm_up_from_preprocessed_hdf5", lambda self: None)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    state = StateManager()
    state._filepath = str(tmp_path / "state.json")
    state._lockpath = str(tmp_path / "state.lock")

    def create(journal_path):
        return TradingKernelService(
            journal_path=journal_path, initial_mode="OBSERVE", state_store=state,
            reconciliation_dir=str(tmp_path / "reconciliation"),
            paper_adapter=PaperExecutionAdapter(state_file_path=str(tmp_path / "paper.json")),
        )
    return create


def test_replay_equivalence_flow(replay_service) -> None:
    """测试常规流程下的回放一致性，验证100%幂等"""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # 1. 实例化服务并指定日志路径
        service = replay_service(tmp_path)

        # 2. 模拟真实信号项
        raw_item = {
            "code": "600519",
            "name": "贵州茅台",
            "created_at": "10:30:00",
            "signal_type": "SECTOR_BREAKOUT",
            "priority": 85.0,
            "current_price": 1800.0,
            "suggest_price": 1800.0,
            "pct_diff": 2.5,
            "dff": 1.8,
            "sector_heat": 60.0,
            "is_leader": True,
            "sws": 1780.0,
            "ma10d": 1790.0,
        }

        # 3. 产生原版 Journal 记录
        service.evaluate_decision_item(raw_item, write_journal=True)

        # 4. 运行回放器
        runner = ReplayRunner(journal_path=tmp_path)
        report = runner.run_replay()

        # 5. 断言判定：回放数量正确，且 100% 成功对齐，无任何错漏
        assert report.total_records == 1
        assert report.success_count == 1
        assert len(report.mismatches) == 0

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_replay_mismatch_detection(replay_service) -> None:
    """测试回放器对篡改/变动哈希的精准检错与拦截能力"""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        service = replay_service(tmp_path)
        raw_item = {
            "code": "000001",
            "name": "平安银行",
            "created_at": "14:15:00",
            "signal_type": "PULLBACK",
            "priority": 70.0,
            "current_price": 10.5,
            "suggest_price": 10.5,
            "pct_diff": 0.8,
            "dff": 0.5,
            "sector_heat": 40.0,
            "is_leader": False,
            "sws": 10.0,
            "ma10d": 10.2,
        }
        service.evaluate_decision_item(raw_item, write_journal=True)

        # 读取并篡改这个 journal 记录里的 expected_intent_hash
        from ats.storage_archive import iter_archive_lines
        from contextlib import closing
        with closing(iter_archive_lines(tmp_path)) as lines:
            line_data = json.loads(next(lines))

        line_data["trace"]["intent_hash"] = "TAMPERED_HASH_VALUE_123"

        tampered_path = tmp_path + ".tampered"
        with open(tampered_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(line_data) + "\n")

        # 运行回放
        runner = ReplayRunner(journal_path=tampered_path)
        report = runner.run_replay()

        # 断言排查出 mismatch
        assert report.total_records == 1
        assert report.success_count == 0
        assert len(report.mismatches) == 1
        assert "intent" in report.mismatches[0]
        assert report.mismatches[0]["intent"]["expected_hash"] == "TAMPERED_HASH_VALUE_123"

    finally:
        if os.path.exists(tmp_path + ".tampered"):
            os.remove(tmp_path + ".tampered")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
