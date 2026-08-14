"""Liftosaur muscle names to the shapes on the body figure.

The figure is drawn per muscle head, so the map is stated at that level: a
lateral raise lights the side deltoid, not "shoulders". Left and right are
always lit together — the log does not record a side.

Path data comes from github.com/vulovix/body-muscles (Apache-2.0). Only the
shapes are theirs; this mapping, the colour scale and the rendering are not.
"""

# One Liftosaur muscle -> the body shapes it covers, without the -left/-right
# suffix. Both sides are lit from the same value.
MUSCLE_TO_PARTS = {
    # shoulders, by head — the whole point of the figure
    "Deltoid Anterior": ["shoulder-front"],
    "Deltoid Lateral": ["shoulder-side"],
    "Deltoid Posterior": ["deltoid-rear"],

    # chest, upper and lower
    "Pectoralis Major Clavicular Head": ["chest-upper"],
    "Pectoralis Major Sternal Head": ["chest-lower"],
    "Serratus Anterior": ["serratus-anterior"],

    # back
    "Latissimus Dorsi": ["lats-upper", "lats-mid", "lats-lower"],
    "Trapezius Upper Fibers": ["traps-upper"],
    "Trapezius Middle Fibers": ["traps-mid"],
    "Trapezius Lower Fibers": ["traps-lower"],
    "Teres Major": ["lats-upper"],
    "Teres Minor": ["lats-upper"],
    "Infraspinatus": ["lats-upper"],
    "Erector Spinae": ["lower-back-erectors", "lower-back-ql", "spine"],
    "Levator Scapulae": ["nape"],
    "Splenius": ["nape"],
    "Sternocleidomastoid": ["neck"],

    # arms
    "Biceps Brachii": ["biceps"],
    "Brachialis": ["biceps"],
    "Brachioradialis": ["forearm", "forearm-flexors"],
    "Triceps Brachii": ["triceps-long", "triceps-lateral"],
    "Wrist Extensors": ["forearm-extensors"],
    "Wrist Flexors": ["forearm-flexors"],

    # core
    "Rectus Abdominis": ["abs-upper", "abs-lower"],
    "Obliques": ["obliques"],
    "Iliopsoas": ["hip-flexor"],

    # legs
    "Quadriceps": ["quads"],
    "Sartorius": ["quads"],
    "Hamstrings": ["hamstrings-medial", "hamstrings-lateral"],
    "Gluteus Maximus": ["gluteus-maximus"],
    "Gluteus Medius": ["gluteus-medius"],
    "Adductor Brevis": ["adductors"],
    "Adductor Longus": ["adductors"],
    "Adductor Magnus": ["adductors"],
    "Pectineous": ["adductors"],
    "Tensor Fasciae Latae": ["gluteus-medius"],
    "Gastrocnemius": ["calves-gastroc-medial", "calves-gastroc-lateral"],
    "Soleus": ["calves-soleus"],
    "Tibialis Anterior": ["tibialis-anterior"],
}
