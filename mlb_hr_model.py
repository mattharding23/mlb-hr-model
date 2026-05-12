#!/usr/bin/env python3
"""
MLB HR Prop Finder v3
──────────────────────────────────────────────────────────────────────────────
Model factors:
  • Season HR/PA rate (base, min 30 PA)
  • vs LHP/RHP splits (regressed, max 45% weight)
  • Hotness: last 14 days HR/PA (regressed, max 35% weight, needs ≥8 PA)
  • Statcast: barrel% + hard-hit% from Baseball Savant (regressed, 40% weight)
  • Starting pitcher HR rate vs league avg
  • Bullpen HR rate (team total − SP, blended 55% SP / 45% BP)
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

Setup:
  pip install requests pybaseball pandas
"""

import sys, os, math, argparse, smtplib, webbrowser, shutil
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
    "early": "🕐 Early Window (12–3:59 pm ET)",
    "mid":   "🕓 Mid Window (4–6:59 pm ET)",
    "late":  "🕖 Late Window (7 pm+ ET)",
}

def in_window(game_date_str, window):
    if not window or not game_date_str:
        return True
    try:
        dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
        hour = (dt.hour - 4) % 24  # EDT = UTC-4 for the full baseball season
        if window == "early": return 12 <= hour < 16
        if window == "mid":   return 16 <= hour < 19
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
    return PA_BY_SPOT.get(spot, 4.1) + (ou - 8.5) * 0.06

def american_to_implied(odds):
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def implied_to_american(p):
    p = max(0.01, min(0.99, p))
    if p >= 0.5: return f"-{round((p / (1-p)) * 100)}"
    return f"+{round(((1-p) / p) * 100)}"

def norm(s):
    return (s or "").lower().replace(".", "").replace("'", "").replace(",", "").strip()

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
    if not api_key: return {}
    events = fetch(
        f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events"
        f"?apiKey={api_key}&dateFormat=iso"
        f"&commenceTimeFrom={date}T00:00:00Z&commenceTimeTo={date}T23:59:59Z"
    )
    if not events or not isinstance(events, list): return {}
    urls = [
        f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{e['id']}/odds"
        f"?apiKey={api_key}&markets=batter_home_runs&oddsFormat=american"
        f"&bookmakers=draftkings,fanduel,betmgm,caesars,pointsbetus,betrivers"
        for e in events
    ]
    responses = fetch_many(urls, workers=3)
    odds_map = {}
    for res in responses:
        if not res: continue
        for book in res.get("bookmakers", []):
            mkt = next((m for m in book.get("markets", []) if m["key"] == "batter_home_runs"), None)
            if not mkt: continue
            for o in mkt.get("outcomes", []):
                key = norm(o.get("description") or o.get("name", ""))
                if key not in odds_map: odds_map[key] = {"books": []}
                odds_map[key]["books"].append({"book": book["title"], "odds": o["price"]})
    for key in odds_map:
        best = max(odds_map[key]["books"], key=lambda x: x["odds"])
        odds_map[key]["best"]      = best["odds"]
        odds_map[key]["best_book"] = best["book"]
    return odds_map


# ──────────────────────────────────────────────────────────────────────────────
# Model
# ──────────────────────────────────────────────────────────────────────────────

