#!/usr/bin/env python3
"""
MLB HR Prop Finder v4
──────────────────────────────────────────────────────────────────────────────
Model factors:
  • Season HR/PA rate (base, min 30 PA)
  • vs LHP/RHP splits (regressed, max 45% weight)
  • Hotness: last 14 days HR/PA (regressed, max 35% weight, needs ≥8 PA)
  • Statcast: barrel% + hard-hit% from Baseball Savant (regressed, 40% weight)
  • Starting pitcher HR rate vs league avg (regressed, platoon-aware)
  • Bullpen HR rate (regressed, platoon-aware, weighted by reliever IP)
  • Park factor (29 venues)
  • Weather: temperature + wind speed for outdoor venues (Open-Meteo, free)

Usage:
  python mlb_hr_model.py                             # today, no lines
  python mlb_hr_model.py -d 2026-05-15               # specific date
  python mlb_hr_model.py -k YOUR_ODDS_KEY --open     # with lines, open report
  python mlb_hr_model.py -k KEY --email-to you@gmail.com --sms-to 5551234567 --carrier verizon

Environment variables (used automatically by GitHub Actions):
  ODDS_API_KEY        The Odds API key
  GMAIL_ADDRESS       Gmail address to send from
  GMAIL_APP_PASSWORD  Gmail App Password (not your regular password)
  REPORT_EMAIL        Email address to receive full HTML report
  REPORT_PHONE        10-digit phone number for SMS summary
  CARRIER             att | verizon | tmobile | sprint | boost | cricket
  BANKROLL            Bankroll in dollars for stake sizing

Setup:
  pip install requests pybaseball pandas
"""

import sys, os, math, argparse, smtplib, webbrowser, shutil, json, unicodedata
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

try:
    import pandas as pd
    from pybaseball import statcast_batter_exitvelo_barrels
    HAS_PYBASEBALL = True
except ImportError:
    HAS_PYBASEBALL = False


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

MLB_API      = "https://statsapi.mlb.com/api/v1"
LG_HR_PA     = 0.034
LG_BARREL    = 0.067
LG_HARD_HIT  = 0.385
VIG_FACTOR   = 1.055  # typical single-outcome prop overround (~5.5%)
MAX_PROP_ODDS = 2500  # filter out longshot/alternate lines above this threshold

PA_BY_SPOT = {1:4.7,2:4.6,3:4.5,4:4.4,5:4.3,6:4.1,7:4.0,8:3.9,9:3.8}

VENUES = {
    "Coors Field":              {"pf":1.38,"lat":39.756, "lon":-104.994,"out":True },
    "Great American Ball Park": {"pf":1.18,"lat":39.097, "lon":-84.507, "out":True },
    "Yankee Stadium":           {"pf":1.15,"lat":40.829, "lon":-73.926, "out":True },
    "Citizens Bank Park":       {"pf":1.10,"lat":39.906, "lon":-75.167, "out":True },
    "Rogers Centre":            {"pf":1.09,"lat":43.641, "lon":-79.389, "out":False},
    "American Family Field":    {"pf":1.08,"lat":43.028, "lon":-87.971, "out":True },
    "Fenway Park":              {"pf":1.07,"lat":42.347, "lon":-71.097, "out":True },
    "Guaranteed Rate Field":    {"pf":1.06,"lat":41.830, "lon":-87.634, "out":True },
    "Chase Field":              {"pf":1.05,"lat":33.445, "lon":-112.067,"out":False},
    "Globe Life Field":         {"pf":1.04,"lat":32.747, "lon":-97.084, "out":False},
    "Nationals Park":           {"pf":1.03,"lat":38.873, "lon":-77.008, "out":True },
    "Camden Yards":             {"pf":1.02,"lat":39.284, "lon":-76.622, "out":True },
    "Wrigley Field":            {"pf":1.02,"lat":41.948, "lon":-87.656, "out":True },
    "Minute Maid Park":         {"pf":1.01,"lat":29.757, "lon":-95.355, "out":False},
    "Truist Park":              {"pf":1.00,"lat":33.890, "lon":-84.468, "out":True },
    "Progressive Field":        {"pf":0.99,"lat":41.496, "lon":-81.685, "out":True },
    "Busch Stadium":            {"pf":0.97,"lat":38.623, "lon":-90.193, "out":True },
    "Citi Field":               {"pf":0.96,"lat":40.757, "lon":-73.846, "out":True },
    "Target Field":             {"pf":0.96,"lat":44.982, "lon":-93.278, "out":True },
    "PNC Park":                 {"pf":0.95,"lat":40.447, "lon":-80.006, "out":True },
    "Kauffman Stadium":         {"pf":0.93,"lat":39.052, "lon":-94.480, "out":True },
    "Tropicana Field":          {"pf":0.93,"lat":27.768, "lon":-82.653, "out":False},
    "T-Mobile Park":            {"pf":0.92,"lat":47.591, "lon":-122.332,"out":True },
    "loanDepot park":           {"pf":0.91,"lat":25.778, "lon":-80.220, "out":False},
    "Comerica Park":            {"pf":0.90,"lat":42.339, "lon":-83.049, "out":True },
    "Petco Park":               {"pf":0.88,"lat":32.707, "lon":-117.157,"out":True },
    "Oracle Park":              {"pf":0.85,"lat":37.778, "lon":-122.389,"out":True },
    "Angel Stadium":            {"pf":1.00,"lat":33.800, "lon":-117.883,"out":True },
    "Dodger Stadium":           {"pf":0.98,"lat":34.074, "lon":-118.240,"out":True },
}

CARRIER_GATEWAYS = {
    "att":      "@txt.att.net",
    "verizon":  "@vtext.com",
    "tmobile":  "@tmomail.net",
    "sprint":   "@messaging.sprintpcs.com",
    "boost":    "@smsmyboostmobile.com",
    "cricket":  "@mms.cricketwireless.net",
    "uscellular":"@email.uscc.net",
}

WINDOW_LABELS = {
    "early": "🕐 Early Window (12–5 pm ET)",
    "mid":   "🕓 Mid Window (4–8 pm ET)",
    "late":  "🕖 Late Window (7 pm+ ET)",
}

def in_window(game_date_str, window):
    if not window or not game_date_str:
        return True
    try:
        dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
        hour = (dt.hour - 4) % 24  # EDT = UTC-4 for the full baseball season
        if window == "early": return 12 <= hour < 17
        if window == "mid":   return 16 <= hour < 20
        if window == "late":  return hour >= 19
    except Exception:
        pass
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────────────────────────────────────

def fetch(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fetch_many(urls, workers=15):
    results = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch, u): i for i, u in enumerate(urls)}
        for f in as_completed(futures):
            results[futures[f]] = f.result()
    return results

def proj_pa(spot, ou=8.5):
    return PA_BY_SPOT.get(spot, 4.1) + (ou - 8.5) * 0.10

def american_to_implied(odds):
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def implied_to_american(p):
    p = max(0.01, min(0.99, p))
    if p >= 0.5: return f"-{round((p / (1-p)) * 100)}"
    return f"+{round(((1-p) / p) * 100)}"

def norm(s):
    """Lowercase, strip accents, remove punctuation for fuzzy name matching."""
    s = (s or "").strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().replace(".", "").replace("'", "").replace(",", "").strip()

def norm_reverse(s):
    """'Last, First' → 'First Last' after normalizing."""
    n = norm(s)
    parts = n.split(" ", 1)
    if len(parts) == 2:
        return parts[1] + " " + parts[0]
    return n

def safe_float(x):
    try: return float(x or 0)
    except: return 0.0

def safe_int(x):
    try: return int(x or 0)
    except: return 0

def fo(n):
    if n is None: return "—"
    return f"+{n}" if n > 0 else str(n)


# ──────────────────────────────────────────────────────────────────────────────
# Data fetchers
# ──────────────────────────────────────────────────────────────────────────────

