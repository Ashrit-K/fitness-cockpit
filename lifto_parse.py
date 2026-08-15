import re

class ParseError(Exception):
    pass

LB_KG = 0.453592

def parse_weight(s):
    s = s.strip()
    if s.endswith("kg"):
        return float(s[:-2])
    if s.endswith("lb"):
        return float(s[:-2]) * LB_KG
    return float(s)

SET_RE = re.compile(r"(\d+)x(\d+)(?:\|(\d+))?\+?\s+([\d.]+)(kg|lb)")

def _parse_sets(text):
    out = []
    for m in SET_RE.finditer(text):
        for _ in range(int(m.group(1))):
            out.append({
                "reps": int(m.group(2)),
                "weight_kg": parse_weight(m.group(4) + m.group(5)),
                "unilateral": m.group(3) is not None,
            })
    return out

def parse_record(text):
    header, _, body = text.partition("exercises: {")
    if not body or not header.startswith("20"):
        raise ParseError("not a liftohistory record")
    meta = {}
    for key, pat in [
        ("program", r'program:\s*"([^"]+)"'),
        ("day_name", r'dayName:\s*"([^"]+)"'),
        ("week", r"week:\s*(\d+)"),
        ("day_in_week", r"dayInWeek:\s*(\d+)"),
        ("duration_s", r"duration:\s*(\d+)s"),
    ]:
        m = re.search(pat, header)
        meta[key] = (m.group(1) if m else None)
    meta["week"] = int(meta["week"]) if meta["week"] else None
    meta["day_in_week"] = int(meta["day_in_week"]) if meta["day_in_week"] else None
    meta["duration_s"] = int(meta["duration_s"]) if meta["duration_s"] else None
    meta["date"] = header.split(" / ")[0].strip()

    exercises = []
    for block in re.split(r"\n\s{2}(?=[A-Z])", body.strip()):
        if block.startswith("//"):
            continue
        name, _, detail = block.partition(" / ")
        detail = re.sub(r"\s*//.*$", "", detail, flags=re.M)
        work_part, sep, after = detail.partition(" / warmup:")
        warm = after.partition(" / target:")[0].strip() if sep else ""
        work = work_part.partition(" / target:")[0].strip()
        exercises.append({
            "name": name.strip(),
            "sets": _parse_sets(work),
            "warmup_sets": _parse_sets(warm),
        })
    meta["exercises"] = exercises
    return meta


REWEIGH_MINUTES = 15


def daily_weights(values, reweigh_minutes=REWEIGH_MINUTES):
    """Day -> body weight in kg, collapsing re-weighs.

    Two readings minutes apart are one weigh-in done twice — you stepped off
    and stepped back on because you doubted the first — so the later one wins.
    Readings hours apart are genuinely separate measurements and are averaged,
    which is what keeps a morning and an evening reading from fighting.

    `values` are dicts with a `date` (ISO) and a `value` ("69.5kg" / "152lb").
    """
    from datetime import datetime

    by_day = {}
    for v in values:
        raw = v.get("value")
        if not raw:
            continue
        try:
            kg = parse_weight(str(raw))
        except ValueError:
            continue
        try:
            dt = datetime.fromisoformat(str(v["date"]).replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        by_day.setdefault(dt.date(), []).append((dt, kg))

    out = {}
    for day, readings in by_day.items():
        readings.sort()
        kept = []
        for dt, kg in readings:
            if kept and (dt - kept[-1][0]).total_seconds() <= reweigh_minutes * 60:
                kept[-1] = (dt, kg)      # same weigh-in, later reading wins
            else:
                kept.append((dt, kg))
        out[day] = sum(k for _d, k in kept) / len(kept)
    return out
