"""Runtime-root regressions without launching Qt, training or trading."""

import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import sys_utils


SOURCE_ROOT = Path(__file__).absolute().parents[1]
CLI_TOOLS = [
    "run_ipo_30d_production_ingest_test", "run_ipo_cutoff_replay_smoke",
    "run_ipo_llm_simulation", "run_ipo_vwap_trade_replay", "run_ipo_offline_learning",
    "run_ipo_shadow_evaluation", "run_ipo_paper_auto", "run_ipo_data_acquisition",
    "bootstrap_ipo_configuration", "ipo_preflight_diagnostics", "generate_matured_labels",
]


@pytest.mark.parametrize("tool", CLI_TOOLS)
@pytest.mark.parametrize("packaged", [False, True])
def test_cli_data_root_uses_system_root_not_bundle_or_cwd(tool, packaged, tmp_path, monkeypatch):
    app = tmp_path / "physical_app"
    app.mkdir()
    monkeypatch.setenv("INSTOCK_APP_ROOT", str(app))
    monkeypatch.setattr(sys, "frozen", packaged, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.chdir(tmp_path)
    tree = ast.parse((SOURCE_ROOT / "tools" / (tool + ".py")).read_text(encoding="utf-8"))
    root_name = "ROOT" if tool == "run_ipo_paper_auto" else "APP_ROOT"
    root_assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == root_name for t in node.targets))
    scope = {"Path": Path, "__file__": str(tmp_path / "bundle/tools" / (tool + ".py")),
             "safe_resolve_path": sys_utils.safe_resolve_path, "get_app_root": sys_utils.get_app_root}
    exec(compile(ast.Module(body=[root_assignment], type_ignores=[]), "<cli-root>", "exec"), scope)
    assert scope[root_name] == app


def test_gate_root_honors_source_environment_override(tmp_path, monkeypatch):
    from ats.strategy.ipo_gate_context_provider import _resolve_project_root, IPOGateContextProvider
    monkeypatch.setenv("INSTOCK_APP_ROOT", str(tmp_path))
    assert _resolve_project_root() == tmp_path
    assert IPOGateContextProvider()._root == tmp_path


def test_ramdisk_error_does_not_break_request_producer(tmp_path, monkeypatch):
    from ats.llm.request_producer import LiveSnapshotRequestProducer
    from ats.strategy.ipo_gate_context_provider import IPOGateContextProvider
    def unsupported(*args, **kwargs):
        raise OSError(1, "GetFinalPathNameByHandle unsupported")
    monkeypatch.setattr(Path, "resolve", unsupported)
    assert LiveSnapshotRequestProducer(tmp_path)._root == tmp_path.absolute()
    assert IPOGateContextProvider(tmp_path)._root == tmp_path.absolute()


def test_default_anchor_path_ignores_cwd(tmp_path, monkeypatch):
    from ats.strategy.listing_anchor_store import ListingAnchorStore
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setenv("INSTOCK_APP_ROOT", str(app))
    monkeypatch.chdir(tmp_path)
    assert ListingAnchorStore().store_path == app / "config/listing_anchors.json"
    explicit = tmp_path / "isolated/anchors.json"
    assert ListingAnchorStore(explicit).store_path == explicit


def test_snapshot_sink_uses_explicit_isolated_learning_root(tmp_path, monkeypatch):
    from ats.strategy.ipo_trading_center import IPOTradingCenter
    from ats.llm import learning_snapshot_store
    center = IPOTradingCenter(learning_root=str(tmp_path))
    destinations = []
    monkeypatch.setattr(learning_snapshot_store, "record_decision_snapshot",
                        lambda root, **kw: destinations.append(root) or True)
    directive = SimpleNamespace(audit_envelope={}, directive_id="test", action="BUY", code="600000",
                                price=10, size_pct=0.1)
    passport = SimpleNamespace(learning_input_snapshot={"as_of_time": "2026-10-14T10:00:00+08:00"},
                               learning_input_snapshot_hash="hash", configuration_version="v1")
    center._record_r9_learning_snapshot(directive, passport)
    assert destinations == [tmp_path]


def test_config_release_stays_in_explicit_root(tmp_path, monkeypatch):
    from ats.strategy.ipo_gate_context_provider import _ensure_yaml_config
    calls = []
    def release(path, base_dir=None):
        calls.append(base_dir)
        return str(tmp_path / "config/ipo_sentiment.yaml")
    monkeypatch.setattr(sys_utils, "get_conf_path", release)
    _ensure_yaml_config(tmp_path / "config/ipo_sentiment.yaml")
    assert calls == [str(tmp_path)]


@pytest.mark.parametrize("packager", ["pyinstaller", "nuitka"])
def test_system_root_uses_physical_executable_without_environment_override(tmp_path, monkeypatch, packager):
    app = tmp_path / "physical"
    bundle = tmp_path / "bundle"
    app.mkdir()
    bundle.mkdir()
    executable = app / "ATS.exe"
    executable.write_bytes(b"test fixture; never executed")
    monkeypatch.delenv("INSTOCK_APP_ROOT", raising=False)
    monkeypatch.delenv("NUITKA_ONEFILE_BINARY", raising=False)
    monkeypatch.delenv("NUITKA_ONEFILE_DIRECTORY", raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    if packager == "pyinstaller":
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    else:
        monkeypatch.setenv("NUITKA_ONEFILE_BINARY", str(executable))
        monkeypatch.setenv("NUITKA_ONEFILE_DIRECTORY", str(bundle))
    assert sys_utils.safe_resolve_path(sys_utils.get_app_root()) == app
