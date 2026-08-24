import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.intraday_strategy_engine import IntradayStrategyEngine

fetcher = TDXRealtimeFetcher.get_instance()
engine = IntradayStrategyEngine.get_instance()

c = '688826'
snap = fetcher.fetch_stock_snapshot(c)
print('SNAP:', 'open:', snap['open_price'], 'price:', snap['price'], 'high:', snap['high_price'], 'low:', snap['low_price'], 'vwap:', snap['vwap'])

bars = fetcher.fetch_intraday_bars(c)
print('BARS shape:', bars.shape)
print('BARS high max:', bars['high'].max(), 'low min:', bars['low'].min())

engine.hydrate_from_intraday_df(c, bars, snap['open_price'])
st = engine._get_stock_state(c, snap['open_price'])
print('STATE after hydration:', 'open:', st['open_price'], 'max:', st['max_price'], 'min:', st['min_price'], 'high_am:', st['high_am'])

eval_res = engine.evaluate_seven_nodes(
    code=c,
    current_time_str='15:00:00',
    open_price=snap['open_price'],
    price=snap['price'],
    high_price=st['max_price'],
    low_price=st['min_price'],
    vwap=snap['vwap'],
    turnover_rate=snap['turnover_rate'],
    amount=snap['amount'],
    last_close=snap['last_close']
)

print('EVAL SCORE:', eval_res['total_weighted_score'])
print('PATTERN:', eval_res['pattern'])
print('ACTION:', eval_res['action_execution_text'])
for nr in eval_res['node_results']:
    print(f"  Node {nr['node_id']} ({nr['name']}, {nr['time_str']}): input={nr['input_val']}, judgment={nr['judgment']}, score={nr['final_score']}, weight={nr['weight_pct']}, remarks={nr.get('remarks')}")
