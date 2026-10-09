"""Refresh frozen ATS parity data for pure-Go tests; never needed by server."""
import argparse
import datetime as dt
import json
import gzip
import sys
import types
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def generate(target):
    reference = ROOT/'tools/sbc_reference'
    engine = types.ModuleType('sbc_reference')
    sys.modules[engine.__name__] = engine
    exec((reference/'engine.py').read_text(encoding='utf-8'), engine.__dict__)
    exec((reference/'adapter.py').read_text(encoding='utf-8'), engine.__dict__)
    cases = []
    coverage = set()

    def add(name, prices, volume=None, period='day', wick=.3, opens=None):
        rng = np.random.RandomState(42)
        bars = []
        for i,close in enumerate(prices):
            opening = float(opens[i]) if opens is not None else float(close)
            bars.append(dict(symbol='600733.SH',time=(dt.datetime(2025,1,1)+dt.timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                open=opening, high=float(max(opening,close)+wick), low=float(min(opening,close)-wick),close=float(close),
                volume=float(volume[i]) if volume is not None else int(rng.randint(1000,100000)),amount=100000,
                meta={'source':'isolated-ats-reference','stale':True,'trade_date':'2025-10-09'}))
        request=dict(symbol='600733.SH',period=period,bars=bars)
        expected=engine.analyze(request)
        strategy=expected['strategy']
        coverage.add(strategy['pattern_name'] + (' 命中' if strategy['is_matched'] else ' 未命中'))
        cases.append(dict(name=name,input=request,expected=expected))

    for size in (10,14,15,24,25,29,30,72,73,120):
        add('flat-'+str(size),np.full(size,10.),np.zeros(size))
    add('ascending',np.linspace(10,20,150))
    add('descending',np.linspace(20,10,150))
    add('weekly',np.linspace(10,12,80),period='week')
    add('monthly',np.linspace(20,10,60),period='month')
    add('minute',np.linspace(10,12,100),period='5')
    for seed in range(8):
        rng=np.random.RandomState(seed)
        add('random-'+str(seed),10+np.cumsum(rng.normal(.015,.12,160)))
    add('maximum-size',10+np.sin(np.arange(1000)/8),np.full(1000,10000))
    add('dominant-drop',np.r_[np.linspace(20,21,15),np.linspace(21,7,40),np.linspace(7,8,25)])
    add('rebound-subchannel',np.r_[np.linspace(20,12,25),np.linspace(12,20,15)])
    prices=np.full(70,10.);prices[25:]=10.5;prices[45:]=11.;prices[65:]=11.6
    volumes=np.full(70,10000.);volumes[[25,45,65]]=100000
    add('pioneer-multiple',prices,volumes)
    # Descending -> dry base -> breakout, no 2.8% candle (separate strategy branch).
    prices=np.r_[np.linspace(20,10,35),np.full(12,10.5),np.linspace(10.6,11,5)]
    volumes=np.r_[np.full(35,10000),np.full(12,2000),np.full(5,5000)]
    add('bottom-reversal',prices,volumes,wick=.05)
    prices=np.r_[np.linspace(20,10,35),np.full(12,10.5),np.full(4,10.3),10.56]
    add('bottom-last-bar-breakout',prices,volumes,wick=.05)
    # Quiet support retest rather than a volume breakout.
    prices=np.r_[np.linspace(10,12,65),np.linspace(12,11.8,5)]
    add('ascending-pullback',prices,np.full(70,10000),wick=.05)
    add('oscillator-turns',10+np.sin(np.arange(240)/10)*4,np.full(240,10000))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(gzip.compress((json.dumps(cases,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8'),mtime=0))
    print('cases:',len(cases),'bytes:',target.stat().st_size)
    print('strategies:',sorted(coverage))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'source/easy-stock-analysis/backend/internal/sbc/testdata/ats_v1.json.gz')
    generate(parser.parse_args().output)
