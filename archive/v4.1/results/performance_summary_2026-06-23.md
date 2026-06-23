# MLB HR Model — Performance Analysis
**Scope:** Post-commit 766b013 | Jun 12 – Jun 23, 2026 | Generated 2026-06-23

---

## 1. Headline Numbers

### Pick volume

| Tier | Count | Resolved | Unresolved |
|------|------:|--------:|-----------:|
| **Bet** (edge > +5pp) | 446 | 445 | 1 |
| **Lean** (edge +2–5pp) | 166 | 164 | 2 |
| **—** (edge −4 to +2pp, borderline) | 506 | 502 | 4 |
| **Skip** (edge < −4pp, or no odds) | 1,431 | 1,430 | 1 |
| **Total** | **2,549** | **2,541** | **8** |

- **Date range:** Jun 12 – Jun 23 (12 game-days); 8 unresolved picks are from Jun 23 (today, not yet scored)
- **Note on '—' tier:** 506 picks with edge 0–4pp above zero (or 0–4pp negative) that didn't clear the Lean threshold. `units_staked` is null for these — no units were committed.

### Win/loss & ROI (Bet and Lean only)

| Tier | W | L | Win% | Units Staked | Net Units | ROI |
|------|--:|--:|-----:|-------------:|----------:|----:|
| Bet | 64 | 381 | 14.4% | 10.08 | −1.04 | **−10.3%** |
| Lean | 19 | 145 | 11.6% | 1.07 | −0.12 | **−10.9%** |
| **Combined** | **83** | **526** | **13.6%** | **11.15** | **−1.16** | **−10.4%** |

**Interpretation:** Negative ROI across both tiers, and near-identical loss rate (−10.3% vs −10.9%). The Lean tier isn't behaving differently from Bet — both are losing at the same rate, which is the first indicator that edge calculation isn't finding real value.

### Odds match rate by day

| Date | Picks | With Odds | Match Rate | Flag |
|------|------:|----------:|----------:|------|
| 2026-06-12 | 243 | 169 | 69.5% | ⚠ BELOW 80% |
| 2026-06-13 | 259 | 130 | 50.2% | ⚠ BELOW 80% |
| 2026-06-14 | 285 | 235 | 82.5% | ✓ |
| 2026-06-15 | 170 | 66 | 38.8% | ⚠ BELOW 80% |
| 2026-06-16 | 230 | 134 | 58.3% | ⚠ BELOW 80% |
| 2026-06-17 | 260 | 159 | 61.2% | ⚠ BELOW 80% |
| 2026-06-18 | 139 | 114 | 82.0% | ✓ |
| 2026-06-19 | 227 | 104 | 45.8% | ⚠ BELOW 80% |
| 2026-06-20 | 241 | 134 | 55.6% | ⚠ BELOW 80% |
| 2026-06-21 | 279 | 190 | 68.1% | ⚠ BELOW 80% |
| 2026-06-22 | 208 | 136 | 65.4% | ⚠ BELOW 80% |
| 2026-06-23 | 8 | 8 | 100.0% | ✓ |

**10 of 12 days are below the 80% threshold.** Average match rate across the period: ~63%. This means roughly 37% of all players in the model universe are getting no odds from The Odds API, forcing them to Skip regardless of their model probability. Two explanations: (a) The Odds API coverage gaps for batter_home_runs market on those books, or (b) many qualifying players just aren't offered as props on any tracked sportsbook that day. Either way, the actionable universe each day is smaller than the model's raw output suggests.

---

## 2. Calibration

**Total resolved picks used:** 2,541 | **Overall actual HR rate:** 12.8%

| Bin | N | Avg Predicted | Actual HR Rate | Δ (Pred − Actual) | Small Sample? |
|-----|--:|-------------:|---------------:|------------------:|:-------------:|
| 0–5% | 500 | 2.3% | **7.4%** | −5.1pp | No |
| 5–10% | 517 | 7.4% | **10.8%** | −3.4pp | No |
| 10–15% | 443 | 12.4% | **10.6%** | +1.8pp | No |
| 15–20% | 391 | 17.5% | **14.8%** | +2.7pp | No |
| 20%+ | 690 | 26.7% | **18.4%** | **+8.3pp** | No |

### Brier score

| Metric | Value |
|--------|------:|
| Model Brier score | 0.11228 |
| Baseline Brier (predict mean rate for everyone) | 0.11154 |
| **Brier Skill Score** | **−0.007** |

**Critical finding:** Brier Skill Score of −0.007 means the model is essentially no better than predicting the same 12.8% HR rate for every player. Slightly *worse* than the naive baseline. The model adds no calibration value in aggregate.

### What the bins show

Two clear problems:

1. **Severe overconfidence at 20%+.** The model assigns 26.7% average probability to its highest bin, but those players actually hit HRs at 18.4%. This is an 8.3pp systematic overestimate — the most consequential finding given that nearly all Bet/Lean picks fall in this bin. The tightened caps from 766b013 helped but didn't go far enough.

