# MLB HR Model — Version History

A running ledger of model versions, performance, and known issues.
Read top-to-bottom for the full trend. Each entry covers one tracked era.

---

## v4.1 (Jun 12 – Jun 23, 2026)

**Archive:** `archive/v4.1/`  
**Base commit:** `766b013` (Jun 12, 2026) — devig formula + cap tightening + results workflow  
**Picks resolved:** 609 Bet/Lean (445 Bet, 164 Lean) | 2,541 total tracked

### Performance

> **ROI formula correction (2026-06-28):** All figures originally computed with a buggy formula
> (`units_net = sum(units_returned)`) that treated gross win returns as profit, inflating ROI by
> approximately the win rate. Fixed to kelly-weighted net P&L: win profit = gross_return − stake.
> Original (superseded) figures are kept for the record; corrected figures follow each table.

**Original figures (SUPERSEDED — Formula B, buggy):**

| Tier | W | L | Win% | Net Units | ROI |
|------|--:|--:|-----:|----------:|----:|
| Bet  | 64 | 381 | 14.4% | −1.04u | −10.3% |
| Lean | 19 | 145 | 11.6% | −0.12u | −10.9% |
| **Combined** | **83** | **526** | **13.6%** | **−1.16u** | **−10.4%** |

**Corrected figures (Formula C, kelly-weighted net P&L):**

| Tier | W | L | Win% | Net Units | ROI |
|------|--:|--:|-----:|----------:|----:|
| Bet  | 64 | 381 | 14.4% | −2.44u | −24.2% |
| Lean | 19 | 145 | 11.6% | −0.24u | −22.8% |
| **Combined** | **83** | **526** | **13.6%** | **−2.68u** | **−24.0%** |

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

**Original results (SUPERSEDED — Formula B, buggy):**

| | Original v4.1 | After corroboration filter | After both filters |
|---|------:|------:|------:|
| Staked picks | 609 | 162 | **143** |
| Win% | 13.6% | 18.5% | **16.1%** |
| Net units | −1.16u | +1.03u | **+0.27u** |
| ROI | −10.4% | +32.5% | **+10.2%** |

**Corrected results (Formula C, kelly-weighted net P&L):**

> Pick counts use the best-reproducible proxy (exact float model_prob match, ≥2 dates).
> Original session used a slightly different proxy giving 143 picks; this proxy gives 140 picks.
> The 3-pick difference is within the documented proxy uncertainty. ROI direction is unchanged.

| | Original v4.1 | After corroboration filter | After both filters |
|---|------:|------:|------:|
| Staked picks | 609 | 162 | **~140** |
| Win% | 13.6% | 18.5% | **15.7%** |
| Net units | −2.68u | +0.34u | **−0.23u** |
| ROI | −24.0% | +10.6% | **−8.9%** |

**Key sub-findings from counterfactual (corrected):**

1. The corroboration filter alone swings ROI from −24.0% to +10.6% (corrected). The entire v4.1 loss is attributable to Caesars outlier contamination — this finding is unchanged.

2. After filtering, all 162 retained picks are BetOnline. BetOnline lines appear to carry real market consensus.

3. The sp_data_missing proxy removes ~22 Bet-tier picks, reducing ROI from +10.6% to −8.9%. The counterfactual baseline is negative with the correct formula — the prior +10.2% figure was a formula artifact on a slightly different proxy.

4. **Lean tier remains problematic** even on clean BetOnline lines: 40 picks, 5.0% win rate, −72.6% ROI. The +2–5pp edge threshold does not identify genuine value on BetOnline lines. *(Original figure −67.5% also Formula B; corrected −72.6%.)*

5. **+5–10pp Bet bucket is the signal zone**: ~58 picks, 25.9% win rate, +38.2% ROI (corrected from 60 picks / 26.7% / +32.5%). Strong positive signal; this is the primary evidence supporting v4.3's focus on this range.

6. **+15pp+ BetOnline bucket** (7 picks, 0 hits, −100%): even BetOnline occasionally posts outlier lines. Not affected by formula bug (0 wins means gross return = 0 = net return).

