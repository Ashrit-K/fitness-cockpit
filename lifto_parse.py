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
