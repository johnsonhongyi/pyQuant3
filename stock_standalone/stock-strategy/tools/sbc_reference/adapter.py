import json
import sys

def analyze(request):
    bars = request["bars"]
    if not 10 <= len(bars) <= 1000:
        raise ValueError("SBC requires 10 to 1000 bars")
    frame = pd.DataFrame(bars)
    frame.index = pd.to_datetime(frame.pop("time"), utc=True)
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("bars must have unique ascending timestamps")
    for name in ("open", "high", "low", "close", "volume"):
        values = frame[name].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("invalid " + name)
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("prices must be positive")
    if ((frame.high < frame[["open", "close", "low"]].max(axis=1)) |
            (frame.low > frame[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("invalid OHLC bounds")
    frame["vol"] = frame.volume
    frame = td_sequential_fast(calc_trend_channel(frame))
    for period in (5, 10, 20):
        frame["ma" + str(period)] = frame.close.rolling(period).mean()
    columns = [c for c in frame.columns if c.startswith(("ch_", "fib_", "sig_", "td_", "ma"))]
    columns += ["chan_kx", "reversal_line", "open", "high", "low", "close"]
    points = json.loads(frame[columns].to_json(orient="records"))
    for point, bar in zip(points, bars):
        point["time"] = bar["time"]
    days = []
    if request.get("period") == "day":
        for i in range(max(1, len(frame) - 5), len(frame)):
            amp = round(float((frame.high.iloc[i] - frame.low.iloc[i]) / frame.close.iloc[i-1] * 100), 1)
            days.append([str(bars[i]["time"])[:10], amp])
    activity = None
    if days:
        amps = [item[1] for item in days]
        avg, maximum = round(float(np.mean(amps)), 1), max(amps)
        rating = "极高活跃" if avg >= 7 or maximum >= 10 else "高度活跃" if avg >= 4.5 else "温和波动" if avg >= 2.5 else "低位沉寂"
        activity = {"avg_amp": avg, "max_amp": maximum, "days": days, "rating": rating}
    return {"schema_version": 1, "source": "ats-sbc", "period": request["period"],
            "symbol": request["symbol"], "as_of": bars[-1]["time"],
            "trade_date": (bars[-1].get("meta") or {}).get("trade_date") or str(bars[-1]["time"])[:10],
            "market_meta": bars[-1].get("meta"), "points": points,
            "activity": activity,
            "levels": [{"ratio": ratio, "price": float(frame.low.min() + (frame.high.max()-frame.low.min())*ratio)}
                       for ratio in (0.191, 0.382, 0.5, 0.618, 0.809)],
            "strategy": evaluate_channel_strategy(frame)}

if __name__ == "__main__":
    try:
        print(json.dumps(analyze(json.load(sys.stdin)), allow_nan=False))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