**Baseline for v4.2/v4.3 measurement (corrected):**
The v4.1 counterfactual baseline is **~−8.9% ROI on ~140 picks** (corrected from +10.2% / 143 picks). The +5–10pp Bet-zone sub-bucket remains the signal zone at +38.2% ROI (corrected from +32.5%). v4.3 should be compared against the +5–10pp signal zone, not the overall counterfactual baseline which is negative.

---

## v4.2 (Jun 23 – Jun 28, 2026)

**Base commits:** `ffec0af` (archive/reset) through `b71c009` (book dedup upstream)  
**Archive:** `archive/v4.2/`  
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

**Evidence:** Retroactive backtest of v4.1 archive on corroborated BetOnline lines only.

**Original figures (SUPERSEDED — Formula B, buggy):**

| Edge zone | N | Win% | ROI |
|-----------|--:|-----:|----:|
| +2–5pp (old Lean) | 40 | 5.0% | −67.5% |
| +5–10pp (Bet) | 60 | 26.7% | +32.5% |
| +10–15pp (Bet) | 36 | 13.9% | −3.3% |

**Corrected figures (Formula C, kelly-weighted net P&L; applied to ~140-pick proxy group):**

| Edge zone | N | Win% | ROI |
|-----------|--:|-----:|----:|
| +2–5pp (old Lean) | 40 | 5.0% | −72.6% |
| +5–10pp (Bet) | ~58 | 25.9% | +38.2% |
| +10–15pp (Bet) | ~35 | 14.3% | −23.4% |
| +15pp+ (Bet) | 7 | 0.0% | −100% |

*(N counts for +5–10pp and +10–15pp differ from original by 2–3 due to proxy variation; +2–5pp and +15pp+ match exactly. ROI sign and direction of key finding — Lean is bad, +5–10pp is the signal zone — are preserved.)*

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

### Actual v4.2 results (final)

**Period:** Jun 24 – Jun 28, 2026 (5 days, 1,357 picks tracked)

| Metric | Value |
|--------|-------|
| Bet-tier picks | **0** |
| Units staked | **0** |
| ROI | **N/A** (no stakes) |
| Resolved HR rate | 11.1% (128/1,156 resolved) |
| Odds matched | 67.1% (911/1,357), all Caesars |

**Root cause of failure:** The multi-book corroboration filter (`MULTI_BOOK_CORROBORATION_MIN=2`) was never satisfiable. Investigation (via test scripts in Jun 2026) confirmed that `williamhill_us` (Caesars, rebranded 2021 but API key never migrated) is the only sportsbook posting `batter_home_runs` at the current Odds API plan level. DraftKings, FanDuel, and BetMGM are not available for this market at this plan. With only 1 book, corroboration count can never reach 2 → all Bet-tier picks downgraded to "—" → Season Performance permanently frozen.

**Investigation also confirmed:** OddsPapi (evaluated as replacement) has no HR prop coverage for US sportsbooks on their free tier and requires exactly 1 bookmaker per bulk call, making it not viable as a drop-in replacement.

**Conclusion:** v4.2's corroboration gate was structurally sound in concept but unachievable given the API constraint. Replaced in v4.3 with observable single-book gates: odds cap (≤+500) and devigged implied-probability floor (≥10%).

---

## v4.3 (Jun 28, 2026 – present)

**Base commit:** `0d709ed` (Jun 28, 2026)  
**Tracking started:** 2026-06-28 (picks.json reset to [])

### Problem solved

The v4.2 multi-book corroboration filter could never be satisfied because only one sportsbook (`williamhill_us`/Caesars) posts `batter_home_runs` at the current Odds API plan level. Every Bet-tier pick since Jun 23 was downgraded to "—" → 0 stakes across 5 days.

### New gates replacing corroboration

Two hard gates applied after the raw edge threshold, before staking:

1. **Max-odds cap** (`MAX_BET_ODDS = 500`): Bet tier requires American odds ≤ +500. Rationale: v4.1 BetOnline retrospective showed 0 wins on +500–+800 picks (0W/36L, −100% ROI, formula-independent). No model with a single HR/PA regressor has predictive power at extreme odds.

