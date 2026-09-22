from pathlib import Path

from webTools.window_manager.agent_hub_ui import AgentHubDataEngine


def test_agent_hub_uses_explicit_packaged_project_root():
    project_root = Path(__file__).parent.parent.absolute()
    engine = AgentHubDataEngine(project_root=project_root)

    assert engine.project_root == project_root
    assert engine.hub_dir == project_root / ".agent_hub"


def test_agent_hub_frozen_fallback_uses_explicit_app_root(monkeypatch):
    project_root = Path(__file__).parent.parent.absolute()
    monkeypatch.setattr("webTools.window_manager.agent_hub_ui.sys.frozen", True, raising=False)
    monkeypatch.setenv("INSTOCK_APP_ROOT", str(project_root))

    engine = AgentHubDataEngine()

    assert engine.project_root == project_root


def test_agent_hub_falls_back_when_exe_directory_has_no_hub(monkeypatch):
    project_root = Path(__file__).parent.parent.absolute()
    (project_root / ".agent_hub").mkdir(exist_ok=True)
    fake_exe_dir = project_root / "dist" / "agent_test"
    monkeypatch.setattr("webTools.window_manager.agent_hub_ui.sys.executable", str(fake_exe_dir / "app.exe"))
    monkeypatch.delenv("INSTOCK_APP_ROOT", raising=False)

    engine = AgentHubDataEngine(project_root=fake_exe_dir)

    assert engine.project_root == project_root


def test_agent_hub_uses_cct_configured_path(monkeypatch, tmp_path=None):
    # 使用现有项目根目录，避免测试框架临时目录在当前 Windows 环境不可解析。
    configured_root = Path(__file__).parent.parent.absolute()
    monkeypatch.setattr("webTools.window_manager.agent_hub_ui.cct.agent_hub_path", str(configured_root), raising=False)
    monkeypatch.setattr("webTools.window_manager.agent_hub_ui.sys.executable", "G:/Temp/missing-agent.exe")

    engine = AgentHubDataEngine(project_root="G:/Temp/missing-project")

    assert engine.project_root == configured_root


def test_empty_cct_path_falls_back_to_source_project_root(monkeypatch):
    monkeypatch.setattr("webTools.window_manager.agent_hub_ui.cct.agent_hub_path", "", raising=False)
    monkeypatch.delenv("INSTOCK_APP_ROOT", raising=False)

    engine = AgentHubDataEngine(project_root="G:/Temp/missing-project")

    assert engine.project_root == Path(__file__).parent.parent.absolute()
