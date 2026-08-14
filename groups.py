"""Muscle-group constants and lookup, shared by volume.py and report.py."""

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

# Six reading categories for the share-by-year chart.
GROUP_TO_CATEGORY = {
    "Chest": "Chest",
    "Back": "Back",
    "Shoulders": "Shoulders",
    "Biceps": "Arms",
    "Triceps": "Arms",
    "Quads": "Legs",
    "Hamstrings": "Legs",
    "Glutes": "Legs",
    "Calves": "Legs",
    "Core": "Core",
}

CATEGORIES = ["Back", "Shoulders", "Chest", "Arms", "Legs", "Core"]

# The groups that build the V taper. These lead the volume view.
VTAPER = ["Back", "Shoulders", "Chest"]

# The weekly effective-sets band each group is aimed at.
TARGET_LOW = 10
TARGET_HIGH = 20


# Equipment suffixes Liftosaur appends to a base exercise name.
EQUIPMENT_SUFFIXES = (", Leverage Machine", ", Smith Machine", ", Cable",
                      ", Dumbbell", ", Barbell", ", Kettlebell", ", Band",
                      ", Bodyweight")


# A set counts fully for a muscle it targets and half for one it assists.
# The 10-20 weekly band is defined on that basis: direct sets plus part credit
# for indirect ones. Counting targets alone reads every press as no triceps
# work at all.
SYNERGIST_CREDIT = 0.5


def _entry(name, customs, builtins):
    """The raw map entry for an exercise, or None.

    A name the map does not hold is retried without its equipment suffix — the
    muscles a lift trains do not change with the equipment.
    """
    custom = customs.get(name)
    if custom:
        return {"target": list(custom.get("targetMuscles") or []),
                "synergist": list(custom.get("synergistMuscles") or [])}
    hit = builtins.get(name)
    if hit is None:
        for suffix in EQUIPMENT_SUFFIXES:
            if name.endswith(suffix):
                base = name[:-len(suffix)]
                return _entry(base, customs, builtins) if base != name else None
        return None
    # muscle_map.json used to be a flat list of target muscles.
    if isinstance(hit, list):
        return {"target": hit, "synergist": []}
    return {"target": list(hit.get("target") or []),
            "synergist": list(hit.get("synergist") or [])}


def muscles_for(name, customs, builtins):
    """Target muscles for an exercise name. Custom exercises win over built-ins."""
    e = _entry(name, customs, builtins)
    return e["target"] if e else []


def synergists_for(name, customs, builtins):
    """Assisting muscles for an exercise name, never repeating a target."""
    e = _entry(name, customs, builtins)
    if not e:
        return []
    return [m for m in e["synergist"] if m not in e["target"]]


def weighted_groups(name, customs, builtins):
    """{group: credit} for one set — 1.0 where it is targeted, 0.5 where assisted.

    A group is credited once at its highest claim, so an exercise listing two
    heads of one muscle does not count twice.
    """
    out = {}
    for m in synergists_for(name, customs, builtins):
        g = MUSCLE_TO_GROUP.get(m)
        if g:
            out[g] = SYNERGIST_CREDIT
    for m in muscles_for(name, customs, builtins):
        g = MUSCLE_TO_GROUP.get(m)
        if g:
            out[g] = 1.0
    return out


def groups_for(name, customs, builtins):
    """Broad muscle groups an exercise trains, de-duplicated, order preserved."""
    out = []
    for m in muscles_for(name, customs, builtins):
        g = MUSCLE_TO_GROUP.get(m)
        if g and g not in out:
            out.append(g)
    return out