2. **Devigged implied-probability floor** (`MIN_DEVIGGED_IMPLIED = 0.16`): Bet tier requires devigged implied prob ≥ 16% (using `VIG_FACTOR = 0.92`). At exactly +500, devigged implied is ~15.3%, so this gate fires on +500 lines while passing +475 lines (~16.0%). The two gates partition at the +475/+500 boundary: `implied_prob_floor` catches +475–+500; `max_odds` catches +501+. Both gates fire independently on real data.

Both gates set `gate_failed` ("max_odds" or "implied_prob_floor") on the pick and downgrade `rec` from "Bet" to "—". Gated picks are saved to picks.json and shown in a dedicated "Gated — Diagnostic Only" report section. The corroboration block is kept dormant: still computed and stored in `book_corroboration`, but no longer gates picks.

### All changes in v4.3

| # | Change | Rationale |
|---|--------|-----------|
| 1 | Replace corroboration gate with max-odds cap + implied-prob floor | Corroboration permanently unachievable at one-book API plan; observable single-book gates substitute |
| 2 | `gate_failed` field in picks.json | Track which gate blocked each pick for post-window threshold calibration |
| 3 | "Gated — Diagnostic Only" report section | Surface blocked picks for human review without polluting the Bet-tier record |
| 4 | Bug fix: totals URL `caesars` → `williamhill_us` | `caesars` is not a valid Odds API bookmaker key; correct key is `williamhill_us` |
| 5 | Bug fix: `append_to_combined()` window dedup | Each window run was appending a new `<section>`; same-window re-runs now replace via `<!-- window:X -->` comment markers |
| 6 | Bug fix: "Lines from: ." when no book matches | Empty `all_books` list produced malformed footer |
| 7 | Relabel "Value bets" → "Raw edge ≥5pp" + add "Bet tier" metric | Distinguishes pre-gate raw count from post-gate staked count in the Season Performance panel |
| 8 | **ROI formula fix**: `compute_stats()` and `check_results.py` | `units_net` was summing gross win returns (stake included) as profit — inflating all historical ROI figures by ~win_rate. Fixed to kelly-weighted net P&L: win profit = `gross_return − stake`. Convention documented: ROI in this project is kelly-weighted (return on actual capital deployed), not equal-weight. |
| 9 | VERSION_HISTORY historical figures corrected | All v4.1/v4.2 ROI figures annotated with original (superseded-buggy) and corrected values alongside |

### Measurement target for v4.3

**Baseline:** v4.1 counterfactual +5–10pp Bet-zone signal bucket (BetOnline, ~58 picks, 25.9% win rate, **+38.2% ROI** corrected — originally stated +32.5% using buggy Formula B).  
**Primary target:** positive ROI on Bet-tier stakes; match or exceed the +5–10pp signal zone baseline.  
**Minimum sample:** 30 resolved Bet picks before drawing conclusions.

### Watch items for post-observation-window diagnostic

When the first 30+ Bet picks resolve, check the following in addition to headline ROI:

1. **Edge-magnitude monotonicity** *(priority — check first)*: In corrected v4.1 data, ROI is non-monotonic across edge buckets: +5–10pp: **+38.2%**, +10–15pp: **−23.4%**, +15pp+: **−100%** (n=7). If this pattern holds in v4.3 data, the model's edge estimate above +10pp is unreliable and high-edge picks should not receive elevated stakes. Diagnose whether the +10–15pp underperformance clusters by game context, lineup spot, or pitcher-data-missing before attributing it to model calibration vs. small-sample noise.

2. **sp/bp_data_missing rates by window**: Track what fraction of picks have `sp_data_missing=True` or `bp_data_missing=True` per window (early/mid/late). A material drop from early to mid windows confirms the workflow timing is working. Persistent high rates in mid/late windows indicate pitcher announcements are arriving late and the model may need a fallback.

