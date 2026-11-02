"""Build a secret-free, checksummed paper-worker release on Windows or Linux."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

try:
    import yaml
except ImportError:  # production host has no PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        target = args.directory.resolve()
    except OSError:
        target = args.directory.absolute()
    target.mkdir(parents=True, exist_ok=False)
    service = target / "source" / "easy-stock-service"
    service.mkdir(parents=True)
    for name in ("auto_follow.py", "follow_research.py", "follow_ai.py", "auto_research_policy.py",
                 "signal_engine.py", "loop_state.py", "strong_scan.py", "attribution.py", "optimizer.py",
                 "simple_config.py", "housekeeping.py",
                 "test_auto_follow.py", "test_follow_research.py", "test_follow_ai.py",
                 "test_auto_research_policy.py", "test_signal_engine.py", "test_attribution.py",
                 "test_optimizer.py", "test_loop_cycle.py", "test_housekeeping.py",
                 "stockstrategy-auto-follow.service"):
        shutil.copyfile(ROOT / name, target / name)
    for name in ("daily_review.py", "market_cache.py", "market_network.py", "data_store.py", "trading_calendar.py"):
        shutil.copyfile(ROOT / "source" / "easy-stock-service" / name, service / name)
    strategy_path = ROOT / "source" / "easy-stock-service" / "strategy.yaml"
    if yaml is not None:
        cfg = yaml.safe_load(strategy_path.read_text(encoding="utf-8"))
    else:
        import simple_config
        cfg = simple_config.load(strategy_path)
    snapshot = {key: cfg[key] for key in ("version", "buy", "sell", "decision_gate", "execution")}
    (target / "config.json").write_bytes(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
    files = sorted(p for p in target.rglob("*") if p.is_file())
    manifest = "".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.relative_to(target).as_posix() + "\n" for p in files)
    (target / "SHA256SUMS").write_bytes(manifest.encode("utf-8"))
    archive = target.with_name(target.name + ".tar.gz")
    def permissions(member):
        member.mode = 0o644
        member.uid = member.gid = 0
        member.uname = member.gname = "root"
        return member
    with tarfile.open(archive, "w:gz") as bundle:
        for p in sorted(target.rglob("*")):
            if p.is_file():
                bundle.add(p, arcname=p.relative_to(target).as_posix(), recursive=False, filter=permissions)
    print(json.dumps({"archive": str(archive), "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