def run_model(batter, season, splits, hot, sp_stat, team_stat,
              weather, sc_by_id, sc_by_name, odds_map):
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
            w = min(s_pa / 150, 0.45)
            split_adj = max(0.5, min(2.5, ((s_hr/s_pa)*w + sr*(1-w)) / sr))

    # 2. Hotness — last 14 days (regressed)
    hot_adj = 1.0; r_hr = r_pa = 0
    if hot and sr > 0:
        r_pa = safe_int(hot.get("plateAppearances"))
        r_hr = safe_int(hot.get("homeRuns"))
        if r_pa >= 8:
            w = min(r_pa / 55, 0.35)
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

    # 4. Starting pitcher
    sp_adj = 1.0
    if sp_stat:
        ip = safe_float(sp_stat.get("inningsPitched"))
        if ip > 10:
            sp_adj = max(0.4, min(3.0, (safe_int(sp_stat.get("homeRuns")) / (ip * 4.35)) / LG_HR_PA))

    # 5. Bullpen (team − SP)
    bp_adj = 1.0
    if team_stat:
        t_ip = safe_float(team_stat.get("inningsPitched"))
        t_hr = safe_int(team_stat.get("homeRuns"))
        if t_ip > 50:
            sp_ip = safe_float(sp_stat.get("inningsPitched")) if sp_stat else 0
            sp_hr = safe_int(sp_stat.get("homeRuns"))         if sp_stat else 0
            bp_ip = max(t_ip - sp_ip, 10)
            bp_adj = max(0.5, min(2.5, (max(t_hr - sp_hr, 0) / (bp_ip * 4.35)) / LG_HR_PA))

    pitch_blend = 0.55 * sp_adj + 0.45 * bp_adj

    # 6. Park factor
    park_adj = VENUES.get(batter["venue"], {}).get("pf", 1.0)

    # 7. Weather
    temp_adj = wind_adj = 1.0
    if weather:
        temp_adj = max(0.92, min(1.10, 1 + (weather["temp_f"]   - 72) * 0.0015))
        wind_adj = max(0.92, min(1.12, 1 + max(0, weather["wind_mph"] - 5) * 0.005))

    pp     = proj_pa(batter["batting_order"])
    per_pa = max(0.001, min(0.12, sr * split_adj * hot_adj * sc_adj * pitch_blend * park_adj * temp_adj * wind_adj))
    gp     = 1 - (1 - per_pa) ** pp

    od        = odds_map.get(norm(batter["name"]), {})
    best_odds = od.get("best")
    best_book = od.get("best_book")
    implied   = american_to_implied(best_odds) if best_odds is not None else None
    edge      = (gp - implied) if implied is not None else None

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
        "implied": implied, "edge": edge,
        "all_books": od.get("books", []), "weather": weather,
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
"""

def cfactor(adj, label, thresh=0.04):
    d = adj - 1
    if abs(d) < thresh: return None
    color = "#22c55e" if d > 0 else "#f87171"
    return f'<span style="color:{color}">{"↑" if d>0 else "↓"}{label} {d*100:+.0f}%</span>'

def _build_section(results, date, has_odds, has_statcast, weather_count, has_key, window=None):
    total      = len(results)
    with_lines = sum(1 for r in results if r["best_odds"] is not None)
    value_bets = sum(1 for r in results if (r.get("edge") or 0) > 0.02)
    avg_prob   = sum(r["game_prob"] for r in results) / total if total else 0

    rows = []
    for r in results:
        e  = r.get("edge"); gp = r["game_prob"]
        rbg = "background:rgba(34,197,94,.05);" if (e or 0) > 0.05 else ""
        ec = "#64748b" if e is None else "#22c55e" if e>.05 else "#86efac" if e>.02 else "#94a3b8" if e>-.02 else "#f87171"
        pc = "#22c55e" if gp>.11 else "#f59e0b" if gp>.07 else "#e2e8f0"
        badge = '<span class="badge bet">Bet</span>' if (e or-1)>.05 else '<span class="badge lean">Lean</span>' if (e or-1)>.02 else '<span class="badge skip">Skip</span>' if (e or-1)<-.04 else "—"

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

        odds_cols = ""
        if has_odds:
            bo = r["best_odds"]
            bo_str = fo(bo) if bo is not None else '<span style="color:#334155">—</span>'
            edge_str = f"{e*100:+.1f}%" if e is not None else "—"
            odds_cols = f'<td style="text-align:right;font-weight:600">{bo_str}</td><td style="font-size:11px;color:#64748b">{r.get("best_book") or "—"}</td><td style="text-align:right;font-weight:700;color:{ec}">{edge_str}</td><td>{badge}</td>'

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
            <span style="font-weight:600">{r["name"]}</span>{" "+r["hot_label"] if r["hot_label"] else ""}
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
    odds_ths = '<th style="text-align:right">Best line</th><th>Book</th><th style="text-align:right">Edge</th><th>Rec</th>' if has_odds else ""
    all_books = list({b["book"] for r in results for b in r.get("all_books",[])})
    odds_note = f"Lines from: {', '.join(all_books[:6])}. Edge = model − implied. Bet ≥+5pp · Lean +2–5pp · Skip ≤−4pp." if has_key else "Run with -k YOUR_ODDS_KEY for live line comparison."
    sc_note   = f"Statcast: barrel% + hard-hit% (barrel ratio vs {LG_BARREL*100:.1f}% league avg, exp 0.40)." if has_statcast else "Statcast disabled — install pybaseball."
    wh = f'<div class="wh">{WINDOW_LABELS[window]}</div>' if window else ""

    return f"""<section>
{wh}<div class="g5">
  <div class="metric"><div class="ml">Players</div><div class="mv">{total}</div></div>
  <div class="metric"><div class="ml">With lines</div><div class="mv">{with_lines}</div></div>
  <div class="metric"><div class="ml">Value bets</div><div class="mv g">{value_bets}</div></div>
  <div class="metric"><div class="ml">Avg prob</div><div class="mv">{avg_prob*100:.1f}%</div></div>
  <div class="metric"><div class="ml">Weather</div><div class="mv">{weather_count}</div></div>
