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

### Final v4.4 results (retired 2026-08-02)

**9-87, Net −1.17u, ROI −54.88%** (96 resolved Bet-tier picks, latest-window dedup,
2026-07-22 – 2026-08-01, quarter-Kelly variable staking). Confirmed by direct recompute
from raw `picks.json` — see `archive/diagnostics/v4.4_diagnostic_2026-08-02.md`. This is
the benchmark v4.5 needs to beat.

**Archive:** `archive/v4.4/mlb_hr_model_v4.4.py`, `archive/v4.4/check_results_v4.4.py`,
`archive/v4.4/picks_v4.4.json` (final picks.json, 3,737 total / 3,267 resolved picks).

---

## v4.5 (Aug 2, 2026 – present)

**Launch date:** 2026-08-02
**Base:** `archive/v4.4/mlb_hr_model_v4.4.py`
**Tracking started:** 2026-08-02 (`picks.json` reset to `[]`)

### Problem solved

`archive/diagnostics/v4.4_diagnostic_2026-08-02.md` §4 and §7 found `hot_adj` (L14
hotness) and `sc_adj` (Statcast) were the dominant log-odds contributors behind both the
general overprediction pattern (§2: every 2.5pp calibration band from 15% predicted
probability up was overpredicted, worsening to −15 to −16pp around 27.5–32.5%) and the
concrete 2026-08-01 loss cluster that produced the v4.4 season's 10-game losing streak
(§6: `hot_adj` or `sc_adj` was the top log-odds contributor on 9 of the 10 losses that day).
Root cause (§7): `hot_adj`'s regression weight (`min(r_pa/45, 0.45)`) hard-capped at its
0.45 ceiling for any L14 sample of `r_pa ≥ ~20.25` (about 5 games) — a 5-game hot streak
got the same maximum trust as a full 14-day, ~55-PA window, with no further shrinkage
past that point. `sc_adj` had no sample-size-based shrinkage at all — barrel%/hard-hit%
fed the exponents at full strength regardless of how many batted-ball events the season
rate was built on; the fixed exponents (0.40/0.20) and the v4.4 cap reduction were the
only dampening.

### All changes in v4.5

