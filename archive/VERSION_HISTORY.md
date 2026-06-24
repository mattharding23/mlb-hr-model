# MLB HR Model — Version History

A running ledger of model versions, performance, and known issues.
Read top-to-bottom for the full trend. Each entry covers one tracked era.

---

## v4.1 (Jun 12 – Jun 23, 2026)

**Archive:** `archive/v4.1/`  
**Base commit:** `766b013` (Jun 12, 2026) — devig formula + cap tightening + results workflow  
**Picks resolved:** 609 Bet/Lean (445 Bet, 164 Lean) | 2,541 total tracked

### Performance

| Tier | W | L | Win% | Net Units | ROI |
|------|--:|--:|-----:|----------:|----:|
| Bet  | 64 | 381 | 14.4% | −1.04u | −10.3% |
| Lean | 19 | 145 | 11.6% | −0.12u | −10.9% |
| **Combined** | **83** | **526** | **13.6%** | **−1.16u** | **−10.4%** |

### Calibration

- Brier Score: **0.11228** vs baseline 0.11154 → Skill Score **−0.007** (essentially no calibration advantage)
- 20%+ probability bin: predicted avg 26.7%, actual HR rate 18.4% → **+8.3pp systematic overestimate**
- 0–5% bin: predicted 2.3%, actual 7.4% → **−5.1pp underestimate** (less consequential)
- Bins 10–20% are roughly calibrated (within ±3pp)

### Known issues carried into v4.2

1. **Caesars outlier contamination** — Single-book Caesars lines created phantom +15–26pp edge; +10pp+ picks performed worse than Skip-tier picks. Fixed in v4.2 by multi-book corroboration filter.
2. **Window field null throughout** — All picks saved with window=None due to missing `--window` arg in workflow. Fixed in v4.2 by auto-detecting window from UTC time.
3. **Low odds match rate** (~63% average, 10/12 days below 80%) — Corollary of #2: 11:30am run fires before books post props. Fixed in v4.2 by proper window tracking.
4. **Factor values not logged** — No per-pick factor breakdown; per-factor calibration analysis not possible. Fixed in v4.2 by adding `factors` dict to each pick record.
5. **per_pa cap saturation** — Hard cap at 0.08 causes identical probs across dates for top-end players (confirmed: Rodolfo Durán, player_id 660710). Not a caching bug — model saturation. Flagged in v4.2 via `per_pa_capped` field.
6. **Silent SP/BP data defaults** — When no probable pitcher announced (common at 11:30am ET), `sp_adj = bp_adj = 1.0` with no flag. Model proceeded to Bet/Lean with no pitcher information. Fixed in v4.2: `sp_data_missing`/`bp_data_missing` flags added; missing-pitcher picks downgraded to "—".
7. **Alternate totals parsed as game total** — The odds API `totals` market sometimes includes alternate lines (e.g. 12.5) before the standard game total. Code took the first "Over" outcome, inflating proj_PA for all batters in that game. Confirmed on Jun 17 CIN cluster. Fixed in v4.2: take minimum qualifying Over (≥7.0) across all outcomes.
8. **Doubleheader ROI dedup bug** — `apply_roi_dedup` grouped by `(date, player_id)`, so both games of a doubleheader were lumped together and one game's pick was dropped from ROI tracking. Fixed in v4.2: group by `(date, player_id, game_pk)`.

### v4.1 Counterfactual: what v4.2 filters would have produced

Retroactive re-scoring of v4.1 archive by applying two v4.2 filters without re-running the live model. **These are proxies, not exact figures** — exact numbers require re-running against archived odds API responses that don't exist.

**Methodology:**
- Multi-book corroboration proxy: picks where `best_book == "Caesars"` treated as corroboration-failed (downgraded to "—"). Historical data shows Caesars was the sole outlier book on virtually all high-edge picks. May slightly overcount exclusions.
- `sp_data_missing` proxy: picks where the same player had the same `model_prob` on ≥2 dates, fingerprinting `pitch_blend = 1.0` (league-average SP default). Lower-bound proxy — true count is higher because weather/hotness variation masks some occurrences.

**Results:**

| | Original v4.1 | After corroboration filter | After both filters |
|---|------:|------:|------:|
| Staked picks | 609 | 162 | **143** |
| Win% | 13.6% | 18.5% | **16.1%** |
| Net units | −1.16u | +1.03u | **+0.27u** |
| ROI | −10.4% | +32.5% | **+10.2%** |

**Key sub-findings from counterfactual:**

1. The corroboration filter alone (removing 447 Caesars-best-book picks, 73% of all staked picks) swings ROI from −10.4% to +32.5%. The entire v4.1 loss is attributable to Caesars outlier contamination.

2. After filtering, all 162 retained picks are BetOnline. BetOnline lines appear to carry real market consensus.

3. The sp_data_missing proxy removes an additional 19 Bet-tier picks (all from the Bet tier; Lean is unaffected), reducing ROI to +10.2%. This is a lower-bound estimate of the pitcher-data impact.

