"""Backtests for Strategy A (mutually-exclusive mispricing) and B (weather forecast edge).
Data: Kalshi hourly candlesticks (yes_bid/yes_ask CLOSE of each hour = proxy for top of book; NO depth info).
"""
import json, glob, math, collections, datetime as dt
from zoneinfo import ZoneInfo
TZ = {"KXHIGHNY":"America/New_York","KXHIGHCHI":"America/Chicago","KXHIGHMIA":"America/New_York",
      "KXHIGHLAX":"America/Los_Angeles","KXHIGHAUS":"America/Chicago","KXHIGHDEN":"America/Denver","KXHIGHPHIL":"America/New_York"}
START_EQ, DD_STOP, VOL_FRAC = 500.0, 0.10, 0.10
def fee(n, p):  # Kalshi taker fee, ceil to cent, per order (leg)
    return math.ceil(round(0.07*n*p*(1-p)*100, 6))/100 if n > 0 else 0.0
def load():
    ev = collections.defaultdict(list)
    for fn in sorted(glob.glob("data/KXHIGH*.json")):
        s = fn.split("/")[-1][:-5]
        for m in json.load(open(fn)): m["series"] = s; ev[m["event"]].append(m)
    return ev
def event_day(et):  # KXHIGHNY-26OCT12 -> date
    return dt.datetime.strptime(et.split("-")[1], "%y%b%d").date()
class Book:
    def __init__(s, stop=DD_STOP): s.stop=stop; s.eq=START_EQ; s.peak=START_EQ; s.maxdd=0; s.halted=None; s.trades=[]
    def settle(s, day, pnl, info):
        if s.halted: return
        s.eq += pnl; s.trades.append(dict(day=str(day), pnl=round(pnl,2), eq=round(s.eq,2), **info))
        s.peak = max(s.peak, s.eq); dd = 1 - s.eq/s.peak; s.maxdd = max(s.maxdd, dd)
        if dd >= s.stop: s.halted = str(day)   # halt & flatten (positions settle same day; no new opens)
    def summary(s):
        t = s.trades; by = collections.defaultdict(float); byq = collections.defaultdict(float)
        for x in t:
            by[x["day"][:7]] += x["pnl"]; d = dt.date.fromisoformat(x["day"]); byq[f"{d.year}Q{(d.month-1)//3+1}"] += x["pnl"]
        return dict(trades=len(t), wins=sum(x["pnl"]>0 for x in t), win_rate=round(sum(x["pnl"]>0 for x in t)/len(t),3) if t else None,
            net_pnl=round(s.eq-START_EQ,2), return_pct=round((s.eq/START_EQ-1)*100,2), max_dd_pct=round(s.maxdd*100,2),
            halted_on=s.halted, pnl_by_month={k:round(v,2) for k,v in sorted(by.items())}, pnl_by_quarter={k:round(v,2) for k,v in sorted(byq.items())})
