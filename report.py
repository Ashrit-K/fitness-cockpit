"""Build report.json — every series the editorial page renders.

Reads the raw Liftosaur exports and emits one file of pre-computed statistics.
Each function takes data and returns data, so the tests never touch the disk.
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from groups import CATEGORIES, GROUP_TO_CATEGORY, groups_for
from lifto_parse import parse_record, ParseError

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


def e1rm_panels(sessions, limit=6, window=5):
    """Best estimated 1RM per training day, for the most-logged free-weight lifts."""
    days = defaultdict(dict)  # name -> date -> best e1rm
    for ses in sessions:
        for name, s in all_sets(ses):
            if not is_free_weight(name) or s["weight_kg"] <= 0 or s["reps"] > 15:
                continue
            v = epley(s["weight_kg"], s["reps"])
            cur = days[name].get(ses["date"])
            if cur is None or v > cur:
                days[name][ses["date"]] = v

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


def bodyweight_series(weights):
    """Daily-averaged body weight in kg, oldest first."""
    by_day = defaultdict(list)
    for v in weights.get("values", []):
        raw = v.get("value")
        if not raw:
            continue
        m = re.match(r"^([\d.]+)\s*(kg|lb)?$", str(raw).strip())
        if not m:
            continue
        kg = float(m.group(1)) * (0.453592 if m.group(2) == "lb" else 1.0)
        by_day[v["date"][:10]].append(kg)
    return [{"d": d, "kg": round(sum(v) / len(v), 2)}
            for d, v in sorted(by_day.items())]


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


def notes(m, cats, sessions):
    zero = sum(1 for ses in sessions for _n, s in all_sets(ses) if s["weight_kg"] == 0)
    out = [
        {"k": "Warmups", "v": "Excluded everywhere. Only work sets count toward "
                              "sets, reps, tonnage and volume."},
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

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "meta": m,
        "facts": build_facts(sessions, m, cal, lay, mon, yrs, cats, reps,
                             e1rm, bw, life, dow),
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
        "weight": bodyweight_series(weights),
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