3. **Gated vs. passed pick distribution**: Of raw-edge picks (≥+5pp), track the fraction hitting `max_odds` vs. `implied_prob_floor` vs. passing both gates. If >80% are gated, the threshold pair is too aggressive for current Caesars line distribution. If 0% are gated on any day with odds, verify gates are executing.

4. **BetOnline corroboration rate** *(dormant diagnostic)*: `book_corroboration` is still computed on every pick even though it no longer gates. Track the fraction of Bet-tier picks that would have passed corroboration — this sets a lower bound on what a future multi-book API plan would produce.

### Final v4.3 results (retired 2026-07-22)

**Diagnostic-basis period:** Jun 28 – Jul 18, 2026 (19 dates, 4,877 total picks / 4,806
resolved) — the sample the 2026-07-18 diagnostic was run against and that motivated the
v4.4 redesign decision below.

| Tier | W | L | Win% | Net Units | ROI |
|------|--:|--:|-----:|----------:|----:|
| Bet  | 39 | 141 | 21.7% | −0.35u | −9.1% |

**True final period (v4.3 code stayed live in production a few extra days before the
v4.4 rollout landed):** Jun 28 – Jul 22, 2026 (23 dates, 6,223 total picks / 6,127
resolved).

| Tier | W | L | Win% | Net Units | ROI |
|------|--:|--:|-----:|----------:|----:|
| Bet  | 42 | 176 | 19.3% | −0.80u | **−17.2%** |

The four extra live days (Jul 19–22) were a losing stretch (streak −4 at close) that pulled
final ROI down from −9.1% to −17.2% — consistent with, not contradicting, the retirement
rationale. Staking is quarter-Kelly (capped 0.03u/pick), not flat; both the diagnostic-basis
and true-final figures were computed with `compute_stats()` from the archived v4.3 code
against the corresponding `picks.json` snapshot.

**Reason for retirement:** A logistic recalibration fit on all 4,806 resolved tracked
picks as of Jul 18 (`outcome ~ logit(model_prob)`) produced a slope of **0.40 (SE 0.05)**,
significantly below 1 — confirming the model is overdispersed (its probability spread is
roughly 2.5x too wide relative to what outcomes support). Root-cause analysis traced this
to **factor-stacking in probability space**: overprediction was cleanly monotonic with both
the reconstructed total per-PA multiplier and the count of simultaneously-positive
adjustment factors (0 positive factors: +4.9pp underprediction; 7 positive factors:
−10.0pp overprediction, n=97). The Statcast +35% cap alone accounted for picks 6.75x more
overpredicted than uncapped picks. Additionally, edge-magnitude was non-monotonic for a
third consecutive model version (best ROI at 5–7.5pp raw edge, worst at 10–15pp),
and the `implied_prob_floor` gate looked weak relative to `max_odds` (breakeven at n=30,
all at exactly +500 odds) — both addressed in v4.4.

**Diagnostic reference:** `archive/diagnostics/v4.3_diagnostic_2026-07-18.md` (figures in
that report reflect the Jul 18 sample, not the true-final Jul 22 closeout above)

**Archive:** `archive/v4.3/mlb_hr_model_v4.3.py`, `archive/v4.3/picks_v4.3.json` (true-final
snapshot through 2026-07-22)

---

## v4.4 (Jul 22, 2026 – present)

**Launch date:** 2026-07-22 (spec drafted 2026-07-18; v4.3 stayed live in production for
four extra days while these changes were finalized — see the true-final v4.3 figures above)
**Base:** `archive/v4.3/mlb_hr_model_v4.3.py`
**Tracking started:** 2026-07-22 (`picks.json` reset to `[]`)

### Problem solved

The v4.3 diagnostic (2026-07-18) found the model overdispersed (logistic recalibration
slope 0.40, SE 0.05) and traced the root cause to multiplicative probability-space factor
compounding: simultaneous positive adjustment factors stacked geometrically, producing
overprediction that grew monotonically with both total multiplier and count of positive
factors (0 positive: +4.9pp underprediction; 7 positive: −10.0pp overprediction). The
Statcast +35% cap and the (structurally weak) `implied_prob_floor` gate were identified as
specific contributors.