def get_statcast(year):
    if not HAS_PYBASEBALL:
        print("  ⚠  pybaseball not installed — Statcast disabled")
        return {}, {}
    print("  Fetching Statcast (Baseball Savant)…", end=" ", flush=True)
    try:
        import io
        from contextlib import redirect_stdout, redirect_stderr
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            df = statcast_batter_exitvelo_barrels(year, minBBE=50)
        by_id, by_name = {}, {}
        for _, row in df.iterrows():
            pid = safe_int(row.get("player_id"))
            raw = str(row.get("last_name, first_name") or row.get("player_name") or "")
            if "," in raw:
                p = raw.split(",", 1)
                full = p[1].strip() + " " + p[0].strip()
            else:
                full = raw
            rb = safe_float(row.get("barrel_batted_rate") or row.get("brl_percent") or row.get("barrel_percent"))
            rh = safe_float(row.get("hard_hit_percent")   or row.get("ev95percent")  or row.get("hard_hit_pct"))
            entry = {
                "barrel_pct":   rb   / 100 if rb   > 1 else rb,
                "hard_hit_pct": rh   / 100 if rh   > 1 else rh,
                "avg_ev":       safe_float(row.get("avg_hit_speed") or row.get("avg_exit_velocity")),
            }
            if pid:      by_id[pid]      = entry
            if norm(full): by_name[norm(full)] = entry
        print(f"✓  {len(by_id)} players")
        return by_id, by_name
    except Exception as e:
        print(f"✗  ({e})")
        return {}, {}

def get_weather(venue_game_times):
    result = {}
    for venue, game_time in venue_game_times.items():
        vd = VENUES.get(venue)
        if not vd or not vd["out"]: continue
        r = fetch(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={vd['lat']}&longitude={vd['lon']}"
            f"&hourly=temperature_2m,windspeed_10m&timezone=auto&forecast_days=2"
        )
        if not r or "hourly" not in r: continue
        try:
            times = r["hourly"]["time"]
            ts = game_time.replace("Z", "") if game_time else None
            target = datetime.fromisoformat(ts).replace(tzinfo=None) if ts else datetime.now().replace(hour=19)
            ci, md = 0, float("inf")
            for i, t in enumerate(times):
                try:
                    d = abs((datetime.fromisoformat(t) - target).total_seconds())
                    if d < md: md, ci = d, i
                except: pass
            result[venue] = {
                "temp_f":   safe_float(r["hourly"]["temperature_2m"][ci]) * 9/5 + 32,
                "wind_mph": safe_float(r["hourly"]["windspeed_10m"][ci]) * 0.621371,
            }
        except: pass
    return result

def get_odds(api_key, date):
    if not api_key: return {}, {}
    events = fetch(
        f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events"
        f"?apiKey={api_key}&dateFormat=iso"
        f"&commenceTimeFrom={date}T00:00:00Z&commenceTimeTo={date}T23:59:59Z"
    )
    if not events or not isinstance(events, list): return {}, {}

    # Build event map for totals lookup: norm(away + home) -> over line
    game_totals = {}

    # Fetch both batter_home_runs and totals in one batch
    hr_urls = [
        f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{e['id']}/odds"
        f"?apiKey={api_key}&markets=batter_home_runs&oddsFormat=american"
        f"&regions=us"
        for e in events
    ]
    totals_urls = [
        f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{e['id']}/odds"
        f"?apiKey={api_key}&markets=totals&oddsFormat=american"
        f"&bookmakers=draftkings,fanduel,betmgm,caesars"
        for e in events
    ]
    all_urls = hr_urls + totals_urls
    responses = fetch_many(all_urls, workers=6)
    hr_responses     = responses[:len(events)]
    totals_responses = responses[len(events):]

    odds_map = {}
    for res in hr_responses:
        if not res: continue
        for book in res.get("bookmakers", []):
            if book.get("key") == "betrivers":
                continue
            mkt = next((m for m in book.get("markets", []) if m["key"] == "batter_home_runs"), None)
            if not mkt: continue
            for o in mkt.get("outcomes", []):
                if o.get("point", 0.5) != 0.5:
                    continue
                if o.get("name") != "Over":
                    continue
                if o["price"] > MAX_PROP_ODDS:
                    continue
                raw_name = o.get("description") or o.get("name", "")
                keys = {norm(raw_name), norm_reverse(raw_name)}
                for key in keys:
                    if not key: continue
                    if key not in odds_map: odds_map[key] = {"books": [], "_raw": raw_name}
                    odds_map[key]["books"].append({"book": book["title"], "odds": o["price"]})
    for key in odds_map:
        best = max(odds_map[key]["books"], key=lambda x: x["odds"])
        odds_map[key]["best"]      = best["odds"]
        odds_map[key]["best_book"] = best["book"]

    # Parse totals
    for ev, res in zip(events, totals_responses):
        if not res: continue
        home_team = ev.get("home_team", "")
        away_team = ev.get("away_team", "")
        pair_key  = norm(away_team)  # use away team as primary key
        for book in res.get("bookmakers", []):
            mkt = next((m for m in book.get("markets", []) if m["key"] == "totals"), None)
            if not mkt: continue
            for o in mkt.get("outcomes", []):
                if (o.get("name") or "").lower() == "over":
                    pt = o.get("point")
                    if pt is not None and pair_key not in game_totals:
                        game_totals[pair_key] = float(pt)
                    break
            if pair_key in game_totals:
                break

    return odds_map, game_totals


# ──────────────────────────────────────────────────────────────────────────────
# Model
# ──────────────────────────────────────────────────────────────────────────────

def regressed_hr_pa(hr, ip, min_ip=10, max_weight=0.70, full_ip=150):
    if ip < min_ip:
        return LG_HR_PA
    pa_faced = ip * 4.35
    raw = hr / pa_faced
    weight = min(ip / full_ip, max_weight)
    return raw * weight + LG_HR_PA * (1 - weight)


