from ats.fusion.focus import select_focus, audit_focus


def test_focus_is_causal_bounded_and_drops_invalid_latest_quote():
    def row(code, ts=100, **kw):
        return dict(code=code, ts=ts, time="09:31", entry=10.1, pct=1,
                    patterns=["逆势收复启动"],
                    reclaim_detail={"vwap": 10, "vwap3": 10, "vwap5": 10, "hold_ratio": .8}, **kw)
    rows = [row(str(i)) for i in range(15)]
    rows += [row("future", ts=200), row("stale", ts=1), row("veto", veto="风险否决")]
    rows.append({**rows[0], "ts": 101, "patterns": []})
    selected = select_focus(rows, 110, max_age=60)
    assert len(selected) == 10
    assert not {"0", "future", "stale"} & {r["code"] for r in selected}
    assert select_focus([row("veto", veto="退潮期非龙头")], 110)[0]["execution_veto"] == "退潮期非龙头"
    fresh = row("fresh")
    fresh["counter_reclaim_first_ts"] = 100
    fresh["reclaim_detail"]["hold_ratio"] = .5
    assert select_focus(rows + [fresh], 110)[0]["code"] == "fresh"
    concentrated = [dict(row(str(i)), sector="同一板块") for i in range(12)]
    assert len(select_focus(concentrated, 110)) == 2
    assert len(concentrated) == 12
    audit = audit_focus([row("one"), row("one", ts=200)], {"one": 10})
    assert audit["false_positive_count"] == 1
    assert audit["daily_distinct"] == 1


def test_cross_day_keeps_early_observation_even_when_execution_is_vetoed():
    import time
    from ats.fusion.cross_day import build_cross_day
    day = "2026-10-29"
    ts = time.mktime(time.strptime(day + " 09:40", "%Y-%m-%d %H:%M"))
    data = {day: {"600809": [dict(code="600809", ts=ts, price=112.77,
                                  patterns=["逆势收复启动"],
                                  fusion={"tier": 0, "veto_reason": "退潮期非龙头"})]}}
    state = build_cross_day(data, "2026-10-30")[0]
    assert state["reference"] == 112.77
    assert state["signal_status"] == "信号被否决"
    assert state["status"] == "所选日无记录"
