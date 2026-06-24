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
