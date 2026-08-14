import json
from datetime import datetime, timedelta, timezone

from groups import BROAD_GROUPS, weighted_groups
from lifto_parse import parse_record, ParseError

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

    groups = {g: [0.0] * 8 for g in BROAD_GROUPS}
    direct = {g: [0] * 8 for g in BROAD_GROUPS}
    indirect = {g: [0] * 8 for g in BROAD_GROUPS}
    tonnage = {g: [0.0] * 8 for g in BROAD_GROUPS}
    session_dates = {i: set() for i in range(8)}
    performed = [0] * 8
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
        session_dates[i].add(dt.date().isoformat())
        for ex in parsed["exercises"]:
            sets = ex["sets"]
            if not sets:
                continue
            # A set counts 1.0 for a group it targets and 0.5 for one it assists,
            # and each group is credited once — the same rule report.py applies.
            credits = weighted_groups(ex["name"], customs, builtins)
            if not credits:
                warnings.append(f"unmapped: {ex['name']}")
                continue
            performed[i] += len(sets)
            n = len(sets)
            t = _tonnage(sets)
            for g, credit in credits.items():
                groups[g][i] += credit * n
                tonnage[g][i] += credit * t
                if credit == 1.0:
                    direct[g][i] += n
                else:
                    indirect[g][i] += n

    return {
        "weeks": [w.isoformat() for w in weeks],
        "groups": {g: [round(v, 1) for v in groups[g]] for g in BROAD_GROUPS},
        "direct": direct,
        "indirect": indirect,
        "tonnage": {g: [round(v, 1) for v in tonnage[g]] for g in BROAD_GROUPS},
        "performed": performed,
        "sessions": [len(session_dates[i]) for i in range(8)],
        "warnings": warnings,
    }


import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.style.use("seaborn-v0_8-whitegrid")

GROUP_COLORS = {
    "Chest": "#c53030", "Back": "#2b6cb0", "Shoulders": "#dd6b20",
    "Biceps": "#2f855a", "Triceps": "#805ad5", "Quads": "#3182ce",
    "Hamstrings": "#d69e2e", "Glutes": "#e53e3e", "Core": "#38a169",
    "Calves": "#718096",
}


def _style(ax):
    ax.set_facecolor("white")
    ax.set_axisbelow(True)
    ax.minorticks_on()
    ax.grid(True, which="major", color="#d0d0d0", lw=0.8)
    ax.grid(True, which="minor", color="#f2f2f2", lw=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _stacked_bars(res, key, title, ylabel, out):
    weeks = res["weeks"]
    labels = [w[5:] for w in weeks]  # MM-DD
    x = np.arange(len(weeks))
    fig, ax = plt.subplots(figsize=(14, 5.5))
    fig.patch.set_facecolor("white")
    bottom = np.zeros(len(weeks))
    for g in BROAD_GROUPS:
        vals = res[key][g]
        ax.bar(x, vals, bottom=bottom, label=g, color=GROUP_COLORS[g], width=0.7)
        bottom += np.array(vals, dtype=float)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend(ncol=5, loc="upper left", framealpha=0.9)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=140, facecolor="white")
    plt.close(fig)


def _heatmap(res, out):
    weeks = res["weeks"]
    labels = [w[5:] for w in weeks]
    mat = np.array([res["sets"][g] for g in BROAD_GROUPS], dtype=float)
    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("white")
    colors = np.empty(mat.shape, dtype=object)
    colors[mat < 10] = "#f6e05e"   # yellow: below
    colors[(mat >= 10) & (mat <= 20)] = "#48bb78"  # green: in range
    colors[mat > 20] = "#fc8181"   # red: above
    ax.imshow(np.ones(mat.shape), cmap="Greys", vmin=0, vmax=1)
    for r in range(mat.shape[0]):
        for c in range(mat.shape[1]):
            ax.add_patch(plt.Rectangle((c - 0.5, r - 0.5), 1, 1,
                         facecolor=colors[r, c], edgecolor="white", lw=2))
            ax.text(c, r, f"{mat[r, c]:g}", ha="center", va="center",
                    fontsize=9)
    ax.set_xticks(range(len(weeks)))
    ax.set_xticklabels(labels)
    ax.set_yticks(range(len(BROAD_GROUPS)))
    ax.set_yticklabels(BROAD_GROUPS)
    ax.set_title("Effective sets per muscle group per week "
                 "(green = 10–20 target range; assists count 0.5)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=140, facecolor="white")
    plt.close(fig)


def main():
    res = aggregate()
    res["sets"] = res.pop("groups")
    _stacked_bars(res, "sets", "Weekly effective sets by muscle group",
                  "effective sets", "chart_sets.png")
    _stacked_bars(res, "tonnage", "Weekly effective tonnage by muscle group", "kg",
                  "chart_tonnage.png")
    _heatmap(res, "chart_targets.png")
    with open("volume_stats.json", "w") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": res["weeks"],
            "sets": res["sets"],
            "direct": res["direct"],
            "indirect": res["indirect"],
            "tonnage": res["tonnage"],
            "performed": res["performed"],
            "sessions": res["sessions"],
            "warnings": sorted(set(res["warnings"])),
        }, f, indent=2)
    print("volume charts saved")


if __name__ == "__main__":
    main()