### All changes in v4.4

| # | Change | Rationale |
|---|--------|-----------|
| 1 | Additive log-odds factor compounding (replaces multiplicative probability-space compounding) | Log-odds addition dampens simultaneous-factor stacking non-linearly instead of compounding geometrically; root-cause fix for the overprediction pattern found in the v4.3 diagnostic |
| 2 | Statcast cap reduced +35% → +15% log-odds equivalent (`sc_adj` upper bound 1.35 → 1.15) | Statcast-capped picks were 6.75x more overpredicted than uncapped picks (−5.4pp vs. −0.8pp) in the v4.3 diagnostic |
| 3 | Recalibration layer added (`RECAL_A`/`RECAL_B` constants, pass-through at launch: `RECAL_A=0.0`, `RECAL_B=1.0`) | Named constants make it easy to re-fit a logistic recalibration on live v4.4 data after ~50 resolved picks, without touching factor logic |
| 4 | `MIN_DEVIGGED_IMPLIED` gate removed (`implied_prob_floor`); `MAX_BET_ODDS` (≤+500) kept | v4.3 diagnostic found the floor gate breakeven (n=30, all at exactly +500 odds) while `max_odds` carried essentially all of the gates' protective value |
| 5 | Dashboard footer: implied-floor mention removed, footer now describes only the surviving `max_odds` gate; model description bumped to "v4.4" with "log-odds factor compounding" noted | Footer previously stated the wrong threshold (≥10% vs. actual 16%) for a gate that no longer exists |
| 6 | Version strings bumped v4.3 → v4.4 throughout output/headers/dashboard | Historical comments describing when past features/gates were introduced were left as `v4.3`/`v4.2` for accuracy |
| 7 | `picks.json` reset to `[]`; `results/reset_date.txt` set to 2026-07-22 | Fresh tracking window for the restructured model |

**Not changed:** `check_results.py`, `.github/workflows/`, the 55/45 SP/bullpen blend weight,
the 0.08 per-PA hard cap, `MAX_BET_ODDS`, any other factor input/weight/threshold not
listed above, and the dormant multi-book corroboration logic.

### Benchmark

**v4.3 final (retired):** 42-176, Net −0.80u, ROI **−17.2%** (218 resolved Bet-tier picks,
Jun 28 – Jul 22, quarter-Kelly variable staking). This is the true closeout figure — v4.3
stayed live in production through Jul 22 while the v4.4 code changes here were finalized;
the diagnostic that motivated the redesign was run against an earlier, less-negative
Jul 18 sample (−9.1%, see the v4.3 entry above). v4.4 is measured against the −17.2% true
final baseline.

### Sanity check (2026-07-22, pre-commit)

Synthetic test per the implementation spec: `baseline_prob=0.10`, 7 simultaneous positive
factors each `+25%` (ratio 1.25) — an isolated test of the combination formula itself
(pre-per-PA-cap), since the new per-factor caps (e.g. Statcast now capped at 1.15) make it
impossible to construct this exact scenario through a live `run_model()` call. Old
multiplicative architecture: `0.10 × 1.25^7 = 0.4768` (~0.48, in the ballpark of the spec's
"~0.56" estimate). New additive log-odds architecture: `sigmoid(logit(0.10) + 7·ln(1.25))
= 0.3463`. **PASS: 0.3463 < 0.35**, though narrowly — this is a meaningfully smaller
reduction (0.4768 → 0.3463, ~27% relative) than the old-vs-new gap looks at first glance
once the shared 0.08 per-PA hard cap is applied downstream (both architectures clip to
0.08 in this specific scenario; the pre-cap comparison is the one that reflects the actual
change in Step 2). A full `run_model()` dry run with synthetic batter/season/pitcher/
weather/odds data (no network calls) also executed without error and produced a sane
result (game_prob=31.6%, edge=+11.1%, recommendation=Bet, `sc_adj` correctly enforced at
its new 1.15 cap).

---
