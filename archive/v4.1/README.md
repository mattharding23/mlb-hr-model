# Archive: MLB HR Model v4.1

**Archived:** 2026-06-23  
**Era:** Jun 12 – Jun 23, 2026 (12 game-days, 2,549 picks, 2,541 resolved)

## What this version was

v4 base was introduced at commit `0e08992` (May 18, 2026) with platoon regression,
3-window daily schedule, and game-totals integration.

v4.1 was the patch at commit `766b013` (Jun 12, 2026):
- Devig formula change: VIG_FACTOR 1.055→0.92 (multiply instead of divide)
- Tightened adjustment caps: split [0.5,2.5]→[0.75,1.40], hot [0.65,1.5]→[0.78,1.28],
  Statcast [0.70,1.50]→[0.78,1.35], SP [0.4,3.0]→[0.55,2.20], BP [0.5,2.5]→[0.65,1.80]
- Added results tracking workflow (check-results cron job, picks.json auto-commit)

## Headline performance (post-766b013 only)

| Tier | W | L | Win% | Net Units | ROI |
|------|--:|--:|-----:|----------:|----:|
| Bet  | 64 | 381 | 14.4% | −1.04 | −10.3% |
| Lean | 19 | 145 | 11.6% | −0.12 | −10.9% |
| **Combined** | **83** | **526** | **13.6%** | **−1.16** | **−10.4%** |

Brier Score: 0.11228 vs baseline 0.11154 → Skill Score ≈ −0.007 (no calibration advantage)

## Known issues fixed in v4.2

1. **Caesars outlier contamination (primary ROI drag):** Single-book Caesars lines at
   +700–1500 created phantom edge of +15–26pp. Virtually all high-edge picks used
   Caesars as the sole or dominant book. Fixed by multi-book corroboration filter
   (≥2 books within 3pp implied spread required for Bet/Lean tier).

2. **Jun 17 CIN cluster root cause:** 5+ CIN players with >15pp stated edge traced to
   Caesars posting outlier longshot lines against a backdrop of GABP park factor (1.18×),
   inferred game O/U ~12.5 (verified: JJ Bleday prob=0.3409 = 1−0.92^5.0, requiring
   proj_pa=5.0, requiring ou=12.5 for batting_order=2). No model bug — multi-book
   filter is the fix.

3. **Durán per_pa saturation (not a caching bug):** player_id 660710 (Rodolfo Durán, SD)
   showed identical model_prob on Jun 15/16/19 (0.2716). Root cause: per_pa hits the
   0.08 hard cap on PETCO home games (park_adj=0.88) when the same batting_order=9
   and game O/U produces the same projected_pa. This is model saturation, not a code
   cache. Fixed by logging per_pa_capped flag in picks.json for analysis.

4. **Window field always null:** `--window` flag never passed by GitHub Actions workflow.
   All three daily runs save picks with window=None; the dedup key (date, player_id, None)
   causes the 5:45pm and 8:45pm runs to silently skip all picks already saved by the
   11:30am run. Fixed by auto-detecting window from UTC time in main().

5. **Low odds match rate (corollary of #4):** At 11:30am ET, most sportsbooks haven't
   posted HR props yet. Because window=None dedup causes only the 11:30am run to save
   picks, the picks file is populated before odds are available. Fixed by window tracking:
   each run window now saves its own pick records independently.

6. **Factor and window values not logged:** picks.json stored no per-pick factor breakdown,
   preventing calibration analysis. Fixed by adding factors dict and actual_pa to each record.

## Files in this archive

- `mlb_hr_model.py` — model as of the v4.1 era
- `check_results.py` — results resolver as of the v4.1 era
- `results/picks.json` — full 2,541-pick resolved dataset
- `results/reset_date.txt` — previous reset date (2026-06-03)
- `results/performance_summary_2026-06-23.json` — computed analytics
- `results/performance_summary_2026-06-23.md` — full markdown analysis report
