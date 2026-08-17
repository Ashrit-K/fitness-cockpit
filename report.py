"""Build report.json — every series the editorial page renders.

Reads the raw Liftosaur exports and emits one file of pre-computed statistics.
Each function takes data and returns data, so the tests never touch the disk.
"""

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from body_map import MUSCLE_TO_PARTS
from groups import (BROAD_GROUPS, CATEGORIES, GROUP_TO_CATEGORY, SYNERGIST_CREDIT,
                    VTAPER, groups_for, muscles_for, synergists_for, weighted_groups)
from landmarks import LANDMARKS, state
from patterns import DELT_HEADS, PATTERNS
from lifto_parse import daily_weights, parse_record, ParseError

# Liftosaur strips the local offset and stores every timestamp as +00:00.
# The log was recorded in India, so clock-time questions need this back.
IST = timedelta(hours=5, minutes=30)

# Duration, not repetitions. These pollute every rep and set statistic.
CARDIO = {"Incline Walking", "Elliptical Machine"}

# Loads on these are gym-specific and cannot be compared across years.
MACHINE_WORDS = ("Leverage Machine", "Machine", "Cable", "Pulldown", "Pushdown")

REP_BINS = [("1–5", 1, 5), ("6–8", 6, 8), ("9–12", 9, 12),
            ("13–20", 13, 20), ("21+", 21, 10 ** 6)]

DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

MIN_E1RM_DAYS = 12      # a strength panel needs this many training days
MIN_LIFESPAN_SETS = 10  # rotation bars ignore anything rarer than this
BW_SET_SHARE = 0.8      # a movement is bodyweight at this share of 0 kg sets

# The current objective: reach this weight, hold strength, add muscle where
# possible. It is one number, not a range — low and high are kept equal so the
# page can still draw it as a line and the milestone list can end on it.
GOAL_KG = 64.0
GOAL_LOW_KG = GOAL_KG
GOAL_HIGH_KG = GOAL_KG

# The headline weight is a smoothed estimate, not the last reading. A scale is
# only good to about half a kilo and body weight swings on water and food, so a
# single number off one morning is the noisiest thing on the page. Seven days
# spans a full week of eating and training.
SMOOTH_WINDOW_DAYS = 7

# Fixed, evenly spaced markers on the way down from the peak.
MILESTONE_PCTS = [2.5, 5.0, 7.5]

# Strength retention compares a recent window against the year before it.
WATCH_DAYS = 56
BASELINE_DAYS = 365
MIN_WATCH_DAYS = 3      # training days needed in each window to compare a lift


# --------------------------------------------------------------- ingest

def load_sessions(records):
    """Parsed records as session dicts, oldest first. Cardio is dropped."""
    out = []
    for rec in records:
        try:
            parsed = parse_record(rec["text"])
        except ParseError:
            continue
        try:
            dt = datetime.fromisoformat(parsed["date"].replace("Z", "+00:00"))
        except ValueError:
            continue
        exercises = [
            {"name": e["name"], "sets": e["sets"]}
            for e in parsed["exercises"]
            if e["sets"] and e["name"] not in CARDIO
        ]
        if not exercises:
            continue
        out.append({
            "dt": dt,
            "date": dt.date(),
            "local": dt + IST,
            "duration_s": parsed["duration_s"],
            "program": parsed["program"],
            "week": parsed["week"],
            "day_in_week": parsed["day_in_week"],
            "day_name": parsed["day_name"],
            "exercises": exercises,
        })
    out.sort(key=lambda s: s["dt"])
    return out


def all_sets(session):
    for ex in session["exercises"]:
        for s in ex["sets"]:
            yield ex["name"], s


def n_sets(session):
    return sum(len(ex["sets"]) for ex in session["exercises"])


def tonnage(session):
    return sum(s["reps"] * s["weight_kg"] for _, s in all_sets(session))


# --------------------------------------------------------------- sections

def monday(d):
    return d - timedelta(days=d.weekday())


def meta(sessions, active_now, exercises):
    reps = sum(s["reps"] for ses in sessions for _, s in all_sets(ses))
    sets = sum(n_sets(ses) for ses in sessions)
    secs = sum(ses["duration_s"] or 0 for ses in sessions)
    first, last = sessions[0]["date"], sessions[-1]["date"]
    return {
        "first_date": first.isoformat(),
        "last_date": last.isoformat(),
        "years": round((last - first).days / 365.25, 1),
        "sessions": len(sessions),
        "sets": sets,
        "reps": reps,
        "tonnage_kg": round(sum(tonnage(ses) for ses in sessions)),
        "hours": round(secs / 3600),
        "exercises": exercises,
        "active_now": active_now,
    }


def calendar_cells(sessions):
    """One cell per ISO week that holds at least one session."""
    cells = {}
    for ses in sessions:
        y, w, _ = ses["date"].isocalendar()
        key = (y, w)
        c = cells.setdefault(key, {"y": y, "w": w, "n": 0, "s": 0, "days": set()})
        c["n"] += 1
        c["s"] += n_sets(ses)
        c["days"].add(ses["date"])
    out = []
    for (y, w), c in sorted(cells.items()):
        monday = datetime.fromisocalendar(y, w, 1).date()
        out.append({"y": y, "w": w, "d": monday.isoformat(),
                    "n": c["n"], "s": c["s"]})
    return out


