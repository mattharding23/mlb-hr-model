#!/usr/bin/env python3
"""
check_results.py — Resolve pending MLB HR prop picks against actual boxscore data.

Loads results/picks.json, finds entries where result is null and date < today,
fetches MLB boxscores, and fills in result / units_returned.

Usage:
  python check_results.py
  python check_results.py --date 2026-05-10   # resolve a specific date only
"""

import json
import os
import sys
import argparse
from datetime import datetime, date as date_type
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


MLB_API = "https://statsapi.mlb.com/api/v1"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def fetch(url, timeout=20):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_many(urls, workers=10):
    results = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch, u): i for i, u in enumerate(urls)}
        for f in as_completed(futures):
            results[futures[f]] = f.result()
    return results


def american_to_decimal(odds):
    if odds > 0:
        return odds / 100 + 1
    return 100 / abs(odds) + 1


def safe_int(x):
    try:
        return int(x or 0)
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# Core logic
# ──────────────────────────────────────────────────────────────────────────────

def get_game_pks_for_date(date_str):
    """Fetch all gamePks for a given date string (YYYY-MM-DD)."""
    r = fetch(f"{MLB_API}/schedule?sportId=1&date={date_str}&hydrate=decisions")
    if not r:
        return []
    games = r.get("dates", [{}])[0].get("games", [])
    return [g["gamePk"] for g in games if "gamePk" in g]


def get_hr_map_for_game(game_pk):
    """
    Returns a dict {player_id: hr_count} for all batters in a game's boxscore.
    """
    box = fetch(f"{MLB_API}/game/{game_pk}/boxscore")
    if not box:
        return {}
    hr_map = {}
    teams = box.get("teams", {})
    for side in ("home", "away"):
        players = teams.get(side, {}).get("players", {})
        for key, pdata in players.items():
            # key is "ID{playerId}"
            if not key.startswith("ID"):
                continue
            try:
                pid = int(key[2:])
            except ValueError:
                continue
            batting = pdata.get("stats", {}).get("batting", {})
            hrs = safe_int(batting.get("homeRuns"))
            hr_map[pid] = hrs
    return hr_map