# ---------------- Strategy A ----------------
def strat_a(ev):
    raw = []; checked = 0; bad_mece = 0; crossed = 0
    for et, ms in ev.items():
        if sum(m["result"]=="yes" for m in ms) != 1: bad_mece += 1; continue
        idx = [{c["ts"]:c for c in m["candles"]} for m in ms]
        common = set.intersection(*[set(i) for i in idx]) if idx else set()
        seen = False
        for ts in sorted(common):
            cs = [i[ts] for i in idx]; checked += 1
            if any(c["ask"] is not None and c["bid"] is not None and c["bid"] > c["ask"] for c in cs): crossed += 1; continue
            asks = [c["ask"] for c in cs]; bids = [c["bid"] for c in cs]; vols = [c["vol"] or 0 for c in cs]
            # BUY all YES at ask
            if all(a is not None and 0 < a < 1 for a in asks):
                g = 1 - sum(asks) - sum(fee(1,a) for a in asks)
                if g > 0: raw.append(dict(event=et, ts=ts, side="buy_all_yes", gross_sum=round(sum(asks),4), edge_1set=round(g,4), minvol=min(vols), prices=asks))
            # BUY all NO at (1-bid)  == selling YES set when sum(bids) > 1
            if all(b is not None and 0 < b < 1 for b in bids):
                nos = [1-b for b in bids]; g = (len(ms)-1) - sum(nos) - sum(fee(1,p) for p in nos)
                if g > 0: raw.append(dict(event=et, ts=ts, side="buy_all_no", gross_sum=round(sum(bids),4), edge_1set=round(g,4), minvol=min(vols), prices=nos))
    # one trade per event (first qualifying hour), size limited by min leg hourly volume * VOL_FRAC and cash
    first = {}
    for r in sorted(raw, key=lambda r: r["ts"]): first.setdefault(r["event"], r)
    bk = Book(); depth_notes = []
    for r in sorted(first.values(), key=lambda r: event_day(r["event"])):
        if bk.halted: break
        cost1 = sum(r["prices"])
        n = int(min(r["minvol"]*VOL_FRAC, bk.eq/cost1))
        if n < 1: depth_notes.append(r["event"]); continue
        payout = n*(1 if r["side"]=="buy_all_yes" else len(r["prices"])-1)
        pnl = payout - n*cost1 - sum(fee(n,p) for p in r["prices"])
        bk.settle(event_day(r["event"]), pnl, dict(event=r["event"], side=r["side"], sets=n, edge_1set=r["edge_1set"]))
    s = bk.summary()
    s.update(event_hours_checked=checked, crossed_candle_hours_excluded=crossed, events=len(ev), events_not_exactly_one_yes=bad_mece, raw_opportunity_hours=len(raw),
             events_with_opportunity=len(first), skipped_zero_volume=len(depth_notes),
             median_edge_1set=sorted(r["edge_1set"] for r in raw)[len(raw)//2] if raw else None,
             median_minleg_volume=sorted(r["minvol"] for r in first.values())[len(first)//2] if first else None)
    return s, bk, raw
# ---------------- Strategy B ----------------
def ncdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def bracket(m):
    st = m["strike_type"]
    if st == "between": return m["floor"]-0.5, m["cap"]+0.5
    if st == "greater": return m["floor"]+0.5, 1e9
    if st == "less": return -1e9, m["cap"]-0.5
    return None
def strat_b(ev, dd_stop=True, decide_hour=8, margin=0.05, kelly=0.25, window=30, minhist=15, lead="d1"):
    fc = json.load(open("data/forecasts.json")); li = 0 if lead=="d1" else 1
    # observed daily high = expiration_value (settlement source value)
    obs = {}
    for et, ms in ev.items():
        v = []
        for m in ms:
            try: v.append(float(m.get("expiration_value")))
            except (TypeError, ValueError): pass
        if v: obs[et] = v[0]
    days = sorted(ev, key=event_day); bk = Book()
    bk.stop = DD_STOP if dd_stop else 9.9; cal = []; mismatch = 0
    hist = collections.defaultdict(list)  # series -> [(day, err)]
    byday = collections.defaultdict(list)
    for et in days: byday[event_day(et)].append(et)
    for day in sorted(byday):
        dayp = []
        for et in byday[day]:
            ms = ev[et]; s = ms[0]["series"]; f = fc[s].get(str(day), (None,None))[li]
            if f is None or et not in obs: continue
            past = [e for d,e in hist[s] if (day-d).days <= window and d < day]
            hist[s].append((day, obs[et]-f))
            # sanity: brackets consistent with result
            for m in ms:
                b = bracket(m)
                if b and ((b[0] <= obs[et] <= b[1]) != (m["result"]=="yes")): mismatch += 1
            if len(past) < minhist: continue
            mu = f + sum(past)/len(past); sd = max(1.0, (sum((e-sum(past)/len(past))**2 for e in past)/(len(past)-1))**0.5)
            tz = ZoneInfo(TZ[s]); dts = int(dt.datetime(day.year,day.month,day.day,decide_hour,tzinfo=tz).timestamp())
            best = None
            for m in ms:
                b = bracket(m); c = {x["ts"]:x for x in m["candles"]}.get(dts)
                if not b or not c or (c["ask"] is not None and c["bid"] is not None and c["bid"] > c["ask"]): continue
                p = ncdf((b[1]-mu)/sd) - ncdf((b[0]-mu)/sd); p = min(max(p,0.001),0.999)
                if c["ask"] and c["bid"] is not None: cal.append((p, (c["ask"]+c["bid"])/2, m["result"]=="yes"))
                for side, price, q in (("yes", c["ask"], p), ("no", None if c["bid"] is None else 1-c["bid"], 1-p)):
                    if price is None or not (0.01 <= price <= 0.99): continue
                    edge = q - price - fee(1, price)
                    if edge > margin and (best is None or edge > best[0]): best = (edge, m, side, price, q, c["vol"] or 0)
            if best: dayp.append((et, best))
        if bk.halted: continue   # keep collecting calibration stats, no trading
        eq0 = bk.eq
        for et, (edge, m, side, price, q, vol) in dayp:
            fstar = (q - price)/(1 - price); stake = min(kelly*fstar, 0.10)*eq0
            n = int(min(stake/price, vol*VOL_FRAC))
            if n < 1: continue
            win = (m["result"]=="yes") == (side=="yes")
            pnl = n*((1 if win else 0) - price) - fee(n, price)
            bk.settle(day, pnl, dict(event=et, ticker=m["ticker"], side=side, n=n, price=price, model_p=round(q,3), edge=round(edge,3)))
    s = bk.summary()
    br_m = sum((p-o)**2 for p,_,o in cal)/len(cal); br_k = sum((k-o)**2 for _,k,o in cal)/len(cal)
    s.update(params=dict(decide_hour_local=decide_hour, margin=margin, kelly=kelly, lead=lead), bracket_result_mismatches=mismatch,
             brier_model=round(br_m,4), brier_market_mid=round(br_k,4), calib_points=len(cal))
    return s, bk
if __name__ == "__main__":
    ev = load(); out = {}
    a, bka, raw = strat_a(ev); out["A"] = a
    json.dump(raw, open("reports/strategyA_raw_opportunities.json","w")); json.dump(bka.trades, open("reports/strategyA_trades.json","w"))
    out["B"] = {}
    for h in (8, 0): 
        for mg in (0.03, 0.05, 0.10):
            for ld in ("d1","d2"):
                s, bk = strat_b(ev, decide_hour=h, margin=mg, lead=ld); out["B"][f"h{h}_m{mg}_{ld}"] = s
                s2, _ = strat_b(ev, dd_stop=False, decide_hour=h, margin=mg, lead=ld); out["B"][f"h{h}_m{mg}_{ld}_NOSTOP"] = s2
                if (h,mg,ld)==(8,0.05,"d1"): json.dump(bk.trades, open("reports/strategyB_trades_base.json","w"))
    json.dump(out, open("reports/results.json","w"), indent=1); print(json.dumps(out, indent=1)[:6000])
