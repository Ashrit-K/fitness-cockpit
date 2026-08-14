"""The movement patterns the current block is actually judged on.

Muscle maps carry target muscles only, so indirect stimulus — front delts in a
chest press, rear delts in a row — cannot be derived from them. These lists say
it explicitly instead.

`names` are matched against the exercise name exactly as Liftosaur records it.
A name that never appears in the log is harmless: it contributes nothing.
"""

INCLINE_PRESS = [
    "Incline Bench Press",
    "Incline Bench Press, Dumbbell",
    "Incline Chest Press, Leverage Machine",
    "Bench Press",
    "Bench Press, Dumbbell",
    "Bench Press Close Grip",
    "Chest Press, Leverage Machine",
    "Push Up",
    "Deficit Push Up",
]

VERTICAL_PULL = [
    "Pull Up",
    "Chin Up",
    "Neutral Grip Pull Up",
    "Lat Pulldown",
    "Lat Pulldown, Leverage Machine",
    "Lat Pulldown Neutral",
    "Lat Pulldown Pronated Medium",
    "Lat Pulldown Pronated Wide",
    "Lat Pulldown Supinated",
    "Arch Hang",
]

ROW = [
    "Incline Row",
    "Seated Row, Leverage Machine",
    "Renegade Row",
]

DELT_LATERAL = [
    "Lateral Raise",
    "Lateral Raise, Cable",
    "Upright Row",
]

DELT_FRONT = [
    "Shoulder Press",
    "Shoulder Press, Leverage Machine",
    "Overhead Press",
    "Overhead Press, Dumbbell",
    "Arnold Press",
    "Arnold Press, Kettlebell",
    "Behind The Neck Press",
    "Front Raise",
]

DELT_REAR = [
    "Reverse Fly",
    "Reverse Fly, Leverage Machine",
    "Reverse Fly, Cable",
    "Face Pull",
]

# Cards, in the order they are read.
PATTERNS = [
    {
        "key": "incline_press",
        "label": "Incline / chest press",
        "note": "e1RM per lift, and pressing volume",
        "names": INCLINE_PRESS,
    },
    {
        "key": "vertical_pull",
        "label": "Vertical pull",
        "note": "pull ups, chin ups, neutral grip, pulldowns",
        "names": VERTICAL_PULL,
    },
    {
        "key": "row",
        "label": "Rowing",
        "note": "incline row and machine rows",
        "names": ROW,
    },
    {
        "key": "delt_lateral",
        "label": "Lateral delts",
        "note": "the head being pushed — volume is the driver, not load",
        "names": DELT_LATERAL,
    },
]

# Each delt head gets direct work and indirect work from other patterns.
DELT_HEADS = [
    {"key": "lateral", "label": "Lateral", "direct": DELT_LATERAL, "indirect": []},
    {"key": "front", "label": "Front", "direct": DELT_FRONT, "indirect": INCLINE_PRESS},
    {"key": "rear", "label": "Rear", "direct": DELT_REAR, "indirect": VERTICAL_PULL + ROW},
]
