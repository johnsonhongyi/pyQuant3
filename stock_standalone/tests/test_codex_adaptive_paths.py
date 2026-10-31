"""Managed engine selection follows either updater without launching a CLI."""
from pathlib import Path

from ats.llm import cli_paths


def test_cli_utilities_do_not_require_desktop_configuration():
    import subprocess
    import sys
    result=subprocess.run([sys.executable,'-c',
        "import sys; sys.modules['sys_utils']=None; import ats.llm.cli_paths; import ats.llm.cli_process"],
        capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_newest_current_engine_wins_and_equal_versions_prefer_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME',str(tmp_path))
    versions={'app-server-daemon':'0.166.0','standalone':'0.167.0'}
    mapping={}
    for package,version in versions.items():
        current=tmp_path/'packages'/package/'current/bin/codex.exe'
        current.parent.mkdir(parents=True);current.touch()
        mapping[current]=tmp_path/'packages'/package/'releases'/f'{version}-x86_64-pc-windows-msvc'/'bin/codex.exe'
    monkeypatch.setattr(cli_paths,'safe_resolve_path',lambda path:mapping[Path(path)])
    assert 'standalone' in cli_paths.resolve_cli_path('','codex')
    standalone=next(path for path in mapping if 'standalone' in path.parts)
    mapping[standalone]=Path(str(mapping[standalone]).replace('0.167.0','0.165.0'))
    assert 'app-server-daemon' in cli_paths.resolve_cli_path('','codex')
    mapping[standalone]=Path(str(mapping[standalone]).replace('0.165.0','0.166.0'))
    assert 'app-server-daemon' in cli_paths.resolve_cli_path('','codex')
