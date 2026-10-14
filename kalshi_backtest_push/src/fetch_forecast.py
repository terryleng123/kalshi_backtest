"""Archived day-ahead model forecasts via Open-Meteo Previous Runs API (temperature_2m_previous_day1 =
value forecast by the run ~24h earlier). Proxy for NWS forecasts (true NWS/NDFD point-forecast archives are not
readily available via a simple API). Daily max over local calendar day."""
import json, requests
ST = {"KXHIGHNY":(40.7789,-73.9692,"America/New_York"),"KXHIGHCHI":(41.7868,-87.7522,"America/Chicago"),
 "KXHIGHMIA":(25.7906,-80.3164,"America/New_York"),"KXHIGHLAX":(33.9382,-118.3866,"America/Los_Angeles"),
 "KXHIGHAUS":(30.1945,-97.6699,"America/Chicago"),"KXHIGHDEN":(39.8466,-104.6562,"America/Denver"),
 "KXHIGHPHIL":(39.8733,-75.2268,"America/New_York")}
out = {}
for s,(la,lo,tz) in ST.items():
    r = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", params=dict(latitude=la, longitude=lo,
        hourly="temperature_2m_previous_day1,temperature_2m_previous_day2", temperature_unit="fahrenheit", timezone=tz,
        start_date="2026-01-01", end_date="2026-10-12"), timeout=60).json()
    h = r["hourly"]; d = {}
    for t,v1,v2 in zip(h["time"], h["temperature_2m_previous_day1"], h["temperature_2m_previous_day2"]):
        day = t[:10]; e = d.setdefault(day, [[],[]])
        if v1 is not None: e[0].append(v1)
        if v2 is not None: e[1].append(v2)
    out[s] = {k:(max(a) if len(a)==24 else None, max(b) if len(b)==24 else None) for k,(a,b) in d.items()}
json.dump(out, open("data/forecasts.json","w")); print({k:len(v) for k,v in out.items()})