| # | Change | Rationale |
|---|--------|-----------|
| 1 | Logging: `factors` now also records `r_pa`, `r_hr`, `season_rate` (backing `hot_adj`), `s_pa`, `s_hr` (backing `split_adj`), and `sc_bbe` (batted-ball-event count backing `sc_adj`, from Baseball Savant's `attempts` column, previously fetched but not persisted) | Diagnostic §4 could not check whether small-sample L14 windows were driving overprediction because the raw PA counts weren't stored anywhere — only the derived `hot_adj`/`split_adj` ratios were. This is additive-only: verified as a byte-identical no-op on every existing computed field (`model_prob`, `hot_adj`, `sc_adj`, `split_adj`, and all other `*_adj` values) via a direct `run_model()` diff across four synthetic scenarios before/after the change |
| 2 | `hot_adj` shrinkage: replaced the hard-capped linear weight `min(r_pa/45, 0.45)` with continuous empirical-Bayes shrinkage `w = r_pa / (r_pa + HOT_SHRINKAGE_K)`, `HOT_SHRINKAGE_K = 40` | Root-cause fix for the §7 finding above. At `k=40`: a 5-game window (`r_pa≈20`) now gets *less* trust than before (w=0.333 vs. the old flat 0.444–0.45), while a full 14-day window (`r_pa≈55`) gets *more* trust than the old ceiling ever allowed (w=0.579 vs. 0.45) — the weight now separates sample sizes instead of capping them together, and never fully saturates. `k` values from 35–50 were compared (see table below); 40 was chosen as the round middle value giving the clearest small-vs-large-sample separation without being aggressive at either end. The final 0.78/1.28 clip on `hot_adj` is unchanged |
| 3 | `sc_adj` shrinkage: barrel%/hard-hit% are now shrunk toward league average (`LG_BARREL`/`LG_HARD_HIT`) before the 0.40/0.20 exponents are applied, weighted by BBE count via the same form: `w = n / (n + SC_SHRINKAGE_K)`, `SC_SHRINKAGE_K = 100` | `sc_adj` had zero sample-size-based shrinkage previously. At `k'=100`: a player at the pipeline's minimum eligible sample (50 BBE — `statcast_batter_exitvelo_barrels(year, minBBE=50)` already filters out anyone below this) gets only 33% trust in their raw rate; a ~200-BBE half-season sample gets 67%; a 350+-BBE full-time regular gets 78%+. `k'` values from 50–200 were compared (see table below); 100 was chosen to give meaningful correction at the low-BBE end (just above the 50-BBE floor) without over-shrinking full-season regulars. The final 0.78/1.15 clip on `sc_adj` is unchanged |
| 4 | Version bump to v4.5 in docstring, argparse description, console banner, and dashboard footer/labels; module docstring's factor list updated to describe empirical-Bayes shrinkage instead of the retired fixed-weight caps | Historical comments describing when past features/gates were introduced (e.g. "v4.4 recalibration layer", "v4.3 hard gate") were left with their original version numbers for accuracy, per the same convention used in the v4.3→v4.4 transition |
| 5 | `picks.json` reset to `[]`; `results/reset_date.txt` set to 2026-08-02 | Fresh tracking window for the shrinkage-corrected model |

**Not changed:** `MAX_BET_ODDS` (still 500) and all gate logic, `check_results.py`, the
55/45 SP/bullpen blend weight, the 0.08 per-PA hard cap, the log-odds compounding
architecture, `RECAL_A`/`RECAL_B` (still pass-through), the corroboration logic, and any
other factor input/weight/threshold not listed above. In particular, the diagnostic's §5
finding — that the `max_odds` gate excluded picks (n=77) with a hypothetical +19.1% ROI
while the picks that passed the gate lost −54.9% — is **being tracked, not acted on**.
That finding was based on a small early sample (9 wins) and needs a larger resolved
population before the gate itself is a defensible thing to change; v4.5 does not touch it.

### `HOT_SHRINKAGE_K` candidate comparison (w = r_pa / (r_pa + k))

| r_pa | k=35 | k=40 (chosen) | k=45 | k=50 | old capped formula |
|---:|---:|---:|---:|---:|---:|
| 10 | 0.222 | 0.200 | 0.182 | 0.167 | 0.222 |
| 20 | 0.364 | 0.333 | 0.308 | 0.286 | 0.444 |
| 35 | 0.500 | 0.467 | 0.438 | 0.412 | 0.450 |
| 55 | 0.611 | 0.579 | 0.550 | 0.524 | 0.450 |
| 90 | 0.720 | 0.692 | 0.667 | 0.643 | 0.450 |

### `SC_SHRINKAGE_K` candidate comparison (w = n / (n + k), n = BBE)

| n (BBE) | k=50 | k=75 | k=100 (chosen) | k=150 | k=200 |
|---:|---:|---:|---:|---:|---:|
| 50 | 0.500 | 0.400 | 0.333 | 0.250 | 0.200 |
| 100 | 0.667 | 0.571 | 0.500 | 0.400 | 0.333 |
| 200 | 0.800 | 0.727 | 0.667 | 0.571 | 0.500 |
| 350 | 0.875 | 0.824 | 0.778 | 0.700 | 0.636 |
| 500 | 0.909 | 0.870 | 0.833 | 0.769 | 0.714 |

### Benchmark

**v4.4 final (retired):** 9-87, Net −1.17u, ROI **−54.88%** (96 resolved Bet-tier picks,
2026-07-22 – 2026-08-01, quarter-Kelly variable staking). v4.5 is measured against this
figure. See `archive/diagnostics/v4.4_diagnostic_2026-08-02.md` for the full diagnostic
this release is based on.

### Pre-launch fix: duplicate-splits r_pa/s_pa inflation (2026-08-02, same day)

The Step 2 logging addition above (persisting `r_pa`/`r_hr`/`s_pa`/`s_hr`) surfaced a
pre-existing MLB Stats API aggregation bug during the v4.5 sanity check, before any picks
were treated as real tracking data or v4.5 was treated as launch-ready. The API signals its
pre-combined "grand total" row differently per endpoint, and the original code didn't
account for either signal:

- `byDateRange` (backs `hot_adj`'s `r_pa`) returns a per-team row (`sport.id==1`) *and* a
  combined-total row (`sport.id==0`, "All") for every player, every time — for a
  single-team player these two rows carry identical PA/HR. The old code summed every row it
  got back, silently doubling `r_pa` for effectively the **entire slate**, not just traded
  players (median observed `r_pa` was 96 against a ~63 theoretical 14-day ceiling).
- `statSplits` (backs `split_adj`'s `s_pa`, queried season-to-date, not L14) marks its
  combined row via `team is None` instead, and only emits it when a player has multiple
  team stints *at any point in the season* — not just within the 14-day hotness window.
  The old code's `next(...)` grabbed the first (partial, single-team) row instead, silently
  **undercounting** `s_pa` for any player traded during the season. Initial re-verification
  checked only for trades inside the L14 window and reported 1 of 299 affected; re-checking
  against the season-scoped `statSplits` data directly found **11 of 299 players affected**
  (corrected from the initial 1-of-299 figure), worst case Luis Rengifo (traded San Diego →
  Milwaukee), whose vs-RHP `s_pa` was undercounted 38 → should be 163 (4.3x), verified
  directly against the live API.

Fixed with a single `combined_hitting_stat()` helper (prefers the API's explicit combined
row when present via either signal, falling back to summing `sport.id==1` rows otherwise),
used for both `r_pa` and `s_pa`. Verified via a network-free 4-scenario `run_model()`
harness (zero diffs — the fix is entirely upstream of `run_model()`, in `main()`'s data
aggregation, so synthetic non-duplicated inputs are provably unaffected) and via live-slate
re-derivation matching all 299 players 1:1 between pre-fix and post-fix runs of the same
slate. Full detail, including the `model_prob` impact (142/299 picks changed, mean 0.37pp,
largest +3.71pp) and the `HOT_SHRINKAGE_K` re-validation below, is in
`archive/diagnostics/v4.5_dup_bug_reverify_2026-08-02.md`; the original overprediction
pattern that motivated v4.5 is in `archive/diagnostics/v4.4_diagnostic_2026-08-02.md`.

Live re-check post-fix: median `r_pa` corrected from 96 to 48 (max 138 → 69, consistent
with legitimate doubleheader-inflated single-team totals, not further duplication).
`hot_adj` bound-saturation (share of picks with `hot_adj` at/near the 0.78/1.28 clip —
same ≥1.27-or-≤0.79 convention as `archive/diagnostics/v4.4_diagnostic_2026-08-02.md` §4)
dropped from 69.8% (v4.5 formula on buggy `r_pa`) to 64.6% (v4.5 formula on corrected
`r_pa`) — still above the 57.3% the old v4.4 formula gives on the same corrected data,
**by design, not a residual bug**: the new formula extends more trust to `r_pa` at
realistic L14 volumes than the old formula ever did at any volume (e.g. at the corrected
median `r_pa=48`, `w=48/88=0.545` already exceeds the old formula's hard 0.45 ceiling), so
more genuinely noisy 2-week HR-rate swings now reach the outer clip. This is a specific
thing to watch via the dormant `RECAL_A`/`RECAL_B` recalibration layer once ~50 v4.5 picks
resolve, per standing project practice (see the v4.4 recalibration-layer note above) — not
a reason to touch the 0.78/1.28 clip bounds themselves, which v4.5 explicitly left
unchanged.

`HOT_SHRINKAGE_K=40` was re-validated against the corrected `r_pa` data and did not need
revision: the corrected live range (2–69, median 48) sits comfortably inside the 10–90 span
originally used to choose it, and the corrected median lands almost exactly on the
`r_pa=55` reference point from the original curve-check (`w=0.579`; `w=0.545` at the actual
median 48). `SC_SHRINKAGE_K=100` was never affected — its input (Statcast BBE count) comes
from Baseball Savant, a separate data source untouched by this bug.

`results/picks.json` was cleared and regenerated after the fix so v4.5's actual first
tracked day of picks reflects the corrected aggregation, not any pre-fix or partially-mixed
run from earlier the same day. Confirmed clean as of this addendum: 299 picks, single
window, single date, `r_pa` distribution matching the corrected range exactly (max 69, zero
entries above 80).

---

## v4.6 (Aug 12, 2026 – Sep 1, 2026)

**Status: finalized, Phases 1-3 shipped, Phase 4 (`league_adj`) deliberately held — see below.**
`archive/v4.5/` holds the complete pre-release snapshot (`mlb_hr_model_v4.5.py`,
`check_results_v4.5.py`, `picks_v4.5.json` — 2,242 picks, 2026-08-02–2026-08-11); checkpoint
diagnostics moved to `archive/diagnostics/`. `results/picks.json` reset to `[]`,
`results/reset_date.txt` set to 2026-08-12 for a clean v4.6 tracking window.

**Trigger:** `archive/diagnostics/v4.5_checkpoint_2026-08-11.md` and its `_rootcause` follow-up
found `sc_adj` pinned at its 1.15 cap for 94.8% of Bet-tier picks (season-cumulative Statcast
barely moves day to day, so once a player cleared the cap they stayed flagged for weeks
regardless of current form), and traced the 0.40/0.20 barrel%/hard-hit% exponents to having never
been fit to outcome data at all — present unchanged since the very first commit.

**Statcast rework (Phase 1-2, `archive/diagnostics/v4.6_phase1_statcast_refit_2026-08-11.md` +
`..._v45only_refit_2026-08-11.md` + `..._phase2_step1_2_proposal_2026-08-12.md`):**

1. ~12 logistic-regression specifications (pooled v4.2-v4.5 n=9,791 + per-version + v4.5-only
   joint/univariate/bootstrap/date-split) attempted to fit independent marginal exponents for
   `barrel_pct`/`hard_hit_pct` net of the model's other factors (offset-controlled, to isolate
   incremental signal rather than total association already explained elsewhere). None produced a
   confidently positive, stable marginal effect; several flipped sign across cuts.
2. `barrel_pct`/`hard_hit_pct` are weakly correlated with each other (r=0.05-0.08) but each is
   separately confounded with the model's other factors (r=0.39/0.55 with an offset excluding
   `sc_adj`) — the data can't support two independently-fit exponents. Collapsed to one
   equal-weighted geometric-mean "quality of contact" term; confirmed via PCA that the data
   independently supports equal weighting (first component loads ~[0.71,0.71] given near-zero
   mutual correlation).
3. **`SC_GAMMA=0.30` is an explicit, UNANCHORED PLACEHOLDER, not a fitted or validated value.**
   The one finding that held up across every specification was "no confirmed positive marginal
   signal," not a specific magnitude — `SC_GAMMA` is a deliberate, round discount (half the old
   total exponent of 0.60) reflecting that, pending outcome data under this new construction at a
   future checkpoint. Flagging prominently per explicit instruction, since this is the piece of
   the release without an independent empirical or structural anchor (see (5) below for what does
   have one).
4. First attempt at sizing the cap (`SC_GAMMA`=0.20, cap=1.08) was **circular** — both were chosen
   by sweeping and picking whichever combination produced an appealing-looking Bet-tier pin-rate
   reduction (94.8%→27.6%), with the park-factor magnitude comparison computed *afterward* as a
   post-hoc justification. Caught and corrected before shipping (see
   `..._phase2_step1_2_proposal_2026-08-12.md`) — re-derived cap independently of any pin-rate
   check, gamma via a fixed rule stated before looking at outcomes, and reported the resulting
   pin-rate (86.2% under season-cumulative data) purely as an observation rather than continuing
   to tune toward it.
5. **`SC_CAP=1.07` / `SC_FLOOR=0.93` ARE anchored**, unlike `SC_GAMMA`: `ln(SC_CAP)=0.068` matches
   park_adj's mean `|log-odds|` contribution (0.072) in the v4.5 checkpoint's factor-attribution
   table — Statcast's worst-case influence is now sized to a modest, already-established factor
   rather than dominating as the old 1.15 cap did. `SC_FLOOR` is the log-symmetric counterpart
   (1/`SC_CAP`).

**Rolling L14 window (Phase 3):** `sc_adj`'s data source changed from
`statcast_batter_exitvelo_barrels()` (season-cumulative leaderboard, no date-range parameter) to
raw play-level `statcast(start_dt, end_dt)` pulls aggregated to batted-ball events (`type=="X"`)
ourselves — barrel = `launch_speed_angle==6` (Baseball Savant's own classification), hard-hit =
`launch_speed>=95`. Verified this reproduces league-average rates matching `LG_BARREL`/
`LG_HARD_HIT` closely on a live single-day check (7.09% vs 6.7% barrel, 34.3% vs 38.5% hard-hit).
Window matches `hot_adj`'s existing L14 pattern exactly (same `d14`/`date` variables, no
deviation). No by-name fallback in the new source — the raw pull's `player_name` column is the
*pitcher's* name (one row per pitch), unlike the old leaderboard; matching is by MLB player ID
only now.

**BBE sample size dropped sharply under the rolling window** (live check, 2026-07-28 to
2026-08-11, 415 qualifying batters leaguewide): median 26 BBE, mean 25.3, range 3-55 — versus the
season-cumulative distribution `SC_SHRINKAGE_K=100` was originally calibrated against (50-BBE
pipeline floor / ~200 half-season / 350+ full-time regular, per the v4.5 entry above). At the new
median (26 BBE), the empirical-Bayes weight `w=n/(n+100)` is only ~0.21 (79% pulled to league
average) versus ~0.68 average under the old season-cumulative data. **`SC_SHRINKAGE_K` was left
unchanged this release** (per explicit instruction not to retune based on this check alone) — flagging
for the next checkpoint that it now looks calibrated for a data source the model no longer uses,
and is likely over-shrinking relative to what a 14-day-fresh signal probably deserves.

**Pin-rate re-check, reported as an observation, not used to retune `SC_GAMMA`:** Bet-tier at-cap
rate under the *old* season-cumulative window (already re-derived properly, see item 4 above) was
86.2%. Under the *new* rolling L14 window (same `SC_GAMMA`=0.30/cap=1.07/floor=0.93, live snapshot
as of 2026-08-11) it drops to **32.8%** (n=58, all 58 Bet-tier players matched to a current L14
record) — general leaguewide population (415 batters) sits at 4.6%. **Removing the staleness did
most of the practical work on its own** — the rolling window, not further `SC_GAMMA` tightening,
is what took the pin-rate from a near-universal 86-95% down to a real-but-no-longer-dominant ~33%.
Spot-check against the 13 repeat Bet-tier players and cold-tagged 0-7 subset (all previously
pinned at exactly `sc_adj=1.15` regardless of actual form): now properly differentiated —
Esmerlyn Valdez 1.1500→1.0046, Colson Montgomery 1.1500→0.9982, CJ Abrams 1.1500→0.9739 (now
*below* neutral), full table in `archive/diagnostics/v4.6_phase2_step3_4_report_2026-08-12.md`.

**Note on the pin-rate snapshot method:** the 32.8%/4.6% figures use a single live pull as of
2026-08-11 (the last diagnostic date), applied to each Bet-tier pick's player once — not a
per-pick-date historical reconstruction (would require a separate 14-day pull ending on each of
the ~7 distinct pick dates in the window). Same snapshot-approximation approach used for the
pre-ASB/post-ASB league-rate check in the root-cause diagnostic; flagged there for the same reason.

**Phase 2 Step 4 (sanity spot-check) result:** all 13 previously-pinned players (all at exactly
`sc_adj=1.15` under the old construction) confirmed properly differentiated under the new one — 3
of 13 remained at the (much lower) new cap, 10 of 13 spread across a real range. Re-confirmed again
at release finalization with a fresh live pull covering all 28 unique Bet-tier players from the
archived window (not just the original 13): range **0.972–1.070**, only **6 of 28 (21.4%)** at the
new cap, versus 94.8% under the retired construction. See "Release validation" below.

### Phase 3 — sc_adj / hot_adj interaction rule

Implemented in `run_model()`, immediately after the existing `pitcher_data_missing` downgrade
(same pattern, same place in the pipeline):

```python
if hot_adj <= 0.78 and sc_adj > 1.0 and rec == "Bet":
    rec = "—"
```

Targets the cold-tagged 0-7 failure mode directly: `0.78` is `hot_adj`'s existing hard floor (same
value already used for the 🧊 label) — not a new number. `sc_adj > 1.0` is the simplest possible
"pointing the other direction" test. Historical check against the old (pre-Phase-2) `sc_adj`/
`hot_adj` values: **6 of 58 Bet-tier picks would have been blocked, all 6 were losses, 0 false
positives** (no winning pick would have been caught); catches 6 of the 7 known cold-tagged cases
(misses one at `hot_adj=0.986`, not a real floor case). Considered and rejected a looser threshold
(would catch that one miss but fire far more on ordinary noise), a soft-damping alternative
(introduces an unsized new number where the hard downgrade needs none), and a symmetric mirror rule
for the opposite direction (no observed failure instance to justify it, and Phase 2's floor
tightening 0.78→0.93 already sharply limits how much a bad Statcast reading can drag down an
otherwise-hot player). Full design writeup:
`archive/diagnostics/v4.6_phase3_4_proposal_2026-08-12.md`.

### Phase 4 — league_adj: scoped, investigated, deliberately held (not forgotten)

A uniform, player-independent log-odds addend comparing a trailing short-window league-wide HR/PA
rate against a long rolling reference (60-90d, explicitly *not* a fixed season-to-date average —
same staleness failure mode this release exists to fix for `sc_adj`) was designed per the original
spec. Cap was anchored empirically: pulled the actual L14-vs-L90 HR/PA ratio at 8 biweekly
checkpoints this season, observed range 0.863–1.190 (wider than the spec's suggested ±10-15%),
proposed ±15% anyway as a real-but-occasionally-binding cap.

**Held at a follow-up checkpoint on the short-window length.** The original 14-day proposal was
justified only by consistency with `hot_adj` — flagged as not actually transferring, since
`hot_adj`'s window length is driven by individual-player sample-size limits that don't apply to a
league-wide aggregate (thousands of PA/day regardless of window). Recomputed the same 8 checkpoints
under 7/14/21-day short windows: **direction was stable (all three always agree on which side of
1.0), but cap-triggering was not — 3 of 8 checkpoints (37.5%) would have gotten a different
capped/not-capped answer depending purely on window choice** (e.g. 2026-07-29: 7-day reads −20.9%,
21-day reads −1.9% on the *same date*). 7-day was clearly the noisiest of the three; 14 vs. 21 still
disagreed on cap status at 2 of 8 checkpoints even so. This didn't resolve to "any reasonable window
works" — it resolved to a real, unresolved sensitivity. **Decision: do not ship `league_adj` this
release.** None of the available options (widen/drop the cap, pick 21d on the noise evidence alone,
blend multiple windows, hold) were well-anchored enough to ship alongside three phases that *are*
well-anchored. Full sensitivity data: `archive/diagnostics/v4.6_phase4_window_sensitivity_2026-08-12.md`.
Whoever picks this back up next should start from that file, not from the original 14d proposal in
`..._phase3_4_proposal_2026-08-12.md`, which is superseded on the window-length question (the cap
value itself, ±15%, is unaffected by this and can likely be reused).

### Release validation

Same standard as v4.5's launch:
- **Compile check:** `python3 -m py_compile mlb_hr_model.py` clean throughout.
- **Harness (7 tests, all pass):** exercised the actual shipped `run_model()`/`get_statcast()`
  functions (not a parallel hand calculation) — missing-Statcast zero-diff path (`sc_adj` stays
  exactly 1.0), new combined-term formula matches an independent hand calculation to floating-point
  precision, cap/floor constants confirmed (`SC_GAMMA=0.30`, `SC_CAP=1.07`, `SC_FLOOR=0.93`,
  `SC_SHRINKAGE_K=100` unchanged), extreme input clips at the new 1.07 cap (not the old 1.15),
  Phase 3 rule fires with a genuine qualifying edge (positive control), and correctly does *not*
  fire in two negative-control cases (hot_adj not floored; hot_adj floored but `sc_adj<=1.0`,
  i.e. agreement rather than conflict).
- **Live-slate re-derivation:** ran the full pipeline live for 2026-08-12 (`python3
  mlb_hr_model.py --debug`) — schedule, lineups, rolling Statcast fetch ("✓ 407 players"), weather,
  and model all completed without error for 104 players. Live `sc_adj` distribution: min 0.94, p25
  0.99, median 1.00, p75 1.02, max 1.07 — well-behaved, bounded correctly, no pinning.
- **28-player spot-check re-confirmed at release time** (see Phase 2 Step 4 result above) using a
  fresh live pull, not the earlier diagnostic-time snapshot.

### Carried-forward open items for the next checkpoint

1. **`SC_GAMMA=0.30`** — unanchored placeholder, not fitted. Revisit once this construction has its
   own live outcome data.
2. **`SC_SHRINKAGE_K=100`** — calibrated against the old season-cumulative BBE scale (~241 median);
   the new rolling-window scale is much smaller (~26 median), so this constant is likely
   over-shrinking. Not changed this release; flagged in code comments and here.
3. **`league_adj`** — designed, cap empirically anchored, but short-window length (7 vs. 14 vs. 21
   days) unresolved — 37.5% of checkpoints disagreed on cap-triggering across window choices. Held
   for a future version; see `archive/diagnostics/v4.6_phase4_window_sensitivity_2026-08-12.md`.
4. **Odds-cap gate protective value** — tracked since v4.3/v4.4, sign has flipped checkpoint to
   checkpoint (neutral → harmful → helpful) on samples of 47-109 gated picks each; still not a
   stable enough read to act on.
5. **`bp_data_missing`** — ~11% of the `model_prob>15%` population in the v4.5 checkpoint had no
   bullpen split data (defaults to league average), a structural gap not addressed by this release.

---

## v4.7 (Sep 1, 2026 – present)

**Status: shipped. Exactly two changes — recalibration layer activated, `SC_SHRINKAGE_K`
re-anchored. Nothing else moved (`SC_GAMMA`, edge tier cutoffs, `MAX_BET_ODDS`, the
`sc_adj`/`hot_adj` interaction rule, and `league_adj` all deliberately untouched — see below).**

`archive/v4.6/` holds the pre-release snapshot (`mlb_hr_model_v4.6.py`, `check_results_v4.6.py`,
`picks_v4.6.json` — 5,016 picks / 4,990 resolved, 2026-08-12 – 2026-09-01, plus a `README.md`
tag). `results/picks.json` reset to `[]` and `results/reset_date.txt` set to `2026-09-01` on
**2026-09-01 12:40 PDT (2026-09-01T19:40Z)**, launch commit **`d6685d2`**
(`v4.7: activate recalibration layer + re-anchor SC_SHRINKAGE_K`), for a clean v4.7 tracking
window.

**Trigger:** the end-of-life v4.6 checkpoint `archive/diagnostics/v4.6_checkpoint_2026-09-01.md`
(5,016-record live sample, 4,990 resolved). Its headline reconciled exactly with the dashboard
(Bet 11-72 / −0.39u / −23.9% ROI / +1 streak). Two of its findings were rated strong enough to
act on; every other finding was explicitly flagged noisy / sample-limited and is held for the
post-recal checkpoint.

### Change 1 — recalibration layer activated (checkpoint §3)

`RECAL_A` / `RECAL_B` were a mathematical identity pass-through (`0.0` / `1.0`) from v4.4 through
v4.6. Now fitted:

- **Method:** logistic regression `logit(P_HR) = RECAL_A + RECAL_B · logit(model_prob)`,
  Newton–Raphson MLE, observed-information SEs — the same logistic-recalibration method as the
  2026-07-18 v4.3 diagnostic.
- **Sample:** resolved v4.6 picks, **deduplicated** (`counts_toward_roi != False`, which drops
  1,002 earlier-window duplicate rows — a 20% dup rate under v4.6's three windows), **n = 3,988**,
  empirical base rate 10.53% (420 HR).
- **Fit:** **`RECAL_A = −0.7995`** (SE 0.1600), **`RECAL_B = 0.6521`** (SE 0.0790, 95% CI
  **[0.497, 0.807]**). Full precision: `RECAL_A = −0.7994726868`, `RECAL_B = 0.6520988645`
  (stored to 4 dp in code). Slope CI excludes 1.0 → the raw model is overdispersed (probability
  spread ~1.5× too wide); negative intercept → a further multiplicative overprediction on top.
- **For reference** (not used): the all-resolved / non-deduped fit is `−0.8493` / `0.6345`. The
  deduped fit was chosen per the checkpoint's recommendation — the 20% duplicate rate biases the
  non-deduped standard errors low.

**Expected effect:** compresses predictions toward the ~10.5% empirical base rate, most
aggressively at the extremes — raw `model_prob` 0.30 → ~0.206, 0.20 → ~0.154, 0.15 → ~0.127,
0.10 → ~0.097, 0.05 → ~0.062. **Bet-tier volume should drop:** all 83 v4.6 Bet picks sat at
`model_prob ≥ 0.206` (avg 0.271), the zone this pulls down hardest, so many will no longer clear
the +5pp edge threshold. Pick *ranking* is unchanged — the transform is monotonic, only levels
move.

### Change 2 — `SC_SHRINKAGE_K` re-anchored 100 → 29 (checkpoint §5)

`sc_adj`'s empirical-Bayes shrinkage weight is `w = n / (n + k)` on the L14 batted-ball-event
count `n`. `k = 100` was calibrated against v4.5's **season-cumulative** BBE scale (~200 for a
half-season regular); v4.6 switched `sc_adj` to a **14-day rolling window** but left `k` unchanged
(flagged as open item #2 in the v4.6 entry above).

- Live v4.6 L14 BBE distribution (4,912 resolved picks): min 3 / p25 21 / **median 29** / p75 36
  / max 57.
- Under `k = 100` the median pick got only `29/(29+100)` = **22.5%** weight on its own rolling
  reading (~78% pulled to league average).
- `k = 29` sets `w = 29/(29+29)` = **50%** weight at that median.
- **"~50%-weight-at-the-median" is a design choice, not a fitted value** (stated in the code
  comment and checkpoint §5). `SC_CAP` / `SC_FLOOR` (±1.07 / ±0.93) are unchanged, so Statcast's
  *maximum* influence on a pick is identical to v4.6 — only how quickly a given BBE sample reaches
  the cap/floor changed.

### What was NOT changed this release (and why)

- **`SC_GAMMA` (0.30)** — checkpoint §4: the marginal Statcast signal is still sign-unstable
  across specification (OLS partial association −0.13, p=0.009; logistic offset spec +0.89,
  p=0.11) with R² ≈ 0. No defensible action on this evidence.
- **Edge tier cutoffs (`Bet` > +5pp / `Skip` < −4pp)** — deferred: recalibration shifts which
  picks land in each tier, so retuning the cutoffs now would be fitting to a pick-probability
  distribution that is about to move. First task for the post-recal checkpoint.
- **`MAX_BET_ODDS` gate (+500)** — checkpoint §7: "gated picks outperform" recurred (n=184) but is
  driven by longshot-payout variance in the +700-and-longer tail; the decision-relevant +501–700
  band lost 52.8% flat-1u. No case to loosen.
- **`sc_adj`/`hot_adj` interaction rule** — checkpoint §9: only 6 live picks plausibly blocked
  (3–3, ROI inflated by longshot payouts). The pre-launch 6/6-losses record has eroded, but n=6
  is far too small to revise the rule.
- **`league_adj` / post-ASB step-change** — checkpoint §6: a corrected league baseline explains at
  most ~1/4–1/3 of the aggregate overprediction and less of the high-bucket gap; the recal layer
  should absorb most of the remainder. Revisit only if a post-recal checkpoint shows residual
  overprediction the recal cannot explain. (The v4.6 Phase 4 short-window-length sensitivity is
  also still unresolved.)

### Release validation

- **Diff vs `archive/v4.6/mlb_hr_model_v4.6.py`** — 8 hunks, nothing else: `RECAL_A`, `RECAL_B`,
  `SC_SHRINKAGE_K`, their three surrounding comment blocks, and 5 version-string bumps (docstring
  header, argparse description, console banner, both HTML report `<p class="sub">` lines, and the
  "v4.X model:" report footer). `SC_GAMMA` / `SC_CAP` / `SC_FLOOR` / `MAX_BET_ODDS` / the tier
  cutoff line / the interaction-rule line all confirmed byte-identical.
- **Compile:** `python3 -m py_compile mlb_hr_model.py check_results.py` clean.
- **RECAL non-identity check:** through the shipped constants, 0.20 → 0.154 and 0.30 → 0.206 —
  compressed toward the base rate, not unchanged.
- **`SC_SHRINKAGE_K` math:** `29/(29+29)` = 0.500 exactly at the median BBE (vs 0.225 under
  `k=100`).
- **Synthetic end-to-end `run_model()`** (no committed test harness or live spot-check tool
  exists in this repo): ran the current module against the archived v4.6 module on identical
  fabricated inputs across 6 scenarios — `game_prob` compressed in every case (e.g. 0.313 → 0.212,
  0.338 → 0.225), pick *ranking* identical under both versions, and `sc_adj` moves further off
  neutral per BBE under `k=29` as intended.
- **No live-slate run** — the model was not executed against the 2026-09-01 slate (would require
  network + an Odds API key and would write into the freshly-reset tracker). First live v4.7 picks
  come from the next scheduled GitHub Actions run.

### Open items carried into the next checkpoint

1. **`RECAL_A` / `RECAL_B`** — fitted on a single ~3-week v4.6 window (n=3,988 deduped). Re-fit
   once v4.7 has its own resolved outcomes; watch whether the slope drifts back toward 1.0 as the
   independent sample grows.
2. **`SC_GAMMA`** — still an unanchored placeholder (v4.6 open item #1), now with a checkpoint's
   worth of sign-unstable evidence against a positive marginal effect. Revisit with v4.7 outcome
   data.
3. **`SC_SHRINKAGE_K = 29`** — anchored to "50% weight at the current median BBE", not fitted.
   Re-check if the L14 BBE distribution shifts (season wind-down, roster churn).
4. **Edge tier cutoffs** — deliberately not retuned this release; the recal layer moves the
   distribution they sit on. First real task for the post-recal checkpoint.
5. **Odds-cap gate protective value / `league_adj` / `bp_data_missing`** — unchanged v4.6 open
   items #3–#5, plus the Phase 4 `league_adj` window-length sensitivity still unresolved.

---
