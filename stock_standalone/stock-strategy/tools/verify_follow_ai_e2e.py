"""Isolated real-Codex/HMAC/ATS-contract/paper-execution/review integration.

All quotes, ATS observations and fills are synthetic. Only Codex inference is
real. This never reads/writes a production account or calls a broker.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]
import auto_follow as af
import follow_ai as ai
from follow_research import stock_plan
from system_linkage_context import build_ats_leader_evidence
from test_auto_follow import CFG


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", type=Path, default=ROOT / ".build-cache/follow-integration.exe")
    args = parser.parse_args()
    now = datetime.now(af.BJ)
    # Engine replay clock is fixed to a continuous-trading window; the HTTP lease
    # clock remains actual time. Both are explicitly synthetic validation scope.
    replay = now.replace(hour=10, minute=30, second=0, microsecond=0)
    previous = (replay.date() - timedelta(days=1)).isoformat()
    runtime = ROOT / ".build-cache" / ("ai-e2e-" + secrets.token_hex(6))
    runtime.mkdir(parents=True)
    key = secrets.token_hex(32)
    (runtime / "peer.key").write_text(key, encoding="ascii")
    (runtime / "targets.json").write_text(json.dumps({"targets": [{"node_id": "e2e-desktop", "workspace_id": "e2e",
        "base_url": "http://127.0.0.1:26676", "key_file": "peer.key", "enabled": True}]}), encoding="utf-8")
    (runtime / "global.ini").write_text("[general]\nstock_strategy_base_url=http://127.0.0.1:20084\nipc_node_id=e2e-desktop\nipc_workspace_id=e2e\nipc_key_file=peer.key\n", encoding="utf-8")
    def quote(price=10.2, at=replay):
        return {"symbol": "600001.SH", "name": "SYNTHETIC E2E", "price": price, "previous_close": 10,
            "change_percent": (price / 10 - 1) * 100, "high": price, "open": 10, "trade_time": at.isoformat(),
            "meta": {"source": "synthetic_e2e", "stale": False, "fetched_at": at.isoformat()}}
    daily = [{"time": (replay - timedelta(days=20-i)).isoformat(), "close": 8+i*.1,
              "amount": (8+i*.1)*1000, "volume": 1000,
              "meta": {"source": "synthetic_e2e", "stale": False, "available_fields": ["volume_shares"]}} for i in range(20)]
    minute = [{"time": (replay-timedelta(minutes=20-i*5)).isoformat(), "close": 10+i*.02,
               "amount": 10.1*(1000+i*100), "volume": 1000+i*100,
               "meta": {"source": "synthetic_e2e", "stale": False, "fetched_at": replay.isoformat(),
                        "available_fields": ["volume_shares"]}} for i in range(4)]
    state = af.initial()
    state["validation_scope"] = "synthetic_e2e; replay clock frozen; not a real security, observation or fill"
    state["ai_settings"] = {**ai.DEFAULT_AI, "enabled": True, "mode": "enforce", "node_id": "e2e-desktop", "workspace_id": "e2e"}
    state["risk_config"] = {"strategy_version": "synthetic-v1.9", "max_positions": 5, "amount_per_trade": 100000, "max_day_chg": 7}
    stock = {"symbol": "600001.SH", "name": "SYNTHETIC E2E", "route": "limit_up", "theme":"e2e-theme", "primary_theme":"e2e-theme", "streak": 2}
    stock["plan"] = stock_plan(stock, quote(), minute, daily, CFG, replay, previous, state)
    state["candidates"] = [stock]
    state["market"] = {"score": 30,"backend_status":"高位延续","risk_score":10,"checked_at":replay.isoformat(),
                       "source": "synthetic_e2e", "trade_date": replay.date().isoformat(), "risk": "fixture only"}
    flow_meta={"source":"synthetic_e2e","stale":False,"trade_date":replay.date().isoformat(),"fetched_at":replay.isoformat(),"available_fields":["net_inflow","change_percent"]}
    state['research']={dimension:{'meta':flow_meta,'error':None,'coverage':1,'rows':[{'code':'e2e-theme','name':'SYNTHETIC theme',
        'rank':1,'net_flow':20000000,'flow_field':'net_inflow','change_percent':3,'meta':flow_meta}]} for dimension in ('industry','theme')}
    account = af.connect(runtime / "account.db")
    account.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(state),))
    control = af.connect_control(runtime / "account.db");ai.init_ai(control)
    # The ATS builder is the real desktop IPC evidence contract, with synthetic input.
    evidence = build_ats_leader_evidence({"timestamp": replay.timestamp(), "dragon_records": [
        {"code": "600001", "name": "SYNTHETIC E2E", "role": "leader", "priority": 1}]}, now=replay)
    assert evidence, "ATS contract builder must accept fixture"
    with sqlite3.connect(runtime / "trading_signals.db") as db:
        db.execute("CREATE TABLE signal_history(date TEXT,code TEXT,name TEXT,price REAL,action TEXT,reason TEXT,resample TEXT)")
        db.execute("INSERT INTO signal_history VALUES(?,?,?,?,?,?,?)", (replay.date().isoformat(), "600001", "SYNTHETIC E2E", 10.2, "OBSERVE", "synthetic fixture", "5"))
    with sqlite3.connect(runtime / "system_linkage.sqlite3") as db:
        db.execute("CREATE TABLE linkage_context_snapshots(stored_at TEXT,payload TEXT)")
        db.execute("INSERT INTO linkage_context_snapshots VALUES(?,?)", (now.isoformat(), json.dumps({"trade_date": replay.date().isoformat(),
            "as_of": replay.isoformat(), "snapshot_id": "e2e-ats", "evidence": [{"source_id": "ats.leader", "freshness": "fresh", "payload": evidence[2]}]})))
    # Request metadata uses the replay clock, while expiry is the real HTTP clock.
    job_id = ai.enqueue(control, state, replay, question="这是隔离合成模拟执行验收，时间冻结，数据并非真实行情。调用get_stock_evidence与get_ats_evidence核验限定P4/P8/P25条件；满足时给出包含现价的follow区间，不满足则observe。必需数据完整，L2非本次入场依赖。", force=True)
    control.execute("UPDATE ai_jobs SET expires_at=? WHERE id=?", ((now+timedelta(minutes=10)).isoformat(),job_id))
    server_log = (runtime / "service.txt").open("wb")
    server = subprocess.Popen([str(args.service.resolve()), str(runtime)], cwd=runtime, stdout=server_log, stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(50):
            try:
                with opener.open("http://127.0.0.1:20084/api/health",timeout=1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("isolated Go service did not become ready")
        def agent_once():
            result = subprocess.run([sys.executable,str(ROOT/"desktop_strategy_agent.py"),"--config",str(runtime/"global.ini"),
                "--desktop-root",str(ROOT.parent),"--ats-data-root",str(runtime),"--runtime-root",str(runtime/"agent"),"--once"],
                cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            print(result.stdout.decode("utf-8",errors="replace").strip(),flush=True)
            if result.returncode:raise RuntimeError("desktop agent failed: "+str(result.returncode))
        agent_once()
        ai.sync_ai(control,state,replay)
        assert state.get("ai_latest",{}).get("id")==job_id,"real AI result must pass server/worker validation"
        latest = state["ai_latest"]
        plan = latest["result"]["proposal"]["plans"][0]
        if plan["action"]!="follow" or plan["missing_data"]:
            raise AssertionError("AI did not admit synthetic entry; inspect retained evidence at "+str(runtime))
        class Calendar:
            @staticmethod
            def is_trading_day(day,market):return True
            @staticmethod
            def prev_trading_day(day,market):return previous
        meta = {"source":"synthetic_e2e","stale":False,"fetched_at":replay.isoformat()}
        def api(path):
            if "realtime" in path:return {"data":[quote()]}
            if "kline" in path:return {"data":daily if "period=day" in path else minute}
            if "limit-up-ladder" in path:return {"data":{"meta":meta,"current":{"trade_date":replay.date().isoformat()},
                "previous":{"trade_date":previous,"levels":[{"stocks":[stock]}]}}}
            return {"meta":meta,"data":[]}
        af.cycle(state,CFG,api,replay,Calendar,{"score":0},False)
        assert len(state["positions"])==1,"AI + original unique gate must produce one isolated simulated fill"
        assert state["positions"][0]["ai_decision"]["job_id"]==job_id
        after_buy = state["cash"]
        af.cycle(state,CFG,lambda path:{"data":[quote(11.5)]},replay,Calendar,{},True)
        assert len(state["positions"])==1,"T+1 must prevent same-day exit"
        tomorrow = replay+timedelta(days=1)
        af.cycle(state,CFG,lambda path:{"data":[quote(11.5,tomorrow)]},tomorrow,Calendar,{},True)
        assert not state["positions"] and len(state["closed"])==1
        assert state["closed"][0]["ai_decision"]["job_id"]==job_id
        ai.schedule_workflow(control,state,replay,Calendar)
        review_id = control.execute("SELECT id FROM ai_jobs WHERE id!=? ORDER BY created_at DESC LIMIT 1",(job_id,)).fetchone()[0]
        control.execute("UPDATE ai_jobs SET expires_at=? WHERE id=?",((datetime.now(af.BJ)+timedelta(minutes=10)).isoformat(),review_id))
        agent_once();ai.sync_ai(control,state,now)
        assert state.get("ai_review",{}).get("id")==review_id
        assert state["ai_latest"]["id"]==job_id,"review must not overwrite entry proposal"
        tool_names={t["tool"] for t in latest["result"].get("tool_audit",[])}
        assert {"get_stock_evidence","get_ats_evidence"}<=tool_names
        report={"scope":"synthetic isolated replay; real Codex inference", "status":"passed","analysis_job":job_id,
            "review_job":review_id,"thread_id":latest["result"]["thread_id"],"review_thread_id":state["ai_review"]["result"]["thread_id"],
            "buy_cash":after_buy,"final_cash":state["cash"],"closed_count":len(state["closed"]),"t1":"passed",
            "tool_calls":sorted(tool_names),"production_account_touched":False}
        (runtime/"result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=True),flush=True)
    finally:
        server.terminate();server.wait(timeout=5);server_log.close();account.close();control.close()


if __name__=="__main__":main()
