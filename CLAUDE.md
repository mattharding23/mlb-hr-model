# MLB HR Prop Finder

## What this project does
Daily MLB home run prop value finder. Runs automatically via GitHub Actions at 11am ET, 
emails a full HTML report, and sends an SMS summary. The report is also published to 
GitHub Pages for access from any device.

## How to run it
```bash
# Today's games, no odds
python mlb_hr_model.py

# With live lines
python mlb_hr_model.py -k $ODDS_API_KEY

# Specific date, open report in browser
python mlb_hr_model.py -d 2026-05-15 -k $ODDS_API_KEY --open

# Test notifications
python mlb_hr_model.py -k $ODDS_API_KEY --email-to matt@example.com --sms-to 5551234567 --carrier verizon
```

## File structure
```
mlb_hr_model.py              # Main script — model + report + notifications
requirements.txt             # pip install requests pybaseball pandas
.github/workflows/daily.yml  # GitHub Actions cron (runs 11am ET daily)
reports/                     # HTML reports saved locally (report_YYYY-MM-DD.html)
docs/index.html              # Latest report — deployed to GitHub Pages
```

## Model factors (in order of application)
1. Season HR/PA rate — base rate, minimum 30 PA to qualify
2. vs LHP/RHP splits — regressed to mean, max 45% weight on split sample
3. Hotness — last 14 days HR/PA via byDateRange API, regressed, max 35% weight, needs ≥8 PA
4. Statcast — barrel% + hard-hit% from Baseball Savant via pybaseball, regressed (barrel exp 0.40, hard-hit exp 0.20)
5. Starting pitcher HR rate — vs league avg (0.034/PA), capped 0.4x–3.0x
6. Bullpen HR rate — team pitching stats minus SP contribution, blended 55% SP / 45% bullpen
7. Park factor — hardcoded for 29 venues in VENUES dict
8. Weather — Open-Meteo API for outdoor venues: +0.15%/°F above 72°F, +0.5%/mph wind above 5mph
9. Projected PA — by lineup spot (1=4.7 down to 9=3.8) adjusted for game total

Game probability formula: `1 - (1 - per_PA_rate) ^ projected_PA`

## Edge calculation
- Edge = model probability minus sportsbook implied probability (vig included)
- Bet = edge > +5pp
- Lean = edge +2–5pp
- Skip = edge < -4pp

## Data sources
- MLB Stats API — statsapi.mlb.com (free, no key)
- Baseball Savant — via pybaseball statcast_batter_exitvelo_barrels() (free)
- Open-Meteo — api.open-meteo.com (free, no key)
- The Odds API — the-odds-api.com (paid plan required for batter_home_runs market)

## Environment variables / GitHub Secrets
```
ODDS_API_KEY        The Odds API key (the-odds-api.com, paid plan)
GMAIL_ADDRESS       Gmail address used to send notifications
GMAIL_APP_PASSWORD  Gmail App Password (16 chars, not regular password)
REPORT_EMAIL        Comma-separated recipient emails
REPORT_PHONE        Comma-separated 10-digit phone numbers
CARRIER             Comma-separated carriers matching phone order (att/verizon/tmobile/sprint/boost/cricket)
PAGES_URL           GitHub Pages URL for SMS link (https://mattharding23.github.io/mlb-hr-model/)
```

## Automation
- GitHub Actions runs daily.yml at 15:00 UTC (11am ET summer)
- To change run time: edit the cron line in .github/workflows/daily.yml
- Manual trigger: GitHub repo → Actions → Daily MLB HR Model → Run workflow
- No games today = script exits cleanly with code 0, no report generated

## Known limitations / next steps
- Wind direction relative to stadium orientation not modeled (only wind speed)
- Bullpen fatigue / usage not tracked
- Injury status not checked (uses confirmed lineups where available, otherwise roster)
- Barrel% requires pybaseball which has occasional Baseball Savant CORS/rate issues
- Platoon depth for specific relievers not modeled

## Common tasks
- "Run the model for today" → python mlb_hr_model.py -k $ODDS_API_KEY --open
- "Add a new factor to the model" → edit run_model() in mlb_hr_model.py
- "Change the run time" → edit cron in .github/workflows/daily.yml
- "Add another email recipient" → update REPORT_EMAIL secret in GitHub (comma-separated)
- "The Statcast data isn't loading" → check pybaseball version, Baseball Savant may be rate limiting
- "Debug a specific player's output" → add print(r) after run_model() call for that player
