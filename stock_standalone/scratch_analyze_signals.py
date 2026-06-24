# -*- coding: utf-8 -*-
"""Quick analysis of paper account and kernel trace"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

DB_DIR = r'D:\JohnsonProgram\instockMonitorTK'

# Paper account positions analysis
paper_path = os.path.join(DB_DIR, 'logs', 'paper_account_state.json')
with open(paper_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Cash: {data.get('cash', 0):.2f}")
print(f"Initial Capital: {data.get('initial_capital', 0):.2f}")
positions = data.get('positions', {})
print(f"Active Positions: {len(positions)}")

# Analyze position P&L
total_unrealized = 0
win_pos = 0
loss_pos = 0
for code, pos in positions.items():
    entry = pos.get('entry_price', 0)
    current = pos.get('current_price', 0) or pos.get('last_price', 0)
    vol = pos.get('volume', 0)
    if entry > 0 and current > 0:
        pnl = (current - entry) / entry * 100
        unrealized = (current - entry) * vol
        total_unrealized += unrealized
        if pnl > 0:
            win_pos += 1
        else:
            loss_pos += 1
        if abs(pnl) > 5:  # Show significant positions
            print(f"  {code}: Entry={entry:.2f} Curr={current:.2f} PnL={pnl:+.1f}% Vol={vol}")

print(f"\nP&L Summary: Win={win_pos} Loss={loss_pos} Total Unrealized ~{total_unrealized:.0f}")

# Order analysis
orders = data.get('orders', [])
print(f"\nTotal Orders: {len(orders)}")
buy_orders = [o for o in orders if o.get('action') == 'BUY']
sell_orders = [o for o in orders if o.get('action') == 'SELL']
print(f"BUY orders: {len(buy_orders)}, SELL orders: {len(sell_orders)}")

# Recent buy orders with reasons
print("\nRecent BUY orders:")
for o in buy_orders[-10:]:
    reason = str(o.get('reason', ''))[:100]
    print(f"  {o.get('timestamp','')} {o.get('code','')} P={o.get('price',0):.2f} V={o.get('volume',0)} | {reason}")

# Trading kernel trace - look at actual keys
trace_path = os.path.join(DB_DIR, 'logs', 'trading_kernel_trace.jsonl')
print(f"\n{'='*60}")
print(f"TRADING KERNEL TRACE KEYS")
with open(trace_path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i < 3:
            d = json.loads(line.strip())
            print(f"  Keys: {list(d.keys())}")
            print(f"  Data: {json.dumps(d, ensure_ascii=False)[:300]}")
        if i >= 3:
            break

# Last 5 entries with full data
lines = open(trace_path, 'r', encoding='utf-8').readlines()
print(f"\nLast 5 entries:")
for line in lines[-5:]:
    d = json.loads(line.strip())
    print(f"  {json.dumps(d, ensure_ascii=False)[:250]}")