def run_model(batter, season, splits, hot, sp_stat, sp_splits, bp_splits,
              team_stat, weather, sc_by_id, sc_by_name, odds_map, ou=8.5):
    if not season: return None
    pa = safe_int(season.get("plateAppearances"))
    hr = safe_int(season.get("homeRuns"))
    if pa < 30: return None
    sr = hr / pa

    ph = batter["pitcher_hand"]

    # 1. Handedness split (regressed)
    split_adj = 1.0
    rel = splits.get("L" if ph == "L" else "R")
    if rel:
        s_pa = safe_int(rel.get("plateAppearances"))
        s_hr = safe_int(rel.get("homeRuns"))
        if s_pa >= 20 and sr > 0:
            w = min(s_pa / 130, 0.55)
            split_adj = max(0.5, min(2.5, ((s_hr/s_pa)*w + sr*(1-w)) / sr))

    # 2. Hotness — last 14 days (regressed)
    hot_adj = 1.0; r_hr = r_pa = 0
    if hot and sr > 0:
        r_pa = safe_int(hot.get("plateAppearances"))
        r_hr = safe_int(hot.get("homeRuns"))
        if r_pa >= 5:
            w = min(r_pa / 45, 0.45)
            hot_adj = max(0.65, min(1.5, ((r_hr/r_pa)*w + sr*(1-w)) / sr))

    # 3. Statcast (barrel% + hard-hit%)
    sc_adj  = 1.0
    sc_info = sc_by_id.get(batter["id"]) or sc_by_name.get(norm(batter["name"]))
    if sc_info:
        b = sc_info["barrel_pct"]; hh = sc_info["hard_hit_pct"]
        if b > 0:
            sc_adj = max(0.70, min(1.50,
                (b / LG_BARREL) ** 0.40 * ((hh / LG_HARD_HIT) ** 0.20 if hh > 0 else 1.0)
            ))

    bh = batter.get("batter_hand", "R")
    sp_sitcode = "vl" if bh == "L" else "vr"  # SP faces batter: vl=vs lefties, vr=vs righties

    # 4. Starting pitcher (regressed, platoon-aware)
    sp_split = (sp_splits or {}).get(sp_sitcode)
    if sp_split:
        s_hr_sp = safe_int(sp_split.get("homeRuns"))
        s_ip_sp = safe_float(sp_split.get("inningsPitched"))
        sp_rate = regressed_hr_pa(s_hr_sp, s_ip_sp, min_ip=5)
    elif sp_stat:
        sp_rate = regressed_hr_pa(safe_int(sp_stat.get("homeRuns")), safe_float(sp_stat.get("inningsPitched")), min_ip=5)
    else:
        sp_rate = LG_HR_PA
    sp_adj = max(0.4, min(3.0, sp_rate / LG_HR_PA))

    # 5. Bullpen (regressed, platoon-aware)
    bp_rate = (bp_splits or {}).get(bh, LG_HR_PA)
    bp_adj = max(0.5, min(2.5, bp_rate / LG_HR_PA))

    pitch_blend = 0.55 * sp_adj + 0.45 * bp_adj

    # 6. Park factor
    park_adj = VENUES.get(batter["venue"], {}).get("pf", 1.0)

    # 7. Weather
    temp_adj = wind_adj = 1.0
    if weather:
        temp_adj = max(0.92, min(1.10, 1 + (weather["temp_f"]   - 72) * 0.0015))
        wind_adj = max(0.92, min(1.12, 1 + max(0, weather["wind_mph"] - 5) * 0.005))

    pp     = proj_pa(batter["batting_order"], ou)
    per_pa = max(0.001, min(0.08, sr * split_adj * hot_adj * sc_adj * pitch_blend * park_adj * temp_adj * wind_adj))
    gp     = 1 - (1 - per_pa) ** pp

    name_keys = [norm(batter["name"]), norm_reverse(batter["name"])]
    od = {}
    for key in name_keys:
        od = odds_map.get(key, {})
        if od: break

    best_odds    = od.get("best")
    best_book    = od.get("best_book")
    implied      = american_to_implied(best_odds) if best_odds is not None else None
    fair_implied = (implied / VIG_FACTOR) if implied is not None else None
    edge         = (gp - fair_implied) if fair_implied is not None else None

    # Kelly fraction
    kelly = None
    quarter_kelly = None
    if best_odds is not None and edge is not None and edge > 0:
        b = (best_odds / 100) if best_odds > 0 else (100 / abs(best_odds))
        q = 1 - gp
        raw_kelly = (gp * b - q) / b
        kelly = max(0, min(raw_kelly, 0.12))
        quarter_kelly = min(kelly * 0.25, 0.03)

    rec = "Bet" if (edge or -1) > 0.05 else "Lean" if (edge or -1) > 0.02 else "Skip" if (edge or -1) < -0.04 else "—"

    hot_label = ""
    if r_pa >= 8:
        if   hot_adj >= 1.20: hot_label = "🔥"
        elif hot_adj <= 0.78: hot_label = "🧊"
        elif hot_adj >= 1.08: hot_label = "↗"
        elif hot_adj <= 0.90: hot_label = "↘"

    return {
        **batter,
        "pa": pa, "hr": hr, "season_rate": sr,
        "split_adj": split_adj, "hot_adj": hot_adj, "r_hr": r_hr, "r_pa": r_pa, "hot_label": hot_label,
        "sc_adj": sc_adj, "sc_info": sc_info,
        "sp_adj": sp_adj, "bp_adj": bp_adj, "pitch_blend": pitch_blend,
        "park_adj": park_adj, "temp_adj": temp_adj, "wind_adj": wind_adj,
        "proj_pa": round(pp, 1), "game_prob": gp, "fair_line": implied_to_american(gp),
        "best_odds": best_odds, "best_book": best_book,
        "implied": implied, "fair_implied": fair_implied, "edge": edge,
        "kelly": kelly, "quarter_kelly": quarter_kelly,
        "recommendation": rec,
        "all_books": od.get("books", []), "weather": weather,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Picks tracking
# ──────────────────────────────────────────────────────────────────────────────

def save_picks(results, date, window):
    path = "results/picks.json"
    os.makedirs("results", exist_ok=True)
    try:
        with open(path) as f:
            picks = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        picks = []

    existing_keys = {(p["date"], p["player_id"], p.get("window")) for p in picks}

    for r in results:
        key = (date, r["id"], window)
        if key in existing_keys:
            continue
        e = r.get("edge")
        rec = r.get("recommendation", "—")
        qk = r.get("quarter_kelly")
        has_line = r.get("best_odds") is not None
        pick = {
            "date": date,
            "window": window,
            "player": r["name"],
            "player_id": r["id"],
            "team": r["team"],
            "batting_order": r["batting_order"],
            "lineup_confirmed": r.get("lineup_confirmed", True),
            "model_prob": round(r["game_prob"], 4),
            "fair_line": r["fair_line"],
            "best_odds": r.get("best_odds"),
            "best_book": r.get("best_book"),
            "edge": round(e, 4) if e is not None else None,
            "recommendation": rec,
            "kelly_fraction": round(r["kelly"], 4) if r.get("kelly") is not None else None,
            "quarter_kelly": round(qk, 4) if qk is not None else None,
            "units_staked": round(qk, 4) if (qk is not None and rec in ("Bet", "Lean") and has_line) else None,
            "result": None,
            "units_returned": None,
            "resolved_at": None,
        }
        picks.append(pick)

    with open(path, "w") as f:
        json.dump(picks, f, indent=2)


def compute_stats(picks):
    resolved   = [p for p in picks if p.get("result") is not None]
    lined      = [p for p in resolved if p.get("units_staked") is not None]
    bet_picks  = [p for p in lined if p.get("recommendation") == "Bet"]
    lean_picks = [p for p in lined if p.get("recommendation") == "Lean"]

    def wl(lst):
        w = sum(1 for p in lst if p["result"])
        return w, len(lst) - w

    bet_w,  bet_l  = wl(bet_picks)
    lean_w, lean_l = wl(lean_picks)
    units_net    = sum(p["units_returned"] for p in lined if p.get("units_returned") is not None)
    total_staked = sum(p["units_staked"]   for p in lined if p.get("units_staked")   is not None)
    roi = (units_net / total_staked * 100) if total_staked > 0 else 0

    # streak on Bet+Lean lined picks sorted by date
    all_lined = sorted(lined, key=lambda p: (p["date"], p.get("window", "z")))
    streak = 0
    if all_lined:
        last = all_lined[-1]["result"]
        for p in reversed(all_lined):
            if p["result"] == last:
                streak += 1
            else:
                break
        streak = streak if last else -streak

    # calibration buckets
    buckets = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 99)]
    cal = {}
    for lo, hi in buckets:
        bucket_picks = [p for p in resolved if lo <= p["model_prob"] * 100 < hi]
        if bucket_picks:
            cal[f"{lo}-{hi}%"] = {
                "predicted_avg": round(sum(p["model_prob"] for p in bucket_picks) / len(bucket_picks) * 100, 1),
                "actual_rate":   round(sum(1 for p in bucket_picks if p["result"]) / len(bucket_picks) * 100, 1),
                "n": len(bucket_picks),
            }

    return {
        "total_tracked":    len(resolved),
        "total_lined":      len(lined),
        "hit_rate_overall": round(sum(1 for p in resolved if p["result"]) / len(resolved), 3) if resolved else None,
        "bet_w":   bet_w,  "bet_l":  bet_l,
        "lean_w":  lean_w, "lean_l": lean_l,
        "units_net":   round(units_net, 2),
        "roi_pct":     round(roi, 1),
        "streak":      streak,
        "calibration": cal,
    }