</div>
<div class="legend">
  <span>🔥 Hot ≥+20%</span><span>↗ Warm +8–19%</span>
  <span>↘ Cool −10–22%</span><span>🧊 Cold ≤−22%</span>
  <span style="margin-left:8px">↑ raises prob &nbsp; ↓ lowers prob</span>
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
  <strong style="color:#94a3b8">v3 model:</strong>
  season HR/PA · splits (regressed) · hotness L14 (regressed) · {sc_note} ·
  SP HR rate · bullpen HR rate (team−SP, 55/45 blend) · park factor ({len(VENUES)} venues) · weather.<br><br>
  <strong style="color:#94a3b8">Lines:</strong> {odds_note}
</div>
</section>"""


def build_report(results, date, has_odds, has_statcast, weather_count, has_key, window=None):
    section = _build_section(results, date, has_odds, has_statcast, weather_count, has_key, window)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>MLB HR Props — {date}</title>
<style>{CSS}</style></head><body>
<h1>⚾ MLB HR Prop Finder — {date}</h1>
<p class="sub">v3 · hotness · bullpen · weather · Statcast &nbsp;|&nbsp; Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
{section}
</body></html>"""


def append_to_combined(html_path, results, date, has_odds, has_statcast, weather_count, has_key, window=None):
    section = _build_section(results, date, has_odds, has_statcast, weather_count, has_key, window)
    if not os.path.exists(html_path):
        content = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>MLB HR Props — {date}</title>
