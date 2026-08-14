# Editorial Report Page — Design Spec

Date: 2026-08-14
Status: approved
Repo: Ashrit-K/weight-tracker

## Goal

Rebuild the hosted page (`index.html`) as a long-form editorial report in the style of
`RepCount-2018-2026.html`, driven by the full Liftosaur history rather than the last eight weeks
only. The page keeps the existing daily pipeline and keeps fetching JSON at load time.

## Source data

`history.json` holds 910 parsed session records spanning 2018-02-12 to 2026-08-12 —
17,833 work sets, 177,441 reps, 64 distinct exercises. This is the same training history the
RepCount export contained, so every RepCount analysis is reproducible here, and it refreshes daily.

Two data facts drive design decisions:

1. **Timestamps are UTC with the local offset stripped.** All 910 records carry `+00:00`.
   Per-year median start hour is 15:00 (2019) and 07:00–08:00 (2024 onward). Adding +5:30 (IST)
   yields 20:30 → 13:00, matching the RepCount timing story. The timing section therefore applies
   a fixed +5:30 offset and labels the axis IST.
2. **Bodyweight history is richer than RepCount's.** `weights.json` starts 2016-11-12 in kg.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Scope | Full port — all RepCount sections, computed from `history.json` |
| Data delivery | Runtime fetch. Python writes `report.json`; `index.html` stays static |
| Design system | RepCount CSS tokens: light/dark, `--series-*`, `--ramp-*`, mono eyebrows |
| Rendering | Vanilla SVG, no libraries, one delegated `data-tip` tooltip |
| Narrative numbers | Data-bound. No number is hard-coded in prose |
| Timing zone | Fixed +5:30 (IST) |

## Architecture

```
groups.py        NEW — shared muscle constants extracted from volume.py
                 BROAD_GROUPS, MUSCLE_TO_GROUP, muscles_for(name, customs, builtins)

report.py        NEW — reads history.json, weights.json, custom_exercises.json,
                 muscle_map.json → report.json

volume.py        imports from groups.py (constants removed, behaviour unchanged)

index.html       rewritten. Fetches report.json + stats.json + weights.json
                 + volume_stats.json

.github/workflows/update.yml   adds `python report.py`

tests/test_report.py   NEW — unit tests per aggregation
```

`report.py` is a set of pure functions over an already-parsed record list, plus a `main()` that
does the I/O. Every function takes data and returns data, so tests never touch the filesystem.

## report.json shape

```jsonc
{
  "updated_at": "...",
  "meta": { "first_date", "last_date", "years", "sessions", "sets", "reps",
            "tonnage_kg", "hours", "exercises", "active_now" },
  "facts":     { "<key>": "<preformatted string>" },   // deck substitutions
  "calendar":  [ { "y", "w", "d", "n", "s" } ],        // ISO week cells
  "layoffs":   [ { "from", "to", "days" } ],           // gaps > 21 days
  "months":    [ { "m": "YYYY-MM", "sessions", "sets", "avg12" } ],
  "years":     [ { "y", "sessions", "sets", "reps", "spy", "median_min",
                   "bw_share" } ],
  "categories":{ "order": [...], "byYear": { "<cat>": [pct per year] } },
  "reps_dist": { "bins": [...], "byYear": { "<bin>": [pct per year] } },
  "e1rm":      [ { "name", "points": [ { "t", "v" } ], "roll": [ { "t", "v" } ],
                   "best", "best_date" } ],
  "bodyweight_moves": { "order": [...], "years": [...],
                        "reps": { "<move>": [per year] } },
  "lifespans": [ { "name", "first", "last", "sets", "cat" } ],
  "dow":       [ [ count per hour 0..23 ] x 7 ],       // IST
  "notes":     [ { "k", "v" } ]
}
```

## Section plan

| # | Section | Figure |
|---|---|---|
| 1 | Stat strip | 6 tiles from `meta` |
| 2 | Consistency | ISO-week calendar heatmap + layoffs table |
| 3 | Frequency | monthly session bars + 12-month average line + year table |
| 4 | Session shape | sets per session · bodyweight-set share (two panels) |
| 5 | Muscle group balance | category share by year + table |
| 6 | Rep ranges | share by year + table |
| 7 | Strength | e1RM small multiples |
| 8 | Bodyweight movements | unweighted reps by movement and year |
| 9 | Exercise rotation | first-set → last-set lifespan bars |
| 10 | Timing | day × hour heatmap (IST) |
| 11 | Body weight | full history + cut window vs target (restyled FIG 1–2) |
| 12 | Current volume | weekly sets · tonnage · target heatmap (restyled FIG 3–5) |
| 13 | Data quality | notes block + footer |

## Computation rules

- **Work sets only.** Warmup sets are excluded everywhere, as in `volume.py`.
- **Sessions** are distinct calendar days with at least one work set.
- **Calendar cells** are ISO year-weeks; the cell tooltip names the Monday of that week.
- **Layoffs** are gaps of more than 21 days between consecutive session dates.
- **Tonnage** is `reps × weight_kg`, summed over work sets. Zero-load sets add 0.
- **Bodyweight share** is the fraction of work sets recorded at 0 kg.
- **Rep bins** are 1–5, 6–8, 9–12, 13–20, 21+.
- **Categories** are the ten `BROAD_GROUPS`, rolled to Chest / Back / Shoulders / Arms / Legs /
  Core for the share chart. A set counts once per target group, as `volume.py` already does.
- **e1RM** uses Epley, `w × (1 + reps/30)`, best set per training day, sets above 15 reps
  excluded. Machine and cable loads are not comparable across gyms, so an exercise is
  disqualified when its name holds `Leverage Machine`, `Machine`, `Cable`, `Pulldown` or
  `Pushdown`. Everything else that carries load qualifies — the log names most free weights
  without an equipment suffix, so a `Dumbbell`/`Barbell` allow-list would drop Lateral Raise,
  Shoulder Press and Bicep Curl. The six lifts with the most qualifying days get panels; a panel
  needs at least 12 such days. The line is a 5-session rolling median.
- **Bodyweight movements** are exercises whose sets are all 0 kg on at least half their days.
- **Lifespans** run from an exercise's first work set to its last. Exercises with fewer than
  10 total sets are dropped to keep the chart legible.
- **Facts** are preformatted strings so the page never does arithmetic on narrative numbers.

## Prose strategy

RepCount hard-codes numbers in its decks. This page rebuilds daily, so hard-coded numbers rot.
Each deck writes its numbers as `<b data-f="key"></b>`, and the page fills every `[data-f]` from
`report.facts` on load. If a key is missing the span stays empty rather than showing a stale value.

## Error handling

Each section renders independently. A failed fetch or a missing key replaces that figure with a
muted "data unavailable" line and leaves the rest of the page intact — the current page's
behaviour, applied per section. `report.py` fails loudly on missing input files, matching the
existing pipeline convention.

## Testing

`tests/test_report.py` builds small synthetic record lists and asserts on:

- ISO-week bucketing and session-day de-duplication
- layoff detection at the 21-day boundary
- Epley values and the 15-rep exclusion
- rep-range bin edges
- IST offset applied to the day × hour matrix
- lifespan first/last bounds and the 10-set floor
- bodyweight share with mixed 0 kg and loaded sets

`tests/test_volume.py` must keep passing unchanged after the `groups.py` extraction.

## Out of scope

- Embedding data in the HTML at build time
- Changing the fetch or muscle-map steps
- Any new dependency. `report.py` uses the standard library only
