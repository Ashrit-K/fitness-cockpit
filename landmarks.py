"""Weekly volume landmarks per muscle group.

The programme follows the RP / Israetel model: start a block near MEV, add
sets week by week toward MRV, then deload. A single 10-20 band for every group
contradicts that — chest and side delts do not share a ceiling.

  MEV  minimum effective volume — below this a group is not growing
  MAV  maximum adaptive volume — the productive working range
  MRV  maximum recoverable volume — past this recovery fails

These are RP's published figures, rounded, and they are a starting point rather
than a measurement. Edit them here as the block teaches you your own numbers.

They are compared against *effective* sets — a set counts 1.0 for a group it
targets and 0.5 for one it only assists. That matches how the landmark model
counts: heavy back work is credited toward biceps rather than ignored, so a
block with no curls in it does not report zero biceps volume when every pull
in the week loaded them.

Direct sets stay visible alongside, because "12 effective, all of it indirect"
is a different training situation from "12 direct".
"""

LANDMARKS = {
    "Chest":      {"mev": 8,  "mav_low": 12, "mav_high": 20, "mrv": 22},
    "Back":       {"mev": 10, "mav_low": 14, "mav_high": 22, "mrv": 25},
    "Shoulders":  {"mev": 8,  "mav_low": 16, "mav_high": 22, "mrv": 26},
    "Biceps":     {"mev": 8,  "mav_low": 14, "mav_high": 20, "mrv": 26},
    "Triceps":    {"mev": 6,  "mav_low": 10, "mav_high": 14, "mrv": 18},
    "Quads":      {"mev": 8,  "mav_low": 12, "mav_high": 18, "mrv": 20},
    "Hamstrings": {"mev": 4,  "mav_low": 10, "mav_high": 16, "mrv": 20},
    "Glutes":     {"mev": 0,  "mav_low": 4,  "mav_high": 12, "mrv": 16},
    "Core":       {"mev": 0,  "mav_low": 16, "mav_high": 20, "mrv": 25},
    "Calves":     {"mev": 8,  "mav_low": 12, "mav_high": 16, "mrv": 20},
}


def state(group, sets):
    """Where a week's effective sets sit against that group's landmarks."""
    lm = LANDMARKS.get(group)
    if not lm:
        return "unknown"
    if sets <= 0:
        return "none"
    if sets < lm["mev"]:
        return "under MEV"
    if sets < lm["mav_low"]:
        return "at MEV"
    if sets <= lm["mav_high"]:
        return "in MAV"
    if sets <= lm["mrv"]:
        return "near MRV"
    return "over MRV"
