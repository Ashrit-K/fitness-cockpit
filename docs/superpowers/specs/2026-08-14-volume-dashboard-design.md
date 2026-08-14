# Volume Dashboard — Design Spec

Date: 2026-08-14
Status: approved
Repo: Ashrit-K/weight-tracker

## Goal

Extend the live weight-tracking artifact with training-volume analytics: weekly sets and tonnage per muscle group, with hypertrophy target comparison. Charts auto-update daily via GitHub Actions and publish to GitHub Pages.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Goal | Volume management (enough/too much per muscle) |
| Metrics | Both weekly sets AND weekly tonnage per muscle group |
| Display | Stacked bars per week, last 8 weeks |
| Muscle mapping | Liftosaur open-source exercise DB (`astashov/liftosaur` `src/data/exercises.ts`), vendored; custom exercises override from MCP |
| Granularity | 10 broad groups: Chest, Back, Shoulders, Biceps, Triceps, Quads, Hamstrings, Glutes, Core, Calves |
| Targets | 10–20 sets/week band shown via heatmap color scale |
| Rendering | Static PNGs, seaborn white style, no top/right spines |
| Frequency | Daily 02:30 UTC cron + manual dispatch |

## Architecture

```
fetch.py (rename of fetch_weights.py)
  ├─ weight measurements          → weights.json
  ├─ workout history (paginated)  → history.json
  └─ custom exercises             → custom_exercises.json

muscle_map.py
  └─ built-in name → muscle map from vendored Liftosaur DB → muscle_map.json
     (refreshed manually when upstream changes)

volume.py
  ├─ chart_sets.png     stacked bars/week (8 wks) by muscle group
  ├─ chart_tonnage.png  stacked bars/week (8 wks) by tonnage
  └─ chart_targets.png  heatmap: muscles × weeks, sets, color vs 10–20 band
  └─ volume_stats.json  summary + warnings

chart.py (existing)
  ├─ panel 1: full weight history (2018 → now, earliest record in account)
  └─ panel 2: zoom Jul 2026 → now, dense-window trend + 1 lb/wk target
  └─ chart.png

index.html → sections: Weight / Sets / Tonnage / Targets
.github/workflows/update.yml → daily 02:30 UTC
```

Note: user's Liftosaur weight data starts 2018-02-23. No 2016 data exists. Import of older external data is out of scope for this spec.

## Parsing Conventions (Liftohistory)

- Work sets only; `warmup:` lines excluded
- Unilateral `1x8|8` = 1 set, weight counted once
- Bodyweight/0kg sets count toward sets, 0 toward tonnage
- lb values converted to kg on ingest
- `+` (AMRAP) markers ignored; performed reps parsed from actual set lines, not target
- Unknown exercise → "Other" bucket + warning in volume_stats.json
- Week bucketing: Monday-start weeks from record UTC timestamps

## Chart Specs

All charts:
- seaborn white style, white background, major grid visible, minor grid faint
- No top spine, no right spine
- Consistent color map: one color per muscle group across all three volume charts

1. chart_sets.png — stacked bars, x = week (last 8, Monday labels), segments = muscle groups, y = sets
2. chart_tonnage.png — same layout, y = tonnage kg (sets × reps × weight)
3. chart_targets.png — heatmap, rows = 10 muscle groups, cols = last 8 weeks, cells = sets count; color: green = 10–20 sets, yellow = below 10, red = above 20; cell text = set count

## Error Handling

- API failure → workflow fails, published site keeps last good charts
- Record parse failure → skip record, log warning, continue
- Unmapped exercise → "Other" bucket + warning
- Vendored muscle DB insulates from upstream format changes

## Testing

- Fixtures: sanitized real Liftohistory samples (from user's history, scrubbed)
- `volume.py` runs on fixtures offline; CI validates before fetch step
- Parser unit tests for: unilateral syntax, warmup exclusion, lb/kg mix, bodyweight sets, AMRAP

## Out of Scope

- Pre-2018 weight import
- Interactive charts
- Strength/e1RM progression, consistency dashboards (future work)
