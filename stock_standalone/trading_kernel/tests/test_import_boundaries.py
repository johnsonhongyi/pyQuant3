import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_decision_engine_import_boundary():
    imports = _imports(ROOT / "engine" / "decision_engine.py")
    forbidden = {
        "os",
        "sys",
        "sqlite3",
        "pandas",
        "numpy",
        "tkinter",
        "PyQt5",
        "PyQt6",
        "requests",
        "trade_gateway",
        "db_utils",
    }
    assert not (imports & forbidden)


def test_single_flow_import_boundary():
    decision_imports = _imports(ROOT / "engine" / "decision_engine.py")
    risk_imports = _imports(ROOT / "engine" / "risk_gate.py")
    assert "risk_gate" not in decision_imports
    assert "decision_engine" not in risk_imports
