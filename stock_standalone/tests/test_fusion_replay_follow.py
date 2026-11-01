import gzip
import json
import os
import time

import numpy as np

from ats.fusion.replay_follow import compare_signal_streams, read_replay_follow


def stamp(day, hm):
    return time.mktime(time.strptime(day + " " + hm, "%Y-%m-%d %H:%M"))


def archive(root, name, day, records, fingerprint="same"):
    directory = root / name
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({"status": "complete", "config_fingerprint": fingerprint, "engine_fingerprint": "engine1", "config": {"use_production_history": False, "persist_context": False, "state_path": "", "market_path": os.devnull},
        "completed": [{"day": day, "file": day + ".json.gz"}]}), encoding="utf-8")
    with gzip.open(directory / (day + ".json.gz"), "wt", encoding="utf-8") as stream:
        json.dump({"result": {"day": day, "records": records, "meta": {}}}, stream)
    return directory


def test_replay_tracks_across_compatible_runs_and_missing_signal_days(tmp_path):
    days = ["2026-10-28", "2026-10-29", "2026-10-30"]
    first = {"code": "000568", "ts": stamp(days[0], "10:00"), "entry": 10,
             "tier": 1, "patterns": ["逆势收复启动"]}
    directory = archive(tmp_path, "run1", days[0], [first])
    archive(tmp_path, "run2", days[1], [])
    archive(tmp_path, "run3", days[2], [], fingerprint="other")
    bars = np.zeros(6, dtype=[("time", "i8"), ("close", "f8")])
    bars["time"] = [stamp(days[0], "14:56"), stamp(days[0], "14:59"),
                    stamp(days[1], "14:56"), stamp(days[1], "14:59"),
                    stamp(days[2], "11:00"), stamp(days[2], "11:03")]
    bars["close"] = [10.5, 99, 11, 99, 12, 99]
    result = read_replay_follow([tmp_path], days[2], preferred_run=str(directory),
                                price_days=days, minute_cache={"000568": bars},
                                now_ts=stamp(days[2], "12:00"))
    assert set(result["sources"]) == set(days[:2])
    assert result["independent"] is True
    row = result["rows"][0]
    assert row["days"] == days
    assert row["last_price"] == 12
    assert row["status"] == "所选日仅行情采样"
    assert row["signal_status"] == "仅行情采样，当日信号未知"
    assert row["timeline"][-1]["signal_records"] == 0
    assert row["timeline"][-1]["price_source"] == "分钟缓存采样"


def test_replay_missing_and_incomplete_archives_are_explicit(tmp_path):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "manifest.json").write_text('{"status":"running","completed":[]}', encoding="utf-8")
    result = read_replay_follow([tmp_path], "2026-10-30")
    assert result["status"] == "unavailable"
    assert result["rows"] == []


def test_replay_archive_read_can_be_cancelled(tmp_path):
    archive(tmp_path, "run", "2026-10-29", [])
    result = read_replay_follow([tmp_path], "2026-10-30", should_cancel=lambda: True)
    assert result["status"] == "cancelled"


