"""Fetch Kalshi KXHIGH* settled markets + hourly candlesticks (public, unauthenticated endpoints).
Live tier: /events, /series/{s}/markets/{t}/candlesticks  (markets settled after historical cutoff)
Historical tier: /historical/markets, /historical/markets/{t}/candlesticks (settled before cutoff)."""
import json, os, sys, time, datetime as dt, requests
B = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ["KXHIGHNY","KXHIGHCHI","KXHIGHMIA","KXHIGHLAX","KXHIGHAUS","KXHIGHDEN","KXHIGHPHIL"]
START = dt.datetime(2026,4,1,tzinfo=dt.timezone.utc)
OUT = "data"; import threading; _tl = threading.local()
def _s():
    if not hasattr(_tl,"s"): _tl.s = requests.Session()
    return _tl.s
def get(path, **p):
    for i in range(6):
        r = _s().get(B+path, params=p, timeout=30)
        if r.status_code == 429: time.sleep(1+i); continue
        if r.status_code == 404: return None
        r.raise_for_status(); time.sleep(0.2); return r.json()
    raise RuntimeError(path)
def iso(s): return dt.datetime.fromisoformat(s.replace("Z","+00:00"))
def f(x): return None if x is None else float(x)
def norm_candle(c):
    g = lambda d,k: (d or {}).get(k+"_dollars", (d or {}).get(k))
    return dict(ts=c["end_period_ts"], ask=f(g(c.get("yes_ask"),"close")), bid=f(g(c.get("yes_bid"),"close")),
                last=f(g(c.get("price"),"close")), vol=f(c.get("volume_fp", c.get("volume"))))
def markets(series):
    out = {}
    cur = None
    while True:
        d = get("/historical/markets", series_ticker=series, limit=1000, cursor=cur)
        for m in d["markets"]: out[m["ticker"]] = (m, True)
        cur = d.get("cursor")
        if not cur or not d["markets"] or iso(d["markets"][-1]["close_time"]) < START: break
    cur = None
    while True:
        d = get("/events", series_ticker=series, status="settled", limit=200, with_nested_markets="true", cursor=cur)
        for e in d["events"]:
            for m in e.get("markets") or []: out.setdefault(m["ticker"], (m, False))
        cur = d.get("cursor")
        if not cur or not d["events"]: break
    return [v for v in out.values() if iso(v[0]["close_time"]) >= START and v[0].get("result") in ("yes","no")]
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for s in SERIES:
        fn = f"{OUT}/{s}.json"
        if os.path.exists(fn): continue
        ms = markets(s); rows = []
        print(s, len(ms), flush=True)
        from concurrent.futures import ThreadPoolExecutor
        def one(mh):
            m, hist = mh
            st = int(iso(m["open_time"]).timestamp()); en = int(iso(m["close_time"]).timestamp())
            p = f"/historical/markets/{m['ticker']}/candlesticks" if hist else f"/series/{s}/markets/{m['ticker']}/candlesticks"
            d = get(p, start_ts=st, end_ts=en, period_interval=60) or {}
            return (dict(ticker=m["ticker"], event=m["event_ticker"], result=m["result"], hist=hist,
                strike_type=m.get("strike_type"), floor=m.get("floor_strike"), cap=m.get("cap_strike"),
                expiration_value=m.get("expiration_value"), open_time=m["open_time"], close_time=m["close_time"],
                candles=[norm_candle(c) for c in d.get("candlesticks", [])]))
        with ThreadPoolExecutor(6) as ex: rows = list(ex.map(one, ms))
        json.dump(rows, open(fn,"w")); print("done", s, flush=True)
