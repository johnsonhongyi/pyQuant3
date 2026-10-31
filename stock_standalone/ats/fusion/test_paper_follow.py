from ats.fusion.paper_follow import build_paper_follow


def order(identity, day, action, price, volume):
    return dict(order_id=identity, code="000568", timestamp=day + "T10:00:00",
                action=action, price=price, volume=volume, fee=1, request_id=identity)


def test_paper_add_reduce_exit_and_reentry_are_distinct_and_causal():
    snapshot = dict(read_status="READY", trade_date="2026-10-30", reconciliation={}, center={},
                    orders=[order("buy", "2026-10-28", "BUY", 10, 100),
                            order("add", "2026-10-29", "ADD", 12, 100),
                            order("reduce", "2026-10-30", "REDUCE", 11, 100),
                            order("exit", "2026-10-30", "SELL", 13, 100),
                            order("reentry", "2026-10-30", "BUY", 8, 100)],
                    positions={"000568": dict(volume=100, sellable_qty=0, entry_price=8, current_price=9)})
    current = build_paper_follow(snapshot, [], "2026-10-30")["rows"]
    closed = next(row for row in current if row["status"] == "已平仓")
    holding = next(row for row in current if row["status"] == "持仓")
    assert closed["realized"] == 196
    assert holding["remaining"] == 100
    assert holding["sellable"] == 0
    assert holding["floating_pct"] == 12.5
    assert holding["association"] == "无已匹配信号"
    history = build_paper_follow(snapshot, [], "2026-10-29")["rows"]
    assert len(history) == 1
    assert history[0]["remaining"] == 200
    assert history[0]["last_price"] == 12
    assert history[0].get("sellable") is None
    assert len(snapshot["orders"]) == 5


def test_missing_buy_and_blocked_account_are_visible_without_fake_profit():
    snapshot = dict(read_status="READY", trade_date="2026-10-30", positions={},
                    orders=[order("sell", "2026-10-30", "SELL", 10, 100)],
                    reconciliation={"paper_execution_ready": False, "block_reason": "CASH_MISMATCH"})
    output = build_paper_follow(snapshot, [], "2026-10-30")
    row = output["rows"][0]
    assert row["status"] == "账本待核"
    assert row["entry_time"] == ""
    assert row["realized"] is None
    assert output["account"]["reconciliation"]["block_reason"] == "CASH_MISMATCH"
