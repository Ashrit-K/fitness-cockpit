import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from lifto_parse import parse_record, ParseError

BROAD_GROUPS = ["Chest", "Back", "Shoulders", "Biceps", "Triceps",
                "Quads", "Hamstrings", "Glutes", "Core", "Calves"]

MUSCLE_TO_GROUP = {
    "Pectoralis Major Clavicular Head": "Chest",
    "Pectoralis Major Sternal Head": "Chest",
    "Serratus Anterior": "Chest",
    "Latissimus Dorsi": "Back",
    "Trapezius Lower Fibers": "Back",
    "Trapezius Middle Fibers": "Back",
    "Trapezius Upper Fibers": "Back",
    "Teres Major": "Back",
    "Teres Minor": "Back",
    "Infraspinatus": "Back",
    "Erector Spinae": "Back",
    "Levator Scapulae": "Back",
    "Splenius": "Back",
    "Deltoid Anterior": "Shoulders",
    "Deltoid Lateral": "Shoulders",
    "Deltoid Posterior": "Shoulders",
    "Biceps Brachii": "Biceps",
    "Brachialis": "Biceps",
    "Brachioradialis": "Biceps",
    "Triceps Brachii": "Triceps",
    "Quadriceps": "Quads",
    "Sartorius": "Quads",
    "Hamstrings": "Hamstrings",
    "Gluteus Maximus": "Glutes",
    "Gluteus Medius": "Glutes",
    "Adductor Brevis": "Glutes",
    "Adductor Longus": "Glutes",
    "Adductor Magnus": "Glutes",
    "Pectineous": "Glutes",
    "Tensor Fasciae Latae": "Glutes",
    "Rectus Abdominis": "Core",
    "Obliques": "Core",
    "Iliopsoas": "Core",
    "Gastrocnemius": "Calves",
    "Soleus": "Calves",
    "Tibialis Anterior": "Calves",
    "Sternocleidomastoid": "Back",
    "Wrist Extensors": "Biceps",
    "Wrist Flexors": "Biceps",
}

def monday(d):
    return d - timedelta(days=d.weekday())

def _tonnage(sets):
    return sum(s["reps"] * s["weight_kg"] for s in sets)

def aggregate(history_path="history.json", custom_path="custom_exercises.json",
              map_path="muscle_map.json", now=None):
    with open(history_path) as f:
        records = json.load(f)["records"]
    with open(custom_path) as f:
        customs = {e["name"]: e for e in json.load(f)["exercises"]}
    with open(map_path) as f:
        builtins = json.load(f)

    if now is None:
        now = datetime.now(timezone.utc).date()
    this_monday = monday(now)
    weeks = [this_monday - timedelta(weeks=7 - i) for i in range(8)]
    week_idx = {w.isoformat(): i for i, w in enumerate(weeks)}

    groups = {g: [0] * 8 for g in BROAD_GROUPS}
    tonnage = {g: [0.0] * 8 for g in BROAD_GROUPS}
    warnings = []

    for rec in records:
        try:
            parsed = parse_record(rec["text"])
        except ParseError as e:
            warnings.append(f"parse: {e}")
            continue
        try:
            dt = datetime.fromisoformat(parsed["date"].replace("Z", "+00:00"))
        except ValueError:
            warnings.append(f"date: {parsed['date']}")
            continue
        wk = monday(dt.date()).isoformat()
        if wk not in week_idx:
            continue
        i = week_idx[wk]
        for ex in parsed["exercises"]:
            custom = customs.get(ex["name"])
            muscles = None
            if custom:
                muscles = list(custom.get("targetMuscles") or []) + list(custom.get("synergistMuscles") or [])
            else:
                muscles = builtins.get(ex["name"])
            if not muscles:
                warnings.append(f"unmapped: {ex['name']}")
                continue
            sets = ex["sets"]
            if not sets:
                continue
            n = len(sets)
            t = _tonnage(sets)
            for m in muscles:
                g = MUSCLE_TO_GROUP.get(m)
                if g:
                    groups[g][i] += n
                    tonnage[g][i] += t

    return {
        "weeks": [w.isoformat() for w in weeks],
        "groups": groups,
        "tonnage": tonnage,
        "warnings": warnings,
    }