def layoffs(sessions, min_days=21):
    """Gaps longer than min_days between consecutive training days."""
    days = sorted({ses["date"] for ses in sessions})
    out = []
    for a, b in zip(days, days[1:]):
        gap = (b - a).days
        if gap > min_days:
            out.append({"from": a.isoformat(), "to": b.isoformat(), "days": gap})
    return out


def monthly(sessions):
    """Sessions and sets per calendar month, with a 12-month trailing average."""
    counts = defaultdict(lambda: {"sessions": 0, "sets": 0})
    for ses in sessions:
        key = ses["date"].strftime("%Y-%m")
        counts[key]["sessions"] += 1
        counts[key]["sets"] += n_sets(ses)

    first, last = sessions[0]["date"], sessions[-1]["date"]
    months = []
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        months.append("%04d-%02d" % (y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1

    out = []
    for i, key in enumerate(months):
        window = months[max(0, i - 11):i + 1]
        avg = sum(counts[k]["sessions"] for k in window) / len(window)
        out.append({"m": key,
                    "sessions": counts[key]["sessions"],
                    "sets": counts[key]["sets"],
                    "avg12": round(avg, 1)})
    return out


def _median(values):
    v = sorted(values)
    if not v:
        return 0
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def yearly(sessions):
    by = defaultdict(list)
    for ses in sessions:
        by[ses["date"].year].append(ses)
    out = []
    for y in sorted(by):
        group = by[y]
        sets = sum(n_sets(s) for s in group)
        zero = sum(1 for s in group for _, st in all_sets(s) if st["weight_kg"] == 0)
        durations = [s["duration_s"] / 60 for s in group if s["duration_s"]]
        out.append({
            "y": y,
            "sessions": len(group),
            "sets": sets,
            "reps": sum(st["reps"] for s in group for _, st in all_sets(s)),
            "tonnage": round(sum(tonnage(s) for s in group)),
            "spy": round(sets / len(group), 1),
            "median_min": round(_median(durations)),
            "bw_share": round(100 * zero / sets, 1) if sets else 0.0,
        })
    return out


def category_shares(sessions, customs, builtins):
    """Percent of each year's sets that trained each reading category."""
    years = sorted({ses["date"].year for ses in sessions})
    counts = {c: defaultdict(int) for c in CATEGORIES}
    totals = defaultdict(int)
    unmapped = Counter()
    for ses in sessions:
        y = ses["date"].year
        for name, _set in all_sets(ses):
            cats = []
            for g in groups_for(name, customs, builtins):
                c = GROUP_TO_CATEGORY.get(g)
                if c and c not in cats:
                    cats.append(c)
            if not cats:
                unmapped[name] += 1
                continue
            for c in cats:
                counts[c][y] += 1
            totals[y] += len(cats)
    by_year = {}
    for c in CATEGORIES:
        by_year[c] = [round(100 * counts[c][y] / totals[y], 1) if totals[y] else 0.0
                      for y in years]
    raw = {c: [counts[c][y] for y in years] for c in CATEGORIES}
    return {"order": CATEGORIES, "years": years, "byYear": by_year, "raw": raw,
            "unmapped": sorted(unmapped)}


def rep_shares(sessions):
    years = sorted({ses["date"].year for ses in sessions})
    counts = {b[0]: defaultdict(int) for b in REP_BINS}
    totals = defaultdict(int)
    overall = Counter()
    for ses in sessions:
        y = ses["date"].year
        for _name, s in all_sets(ses):
            for label, lo, hi in REP_BINS:
                if lo <= s["reps"] <= hi:
                    counts[label][y] += 1
                    overall[label] += 1
                    totals[y] += 1
                    break
    total = sum(overall.values())
    return {
        "bins": [b[0] for b in REP_BINS],
        "years": years,
        "byYear": {b[0]: [round(100 * counts[b[0]][y] / totals[y], 1) if totals[y] else 0.0
                          for y in years] for b in REP_BINS},
        "overall": {b[0]: round(100 * overall[b[0]] / total, 1) if total else 0.0
                    for b in REP_BINS},
    }


def epley(weight_kg, reps):
    return weight_kg * (1 + reps / 30)


def is_free_weight(name):
    if any(w in name for w in MACHINE_WORDS):
        return False
    return True


def best_e1rm_by_day(sessions, machines=False):
    """name -> {date: best estimated 1RM that day}."""
    days = defaultdict(dict)
    for ses in sessions:
        for name, s in all_sets(ses):
            if not machines and not is_free_weight(name):
                continue
            if s["weight_kg"] <= 0 or s["reps"] > 15:
                continue
            v = epley(s["weight_kg"], s["reps"])
            cur = days[name].get(ses["date"])
            if cur is None or v > cur:
                days[name][ses["date"]] = v
    return days


def strength_watch(sessions, now, limit=8, names=None, machines=False):
    """Recent best estimated 1RM against the year before, per lift.

    This is the retention check for a cut: the recent window should hold its
    ground against the baseline, not fall away with the body weight.

    Machines are excluded by default, because a stack number does not carry
    between gyms. Pass machines=True when the comparison is a lift against its
    own past on the same equipment, where the stack is a fair yardstick.
    """
    days = best_e1rm_by_day(sessions, machines=machines)
    recent_from = now - timedelta(days=WATCH_DAYS)
    base_from = recent_from - timedelta(days=BASELINE_DAYS)
    out = []
    for name, by_day in days.items():
        if names is not None and name not in names:
            continue
        recent = [v for d, v in by_day.items() if d > recent_from]
        base = [v for d, v in by_day.items() if base_from < d <= recent_from]
        if len(recent) < MIN_WATCH_DAYS or len(base) < MIN_WATCH_DAYS:
            continue
        now_kg, base_kg = max(recent), max(base)
        out.append({
            "name": name,
            "now": round(now_kg, 1),
            "base": round(base_kg, 1),
            "delta_pct": round(100 * (now_kg / base_kg - 1), 1),
            "days": len(recent),
        })
    out.sort(key=lambda r: -r["delta_pct"])
    return out[:limit]


def _weekly_buckets(sessions, weeks, now):
    """Week-start dates for the last `weeks` weeks, and an index onto them."""
    starts = [monday(now) - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]
    return starts, {w: i for i, w in enumerate(starts)}


def pattern_series(sessions, now, weeks=12):
    """Per movement pattern: weekly volume, plus each lift against its own past.

    Volume answers "is the stimulus still there"; e1RM answers "is the strength
    still there". A cut needs both, and for unloaded work only the first exists.
    """
    starts, idx = _weekly_buckets(sessions, weeks, now)
    out = []
    for spec in PATTERNS:
        names = set(spec["names"])
        sets = [0] * weeks
        reps = [0] * weeks
        tons = [0.0] * weeks
        best = [0] * weeks     # best unloaded set that week — the pull-up yardstick
        loaded = 0
        for ses in sessions:
            i = idx.get(monday(ses["date"]))
            for name, s in all_sets(ses):
                if name not in names:
                    continue
                if s["weight_kg"] > 0:
                    loaded += 1
                if i is None:
                    continue
                sets[i] += 1
                reps[i] += s["reps"]
                tons[i] += s["reps"] * s["weight_kg"]
                if s["weight_kg"] == 0 and s["reps"] > best[i]:
                    best[i] = s["reps"]
        best_reps = max(best)

        recent = sets[-2:] or [0]
        base = sets[:-2] or [0]
        out.append({
            "key": spec["key"],
            "label": spec["label"],
            "note": spec["note"],
            "weeks": [w.isoformat() for w in starts],
            "sets": sets,
            "reps": reps,
            "tonnage": [round(t) for t in tons],
            "sets_now": sets[-1],
            "sets_prev": sets[-2] if weeks > 1 else 0,
            "sets_mean": round(sum(base) / len(base), 1),
            "unloaded": loaded == 0,
            "best_reps": best,
            "best_unloaded_reps": best_reps,
            "lifts": strength_watch(sessions, now, limit=6,
                                    names=names, machines=True),
        })
    return out


def delt_heads(sessions, now, weeks=12):
    """Weekly sets per delt head, split into direct work and indirect stimulus."""
    starts, idx = _weekly_buckets(sessions, weeks, now)
    heads = []
    for spec in DELT_HEADS:
        direct = set(spec["direct"])
        indirect = set(spec["indirect"])
        d = [0] * weeks
        n = [0] * weeks
        for ses in sessions:
            i = idx.get(monday(ses["date"]))
            if i is None:
                continue
            for name, _s in all_sets(ses):
                if name in direct:
                    d[i] += 1
                elif name in indirect:
                    n[i] += 1
        heads.append({
            "key": spec["key"], "label": spec["label"],
            "direct": d, "indirect": n,
            "direct_now": d[-1], "indirect_now": n[-1],
            "direct_prev": d[-2] if weeks > 1 else 0,
        })
    return {"weeks": [w.isoformat() for w in starts], "heads": heads}


def e1rm_panels(sessions, limit=6, window=5):
    """Best estimated 1RM per training day, for the most-logged free-weight lifts."""
    days = best_e1rm_by_day(sessions)
    ranked = sorted(days.items(), key=lambda kv: -len(kv[1]))
    out = []
    for name, by_day in ranked:
        if len(by_day) < MIN_E1RM_DAYS:
            continue
        pts = [{"t": d.isoformat(), "v": round(v, 1)} for d, v in sorted(by_day.items())]
        roll = []
        for i in range(len(pts)):
            chunk = [p["v"] for p in pts[max(0, i - window + 1):i + 1]]
            roll.append({"t": pts[i]["t"], "v": round(_median(chunk), 1)})
        best = max(pts, key=lambda p: p["v"])
        out.append({"name": name, "points": pts, "roll": roll,
                    "best": best["v"], "best_date": best["t"]})
        if len(out) == limit:
            break
    return out


def bodyweight_moves(sessions):
    """Reps per year for movements that are almost always unloaded."""
    stats = defaultdict(lambda: {"sets": 0, "zero": 0})
    for ses in sessions:
        for name, s in all_sets(ses):
            st = stats[name]
            st["sets"] += 1
            if s["weight_kg"] == 0:
                st["zero"] += 1
    names = [n for n, st in stats.items()
             if st["sets"] >= 50 and st["zero"] / st["sets"] >= BW_SET_SHARE]

    years = sorted({ses["date"].year for ses in sessions})
    reps = {n: {y: 0 for y in years} for n in names}
    for ses in sessions:
        y = ses["date"].year
        for name, s in all_sets(ses):
            if name in reps and s["weight_kg"] == 0:
                reps[name][y] += s["reps"]
    order = sorted(names, key=lambda n: -sum(reps[n].values()))
    return {"order": order, "years": years,
            "reps": {n: [reps[n][y] for y in years] for n in order}}


def lifespans(sessions, customs, builtins):
    """First and last work set for every exercise with a real footprint."""
    info = {}
    for ses in sessions:
        for name, _s in all_sets(ses):
            d = ses["date"]
            rec = info.setdefault(name, {"first": d, "last": d, "sets": 0})
            rec["sets"] += 1
            if d < rec["first"]:
                rec["first"] = d
            if d > rec["last"]:
                rec["last"] = d
    out = []
    for name, rec in info.items():
        if rec["sets"] < MIN_LIFESPAN_SETS:
            continue
        gs = groups_for(name, customs, builtins)
        cat = GROUP_TO_CATEGORY.get(gs[0]) if gs else None
        out.append({"name": name, "first": rec["first"].isoformat(),
                    "last": rec["last"].isoformat(), "sets": rec["sets"],
                    "cat": cat or "Core"})
    out.sort(key=lambda r: (r["first"], r["name"]))
    return out


def dow_matrix(sessions):
    """Sessions per weekday and local hour, Monday first."""
    m = [[0] * 24 for _ in range(7)]
    for ses in sessions:
        local = ses["local"]
        m[local.weekday()][local.hour] += 1
    return m


def weekly_volume(sessions, customs, builtins, weeks=26, now=None):
    """Sets and tonnage per broad group per week, most recent `weeks` weeks.

    A set counts once per group the exercise trains, never twice for two heads
    of the same group.
    """
    if now is None:
        now = sessions[-1]["date"]
    this_monday = monday(now)
    starts = [this_monday - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]
    idx = {w: i for i, w in enumerate(starts)}

    sets = {g: [0.0] * weeks for g in BROAD_GROUPS}
    direct = {g: [0] * weeks for g in BROAD_GROUPS}
    indirect = {g: [0] * weeks for g in BROAD_GROUPS}
    tons = {g: [0.0] * weeks for g in BROAD_GROUPS}
    # A set with no external load carries no tonnage, so leaving it in the
    # denominator would make the ratio measure bodyweight share rather than
    # how heavy the loaded work was. Loaded sets are counted separately.
    loaded_sets = {g: [0.0] * weeks for g in BROAD_GROUPS}
    loaded_reps = {g: [0.0] * weeks for g in BROAD_GROUPS}
    days = [set() for _ in range(weeks)]
    performed = [0] * weeks          # sets actually done, before any group credit
    performed_loaded = [0] * weeks
    total_tons = [0.0] * weeks
    total_reps = [0] * weeks
    for ses in sessions:
        i = idx.get(monday(ses["date"]))
        if i is None:
            continue
        days[i].add(ses["date"])
        performed[i] += n_sets(ses)
        for name, s in all_sets(ses):
            work = s["reps"] * s["weight_kg"]
            if s["weight_kg"] > 0:
                performed_loaded[i] += 1
                total_tons[i] += work
                total_reps[i] += s["reps"]
            for g, credit in weighted_groups(name, customs, builtins).items():
                sets[g][i] += credit
                tons[g][i] += credit * work
                if s["weight_kg"] > 0:
                    loaded_sets[g][i] += credit
                    loaded_reps[g][i] += credit * s["reps"]
                if credit == 1.0:
                    direct[g][i] += 1
                else:
                    indirect[g][i] += 1

    def ratio(num, den):
        return [round(num[k] / den[k], 1) if den[k] else 0.0
                for k in range(weeks)]

    # On a Monday the current week is empty and every "this week" reading would
    # be a true but useless zero, so the page headlines the last week that holds
    # training and says which week that is.
    latest = len(starts) - 1
    while latest > 0 and performed[latest] == 0:
        latest -= 1

    return {
        "weeks": [w.isoformat() for w in starts],
        "latest": latest,
        "current_week_empty": performed[len(starts) - 1] == 0,
        "sets": {g: [round(v, 1) for v in sets[g]] for g in BROAD_GROUPS},
        "direct": direct,
        "indirect": indirect,
        "tonnage": {g: [round(v) for v in tons[g]] for g in BROAD_GROUPS},
        "performed": performed,
        "sessions": [len(d) for d in days],
        # how heavy the work was, rather than how much of it there was
        "intensity": {
            "kg_per_set": ratio(total_tons, performed_loaded),
            "kg_per_rep": ratio(total_tons, total_reps),
            "loaded_sets": performed_loaded,
            "tonnage": [round(t) for t in total_tons],
            "reps": total_reps,
            "by_group": {g: ratio(tons[g], loaded_sets[g]) for g in BROAD_GROUPS},
            "per_rep_by_group": {g: ratio(tons[g], loaded_reps[g])
                                 for g in BROAD_GROUPS},
            "loaded_sets_by_group": {g: [round(v, 1) for v in loaded_sets[g]]
                                     for g in BROAD_GROUPS},
        },
    }


def muscle_week(sessions, customs, builtins, now=None, weeks=2):
    """Credited sets per individual muscle, for the last `weeks` weeks.

    The body figure is drawn per muscle head, so this stops at the muscle and
    never rolls up to a group: a lateral raise has to light the side deltoid
    alone. Credit is the same 1.0 target / 0.5 assist rule.
    """
    if now is None:
        now = sessions[-1]["date"]
    starts = [monday(now) - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]
    idx = {w: i for i, w in enumerate(starts)}
    out = {}
    for ses in sessions:
        i = idx.get(monday(ses["date"]))
        if i is None:
            continue
        for name, _s in all_sets(ses):
            targets = muscles_for(name, customs, builtins)
            assists = [m for m in synergists_for(name, customs, builtins)
                       if m not in targets]
            for m, credit in ([(t, 1.0) for t in targets]
                              + [(a, SYNERGIST_CREDIT) for a in assists]):
                if m not in MUSCLE_TO_PARTS:
                    continue
                rec = out.setdefault(m, {"credit": [0.0] * weeks,
                                         "direct": [0] * weeks,
                                         "indirect": [0] * weeks})
                rec["credit"][i] += credit
                rec["direct" if credit == 1.0 else "indirect"][i] += 1
    for m, rec in out.items():
        rec["credit"] = [round(v, 1) for v in rec["credit"]]
        rec["parts"] = MUSCLE_TO_PARTS[m]
    return {"weeks": [w.isoformat() for w in starts], "muscles": out}


def mesocycle(sessions, customs, builtins):
    """The current block, by programme week rather than calendar week.

    A programme week rarely lines up with a calendar week — this block's week 1
    ran Wed to Mon — and the volume ramp is defined on the programme's weeks,
    so the block view has to count them its own way.
    """
    tagged = [s for s in sessions if s["program"] and s["week"]]
    if not tagged:
        return None
    program = tagged[-1]["program"]
    block = [s for s in tagged if s["program"] == program]
    weeks = {}
    for ses in block:
        w = weeks.setdefault(ses["week"], {
            "week": ses["week"], "days": [], "performed": 0,
            "sets": {g: 0.0 for g in BROAD_GROUPS},
            "direct": {g: 0 for g in BROAD_GROUPS},
        })
        w["days"].append({"d": ses["date"].isoformat(),
                          "day": ses["day_in_week"],
                          "name": ses["day_name"]})
        w["performed"] += n_sets(ses)
        for name, _s in all_sets(ses):
            for g, credit in weighted_groups(name, customs, builtins).items():
                w["sets"][g] += credit
                if credit == 1.0:
                    w["direct"][g] += 1
    out = []
    for n in sorted(weeks):
        w = weeks[n]
        w["sets"] = {g: round(v, 1) for g, v in w["sets"].items()}
        w["days"].sort(key=lambda d: d["d"])
        out.append(w)
    days_per_week = max((len(w["days"]) for w in out), default=0)
    last = out[-1]
    return {
        "program": program,
        "started": block[0]["date"].isoformat(),
        "days_per_week": days_per_week,
        "current_week": last["week"],
        "current_day": len(last["days"]),
        "weeks": out,
    }


def recent_sessions(sessions, customs, builtins, n=24):
    """The last n sessions: total sets, tonnage, and sets per group."""
    out = []
    for ses in sessions[-n:]:
        per = {g: 0.0 for g in BROAD_GROUPS}
        direct = {g: 0 for g in BROAD_GROUPS}
        for name, s in all_sets(ses):
            for g, credit in weighted_groups(name, customs, builtins).items():
                per[g] += credit
                if credit == 1.0:
                    direct[g] += 1
        out.append({
            "d": ses["date"].isoformat(),
            "sets": n_sets(ses),
            "tonnage": round(tonnage(ses)),
            "minutes": round((ses["duration_s"] or 0) / 60),
            "groups": {g: round(v, 1) for g, v in per.items() if v},
            "direct": {g: v for g, v in direct.items() if v},
        })
    return out


def smoothed_weight(series, window=SMOOTH_WINDOW_DAYS):
    """Gaussian-weighted estimate of current weight at the last reading.

    Weighted by distance in days rather than by position, so a gap between
    weigh-ins does not distort it. Only past readings exist at the last point,
    so this lags the raw number slightly — which is the point.
    """
    if not series:
        return None
    last = datetime.fromisoformat(series[-1]["d"]).date()
    sigma = window / 3.0
    num = den = 0.0
    for p in series:
        dt = (datetime.fromisoformat(p["d"]).date() - last).days
        if abs(dt) > window:
            continue
        w = math.exp(-0.5 * (dt / sigma) ** 2)
        num += w * p["kg"]
        den += w
    return round(num / den, 2) if den else None


def goal_block(series):
    """Where the body weight sits against the target band, and how far it has come."""
    goal = {"low": GOAL_LOW_KG, "high": GOAL_HIGH_KG}
    if not series:
        return goal
    latest = series[-1]
    smooth = smoothed_weight(series)
    goal["latest_kg"] = latest["kg"]          # the reading itself
    goal["latest_date"] = latest["d"]
    goal["smooth_kg"] = smooth                # the best estimate of where you are
    goal["smooth_window_days"] = SMOOTH_WINDOW_DAYS
    goal["to_goal_kg"] = round(smooth - GOAL_HIGH_KG, 1)
    goal["reached"] = smooth <= GOAL_HIGH_KG
    goal["in_band"] = goal["reached"]        # kept for older page builds

    # The start of the cut is the highest reading in the year before the latest one.
    year_ago = (datetime.fromisoformat(latest["d"]).date()
                - timedelta(days=365)).isoformat()
    window = [p for p in series if p["d"] >= year_ago] or series
    peak = max(window, key=lambda p: p["kg"])
    goal["peak_kg"] = peak["kg"]
    goal["peak_date"] = peak["d"]
    goal["lost_kg"] = round(peak["kg"] - smooth, 1)
    total = peak["kg"] - GOAL_HIGH_KG
    goal["progress_pct"] = round(100 * min(1.0, max(0.0, (peak["kg"] - smooth) / total)), 1) \
        if total > 0 else 100.0
    return goal


def milestones(series, goal):
    """Percentage-lost markers from the peak, plus the goal band as the last one.

    Fixed and evenly spaced, so each one arrives as its own event rather than
    moving with the data.
    """
    if not series or "peak_kg" not in goal:
        return []
    peak, peak_date = goal["peak_kg"], goal["peak_date"]
    after = [p for p in series if p["d"] >= peak_date]
    out = []
    for pct in MILESTONE_PCTS:
        kg = round(peak * (1 - pct / 100.0), 1)
        hit = next((p for p in after if p["kg"] <= kg), None)
        out.append({"pct": pct, "kg": kg, "label": "%g%% lost" % pct,
                    "hit": hit is not None,
                    "date": hit["d"] if hit else None,
                    "goal": False})
    goal_pct = round(100 * (peak - goal["high"]) / peak, 1)
    hit = next((p for p in after if p["kg"] <= goal["high"]), None)
    out.append({"pct": goal_pct, "kg": goal["high"], "label": "goal",
                "hit": hit is not None,
                "date": hit["d"] if hit else None,
                "goal": True})
    out.sort(key=lambda m: m["pct"])
    return out


def milestone_facts(ms, series):
    f = {}
    if not ms:
        return f
    done = [m for m in ms if m["hit"]]
    todo = [m for m in ms if not m["hit"]]
    f["milestones_hit"] = "%d of %d" % (len(done), len(ms))
    if done:
        f["last_milestone"] = done[-1]["label"]
        f["last_milestone_date"] = done[-1]["date"]
    if todo and series:
        nxt = todo[0]
        f["next_milestone"] = nxt["label"]
        f["next_milestone_kg"] = "%.1f kg" % nxt["kg"]
        f["to_next_milestone"] = "%.1f kg" % (series[-1]["kg"] - nxt["kg"])
    return f


def bodyweight_series(weights):
    """Body weight per day in kg, oldest first.

    A re-weigh minutes later replaces the reading rather than averaging with
    it; readings hours apart are separate measurements and do average.
    """
    by_day = daily_weights(weights.get("values", []))
    return [{"d": d.isoformat(), "kg": round(kg, 2)}
            for d, kg in sorted(by_day.items())]


# --------------------------------------------------------------- narrative

def _fmt(n):
    return "{:,}".format(int(round(n)))


def _hour(h):
    return "%02d:00" % h


def build_facts(sessions, m, cal, lay, mon, yrs, cats, reps, e1rm, bw, life, dow):
    """Every number a deck quotes, pre-formatted. No arithmetic in the page."""
    f = {}
    first_year, this_year = yrs[0]["y"], yrs[-1]["y"]
    f["years"] = str(m["years"])
    f["first_year"] = str(first_year)
    f["this_year"] = str(this_year)
    f["exercises"] = str(m["exercises"])
    f["active_now"] = str(m["active_now"])

    # consistency
    first, last = sessions[0]["date"], sessions[-1]["date"]
    f["weeks_trained"] = _fmt(len(cal))
    f["weeks_total"] = _fmt((last - first).days // 7 + 1)
    f["layoff_count"] = str(len(lay))
    if lay:
        worst = max(lay, key=lambda g: g["days"])
        wd = datetime.fromisoformat(worst["from"]).date()
        f["worst_layoff"] = "%d-day stop from %d %s %d" % (
            worst["days"], wd.day, MONTH_NAMES[wd.month - 1], wd.year)
    gaps_by_year = Counter(int(g["from"][:4]) for g in lay)
    if gaps_by_year:
        frag, n = gaps_by_year.most_common(1)[0]
        f["frag_year"] = str(frag)
        f["frag_year_gaps"] = str(n)

    # frequency
    peak = max(mon, key=lambda x: x["sessions"])
    pd = datetime.strptime(peak["m"], "%Y-%m")
    f["peak_month_sessions"] = str(peak["sessions"])
    f["peak_month"] = "%s %d" % (MONTH_NAMES[pd.month - 1], pd.year)
    f["avg12_now"] = "%.1f" % mon[-1]["avg12"]
    f["avg12_low"] = "%.1f" % min(x["avg12"] for x in mon[11:]) if len(mon) > 11 else "—"
    f["ytd_sessions"] = str(yrs[-1]["sessions"])
    if len(yrs) > 1:
        f["last_year"] = str(yrs[-2]["y"])
        f["last_year_sessions"] = str(yrs[-2]["sessions"])

    # session shape
    f["median_session"] = "%d minutes" % yrs[-1]["median_min"]
    f["spy_first"] = "%.1f" % yrs[0]["spy"]
    low = min(yrs, key=lambda y: y["spy"])
    f["spy_min"] = "%.1f" % low["spy"]
    f["spy_min_year"] = str(low["y"])
    f["spy_now"] = "%.1f" % yrs[-1]["spy"]
    hi = max(yrs, key=lambda y: y["bw_share"])
    f["bw_peak"] = "%.0f%%" % hi["bw_share"]
    f["bw_peak_year"] = str(hi["y"])
    f["bw_now"] = "%.0f%%" % yrs[-1]["bw_share"]

    # balance
    idx = cats["years"].index(this_year)
    big3 = sum(cats["byYear"][c][idx] for c in ("Back", "Shoulders", "Chest"))
    all_big3 = sum(sum(cats["raw"][c]) for c in ("Back", "Shoulders", "Chest"))
    all_total = sum(sum(cats["raw"][c]) for c in CATEGORIES)
    f["big3_share"] = "%.0f%%" % (100 * all_big3 / all_total) if all_total else "—"
    f["big3_share_now"] = "%.0f%%" % big3
    f["leg_sets"] = _fmt(sum(cats["raw"]["Legs"]))
    f["leg_share_now"] = "%.1f%%" % cats["byYear"]["Legs"][idx]
    f["leg_share_first"] = "%.1f%%" % cats["byYear"]["Legs"][0]

    # rep ranges
    f["mid_share"] = "%.0f%%" % reps["overall"]["9–12"]
    f["heavy_share"] = "%.0f%%" % reps["overall"]["1–5"]
    f["heavy_first"] = "%.1f%%" % reps["byYear"]["1–5"][0]
    f["heavy_now"] = "%.1f%%" % reps["byYear"]["1–5"][-1]

    # strength
    if e1rm:
        best = max(e1rm, key=lambda p: p["best"])
        f["best_lift"] = best["name"]
        f["best_e1rm"] = "%.1f kg" % best["best"]
        f["best_year"] = best["best_date"][:4]
        f["e1rm_panels"] = str(len(e1rm))
        recent = [p for p in e1rm if p["best_date"][:4] == str(this_year)]
        f["e1rm_pb_now"] = str(len(recent))

    # bodyweight movements
    if bw["order"]:
        top = bw["order"][0]
        series = bw["reps"][top]
        peak_i = series.index(max(series))
        f["bw_top"] = top
        f["bw_top_peak"] = _fmt(max(series))
        f["bw_top_peak_year"] = str(bw["years"][peak_i])
        f["bw_top_now"] = _fmt(series[-1])
        f["bw_total_now"] = _fmt(sum(bw["reps"][n][-1] for n in bw["order"]))

    # rotation
    span_days = (last - first).days
    long_runners = sum(1 for r in life
                       if (datetime.fromisoformat(r["last"]).date()
                           - datetime.fromisoformat(r["first"]).date()).days
                       > span_days * 0.9)
    f["long_runners"] = str(long_runners)
    f["tracked_exercises"] = str(len(life))

    # timing
    by_year_hour = defaultdict(list)
    for ses in sessions:
        by_year_hour[ses["date"].year].append(ses["local"].hour)
    f["hour_first"] = _hour(int(_median(by_year_hour[first_year])))
    f["hour_now"] = _hour(int(_median(by_year_hour[this_year])))
    per_day = [sum(row) for row in dow]
    top_i = per_day.index(max(per_day))
    low_i = per_day.index(min(per_day))
    f["top_dow"] = DOW_NAMES[top_i]
    f["top_dow_n"] = str(per_day[top_i])
    f["low_dow"] = DOW_NAMES[low_i]
    f["low_dow_n"] = str(per_day[low_i])
    return f


def goal_facts(goal):
    f = {}
    f["goal_band"] = "%g kg" % goal["high"]
    if "latest_kg" not in goal:
        return f
    f["weight_now"] = "%.1f kg" % goal["smooth_kg"]
    f["weight_reading"] = "%.1f kg" % goal["latest_kg"]
    f["weight_date"] = goal["latest_date"]
    f["to_goal"] = ("reached" if goal["reached"]
                    else "%.1f kg" % abs(goal["to_goal_kg"]))
    f["lost_so_far"] = "%.1f kg" % goal["lost_kg"]
    f["peak_kg"] = "%.1f kg" % goal["peak_kg"]
    f["peak_date"] = goal["peak_date"]
    f["progress_pct"] = "%.0f%%" % goal["progress_pct"]
    return f


def volume_facts(vol, recent, watch):
    last = vol["latest"]
    prev = last - 1
    f = {}
    f["week_of"] = vol["weeks"][last]
    f["current_week_empty"] = "yes" if vol["current_week_empty"] else "no"
    total_now = vol["performed"][last]
    total_prev = vol["performed"][prev] if prev >= 0 else 0
    f["sets_this_week"] = "%g" % round(total_now, 1)
    f["sets_last_week"] = "%g" % round(total_prev, 1)
    f["sets_wow"] = ("%+g" % round(total_now - total_prev, 1)) if prev >= 0 else "—"
    f["sessions_this_week"] = str(vol["sessions"][last])
    f["tonnage_this_week"] = "{:,} kg".format(
        sum(vol["tonnage"][g][last] for g in BROAD_GROUPS))

    f["synergist_credit"] = str(SYNERGIST_CREDIT)
    states = {g: state(g, vol["sets"][g][last]) for g in BROAD_GROUPS}
    in_band = sum(1 for g in BROAD_GROUPS if states[g] in ("in MAV", "near MRV"))
    f["groups_in_mav"] = "%d of %d" % (in_band, len(BROAD_GROUPS))
    under = [g for g in BROAD_GROUPS if states[g] in ("under MEV", "none")]
    over = [g for g in BROAD_GROUPS if states[g] == "over MRV"]
    f["groups_under_mev"] = ", ".join(under) if under else "none"
    f["groups_over_mrv"] = ", ".join(over) if over else "none"
    f["groups_in_band"] = "%d of %d" % (in_band, len(BROAD_GROUPS))
    for g in VTAPER:
        f["v_" + g.lower()] = ("%g" % vol["sets"][g][last])
        f["v_" + g.lower() + "_wow"] = \
            ("%+g" % round(vol["sets"][g][last] - vol["sets"][g][prev], 1)) \
            if prev >= 0 else "—"

    if recent:
        f["last_session"] = recent[-1]["d"]
        f["last_session_sets"] = str(recent[-1]["sets"])
        span = [s["sets"] for s in recent]
        f["sets_per_session_recent"] = "%.1f" % (sum(span) / len(span))
    if watch:
        held = sum(1 for w in watch if w["delta_pct"] >= 0)
        f["lifts_watched"] = str(len(watch))
        f["lifts_holding"] = str(held)
        f["watch_worst"] = "%s %+.1f%%" % (watch[-1]["name"], watch[-1]["delta_pct"])
        f["watch_best"] = "%s %+.1f%%" % (watch[0]["name"], watch[0]["delta_pct"])
    return f


def notes(m, cats, sessions):
    zero = sum(1 for ses in sessions for _n, s in all_sets(ses) if s["weight_kg"] == 0)
    out = [
        {"k": "Warmups", "v": "Excluded everywhere. Only work sets count toward "
                              "sets, reps, tonnage and volume."},
        {"k": "Effective sets", "v": "A set counts 1.0 for every muscle group it "
                                     "targets and %g for every group it only assists, "
                                     "so a pull up credits back in full and biceps in "
                                     "part. The 10-20 weekly band is written on that "
                                     "basis. Weekly totals are therefore fractional, "
                                     "and every tooltip shows the direct and indirect "
                                     "split behind the number."
                                     % SYNERGIST_CREDIT},
        {"k": "Cardio", "v": "Incline Walking and Elliptical Machine record minutes, "
                             "not repetitions. Both are dropped from every set and "
                             "rep statistic."},
        {"k": "Clock time", "v": "Liftosaur stores every timestamp as UTC and drops "
                                 "the local offset. The timing section adds 5 hours "
                                 "30 minutes and reads as IST."},
        {"k": "Unloaded sets", "v": "%s of %s sets carry no external load. They count "
                                    "as sets and reps, and add nothing to tonnage."
                                    % (_fmt(zero), _fmt(m["sets"]))},
        {"k": "Estimated 1RM", "v": "Epley, weight × (1 + reps ÷ 30), best set per "
                                    "training day. Sets above 15 reps are excluded — "
                                    "the formula breaks down there. Machine and cable "
                                    "loads are excluded: a stack number is not "
                                    "comparable between gyms."},
        {"k": "Unilateral sets", "v": "A 1x8|8 entry is one set. The load is counted "
                                      "once, not twice."},
    ]
    if cats["unmapped"]:
        out.append({"k": "Unmapped", "v": "No muscle mapping for: "
                                          + ", ".join(cats["unmapped"]) + "."})
    return out


# --------------------------------------------------------------- assembly

def build(records, weights, customs, builtins, now=None):
    sessions = load_sessions(records)
    if not sessions:
        raise ValueError("no sessions parsed from history")
    if now is None:
        now = datetime.now(timezone.utc).date()

    names = {name for ses in sessions for name, _s in all_sets(ses)}
    cutoff = now - timedelta(days=365)
    active = {name for ses in sessions if ses["date"] >= cutoff
              for name, _s in all_sets(ses)}

    m = meta(sessions, len(active), len(names))
    cal = calendar_cells(sessions)
    lay = layoffs(sessions)
    mon = monthly(sessions)
    yrs = yearly(sessions)
    cats = category_shares(sessions, customs, builtins)
    reps = rep_shares(sessions)
    e1rm = e1rm_panels(sessions)
    bw = bodyweight_moves(sessions)
    life = lifespans(sessions, customs, builtins)
    dow = dow_matrix(sessions)
    series = bodyweight_series(weights)
    goal = goal_block(series)
    marks = milestones(series, goal)
    vol = weekly_volume(sessions, customs, builtins, now=now)
    recent = recent_sessions(sessions, customs, builtins)
    bodymap = muscle_week(sessions, customs, builtins)
    block = mesocycle(sessions, customs, builtins)
    watch = strength_watch(sessions, now)
    # weekly views anchor to the last week that holds training: on a Monday the
    # calendar week is empty and every reading off it would be a useless zero
    trained_through = sessions[-1]["date"]
    pats = pattern_series(sessions, trained_through)
    delts = delt_heads(sessions, trained_through)

    facts = build_facts(sessions, m, cal, lay, mon, yrs, cats, reps,
                        e1rm, bw, life, dow)
    facts.update(goal_facts(goal))
    facts.update(milestone_facts(marks, series))
    facts.update(volume_facts(vol, recent, watch))

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "meta": m,
        "goal": goal,
        "milestones": marks,
        "weekly": vol,
        "recent": recent,
        "bodyMap": bodymap,
        "block": block,
        "landmarks": LANDMARKS,
        "watch": watch,
        "patterns": pats,
        "delts": delts,
        "vtaper": VTAPER,
        "groups": BROAD_GROUPS,
        "facts": facts,
        "calendar": cal,
        "layoffs": lay,
        "months": mon,
        "years": yrs,
        "categories": cats,
        "reps": reps,
        "e1rm": e1rm,
        "bodyweightMoves": bw,
        "lifespans": life,
        "dow": dow,
        "weight": series,
        "notes": notes(m, cats, sessions),
    }


def main():
    with open("history.json") as f:
        records = json.load(f)["records"]
    with open("weights.json") as f:
        weights = json.load(f)
    with open("custom_exercises.json") as f:
        customs = {e["name"]: e for e in json.load(f)["exercises"]}
    with open("muscle_map.json") as f:
        builtins = json.load(f)

    report = build(records, weights, customs, builtins)
    with open("report.json", "w") as f:
        json.dump(report, f, separators=(",", ":"))
    print("report.json written — %d sessions, %d sets, %d exercises"
          % (report["meta"]["sessions"], report["meta"]["sets"],
             report["meta"]["exercises"]))


if __name__ == "__main__":
    main()