2. **Underconfidence at 0–5%.** Players assigned <5% model probability are actually hitting HRs at 7.4% — 3× the predicted rate. This is less actionable (we're not betting these) but suggests the low end is also miscalibrated.

3. **10–20% range is roughly OK** (actual rates within 3pp of predicted). The model is most reliable in the middle of its range.

---

## 3. Edge-Magnitude Granularity

*(Only picks with non-null odds/edge, N=1,571 resolved)*

| Edge Bucket | N | Hits | Hit Rate | Net Units | Flag |
|-------------|--:|-----:|---------:|----------:|------|
| −20 to −8pp | 140 | 12 | 8.6% | 0 (no stake) | |
| −8 to −6pp | 129 | 19 | 14.7% | 0 | |
| −6 to −4pp | 191 | 27 | 14.1% | 0 | |
| −4 to −2pp | 173 | 23 | 13.3% | 0 | |
| −2 to 0pp | 153 | 13 | 8.5% | 0 | |
| 0 to +2pp | 175 | 24 | 13.7% | 0 | |
| +2 to +4pp | 112 | 12 | 10.7% | −0.15 | |
| +4 to +6pp | 118 | 19 | **16.1%** | **+0.14** | |
| +6 to +8pp | 116 | 18 | 15.5% | +0.02 | |
| +8 to +10pp | 79 | 13 | 16.5% | +0.03 | |
| +10 to +15pp | 141 | 18 | 12.8% | **−0.75** | ⚠ |
| +15pp+ | 44 | 4 | **9.1%** | **−0.44** | ⚠ |

### Monotonicity check: FAILS

Hit rate does **not** increase monotonically with edge. Key pattern:

- **+4pp to +10pp:** Hit rates are consistently 15–17%, and units are roughly breakeven to slightly positive. This is the only positive-looking region.
- **+10–15pp and +15pp+:** Hit rates *collapse* to 12.8% and 9.1% — *worse* than the −8 to −6pp Skip zone. These highest-stated-edge picks are the worst performers and are responsible for the bulk of unit losses (−1.19 combined net units).

**Conclusion:** The model's highest-edge picks are likely artifacts of stale or outlier sportsbook lines being mistaken for real mispricing — not genuine model edge. The +10pp+ zone should be treated as a red flag, not a strong bet signal.

### High-edge outliers (>15pp) — manual review required

44 picks, 4 hits (9.1% — below the overall HR rate of 12.8%). A selection of the most extreme, sorted by edge:

| Date | Player | Team | Model% | Book | Odds | Edge | Result |
|------|--------|------|-------:|------|-----:|-----:|--------|
| Jun 13 | James Wood | WSH | 34.6% | Caesars | +950 | 25.9pp | Miss |
| Jun 14 | Zach Neto | LAA | 29.0% | Caesars | +1500 | 23.2pp | Miss |
| Jun 17 | JJ Bleday | CIN | 34.1% | Caesars | +700 | 22.6pp | Miss |
| Jun 22 | Paul Goldschmidt | NYY | 30.7% | Caesars | +950 | 21.9pp | Miss |
| Jun 17 | Mark Vientos | NYM | 31.4% | Caesars | +750 | 20.5pp | Miss |
| Jun 14 | Jackson Chourio | MIL | 31.1% | Caesars | +700 | 19.6pp | **Hit** |

**Patterns worth investigating:**

- **Caesars is the source book for virtually all >15pp edge picks.** When Caesars posts a longshot line (e.g., +950, +1500) for a player the model rates at 30%+, it creates massive apparent edge. But if every other book has that player at +300 to +450, the real market edge is zero or negative. Recommendation: before treating a pick as valid, require ≥2 books to have odds within 200% of the best line.

- **Rodolfo Durán (SD, batting order 9)** appears 4 times in the >15pp list across Jun 15, 16, 17, 21 with identical 27.2%+ model probability. A backup catcher hitting 9th should not be a consistent 30% HR probability candidate — this looks like stale Statcast data (possibly a previous team's barrels being mis-attributed) or the model compounding favorable factors incorrectly for his profile.

- **Jun 17 CIN cluster:** 5 CIN players appear in the >15pp list on the same date (Bleday, Lowe, Marte, Ruiz, Stewart/Sal Stewart). This suggests either a park factor or SP factor is being applied in a way that inflates the whole CIN lineup simultaneously. Worth checking what the model assigned as the opposing SP/bullpen adjustment for that game.

---

## 4. Per-Factor Diagnostics

**⚠ Full per-factor analysis is not possible from picks.json.** The file does not store individual factor values (barrel_pct, split_factor, hot_factor, sp_adj, bullpen_adj, park_factor, weather_factor). Only proxy signals from the stored fields are available.

### Available proxy comparison (Bet/Lean hits vs. misses)

| Metric | Hits (n=83) | Misses (n=526) | Δ | Actionable? |
|--------|:-----------:|:--------------:|:--:|:-----------:|
| Avg model probability | 25.4% | 23.4% | +2.0pp | Marginal |
| Avg edge | 8.0pp | 8.1pp | −0.1pp | No — edge is not discriminating |
| Avg batting order | 3.47 | 4.23 | −0.76 | Moderate signal |
| Lineup confirmed | 100% | 100% | 0 | N/A |

**Key finding:** Edge at the time of pick is essentially identical between hits and misses (+8.0pp vs +8.1pp). Among picks that cleared the Bet/Lean threshold, edge offers no additional discrimination — once you're in the "bet" zone, higher edge is not better. This is consistent with the edge-bucket finding above.

**Batting order signal:** Hits cluster meaningfully higher in the lineup (avg pos 3.5 vs 4.2). This is partly a proxy for better hitters, but it may also reflect a projected-PA advantage: lineup spots 1–4 project more PA than 5–9 (4.7 down to ~4.1 PA). If the model is PA-adjusting correctly this should already be captured, but the persistent gap suggests top-of-lineup hitters may have additional upside the model isn't fully capturing.

### To unlock real per-factor diagnostics

Add factor logging to `run_model()` in `mlb_hr_model.py` before the pick is written to picks.json:

```python
"factors": {
    "barrel_pct": barrel_pct,
    "hard_hit_pct": hard_hit_pct,
    "split_factor": split_factor,
    "hot_factor": hot_factor,
    "sp_adj": sp_adj,
    "bullpen_adj": bullpen_adj,
    "park_factor": park_factor,
    "weather_factor": weather_factor,
    "projected_pa": projected_pa,
    "actual_pa": None,  # filled in by check_results.py
}
```

Without this, per-factor calibration is blind.

---

## 5. Run-Window Comparison

**⚠ Not possible.** All 2,549 picks have `window: null`. The `window` field is not being written to picks.json during any of the three daily run windows (11:30am, 5:45pm, 8:45pm ET).

### What's being missed

The core question — does the 5:45pm or 8:45pm run outperform the 11:30am run, presumably because lineups are more confirmed and PA projections are more accurate? — cannot be answered. This is a meaningful blind spot:

- **11:30am run:** Many lineups not yet posted. PA projections may be off if batting order shifts.
- **5:45pm / 8:45pm runs:** Most lineups confirmed (lineup_confirmed flag should be higher). Picks from these windows should have lower PA uncertainty.

### Fix required

In `mlb_hr_model.py`, when writing to picks.json, set `window` to the current window identifier (`"early"`, `"mid"`, or `"late"`), likely derived from the current UTC time or an env var set by the GitHub Actions schedule.

---

## 6. Caveats

| Metric | Value | Status |
|--------|------:|--------|
| Resolved Bet/Lean picks | 609 | Sufficient for headline ROI (not preliminary) |
| Resolved Bet picks | 445 | Large enough for tier analysis |
| Resolved Lean picks | 164 | Sufficient, but per-bucket splits are thin |
| Edge buckets (per 2pp) | 44–191 per bucket | Most buckets ≥40 — reasonable |
| Per-factor diagnostics | N/A | **Not possible — factor data not logged** |
| Per-window diagnostics | N/A | **Not possible — window field not set** |

**Sample size verdict:** 609 resolved Bet/Lean picks across 12 game-days is enough to draw headline conclusions with moderate confidence. The −10.4% ROI is a real signal, not noise. Individual edge buckets are reasonable in size. However:

- Any edge bucket with <30 picks should be treated as preliminary
- The per-book analysis (Caesars vs BetOnline) has not been done and could be informative given the high-edge pattern above
- 12 game-days is too short to claim a seasonal baseline; the model's performance vs. the full 2026 season needs to be assessed as more data accumulates

**Systemic data-quality issues:**
1. Odds match rate averaging ~63% means the model is blind to nearly 40% of qualified players on a given day. Days with <50% match rates (Jun 13, Jun 15, Jun 19) are especially suspect.
2. Window field is null throughout — all three daily runs look identical, removing a key diagnostic variable.
3. Factor values not stored — no way to debug why individual picks succeeded or failed without re-running the model with debug output.

---

## Priority Refinements

Ranked by impact on both model accuracy and analytical visibility:

1. **Fix overconfidence at 20%+ probs.** The 8.3pp gap between predicted and actual in the top bin is the single largest calibration error. Tighten the final probability cap (currently implied by the 0.92 VIG_FACTOR) or add a Platt scaling step before outputting model_prob.

2. **Multi-book edge validation.** Require ≥2 books within 200% of best_odds before flagging as Bet/Lean. This would eliminate most of the +15pp phantom-edge picks that are Caesars outliers.

3. **Log `window` to picks.json.** One-line fix in mlb_hr_model.py. Unlocks the most valuable ongoing diagnostic.

4. **Log factor values to picks.json.** Required for any meaningful per-factor analysis going forward. Minimal storage overhead at current pick volume.

5. **Investigate Rodolfo Durán / repeated high-edge backup catchers.** Four identical appearances across 4 dates suggests a data pipeline issue (possibly cached Statcast row being reused).

6. **Jun 17 CIN cluster investigation.** 5 CIN players with >15pp edge on the same day points to a model factor (SP or park) being applied uniformly in a way that inflates an entire lineup.
