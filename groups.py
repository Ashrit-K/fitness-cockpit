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


# Equipment suffixes Liftosaur appends to a base exercise name.
EQUIPMENT_SUFFIXES = (", Leverage Machine", ", Smith Machine", ", Cable",
                      ", Dumbbell", ", Barbell", ", Kettlebell", ", Band",
                      ", Bodyweight")


def muscles_for(name, customs, builtins):
    """Target muscles for an exercise name. Custom exercises win over built-ins.

    A name the map does not hold is retried without its equipment suffix —
    the muscles a lift trains do not change with the equipment.
    """
    custom = customs.get(name)
    if custom:
        return list(custom.get("targetMuscles") or [])
    hit = builtins.get(name)
    if hit:
        return hit
    for suffix in EQUIPMENT_SUFFIXES:
        if name.endswith(suffix):
            base = name[:-len(suffix)]
            return customs.get(base, {}).get("targetMuscles") or builtins.get(base) or []
    return []


def groups_for(name, customs, builtins):
    """Broad muscle groups an exercise trains, de-duplicated, order preserved."""
    out = []
    for m in muscles_for(name, customs, builtins):
        g = MUSCLE_TO_GROUP.get(m)
        if g and g not in out:
            out.append(g)
    return out