# ──────────────────────────────────────────────────────────────────────────────
# HTML report
# ──────────────────────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0f1117;color:#e2e8f0;padding:24px;}
h1{font-size:18px;font-weight:600;margin-bottom:4px;}
.sub{font-size:12px;color:#64748b;margin-bottom:20px;}
.g5{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:16px;}
.metric{background:#1e293b;border-radius:8px;padding:12px 14px;}
.ml{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;}
.mv{font-size:20px;font-weight:600;color:#e2e8f0;} .mv.g{color:#22c55e;}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px;font-size:11px;color:#64748b;}
.tw{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{padding:6px 8px;text-align:left;color:#64748b;font-weight:500;font-size:10.5px;
   text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #1e293b;white-space:nowrap;}
td{padding:6px 8px;border-bottom:1px solid #1a2234;vertical-align:top;}
tr:hover td{background:#1e293b;}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600;}
.bet{background:#166534;color:#86efac;} .lean{background:#1c3a2a;color:#4ade80;} .skip{background:#3b0f0f;color:#f87171;}
.factors{font-size:10px;color:#475569;line-height:1.7;margin-top:3px;}
.note{font-size:12px;color:#64748b;margin-top:20px;padding:14px;background:#1e293b;border-radius:8px;line-height:1.8;}
section+section{border-top:2px solid #1e293b;margin-top:40px;padding-top:30px;}
.wh{font-size:15px;font-weight:600;color:#94a3b8;margin-bottom:14px;}
.perf-panel{background:#1e293b;border-radius:8px;padding:14px 18px;margin-bottom:16px;}
.perf-panel h3{font-size:13px;color:#94a3b8;margin-bottom:10px;font-weight:600;}
.perf-row{display:flex;gap:24px;flex-wrap:wrap;font-size:12px;margin-bottom:8px;}
.perf-item{display:flex;flex-direction:column;gap:2px;}
.perf-label{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;}
.perf-value{font-size:14px;font-weight:600;color:#e2e8f0;}
.perf-value.pos{color:#22c55e;} .perf-value.neg{color:#f87171;}
.cal-table{font-size:11px;margin-top:8px;border-collapse:collapse;}
.cal-table th,.cal-table td{padding:3px 8px;text-align:right;border:1px solid #334155;}
.cal-table th{color:#64748b;font-weight:500;font-size:10px;}
.top5{background:#1e293b;border-radius:8px;padding:14px 18px;margin-bottom:16px;}
.top5 h3{font-size:13px;color:#94a3b8;margin-bottom:10px;font-weight:600;letter-spacing:.02em;}
.top5-row{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #1a2234;}
.top5-row:last-child{border-bottom:none;}
.top5-rank{font-size:11px;color:#475569;width:16px;flex-shrink:0;text-align:right;}
.top5-name{font-size:13px;font-weight:600;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.top5-prob{font-size:11px;color:#94a3b8;width:44px;text-align:right;flex-shrink:0;}
.top5-odds{font-size:12px;font-weight:600;width:50px;text-align:right;flex-shrink:0;}
.top5-edge{font-size:13px;font-weight:700;width:56px;text-align:right;flex-shrink:0;}
.top5-badge{width:44px;text-align:right;flex-shrink:0;}
"""

def cfactor(adj, label, thresh=0.04):
    d = adj - 1
    if abs(d) < thresh: return None
    color = "#22c55e" if d > 0 else "#f87171"
    return f'<span style="color:{color}">{"↑" if d>0 else "↓"}{label} {d*100:+.0f}%</span>'

def _build_section(results, date, has_odds, has_statcast, weather_count, has_key,
                   window=None, stats=None, bankroll=0, reset_date=""):
    total      = len(results)
    with_lines = sum(1 for r in results if r["best_odds"] is not None)
    value_bets = sum(1 for r in results if (r.get("edge") or 0) > 0.02)
    avg_prob   = sum(r["game_prob"] for r in results) / total if total else 0

    # Performance panel
    perf_html = ""
    if stats is not None and stats.get("total_lined", 0) == 0 and reset_date:
        perf_html = f'<div class="perf-panel"><h3>Season Performance</h3><p style="color:#64748b;font-size:12px;margin:0">Stats reset {reset_date} — no results tracked yet for this season.</p></div>'
    if stats is not None and stats.get("total_lined", 0) > 0:
        s = stats
        bet_rec  = f'{s["bet_w"]}-{s["bet_l"]}'
        lean_rec = f'{s["lean_w"]}-{s["lean_l"]}'
        net_cls  = "pos" if s["units_net"] >= 0 else "neg"
        roi_cls  = "pos" if s["roi_pct"]  >= 0 else "neg"
        streak_val = s["streak"]
        streak_str = f'+{streak_val} streak' if streak_val > 0 else f'{streak_val} streak'
        streak_cls = "pos" if streak_val > 0 else "neg" if streak_val < 0 else ""
        cal_html = ""
        cal = s.get("calibration", {})
        has_cal = any(v["n"] >= 10 for v in cal.values())
        if has_cal:
            cal_rows = ""
            for bucket, bv in cal.items():
                if bv["n"] >= 10:
                    cal_rows += f'<tr><td>{bucket}</td><td>{bv["predicted_avg"]}%</td><td>{bv["actual_rate"]}%</td><td>{bv["n"]}</td></tr>'
            cal_html = f'''<table class="cal-table">
              <thead><tr><th>Prob bucket</th><th>Pred avg</th><th>Actual</th><th>n</th></tr></thead>
              <tbody>{cal_rows}</tbody>
            </table>'''
        perf_html = f'''<div class="perf-panel">
  <h3>Season Performance</h3>
  <div class="perf-row">
    <div class="perf-item"><span class="perf-label">Bet record</span><span class="perf-value">{bet_rec}</span></div>
    <div class="perf-item"><span class="perf-label">Lean record</span><span class="perf-value">{lean_rec}</span></div>
    <div class="perf-item"><span class="perf-label">Net units</span><span class="perf-value {net_cls}">{s["units_net"]:+.2f}u</span></div>
    <div class="perf-item"><span class="perf-label">ROI</span><span class="perf-value {roi_cls}">{s["roi_pct"]:+.1f}%</span></div>
    <div class="perf-item"><span class="perf-label">Streak</span><span class="perf-value {streak_cls}">{streak_str}</span></div>
    <div class="perf-item"><span class="perf-label">Tracked</span><span class="perf-value">{s["total_tracked"]}</span></div>
  </div>
  {cal_html}
</div>'''

    rows = []
    for r in results:
        e  = r.get("edge"); gp = r["game_prob"]
        rbg = "background:rgba(34,197,94,.05);" if (e or 0) > 0.05 else ""
        ec = "#64748b" if e is None else "#22c55e" if e>.05 else "#86efac" if e>.02 else "#94a3b8" if e>-.02 else "#f87171"
        pc = "#22c55e" if gp>.11 else "#f59e0b" if gp>.07 else "#e2e8f0"
        rec = r.get("recommendation", "—")
        if rec == "Bet":
            badge = '<span class="badge bet">Bet</span>'
        elif rec == "Lean":
            badge = '<span class="badge lean">Lean</span>'
        elif rec == "Skip":
            badge = '<span class="badge skip">Skip</span>'
        else:
            badge = "—"

        # Lineup confirmation flag
        lineup_flag = ""
        if not r.get("lineup_confirmed", True):
            lineup_flag = ' <span style="font-size:10px;color:#64748b;background:#1e293b;padding:1px 5px;border-radius:3px">proj</span>'

        # Result indicator
        result_flag = ""
        if r.get("result") is True:
            result_flag = " ✅"
        elif r.get("result") is False:
            result_flag = " ❌"

        parts = [
            cfactor(r["split_adj"],  f'vs {r["pitcher_hand"]}HP'),
            cfactor(r["hot_adj"],    f'L14 ({r["r_hr"]}HR/{r["r_pa"]}PA)') if r["r_pa"]>=8 else None,
            cfactor(r["sc_adj"],     f'Statcast (brl {r["sc_info"]["barrel_pct"]*100:.1f}%)') if (has_statcast and r.get("sc_info")) else None,
            cfactor(r["sp_adj"],     "SP"),
            cfactor(r["bp_adj"],     "BP"),
            cfactor(r["park_adj"],   "park"),
            cfactor(r["temp_adj"],   f'{r["weather"]["temp_f"]:.0f}°F', thresh=0.01) if r.get("weather") else None,
            cfactor(r["wind_adj"],   f'{r["weather"]["wind_mph"]:.0f}mph wind', thresh=0.01) if r.get("weather") else None,
        ]
        parts = [p for p in parts if p]

        pk = (r.get("venue","")).replace(" Stadium","").replace(" Ball Park","").replace(" Park","").replace(" Field","").replace(" Centre","").replace(" Coliseum","")
        pitcher_disp = f'{r["pitcher_name"].split()[-1]} ({r.get("pitcher_hand","?")})' if r.get("pitcher_name") else "TBD"

        bo = r.get("best_odds")
        if bo is not None:
            implied_pct = r.get("implied")
            sub = f'<div style="font-size:10px;color:#64748b">implied: {implied_pct*100:.1f}%</div>' if implied_pct else ""
            bo_str = f'<strong>{fo(bo)}</strong>{sub}'
        else:
            bo_str = '<span style="color:#475569">—</span>'
        book = r.get("best_book") or ""
        if book:
            bk_bg = "#16a34a" if any(x in book.lower() for x in ("draftkings", "fanduel")) else "#475569"
            book_html = f'<span style="font-size:10px;background:{bk_bg};color:#fff;padding:1px 6px;border-radius:3px;white-space:nowrap">{book}</span>'
        else:
            book_html = '<span style="color:#475569">—</span>'
        edge_str = f"{e*100:+.1f}%" if e is not None else "—"
        # Stake display
        stake_str = ""
        qk = r.get("quarter_kelly")
        if bankroll > 0 and qk is not None:
            stake_str = f'<div style="font-size:10px;color:#64748b">${qk*bankroll:.2f}</div>'
        odds_cols = (
            f'<td style="text-align:right">{bo_str}{stake_str}</td>'
            f'<td>{book_html}</td>'
            f'<td style="text-align:right;font-weight:700;color:{ec}">{edge_str}</td>'
            f'<td>{badge}</td>'
        )

        sc_col = ""
        if has_statcast:
            if r.get("sc_info"):
                sc = r["sc_info"]
                sc_col = f'<td style="text-align:right">{sc["barrel_pct"]*100:.1f}%<div style="font-size:10px;color:#64748b">{sc["hard_hit_pct"]*100:.0f}% HH</div></td>'
            else:
                sc_col = '<td style="color:#334155;text-align:right">—</td>'

        rows.append(f"""
        <tr style="{rbg}">
          <td style="min-width:155px;max-width:220px;">
            <span style="font-weight:600">{r["name"]}{result_flag}</span>{lineup_flag}{" "+r["hot_label"] if r["hot_label"] else ""}
            {f'<div class="factors">{"&nbsp;·&nbsp;".join(parts)}</div>' if parts else ""}
          </td>
          <td style="color:#94a3b8;white-space:nowrap;font-size:11px">{pitcher_disp}</td>
          <td style="font-size:11px;color:#64748b;white-space:nowrap">{pk}</td>
          <td style="text-align:center">{r["batting_order"]}</td>
          <td style="text-align:center;color:#94a3b8">{r["proj_pa"]}</td>
          <td style="text-align:right">{r["hr"]}/{r["pa"]}<div style="color:#64748b;font-size:10px">{r["season_rate"]*100:.1f}%/PA</div></td>
          {sc_col}
          <td style="text-align:right;font-weight:700;font-size:13px;color:{pc}">{gp*100:.1f}%</td>
          <td style="text-align:right;color:#64748b">{r["fair_line"]}</td>
          {odds_cols}
        </tr>""")

    sc_th    = '<th style="text-align:right">Barrel%</th>' if has_statcast else ""
    odds_ths = '<th style="text-align:right">Best line</th><th>Book</th><th style="text-align:right">Edge</th><th>Rec</th>'
    all_books = list({b["book"] for r in results for b in r.get("all_books", [])})
    odds_note = f"Lines from: {', '.join(all_books[:6])}. Edge = model − implied. Bet ≥+5pp · Lean +2–5pp · Skip ≤−4pp." if has_key else "Run with -k YOUR_ODDS_KEY for live line comparison."
    sc_note   = f"Statcast: barrel% + hard-hit% (barrel ratio vs {LG_BARREL*100:.1f}% league avg, exp 0.40)." if has_statcast else "Statcast disabled — install pybaseball."
    wh = f'<div class="wh">{WINDOW_LABELS[window]}</div>' if window else ""

    # Top-5 by edge panel (only when odds are available)
    top5_html = ""
    if has_odds:
        lined = [r for r in results if r.get("edge") is not None]
        top5  = sorted(lined, key=lambda r: r["edge"], reverse=True)[:5]
        if top5:
            t5rows = ""
            for rank, r in enumerate(top5, 1):
                e   = r["edge"]
                ec  = "#22c55e" if e > .05 else "#86efac" if e > .02 else "#94a3b8" if e > -.02 else "#f87171"
                rec = r.get("recommendation", "—")
                if rec == "Bet":
                    tbadge = '<span class="badge bet" style="font-size:10px;padding:1px 5px">Bet</span>'
                elif rec == "Lean":
                    tbadge = '<span class="badge lean" style="font-size:10px;padding:1px 5px">Lean</span>'
                elif rec == "Skip":
                    tbadge = '<span class="badge skip" style="font-size:10px;padding:1px 5px">Skip</span>'
                else:
                    tbadge = '<span style="color:#475569;font-size:10px">—</span>'
                t5rows += (
                    f'<div class="top5-row">'
                    f'<span class="top5-rank">{rank}</span>'
                    f'<span class="top5-name">{r["name"]}{" "+r["hot_label"] if r.get("hot_label") else ""}</span>'
                    f'<span class="top5-prob">{r["game_prob"]*100:.1f}%</span>'
                    f'<span class="top5-odds">{fo(r["best_odds"])}</span>'
                    f'<span class="top5-edge" style="color:{ec}">{e*100:+.1f}%</span>'
                    f'<span class="top5-badge">{tbadge}</span>'
                    f'</div>'
                )
            top5_html = f'<div class="top5"><h3>Top 5 by Edge</h3>{t5rows}</div>'

    odds_match_color = "#22c55e" if (total > 0 and with_lines / total >= 0.5) else "#f59e0b" if with_lines > 0 else "#f87171"
    return f"""<section>
{wh}{perf_html}<div class="g5">
  <div class="metric"><div class="ml">Players</div><div class="mv">{total}</div></div>
  <div class="metric"><div class="ml">Odds matched</div><div class="mv" style="color:{odds_match_color}">{with_lines}/{total}</div></div>
  <div class="metric"><div class="ml">Value bets</div><div class="mv g">{value_bets}</div></div>
  <div class="metric"><div class="ml">Avg prob</div><div class="mv">{avg_prob*100:.1f}%</div></div>
  <div class="metric"><div class="ml">Weather</div><div class="mv">{weather_count}</div></div>
</div>
{top5_html}<div class="legend">
  <span>🔥 Hot ≥+20%</span><span>↗ Warm +8–19%</span>
  <span>↘ Cool −10–22%</span><span>🧊 Cold ≤−22%</span>
  <span style="margin-left:8px">↑ raises prob &nbsp; ↓ lowers prob</span>
  <span>⚠ proj = lineup not yet confirmed</span>
</div>
<div class="tw"><table>
  <thead><tr>
    <th>Player &amp; factors</th><th>Opp pitcher</th><th>Park</th>
    <th>#</th><th>PA</th><th style="text-align:right">Season</th>
    {sc_th}<th style="text-align:right">Model %</th>
    <th style="text-align:right">Fair line</th>{odds_ths}
  </tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table></div>
<div class="note">
  <strong style="color:#94a3b8">v4 model:</strong>
  season HR/PA · splits (regressed) · hotness L14 (regressed) · {sc_note} ·
  SP HR rate (regressed, platoon-aware) · bullpen HR rate (regressed, platoon-aware) · park factor ({len(VENUES)} venues) · weather.<br><br>
  <strong style="color:#94a3b8">Lines:</strong> {odds_note}
</div>
</section>"""


def build_report(results, date, has_odds, has_statcast, weather_count, has_key,
                 window=None, stats=None, bankroll=0, reset_date=""):
    section = _build_section(results, date, has_odds, has_statcast, weather_count, has_key,
                             window=window, stats=stats, bankroll=bankroll, reset_date=reset_date)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>MLB HR Props — {date}</title>
<style>{CSS}</style></head><body>
<h1>⚾ MLB HR Prop Finder — {date}</h1>
<p class="sub">v4 · hotness · bullpen · weather · Statcast &nbsp;|&nbsp; Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
{section}
</body></html>"""


def append_to_combined(html_path, results, date, has_odds, has_statcast, weather_count, has_key,
                       window=None, stats=None, bankroll=0, reset_date=""):
    section = _build_section(results, date, has_odds, has_statcast, weather_count, has_key,
                             window=window, stats=stats, bankroll=bankroll, reset_date=reset_date)
    if not os.path.exists(html_path):
        content = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>MLB HR Props — {date}</title>
<style>{CSS}</style></head><body>
<h1>⚾ MLB HR Prop Finder — {date}</h1>
<p class="sub">v4 · hotness · bullpen · weather · Statcast &nbsp;|&nbsp; Combined daily report</p>
{section}
</body></html>"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(html_path, "r", encoding="utf-8") as f:
            existing = f.read()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(existing.replace("</body></html>", f"{section}\n</body></html>"))


# ──────────────────────────────────────────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────────────────────────────────────────

def send_notifications(results, date, html_content, args):
    """Send HTML report by email and a short summary by SMS."""

    value_bets = [r for r in results if (r.get("edge") or 0) > 0.02]
    print(f"  [notify] send_notifications called: {len(results)} results, {len(value_bets)} value bets")

    gmail_addr = os.environ.get("GMAIL_ADDRESS", "")    or args.gmail_from
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD","") or args.gmail_pass
    to_email   = os.environ.get("REPORT_EMAIL", "")     or args.email_to
    to_phone   = os.environ.get("REPORT_PHONE", "")     or args.sms_to
    carrier    = os.environ.get("CARRIER", "").lower()  or (args.carrier or "").lower()
    pages_url  = os.environ.get("PAGES_URL", "")        or args.pages_url

    gmail_addr = gmail_addr.strip()
    gmail_pass = gmail_pass.strip()
    to_email   = to_email.strip()
    to_phone   = to_phone.strip()
    carrier    = carrier.strip()

    print(f"  [notify] gmail_addr={bool(gmail_addr)}, gmail_pass={bool(gmail_pass)}, to_email={repr(to_email)}, to_phone={repr(to_phone)}")

    if not value_bets:
        print("  [notify] Exiting early — no value bets")
        return
    if not gmail_addr or not gmail_pass:
        print("  [notify] Exiting early — missing Gmail credentials")
        return

    # Load season stats for notifications
    season_stats = None
    try:
        with open("results/picks.json") as f:
            all_picks = json.load(f)
        season_stats = compute_stats(all_picks)
    except (FileNotFoundError, json.JSONDecodeError):
        all_picks = []

    window_tag = f" [{args.window.title()}]" if getattr(args, "window", None) else ""
    subject    = f"⚾ MLB HR Props {date}{window_tag} — {len(value_bets)} value bet{'s' if len(value_bets)!=1 else ''}"

    # ── Full HTML email ───────────────────────────────────────────
    if to_email and not getattr(args, "sms_only", False):
        try:
            recipients = [addr.strip() for addr in to_email.split(",") if addr.strip()]
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"MLB HR Model Value <{gmail_addr}>"
            msg["To"]      = ", ".join(recipients)

            # Build plain text with performance prefix
            plain_lines = [f"MLB HR Props — {date}{window_tag}", ""]
            if season_stats and season_stats.get("total_lined", 0) > 0:
                s = season_stats
                plain_lines.append("=== Season Performance ===")
                plain_lines.append(f"Bet: {s['bet_w']}-{s['bet_l']}  Lean: {s['lean_w']}-{s['lean_l']}")
                plain_lines.append(f"Net units: {s['units_net']:+.2f}  ROI: {s['roi_pct']:+.1f}%")
                plain_lines.append("")
                # Yesterday's resolved picks
                yesterday = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                yest_picks = [p for p in all_picks if p.get("date") == yesterday and p.get("result") is not None and p.get("units_staked") is not None]
                if yest_picks:
                    plain_lines.append("=== Yesterday's Results ===")
                    for p in yest_picks:
                        icon = "✅" if p["result"] else "❌"
                        ur = p.get("units_returned")
                        ur_str = f"{ur:+.2f}u" if ur is not None else ""
                        plain_lines.append(f"{icon} {p['player']} ({p['recommendation']}) {ur_str}")
                    plain_lines.append("")

            plain_lines.append(f"{len(value_bets)} value bets:")
            plain_lines.append("")
            for r in value_bets:
                plain_lines.append(f"• {r['name']} {fo(r['best_odds'])} ({r.get('best_book','')}) edge {(r.get('edge') or 0)*100:+.1f}%")
            if pages_url:
                plain_lines.append(f"\nFull report: {pages_url}")
            plain = "\n".join(plain_lines)

            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls()
                s.login(gmail_addr, gmail_pass)
                s.sendmail(gmail_addr, recipients, msg.as_string())
            print(f"  ✓  Email → {to_email}")
        except Exception as e:
            print(f"  ✗  Email failed: {e}")

    # ── SMS via carrier email-to-text gateway (free) ──────────────
    if to_phone and carrier and carrier in CARRIER_GATEWAYS:
        try:
            digits   = "".join(c for c in to_phone.strip() if c.isdigit())
            sms_addr = digits + CARRIER_GATEWAYS[carrier]

            value_bets_sorted = sorted(value_bets, key=lambda r: r.get("edge") or 0, reverse=True)
            top10 = value_bets_sorted[:10]

            lines = [f"⚾ HR Props {date} — {len(value_bets)} value bets"]
            lines.append("─────────────────")
            for r in top10:
                e    = (r.get("edge") or 0) * 100
                prob = r["game_prob"] * 100
                book = (r.get("best_book") or "")[:6]
                lines.append(f"{r['name'].split()[-1]}: {fo(r['best_odds'])} {book}")
                lines.append(f"  {prob:.1f}% prob | edge {e:+.1f}%")
            if pages_url:
                lines.append("─────────────────")
                lines.append(pages_url)

            sms_body = "\n".join(lines).encode("ascii", errors="replace").decode("ascii")
            sms = MIMEText(sms_body)
            sms["Subject"] = ""
            sms["From"]    = gmail_addr
            sms["To"]      = sms_addr
            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls()
                s.login(gmail_addr, gmail_pass)
                s.sendmail(gmail_addr, [sms_addr], sms.as_string())
            print(f"  ✓  SMS  → {to_phone} ({carrier})")
        except Exception as e:
            print(f"  ✗  SMS failed: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Debug
# ──────────────────────────────────────────────────────────────────────────────

def print_debug_summary(results, odds_map, has_key):
    print("\n" + "="*70)
    print("  DEBUG SUMMARY")
    print("="*70)
    if not has_key:
        print("  ⚠  No ODDS_API_KEY — edge cannot be calculated for anyone.")
    else:
        matched   = sum(1 for r in results if r["best_odds"] is not None)
        unmatched = [r["name"] for r in results if r["best_odds"] is None]
        print(f"  Odds matched: {matched}/{len(results)} players")
        if unmatched:
            print("  Unmatched players:")
            for n in unmatched[:15]:
                print(f"    · {n}  →  norm='{norm(n)}'")
            print(f"  Odds map sample keys: {list(odds_map.keys())[:10]}")

    hot_active           = sum(1 for r in results if r["r_pa"] >= 5)
    split_adj_nontrivial = sum(1 for r in results if abs(r["split_adj"] - 1.0) > 0.05)
    sc_active            = sum(1 for r in results if r.get("sc_info"))
    print(f"  Hot factor active (≥5 PA in L14): {hot_active}/{len(results)}")
    print(f"  Split adj non-trivial (>5%):       {split_adj_nontrivial}/{len(results)}")
    print(f"  Statcast data found:               {sc_active}/{len(results)}")
    print(f"\n  Top-10 by model probability:")
    print(f"  {'Player':<26} {'Prob':>6}  {'Fair%':>6}  {'Edge':>7}  Adjustments")
    print("  " + "-"*72)
    for r in sorted(results, key=lambda x: x["game_prob"], reverse=True)[:10]:
        e_str  = f"{r['edge']*100:+.1f}%" if r["edge"] is not None else "no line"
        fi_str = f"{r.get('fair_implied',0)*100:.1f}%" if r.get("fair_implied") else "—"
        adjs   = (f"split×{r['split_adj']:.2f} hot×{r['hot_adj']:.2f} "
                  f"sc×{r['sc_adj']:.2f} pitch×{r['pitch_blend']:.2f} park×{r['park_adj']:.2f}")
        print(f"  {r['name'][:25]:<26} {r['game_prob']*100:.1f}%  {fi_str:>6}  {e_str:>7}  {adjs}")
    print("="*70 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="MLB HR Prop Finder v4")
    p.add_argument("-d","--date",      default=datetime.today().strftime("%Y-%m-%d"))
    p.add_argument("-k","--key",       default=os.environ.get("ODDS_API_KEY",""))
    p.add_argument("--min-edge",       type=float, default=0.0)
    p.add_argument("--open",           action="store_true", help="Open report in browser")
    p.add_argument("--email-to",       default="", help="Recipient email address")
    p.add_argument("--sms-to",         default="", help="10-digit phone number")
    p.add_argument("--carrier",        default="", help="att|verizon|tmobile|sprint|boost|cricket")
    p.add_argument("--gmail-from",     default="", help="Gmail sender address (or set GMAIL_ADDRESS)")
    p.add_argument("--gmail-pass",     default="", help="Gmail App Password (or set GMAIL_APP_PASSWORD)")
    p.add_argument("--window",         choices=["early","mid","late"], default=None, help="Game time window: early(12-5pm ET) mid(4-8pm ET) late(7pm+ ET)")
    p.add_argument("--pages-url",      default="", help="GitHub Pages URL for SMS link")
    p.add_argument("--bankroll",       type=float, default=float(os.environ.get("BANKROLL") or "0"))
    p.add_argument("--debug",          action="store_true", help="Print diagnostic info to diagnose zero-bet issues")
    p.add_argument("--sms-only",       action="store_true", help="Skip email, send SMS only")
    args = p.parse_args()

    for env_var in ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "REPORT_EMAIL", "REPORT_PHONE", "CARRIER"]:
        val = os.environ.get(env_var, "")
        if val:
            os.environ[env_var] = val.strip()

    date = args.date
    yr   = date.split("-")[0]
    d14  = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")

    print(f"\n⚾  MLB HR Prop Finder v4  —  {date}")
    print("─" * 50)

    # Schedule
    print("→ Fetching schedule…", end=" ", flush=True)
    sched = fetch(f"{MLB_API}/schedule?sportId=1&date={date}&hydrate=probablePitcher,team,venue")
    games = (sched or {}).get("dates", [{}])[0].get("games", [])
    if not games:
        print("✗  No games today — exiting cleanly")
        sys.exit(0)
    if args.window:
        games = [g for g in games if in_window(g.get("gameDate",""), args.window)]
        if not games:
            print(f"✗  No games in '{args.window}' window — exiting cleanly")
            sys.exit(0)
    print(f"✓  {len(games)} games")

    # Lineups
    print("→ Fetching lineups…", end=" ", flush=True)
    boxes = fetch_many([f"{MLB_API}/game/{g['gamePk']}/boxscore" for g in games])
    batters, pitcher_ids, team_ids, venue_times = [], set(), set(), {}
    game_pk_map = {}  # gamePk -> game dict

    for game, box in zip(games, boxes):
        hp = game["teams"]["home"].get("probablePitcher")
        ap = game["teams"]["away"].get("probablePitcher")
        if hp: pitcher_ids.add(hp["id"])
        if ap: pitcher_ids.add(ap["id"])
        htid = game["teams"]["home"]["team"].get("id")
        atid = game["teams"]["away"]["team"].get("id")
        if htid: team_ids.add(htid)
        if atid: team_ids.add(atid)
        venue = game.get("venue", {}).get("name", "")
        if venue: venue_times[venue] = game.get("gameDate", "")
        game_pk_map[game["gamePk"]] = game
        if not box: continue
        for side in ["home","away"]:
            opp    = ap if side=="home" else hp
            opp_id = atid if side=="home" else htid
            opp_team_name = game["teams"]["away"]["team"].get("name","") if side=="home" else game["teams"]["home"]["team"].get("name","")
            t = box.get("teams",{}).get(side,{})
            for pid in t.get("batters",[]):
                pl = t.get("players",{}).get(f"ID{pid}")
                if not pl: continue
                bo = pl.get("battingOrder")
                spot = math.floor(safe_int(bo)/100) if bo else 5
                lineup_confirmed = bo is not None
                if not 1<=spot<=9: continue
                batters.append({
                    "id": pid,
                    "name": pl.get("person",{}).get("fullName","Unknown"),
                    "team": t.get("team",{}).get("abbreviation",""),
                    "opp_team_id": opp_id,
                    "opp_team_name": opp_team_name,
                    "batting_order": spot,
                    "lineup_confirmed": lineup_confirmed,
                    "pitcher_id": opp["id"] if opp else None,
                    "pitcher_name": opp.get("fullName") if opp else None,
                    "pitcher_hand": "R",
                    "batter_hand": "R",
                    "venue": venue,
                    "game_date": game.get("gameDate",""),
                    "game_pk": game["gamePk"],
                })

    ubids = list({b["id"] for b in batters})
    upids = list(pitcher_ids)
    utids = list(team_ids)
    print(f"✓  {len(batters)} batters · {len(upids)} pitchers · {len(utids)} teams")

    # Stats — first parallel batch
    print("→ Fetching stats (batch 1)…", end=" ", flush=True)
    nb, np_, nt = len(ubids), len(upids), len(utids)
    raw = fetch_many(
        # Batter season hitting
        [f"{MLB_API}/people/{i}/stats?stats=season&group=hitting&season={yr}"            for i in ubids] +
        # Batter splits (vs L/R)
        [f"{MLB_API}/people/{i}/stats?stats=statSplits&group=hitting&season={yr}&sitCodes=vl,vr" for i in ubids] +
        # Batter hot last 14 days
        [f"{MLB_API}/people/{i}/stats?stats=byDateRange&group=hitting&season={yr}&startDate={d14}&endDate={date}" for i in ubids] +
        # Pitcher season
        [f"{MLB_API}/people/{i}/stats?stats=season&group=pitching&season={yr}"           for i in upids] +
        # Pitcher hand
        [f"{MLB_API}/people/{i}"                                                          for i in upids] +
        # Pitcher splits (vl/vr)
        [f"{MLB_API}/people/{i}/stats?stats=statSplits&group=pitching&season={yr}&sitCodes=vl,vr" for i in upids] +
        # Team pitching season
        [f"{MLB_API}/teams/{i}/stats?stats=season&group=pitching&season={yr}&gameType=R" for i in utids] +
        # Batter hand (people endpoint)
        [f"{MLB_API}/people/{i}"                                                          for i in ubids] +
        # Team roster (for bullpen identification)
        [f"{MLB_API}/teams/{i}/roster?rosterType=active"                                 for i in utids],
        workers=25
    )

    def first_season(r):
        for s in (r or {}).get("stats",[]):
            if s.get("type",{}).get("displayName")=="season" and s.get("splits"):
                return s["splits"][0]["stat"]
        return None

    # Slice out each block
    off0 = 0
    bsm  = {i: first_season(r) for i, r in zip(ubids, raw[off0:off0+nb])}

    off0 += nb
    bspm = {}
    for i, r in zip(ubids, raw[off0:off0+nb]):
        s  = next((x for x in (r or {}).get("stats",[]) if x.get("type",{}).get("displayName")=="statSplits"), None)
        sp = s["splits"] if s else []
        bspm[i] = {
            "L": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vl"), None),
            "R": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vr"), None),
        }

    off0 += nb
    bhotm = {}
    for i, r in zip(ubids, raw[off0:off0+nb]):
        all_splits = []
        for stat_group in (r or {}).get("stats", []):
            all_splits.extend(stat_group.get("splits", []))
        if all_splits:
            total_pa = sum(safe_int(sp.get("stat", {}).get("plateAppearances", 0)) for sp in all_splits)
            total_hr = sum(safe_int(sp.get("stat", {}).get("homeRuns", 0)) for sp in all_splits)
            bhotm[i] = {"plateAppearances": total_pa, "homeRuns": total_hr} if total_pa > 0 else None
        else:
            bhotm[i] = None

    off0 += nb
    psm  = {i: first_season(r) for i, r in zip(upids, raw[off0:off0+np_])}

    off0 += np_
    phm  = {i: (r or {}).get("people",[{}])[0].get("pitchHand",{}).get("code","R") for i, r in zip(upids, raw[off0:off0+np_])}

    off0 += np_
    # Pitcher splits: {pitcher_id: {"vl": stat_or_None, "vr": stat_or_None}}
    psp_m = {}
    for i, r in zip(upids, raw[off0:off0+np_]):
        s  = next((x for x in (r or {}).get("stats",[]) if x.get("type",{}).get("displayName")=="statSplits"), None)
        sp = s["splits"] if s else []
        psp_m[i] = {
            "vl": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vl"), None),
            "vr": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vr"), None),
        }

    off0 += np_
    tsm  = {i: first_season(r) for i, r in zip(utids, raw[off0:off0+nt])}

    off0 += nt
    # Batter hand: {batter_id: "L"|"R"|"S"}
    bhandm = {}
    for i, r in zip(ubids, raw[off0:off0+nb]):
        bhandm[i] = (r or {}).get("people",[{}])[0].get("batSide",{}).get("code","R") or "R"

    off0 += nb
    # Team roster: {team_id: [player_id, ...]} — pitchers only
    team_roster_m = {}
    for i, r in zip(utids, raw[off0:off0+nt]):
        roster = (r or {}).get("roster", [])
        pitcher_ids_on_team = [
            pl["person"]["id"]
            for pl in roster
            if pl.get("position",{}).get("type","") == "Pitcher"
        ]
        team_roster_m[i] = pitcher_ids_on_team

    # Update batter hand and pitcher hand
    for b in batters:
        b["pitcher_hand"] = phm.get(b["pitcher_id"], "R")
        b["batter_hand"]  = bhandm.get(b["id"], "R")

    print("✓")

    # Identify all unique reliever IDs
    # Exclude probable starters from each team's roster
    starter_by_team = {}
    for b in batters:
        if b.get("opp_team_id") and b.get("pitcher_id"):
            starter_by_team.setdefault(b["opp_team_id"], set()).add(b["pitcher_id"])

    all_reliever_ids = []
    reliever_to_team = {}
    for tid in utids:
        starters = starter_by_team.get(tid, set())
        for rid in team_roster_m.get(tid, []):
            if rid not in starters:
                all_reliever_ids.append(rid)
                reliever_to_team[rid] = tid
    all_reliever_ids = list(set(all_reliever_ids))

    # Second parallel batch: reliever splits + reliever season stats
    rel_splits_m  = {}
    rel_season_m  = {}
    if all_reliever_ids:
        print("→ Fetching reliever stats (batch 2)…", end=" ", flush=True)
        nr = len(all_reliever_ids)
        raw2 = fetch_many(
            [f"{MLB_API}/people/{i}/stats?stats=statSplits&group=pitching&season={yr}&sitCodes=vl,vr" for i in all_reliever_ids] +
            [f"{MLB_API}/people/{i}/stats?stats=season&group=pitching&season={yr}"                    for i in all_reliever_ids],
            workers=25
        )
        for i, r in zip(all_reliever_ids, raw2[:nr]):
            s  = next((x for x in (r or {}).get("stats",[]) if x.get("type",{}).get("displayName")=="statSplits"), None)
            sp = s["splits"] if s else []
            rel_splits_m[i] = {
                "vl": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vl"), None),
                "vr": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vr"), None),
            }
        for i, r in zip(all_reliever_ids, raw2[nr:]):
            rel_season_m[i] = first_season(r)
        print(f"✓  {nr} relievers")

    # Build per-team bullpen aggregates (weighted, regressed, platoon-aware)
    bp_splits_m = {}  # {team_id: {"L": hr_pa_rate, "R": hr_pa_rate}}
    for tid in utids:
        starters = starter_by_team.get(tid, set())
        rel_ids  = [r for r in team_roster_m.get(tid, []) if r not in starters]
        for side in ["L", "R"]:
            sitcode = "vl" if side == "L" else "vr"
            total_ip = 0.0
            weighted_rate = 0.0
            for rid in rel_ids:
                sp = rel_season_m.get(rid)
                ip = safe_float((sp or {}).get("inningsPitched"))
                if ip < 5:
                    continue
                rs   = rel_splits_m.get(rid, {}).get(sitcode)
                r_hr = safe_int((rs or {}).get("homeRuns"))
                r_ip = safe_float((rs or {}).get("inningsPitched"))
                if r_ip < 3:
                    r_ip = ip * 0.5  # fallback
                rate = regressed_hr_pa(r_hr, r_ip)
                weighted_rate += rate * ip
                total_ip      += ip
            bp_splits_m.setdefault(tid, {})
            bp_splits_m[tid][side] = (weighted_rate / total_ip) if total_ip > 0 else LG_HR_PA

    # Statcast
    sc_by_id, sc_by_name = get_statcast(int(yr))

    # Weather
    print("→ Fetching weather…", end=" ", flush=True)
    wmap = get_weather({v:t for v,t in venue_times.items() if VENUES.get(v,{}).get("out")})
    print(f"✓  {len(wmap)} venues")

    # Odds
    game_totals = {}
    if args.key:
        print("→ Fetching odds…", end=" ", flush=True)
        odds_map, game_totals = get_odds(args.key, date)
        print(f"✓  {len(odds_map)} players · {len(game_totals)} game totals")
    else:
        odds_map = {}
        print("   (no odds key — model only)")

    # Build game O/U lookup per batter by matching away team name
    # game_totals keyed by norm(away_team) from Odds API
    # Each game has teams.away.team.name we can normalize and look up
    def get_game_ou(game):
        away_name = game.get("teams",{}).get("away",{}).get("team",{}).get("name","")
        key = norm(away_name)
        return game_totals.get(key, 8.5)

    game_pk_ou = {}
    for gpk, game in game_pk_map.items():
        game_pk_ou[gpk] = get_game_ou(game)

    # Model
    print("→ Computing model…", end=" ", flush=True)
    results = []
    for b in batters:
        ou = game_pk_ou.get(b.get("game_pk"), 8.5)
        r = run_model(
            b,
            bsm.get(b["id"]),
            bspm.get(b["id"], {}),
            bhotm.get(b["id"]),
            psm.get(b["pitcher_id"]),
            psp_m.get(b["pitcher_id"]),
            bp_splits_m.get(b["opp_team_id"]),
            tsm.get(b["opp_team_id"]),
            wmap.get(b["venue"]),
            sc_by_id, sc_by_name,
            odds_map,
            ou=ou,
        )
        if r: results.append(r)
    results.sort(key=lambda x:(x["edge"] is not None, x.get("edge") or x["game_prob"]), reverse=True)
    if args.min_edge > 0:
        results = [r for r in results if r.get("edge") is None or r["edge"] >= args.min_edge]
    print(f"✓  {len(results)} players")
    if args.key:
        matched = sum(1 for r in results if r.get("best_odds") is not None)
        print(f"   Odds match rate: {matched}/{len(results)} players")

    # Console summary
    value_bets = [r for r in results if (r.get("edge") or 0) > 0.02]
    print(f"\n  {len(results)} players · {sum(1 for r in results if r['best_odds'] is not None)} with lines · {len(value_bets)} value bets")
    if value_bets:
        print(f"\n  {'PLAYER':<26} {'PROB':>6}  {'LINE':>7}  {'EDGE':>6}  BOOK")
        print("  " + "─"*58)
        for r in value_bets:
            e = r.get("edge") or 0
            print(f"  {r['name'][:25]:<26} {r['game_prob']*100:.1f}%  {fo(r['best_odds']):>7}  {e*100:+.1f}%  {(r.get('best_book') or '')[:14]}{'  🔥' if e>.05 else ''}")

    # Save picks
    save_picks(results, date, args.window)

    # Load season stats for report
    season_stats = None
    reset_date = ""
    try:
        with open("results/picks.json") as f:
            all_picks = json.load(f)
        season_stats = compute_stats(all_picks)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    try:
        with open("results/reset_date.txt") as f:
            reset_date = f.read().strip()
    except FileNotFoundError:
        pass

    # HTML report — standalone window file
    os.makedirs("reports", exist_ok=True)
    window_suffix = f"_{args.window}" if args.window else ""
    report_path   = os.path.abspath(f"reports/report_{date}{window_suffix}.html")
    html = build_report(results, date, bool(odds_map), bool(sc_by_id or sc_by_name), len(wmap), bool(args.key),
                        window=args.window, stats=season_stats, bankroll=args.bankroll, reset_date=reset_date)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Combined daily report for GitHub Pages (append this window's section)
    os.makedirs("docs", exist_ok=True)
    combined_path = f"docs/report_{date}.html"
    append_to_combined(combined_path, results, date, bool(odds_map), bool(sc_by_id or sc_by_name), len(wmap), bool(args.key),
                       window=args.window, stats=season_stats, bankroll=args.bankroll, reset_date=reset_date)
    shutil.copy2(combined_path, "docs/index.html")

    print(f"\n  ✓  Report: {report_path}")

    if args.open:
        webbrowser.open(f"file://{report_path}")

    if args.debug:
        print_debug_summary(results, odds_map, bool(args.key))

    # Notifications
    send_notifications(results, date, html, args)
    print()


if __name__ == "__main__":
    main()
