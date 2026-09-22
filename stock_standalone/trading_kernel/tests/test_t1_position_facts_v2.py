# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from trading_kernel.snapshot_v2 import migrate_reconciliation_snapshot
from trading_kernel.t1_position_facts import build_t1_position_facts


def _iso(day, hour=9, minute=31):
    return datetime.combine(day, datetime.min.time()).replace(
        hour=hour, minute=minute
    ).isoformat(timespec="seconds")


def test_t1_facts_split_yesterday_sellable_and_today_buy():
    today = date.today()
    yesterday = today - timedelta(days=1)
    positions = {
        "000001": {
            "code": "000001",
            "volume": 150,
            "entry_price": 10.0,
            "entry_time": _iso(yesterday),
        }
    }
    orders = [
        {
            "code": "000001", "action": "BUY", "volume": 100, "price": 10.0,
            "timestamp": _iso(yesterday),
        },
        {
            "code": "000001", "action": "ADD", "volume": 50, "price": 10.5,
            "timestamp": _iso(today),
        },
    ]
    facts = build_t1_position_facts(
        positions, orders, trading_day=today.isoformat()
    )["000001"]
    assert facts["total_qty"] == 150
    assert facts["sellable_qty"] == 100
    assert facts["today_buy_qty"] == 50
    assert facts["unresolved_qty"] == 0
    assert len(facts["lots"]) == 2
    assert facts["lots"][0]["sellable"] is True
    assert facts["lots"][1]["today_buy"] is True


def test_t1_legacy_unknown_quantity_fails_closed():
    today = date.today()
    facts = build_t1_position_facts(
        {
            "000001": {
                "code": "000001",
                "volume": 100,
                "entry_price": 10.0,
                "entry_time": "N/A",
            }
        },
        [],
        trading_day=today.isoformat(),
    )["000001"]
    assert facts["total_qty"] == 100
    assert facts["sellable_qty"] == 0
    assert facts["today_buy_qty"] == 0
    assert facts["unresolved_qty"] == 100
    assert facts["t1_fact_status"] == "INCOMPLETE_FAIL_CLOSED"


def test_t1_facts_trim_old_order_ledger_to_authoritative_position_snapshot():
    today = date.today()
    yesterday = today - timedelta(days=1)
    facts = build_t1_position_facts(
        {"000001": {"volume": 80, "entry_time": _iso(yesterday)}},
        [
            {
                "code": "000001", "action": "BUY", "volume": 100,
                "price": 10, "timestamp": _iso(yesterday),
            }
        ],
        trading_day=today.isoformat(),
    )["000001"]
    assert facts["total_qty"] == 80
    assert sum(lot["qty"] for lot in facts["lots"]) == 80
    assert facts["sellable_qty"] == 80


def test_reconciliation_snapshot_v1_migration_defaults_t1_fail_closed():
    v1 = {
        "snapshot_version": "1.0",
        "account": {"cash": 1000000},
        "positions": {
            "000001": {
                "volume": 100,
                "entry_price": 10.0,
            }
        },
        "orders": [],
        "reconciliation": {"status": "ALIGNED"},
    }
    migrated, status = migrate_reconciliation_snapshot(v1)
    assert status == "OK"
    assert migrated["snapshot_version"] == "2.0"
    pos = migrated["positions"]["000001"]
    assert pos["total_qty"] == 100
    assert pos["sellable_qty"] == 0
    assert pos["today_buy_qty"] == 0
    assert pos["unresolved_qty"] == 100
    assert pos["t1_fact_status"] == "MIGRATED_V1_FAIL_CLOSED"


def test_reconciliation_snapshot_rejects_future_or_invalid_t1_facts():
    migrated, status = migrate_reconciliation_snapshot(
        {"snapshot_version": "3.0"}
    )
    assert migrated is None
    assert status.startswith("UNSUPPORTED_SNAPSHOT_VERSION")

    bad = {
        "snapshot_version": "2.0",
        "account": {},
        "positions": {
            "000001": {
                "total_qty": 100,
                "sellable_qty": 101,
                "today_buy_qty": 0,
                "lots": [],
            }
        },
        "orders": [],
        "reconciliation": {},
    }
    migrated, status = migrate_reconciliation_snapshot(bad)
    assert migrated is None
    assert status == "T1_FACTS_EXCEED_TOTAL:000001"


def test_reconciliation_snapshot_fail_closed_on_malformed_v2_facts():
    base = {
        "snapshot_version": "2.0",
        "account": {},
        "orders": [],
        "reconciliation": {},
    }
    malformed = dict(base, positions={"000001": []})
    migrated, status = migrate_reconciliation_snapshot(malformed)
    assert migrated is None
    assert status == "INVALID_POSITION:000001"

    overallocated = dict(base, positions={
        "000001": {
            "total_qty": 100,
            "sellable_qty": 70,
            "today_buy_qty": 40,
            "unresolved_qty": 0,
            "lots": [],
        }
    })
    migrated, status = migrate_reconciliation_snapshot(overallocated)
    assert migrated is None
    assert status == "T1_FACTS_OVERALLOCATED:000001"

    invalid_migration = dict(base, positions={}, migration=[])
    migrated, status = migrate_reconciliation_snapshot(invalid_migration)
    assert migrated is None
    assert status == "INVALID_MIGRATION"