def resolve_picks(picks, today_str):
    """
    For picks where result is None and date < today, resolve using boxscores.
    Returns (updated_picks, summary_lines).
    """
    today = datetime.strptime(today_str, "%Y-%m-%d").date()

    # Find pending dates (date < today, result is null)
    pending = [p for p in picks if p.get("result") is None and p.get("date")]
    pending_dates = sorted({p["date"] for p in pending if datetime.strptime(p["date"], "%Y-%m-%d").date() < today})

    if not pending_dates:
        return picks, []

    print(f"  Found {len(pending)} pending picks across {len(pending_dates)} date(s): {', '.join(pending_dates)}")

    # Build date -> gamePk list
    print("  Fetching schedules…", end=" ", flush=True)
    date_to_game_pks = {}
    for d in pending_dates:
        pks = get_game_pks_for_date(d)
        date_to_game_pks[d] = pks
    print("✓")

    # Collect all unique game PKs
    all_game_pks = list({pk for pks in date_to_game_pks.values() for pk in pks})
    print(f"  Fetching {len(all_game_pks)} boxscores…", end=" ", flush=True)

    # Fetch all boxscores in parallel
    box_responses = fetch_many(
        [f"{MLB_API}/game/{pk}/boxscore" for pk in all_game_pks],
        workers=15,
    )

    # Build game_pk -> hr_map and pa_map
    game_hr_maps = {}
    game_pa_maps = {}
    for pk, box in zip(all_game_pks, box_responses):
        if not box:
            game_hr_maps[pk] = {}
            game_pa_maps[pk] = {}
            continue
        hr_map = {}
        pa_map = {}
        teams = box.get("teams", {})
        for side in ("home", "away"):
            players = teams.get(side, {}).get("players", {})
            for key, pdata in players.items():
                if not key.startswith("ID"):
                    continue
                try:
                    pid = int(key[2:])
                except ValueError:
                    continue
                batting = pdata.get("stats", {}).get("batting", {})
                hr_map[pid] = safe_int(batting.get("homeRuns"))
                pa_map[pid] = safe_int(batting.get("plateAppearances"))
        game_hr_maps[pk] = hr_map
        game_pa_maps[pk] = pa_map

    # Build player_id -> hr_count and pa_count for each date
    date_player_hr = {}
    date_player_pa = {}
    for d, pks in date_to_game_pks.items():
        merged_hr = {}
        merged_pa = {}
        for pk in pks:
            for pid, hrs in game_hr_maps.get(pk, {}).items():
                merged_hr[pid] = hrs
            for pid, pa in game_pa_maps.get(pk, {}).items():
                merged_pa[pid] = pa
        date_player_hr[d] = merged_hr
        date_player_pa[d] = merged_pa

    print("✓")

    # Resolve picks
    resolved_count = 0
    skipped_count  = 0
    summary_lines  = []

    for pick in picks:
        if pick.get("result") is not None:
            continue
        d = pick.get("date")
        if not d:
            continue
        if datetime.strptime(d, "%Y-%m-%d").date() >= today:
            continue

        player_id = pick.get("player_id")
        if player_id is None:
            continue

        hr_by_player = date_player_hr.get(d, {})
        if player_id not in hr_by_player:
            skipped_count += 1
            continue

        hrs = hr_by_player[player_id]
        result = hrs > 0
        pick["result"] = result

        # Fill actual_pa into factors if present (enables PA-projection accuracy analysis)
        if pick.get("factors") is not None:
            pa_by_player = date_player_pa.get(d, {})
            if player_id in pa_by_player:
                pick["factors"]["actual_pa"] = pa_by_player[player_id]

        # Fill units_returned
        units_staked = pick.get("units_staked")
        best_odds    = pick.get("best_odds")

        if units_staked is not None and best_odds is not None:
            decimal_odds = american_to_decimal(best_odds)
            if result:
                # Win: stake * decimal_odds - stake = profit; total return = stake * decimal_odds
                pick["units_returned"] = round(units_staked * decimal_odds, 4)
            else:
                pick["units_returned"] = round(-units_staked, 4)
        elif units_staked is not None:
            # No line — just mark win/loss with no monetary value
            pick["units_returned"] = None

        pick["resolved_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        resolved_count += 1

        icon = "✅" if result else "❌"
        ur   = pick.get("units_returned")
        ur_str = f"  ({ur:+.2f}u)" if ur is not None else ""
        summary_lines.append(
            f"  {icon} {d} {pick['player']:<28} {hrs} HR{ur_str}"
        )

    print(f"  Resolved {resolved_count} picks  ({skipped_count} not found in boxscores)")
    return picks, summary_lines


def main():
    ap = argparse.ArgumentParser(description="Resolve MLB HR prop picks against boxscores")
    ap.add_argument("--date", default=None, help="Only resolve this specific date (YYYY-MM-DD)")
    ap.add_argument("--picks", default="results/picks.json", help="Path to picks JSON file")
    args = ap.parse_args()

    picks_path = args.picks
    today_str  = datetime.utcnow().strftime("%Y-%m-%d")

    # Load picks
    if not os.path.exists(picks_path):
        print(f"No picks file found at {picks_path} — nothing to resolve.")
        sys.exit(0)

    try:
        with open(picks_path) as f:
            picks = json.load(f)
    except json.JSONDecodeError:
        print(f"Picks file at {picks_path} is empty or invalid — nothing to resolve.")
        sys.exit(0)

    print(f"\n⚾  check_results.py  —  resolving against today {today_str}")
    print("─" * 50)
    print(f"  Loaded {len(picks)} total picks from {picks_path}")

    # If --date specified, filter to only that date
    if args.date:
        resolve_date = args.date
        target_picks = [p for p in picks if p.get("date") == resolve_date]
        other_picks  = [p for p in picks if p.get("date") != resolve_date]
        print(f"  Filtering to date {resolve_date}: {len(target_picks)} picks")
        updated_target, summary = resolve_picks(target_picks, today_str)
        all_picks = other_picks + updated_target
    else:
        all_picks, summary = resolve_picks(picks, today_str)

    # Save back
    with open(picks_path, "w") as f:
        json.dump(all_picks, f, indent=2)
    print(f"  Saved {len(all_picks)} picks to {picks_path}")

    if summary:
        print(f"\n  Results:")
        for line in summary:
            print(line)

        # Print aggregate for resolved session
        resolved = [p for p in all_picks if p.get("result") is not None and p.get("units_staked") is not None]
        if resolved:
            net = sum(p.get("units_returned") or 0 for p in resolved)
            staked = sum(p.get("units_staked") or 0 for p in resolved)
            roi = (net / staked * 100) if staked > 0 else 0
            wins = sum(1 for p in resolved if p["result"])
            print(f"\n  Season totals (all resolved lined picks):")
            print(f"  {wins}-{len(resolved)-wins}  net {net:+.2f}u  ROI {roi:+.1f}%  (staked {staked:.2f}u)")
    else:
        print("  No picks to resolve.")

    print()


if __name__ == "__main__":
    main()
