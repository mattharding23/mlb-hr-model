# Model v4.6 archive snapshot

Frozen at the v4.7 cutover (2026-09-01).

| | |
|---|---|
| Version | v4.6 |
| Live from | 2026-08-12 (launch commit `ed04b9c`, tracker reset `results/reset_date.txt` = 2026-08-12) |
| Live to | 2026-09-01 (last slate in this snapshot) |
| Superseded by | v4.7 (2026-09-01) |
| Source commit for these files | `e3ce610` |

## Files

| File | Notes |
|---|---|
| `mlb_hr_model_v4.6.py` | byte-identical copy of `mlb_hr_model.py` at commit `e3ce610` |
| `check_results_v4.6.py` | byte-identical copy of `check_results.py` at commit `e3ce610` |
| `picks_v4.6.json` | full `results/picks.json` at cutover — **5,016 records**, dates **2026-08-12 → 2026-09-01**, 4,990 resolved / 26 pending. This is the complete v4.6 live-tracking history (the tracker is reset to `[]` for v4.7). |

## What v4.6 was

Collapsed Statcast term (single equal-weighted quality-of-contact factor,
`SC_GAMMA` placeholder 0.30, `SC_CAP` re-anchored to 1.07), L14 rolling window
for `sc_adj`, and the `sc_adj`/`hot_adj` interaction rule. See
`archive/VERSION_HISTORY.md` (v4.6 entry) and
`archive/diagnostics/v4.6_checkpoint_2026-09-01.md` for the end-of-life
checkpoint that drove the v4.7 changes.