<style>{CSS}</style></head><body>
<h1>⚾ MLB HR Prop Finder — {date}</h1>
<p class="sub">v3 · hotness · bullpen · weather · Statcast &nbsp;|&nbsp; Combined daily report</p>
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
    if not value_bets:
        return

    gmail_addr = os.environ.get("GMAIL_ADDRESS", "")    or args.gmail_from
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD","") or args.gmail_pass
    to_email   = os.environ.get("REPORT_EMAIL", "")     or args.email_to
    to_phone   = os.environ.get("REPORT_PHONE", "")     or args.sms_to
    carrier    = os.environ.get("CARRIER", "").lower()  or (args.carrier or "").lower()
    pages_url  = os.environ.get("PAGES_URL", "")        or args.pages_url

    if not gmail_addr or not gmail_pass:
        return

    window_tag = f" [{args.window.title()}]" if getattr(args, "window", None) else ""
    subject    = f"⚾ MLB HR Props {date}{window_tag} — {len(value_bets)} value bet{'s' if len(value_bets)!=1 else ''}"

    # ── Full HTML email ───────────────────────────────────────────
    if to_email:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"MLB HR Model Value <{gmail_addr}>"
            msg["To"]      = to_email
            plain = f"MLB HR Props — {date}{window_tag}\n{len(value_bets)} value bets\n\n"
            for r in value_bets:
                plain += f"• {r['name']} {fo(r['best_odds'])} ({r.get('best_book','')}) edge {(r.get('edge') or 0)*100:+.1f}%\n"
            if pages_url:
                plain += f"\nFull report: {pages_url}"
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls()
                s.login(gmail_addr, gmail_pass)
                s.sendmail(gmail_addr, [to_email], msg.as_string())
            print(f"  ✓  Email → {to_email}")
        except Exception as e:
            print(f"  ✗  Email failed: {e}")

    # ── SMS via carrier email-to-text gateway (free) ──────────────
    if to_phone and carrier and carrier in CARRIER_GATEWAYS:
        try:
            digits   = "".join(c for c in to_phone if c.isdigit())
            sms_addr = digits + CARRIER_GATEWAYS[carrier]

            lines = [f"⚾ HR Props {date}{window_tag}"]
            for r in value_bets[:4]:
                e     = (r.get("edge") or 0) * 100
                label = "🔥 Strong" if e > 5 else "✅ Lean"
                book  = (r.get("best_book") or "")[:3]
                lines.append(f"• {r['name'].split()[-1]} {fo(r['best_odds'])} {book} {label} {e:+.1f}%")
            if pages_url:
                lines.append(pages_url)

            sms = MIMEText("\n".join(lines))
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
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="MLB HR Prop Finder v3")
    p.add_argument("-d","--date",      default=datetime.today().strftime("%Y-%m-%d"))
    p.add_argument("-k","--key",       default=os.environ.get("ODDS_API_KEY",""))
    p.add_argument("--min-edge",       type=float, default=0.0)
    p.add_argument("--open",           action="store_true", help="Open report in browser")
    p.add_argument("--email-to",       default="", help="Recipient email address")
    p.add_argument("--sms-to",         default="", help="10-digit phone number")
    p.add_argument("--carrier",        default="", help="att|verizon|tmobile|sprint|boost|cricket")
    p.add_argument("--gmail-from",     default="", help="Gmail sender address (or set GMAIL_ADDRESS)")
    p.add_argument("--gmail-pass",     default="", help="Gmail App Password (or set GMAIL_APP_PASSWORD)")
    p.add_argument("--window",         choices=["early","mid","late"], default=None, help="Game time window: early(12-4pm ET) mid(4-7pm ET) late(7pm+ ET)")
    p.add_argument("--pages-url",      default="", help="GitHub Pages URL for SMS link")
    args = p.parse_args()

    date = args.date
    yr   = date.split("-")[0]
    d14  = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")

    print(f"\n⚾  MLB HR Prop Finder v3  —  {date}")
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
        if not box: continue
        for side in ["home","away"]:
            opp    = ap if side=="home" else hp
            opp_id = atid if side=="home" else htid
            t      = box.get("teams",{}).get(side,{})
            for pid in t.get("batters",[]):
                pl = t.get("players",{}).get(f"ID{pid}")
                if not pl: continue
                bo = pl.get("battingOrder")
                spot = math.floor(safe_int(bo)/100) if bo else 5
                if not 1<=spot<=9: continue
                batters.append({
                    "id":pid,"name":pl.get("person",{}).get("fullName","Unknown"),
                    "team":t.get("team",{}).get("abbreviation",""),
                    "opp_team_id":opp_id,"batting_order":spot,
                    "pitcher_id":opp["id"] if opp else None,
                    "pitcher_name":opp.get("fullName") if opp else None,
                    "pitcher_hand":"R","venue":venue,"game_date":game.get("gameDate",""),
                })

    ubids = list({b["id"] for b in batters})
    upids = list(pitcher_ids)
    utids = list(team_ids)
    print(f"✓  {len(batters)} batters · {len(upids)} pitchers · {len(utids)} teams")

    # Stats (all parallel)
    print("→ Fetching stats…", end=" ", flush=True)
    nb, np_, nt = len(ubids), len(upids), len(utids)
    raw = fetch_many(
        [f"{MLB_API}/people/{i}/stats?stats=season&group=hitting&season={yr}"            for i in ubids] +
        [f"{MLB_API}/people/{i}/stats?stats=statSplits&group=hitting&season={yr}&sitCodes=vl,vr" for i in ubids] +
        [f"{MLB_API}/people/{i}/stats?stats=byDateRange&group=hitting&season={yr}&startDate={d14}&endDate={date}" for i in ubids] +
        [f"{MLB_API}/people/{i}/stats?stats=season&group=pitching&season={yr}"           for i in upids] +
        [f"{MLB_API}/people/{i}"                                                          for i in upids] +
        [f"{MLB_API}/teams/{i}/stats?stats=season&group=pitching&season={yr}&gameType=R" for i in utids],
        workers=20
    )

    def first_season(r):
        for s in (r or {}).get("stats",[]):
            if s.get("type",{}).get("displayName")=="season" and s.get("splits"):
                return s["splits"][0]["stat"]
        return None

    bsm  = {i: first_season(r) for i,r in zip(ubids, raw[0:nb])}
    bspm = {}
    for i,r in zip(ubids, raw[nb:2*nb]):
        s  = next((x for x in (r or {}).get("stats",[]) if x.get("type",{}).get("displayName")=="statSplits"), None)
        sp = s["splits"] if s else []
        bspm[i] = {
            "L": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vl"), None),
            "R": next((x["stat"] for x in sp if x.get("split",{}).get("code")=="vr"), None),
        }
    bhotm = {}
    for i,r in zip(ubids, raw[2*nb:3*nb]):
        found = next((x for x in (r or {}).get("stats",[]) if x.get("splits")), None)
        bhotm[i] = found["splits"][0]["stat"] if found and found.get("splits") else None
    psm  = {i: first_season(r) for i,r in zip(upids, raw[3*nb:3*nb+np_])}
    phm  = {i:(r or {}).get("people",[{}])[0].get("pitchHand",{}).get("code","R") for i,r in zip(upids, raw[3*nb+np_:3*nb+2*np_])}
    tsm  = {i: first_season(r) for i,r in zip(utids, raw[3*nb+2*np_:])}
    for b in batters: b["pitcher_hand"] = phm.get(b["pitcher_id"],"R")
    print("✓")

    # Statcast
    sc_by_id, sc_by_name = get_statcast(int(yr))

    # Weather
    print("→ Fetching weather…", end=" ", flush=True)
    wmap = get_weather({v:t for v,t in venue_times.items() if VENUES.get(v,{}).get("out")})
    print(f"✓  {len(wmap)} venues")

    # Odds
    if args.key:
        print("→ Fetching odds…", end=" ", flush=True)
        odds_map = get_odds(args.key, date)
        print(f"✓  {len(odds_map)} players")
    else:
        odds_map = {}
        print("   (no odds key — model only)")

    # Model
    print("→ Computing model…", end=" ", flush=True)
    results = []
    for b in batters:
        r = run_model(b, bsm.get(b["id"]), bspm.get(b["id"],{}), bhotm.get(b["id"]),
                      psm.get(b["pitcher_id"]), tsm.get(b["opp_team_id"]),
                      wmap.get(b["venue"]), sc_by_id, sc_by_name, odds_map)
        if r: results.append(r)
    results.sort(key=lambda x:(x["edge"] is not None, x.get("edge") or x["game_prob"]), reverse=True)
    if args.min_edge > 0:
        results = [r for r in results if r.get("edge") is None or r["edge"] >= args.min_edge]
    print(f"✓  {len(results)} players")

    # Console summary
    value_bets = [r for r in results if (r.get("edge") or 0) > 0.02]
    print(f"\n  {len(results)} players · {sum(1 for r in results if r['best_odds'] is not None)} with lines · {len(value_bets)} value bets")
    if value_bets:
        print(f"\n  {'PLAYER':<26} {'PROB':>6}  {'LINE':>7}  {'EDGE':>6}  BOOK")
        print("  " + "─"*58)
        for r in value_bets:
            e = r.get("edge") or 0
            print(f"  {r['name'][:25]:<26} {r['game_prob']*100:.1f}%  {fo(r['best_odds']):>7}  {e*100:+.1f}%  {(r.get('best_book') or '')[:14]}{'  🔥' if e>.05 else ''}")

    # HTML report — standalone window file
    os.makedirs("reports", exist_ok=True)
    window_suffix = f"_{args.window}" if args.window else ""
    report_path   = os.path.abspath(f"reports/report_{date}{window_suffix}.html")
    html = build_report(results, date, bool(odds_map), bool(sc_by_id or sc_by_name), len(wmap), bool(args.key), window=args.window)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Combined daily report for GitHub Pages (append this window's section)
    os.makedirs("docs", exist_ok=True)
    combined_path = f"docs/report_{date}.html"
    append_to_combined(combined_path, results, date, bool(odds_map), bool(sc_by_id or sc_by_name), len(wmap), bool(args.key), window=args.window)
    shutil.copy2(combined_path, "docs/index.html")

    print(f"\n  ✓  Report: {report_path}")

    if args.open:
        webbrowser.open(f"file://{report_path}")

    # Notifications
    send_notifications(results, date, html, args)
    print()


if __name__ == "__main__":
    main()