4. **Lean tier remains problematic** even on clean BetOnline lines: 40 picks, 5.0% win rate (vs 12.8% base rate), −67.5% ROI (−0.17u). The +2–5pp edge threshold does not identify genuine value on BetOnline lines. v4.2 should consider raising the Lean threshold or eliminating the tier.

5. **+5–10pp Bet bucket is the signal zone**: 60 picks, 26.7% win rate, +0.77u. The sweet spot for genuine edge is 5–10pp above BetOnline implied.

6. **+15pp+ BetOnline bucket** (7 picks, 0 hits, −0.21u): even BetOnline occasionally posts outlier lines. The v4.2 multi-book corroboration filter (requiring ≥2 books, not just "not Caesars") would also catch these.

**Baseline for v4.2 measurement:**
v4.2 performance should be compared against the counterfactual set (143 picks, +10.2% ROI, 16.1% win rate) rather than the original v4.1 baseline, since the filters were not active during the v4.1 era and the v4.1 numbers reflect contaminated picks.

---

## v4.2 (Jun 23, 2026 – present)

**Base commits:** `ffec0af` (archive/reset) through `bcdf9ab` (doubleheader dedup)  
**Tracking started:** 2026-06-23 (picks.json reset to [])

### Changes from v4.1

| # | Change | Commit | Rationale |
|---|--------|--------|-----------|
| 1 | Multi-book corroboration filter | `88fa471` | Caesars outlier contamination caused 73% of staked picks and all unit losses in v4.1 |
| 2 | Window auto-detect (`early`/`mid`/`late`) | `74c3f0e` | Fixed window=null dedup bug; now each daily run saves picks independently |
| 3 | Factor logging to picks.json | `74c3f0e` | Enables per-factor calibration; adds `barrel_pct`, `hard_hit_pct`, all adj fields, `actual_pa` |
| 4 | Totals-parse bug fix (min qualifying Over ≥7.0) | `0436fca` | Alternate totals (e.g. 12.5) were parsed as game total, inflating proj_PA |
| 5 | `counts_toward_roi` window dedup | `0436fca` | Prevents triple-counting the same logical bet across 3 daily windows |
| 6 | `game_ou` in factors dict | `0436fca` | Game total now auditable per pick |
| 7 | `sp_data_missing` / `bp_data_missing` flags | `65bdca9` | Missing probable-pitcher data was silently defaulting to league-average |
| 8 | Missing-pitcher picks downgraded from Bet to "—" | `65bdca9` | Model cannot justify high-confidence picks without pitcher info |
| 9 | `game_pk` in picks schema + dedup key | `bcdf9ab` | Fixes doubleheader ROI tracking (both games now count independently) |
| 10 | **Lean tier eliminated** | `(this commit)` | See below |

### Lean tier elimination

**Evidence:** Retroactive backtest of v4.1 archive on corroborated BetOnline lines only:

| Edge zone | N | Win% | ROI |
|-----------|--:|-----:|----:|
| +2–5pp (old Lean) | 40 | 5.0% | −67.5% |
| +5–10pp (Bet) | 60 | 26.7% | +32.5% |
| +10–15pp (Bet) | 36 | 13.9% | −3.3% |

The +2–5pp zone shows win rate below the 12.8% unconditional HR base rate, meaning taking these bets destroys value. There is no evidence the model identifies real edge at this threshold.

**Decision:** Eliminate Lean as a tier. Going forward, two tiers only:
- **Bet** — edge ≥ +5pp, corroborated, pitcher data present → stake quarter-Kelly (capped 0.03u)
- **Skip** — edge < −4pp → model sees clear negative value
- **"—"** — everything else, including the former +2–5pp Lean zone → no stake, no signal

The +2–5pp zone will remain visible in the report table (players in that range still appear with their model probability and edge) but will not generate a Bet badge or stake units. If future data accumulates evidence of genuine value at a different intermediate threshold, a tier can be reintroduced.

**Code changes:**
- `rec` formula: `"Lean" if edge > 0.02` branch removed
- `pitcher_data_missing` and multi-book downgrade checks: `rec in ("Bet","Lean")` → `rec == "Bet"`
- `units_staked`: only set for `rec == "Bet"` (was `rec in ("Bet","Lean")`)
- HTML performance panel: "Lean record" row removed
- Odds note footer: "Lean +2–5pp ·" removed
- Edge color in report table: intermediate green (#86efac) for >+2pp edge removed; now binary green/gray/red at the ±4pp boundaries
- SMS text: Lean W-L removed
- Console edge distribution: "Lean value" line replaced with "Borderline (0–+5pp)"
- `compute_stats()`: lean_w/lean_l retained in stats dict for backward compat with any legacy v4.1 display

### Measurement target for v4.2

Primary: beat the v4.1 counterfactual baseline — 16.1% win rate, +10.2% ROI on 143-pick proxy sample.  
Secondary: demonstrate Lean-zone picks (now excluded) continue to underperform, validating the decision.  
Minimum sample for conclusions: 50 resolved Bet picks.

---