def test_legacy_or_different_engine_runs_are_not_silently_mixed(tmp_path):
    first = archive(tmp_path, "first", "2026-10-28", [])
    second = archive(tmp_path, "second", "2026-10-29", [])
    path = second / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["engine_fingerprint"] = "different"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert set(read_replay_follow([tmp_path], "2026-10-30", str(first))["sources"]) == {"2026-10-28"}
    path = first / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["engine_fingerprint"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = read_replay_follow([tmp_path], "2026-10-30", str(first))
    assert set(result["sources"]) == {"2026-10-28"}
    assert "缺少版本指纹" in result["compatibility_note"]


def test_archive_using_production_history_is_not_labeled_independent(tmp_path):
    directory = archive(tmp_path, "run", "2026-10-29", [])
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["config"]["use_production_history"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = read_replay_follow([], "2026-10-30", str(directory))
    assert result["independent"] is False
    assert result["production_history"] is True
    manifest["config"]["use_production_history"] = False
    manifest["config"]["market_path"] = "logs/fusion_state/market_history.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert read_replay_follow([], "2026-10-30", str(directory))["independent"] is False


def test_malformed_replay_rows_are_reported_and_do_not_block_valid_data(tmp_path):
    day = "2026-10-29"
    valid = {"code": "000568", "ts": stamp(day, "10:00"), "entry": 10, "tier": 2}
    directory = archive(tmp_path, "valid", day, [valid, {"code": "000001", "ts": "invalid", "entry": 10}])
    result = read_replay_follow([], day, str(directory))
    assert [row["code"] for row in result["rows"]] == ["000568"]
    assert "1条回放记录无效" in result["errors"][0]


def test_same_day_future_replay_records_are_not_displayed(tmp_path):
    day = "2026-10-30"
    rows = [{"code": "000568", "ts": stamp(day, hm), "entry": price, "tier": 2}
            for hm, price in (("10:00", 10), ("14:00", 20))]
    directory = archive(tmp_path, "run", day, rows)
    result = read_replay_follow([], day, str(directory), now_ts=stamp(day, "12:00"))
    assert result["rows"][0]["last_price"] == 10
    assert "1条回放记录无效" in result["errors"][0]


def test_stream_comparison_requires_same_date_and_nearby_time():
    live = {"code": "000568", "first_day": "2026-10-29", "first_ts": stamp("2026-10-29", "10:00"), "reference": 10}
    replay = dict(live, first_ts=stamp("2026-10-29", "10:02"), reference=10.1)
    assert "价差+1.00%" in compare_signal_streams([live], [replay])["000568"]
    replay["first_ts"] = stamp("2026-10-29", "10:30")
    assert "未作同刻价格比较" in compare_signal_streams([live], [replay])["000568"]
    replay["first_day"] = "2026-10-30"
    assert "无共同记录日" in compare_signal_streams([live], [replay])["000568"]


def test_stream_comparison_uses_latest_shared_signal_day_not_price_only_day():
    live = {"code": "000568", "first_day": "2026-10-28", "timeline": [
        {"day": "2026-10-28", "first_ts": stamp("2026-10-28", "10:00"), "first_price": 10, "signal_records": 1},
        {"day": "2026-10-30", "first_ts": stamp("2026-10-30", "10:00"), "first_price": 11, "signal_records": 1}]}
    replay = {"code": "000568", "first_day": "2026-10-28", "timeline": [
        {"day": "2026-10-28", "first_ts": stamp("2026-10-28", "10:01"), "first_price": 10.1, "signal_records": 1},
        {"day": "2026-10-30", "first_ts": stamp("2026-10-30", "15:00"), "first_price": 12, "signal_records": 0}]}
    assert "2026-10-28" in compare_signal_streams([live], [replay])["000568"]
    assert "2026-10-30" not in compare_signal_streams([live], [replay])["000568"]
    replay["timeline"][-1]["signal_records"] = 1
    compared = compare_signal_streams([live], [replay])["000568"]
    assert "2026-10-28" in compared and "2026-10-30" in compared


def test_selected_run_replaces_overlap_even_if_old_manifest_was_touched(tmp_path):
    day = "2026-10-29"
    signal = {"code": "000568", "ts": stamp(day, "10:00"), "entry": 10, "tier": 2}
    old = archive(tmp_path, "old", day, [signal])
    other_day = "2026-10-28"
    archive(tmp_path, "nonoverlap", other_day, [{**signal, "ts": stamp(other_day, "10:00")}])
    fresh = archive(tmp_path, "fresh", day, [])
    os.utime(old / "manifest.json", (time.time() + 100, time.time() + 100))
    result = read_replay_follow([tmp_path], day, preferred_run=str(fresh))
    assert result["sources"][day] == str(fresh / (day + ".json.gz"))
    assert other_day in result["sources"]
    assert result["rows"][0]["last_day"] == other_day
    assert (old / (day + ".json.gz")).exists()


def test_replacement_day_with_bad_archive_does_not_revive_old_signals(tmp_path):
    day = "2026-10-29"
    archive(tmp_path, "old", day, [{"code": "000568", "ts": stamp(day, "10:00"), "entry": 10, "tier": 2}])
    fresh = archive(tmp_path, "fresh", day, [])
    (fresh / (day + ".json.gz")).write_bytes(b"broken")
    result = read_replay_follow([tmp_path], day, preferred_run=str(fresh))
    assert result["errors"] and not result["rows"]
