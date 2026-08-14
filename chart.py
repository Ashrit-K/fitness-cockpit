import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

plt.style.use("seaborn-v0_8-whitegrid")

LB_KG = 0.453592
TARGET_KG_PER_DAY = -0.4536 / 7


def parse_value(v):
    s = str(v).strip()
    if s.endswith("lb"):
        return float(s[:-2]) * LB_KG
    if s.endswith("kg"):
        return float(s[:-2])
    return float(s)


def load():
    with open("weights.json") as f:
        data = json.load(f)
    by_day = defaultdict(list)
    for rec in data["values"]:
        ts = rec["timestamp"]
        if isinstance(ts, str):
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        by_day[d.date()].append(parse_value(rec["value"]))
    days = sorted(by_day)
    dates = [datetime(d.year, d.month, d.day) for d in days]
    weights = [sum(by_day[d]) / len(by_day[d]) for d in days]
    return dates, weights


def dense_window(dates, weights):
    if not dates:
        return [], []
    end = len(dates) - 1
    start = end
    while start > 0 and (dates[start] - dates[start - 1]).days <= 2:
        start -= 1
    dense_dates = dates[start:]
    dense_weights = weights[start:]
    if len(dense_dates) < 3:
        return dates, weights
    return dense_dates, dense_weights


def main():
    dates, weights = load()
    dense_dates, dense_weights = dense_window(dates, weights)
    now = datetime.now(timezone.utc)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.patch.set_facecolor("white")

    history_start = dates[0] if dates else datetime(2025, 1, 1)
    ax1.plot(dates, weights, "o-", color="#2b6cb0", lw=1.5, ms=4)
    ax1.set_title("Body weight — history")
    ax1.set_ylabel("kg")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    for label in ax1.get_xticklabels():
        label.set_rotation(30)

    if dense_dates:
        x = np.array([(d - dense_dates[0]).days for d in dense_dates], dtype=float)
        y = np.array(dense_weights)
        slope, intercept = np.polyfit(x, y, 1)
        slope_wk = slope * 7

        xr = np.linspace(0, x.max() + 7, 50)
        trend_dates = [dense_dates[0] + timedelta(days=float(v)) for v in xr]
        ax2.plot(dense_dates, dense_weights, "o-", color="#c53030", lw=1.8, ms=6,
                 label="daily avg")
        ax2.plot(trend_dates, intercept + slope * xr, "--", color="#dd6b20",
                 label=f"current trend: {slope_wk:+.2f} kg/week")
        ax2.plot(trend_dates, dense_weights[0] + TARGET_KG_PER_DAY * xr, "--",
                 color="#2f855a",
                 label=f"target from {dense_dates[0]:%b %d}: 1 lb/week")
        ax2.set_title(
            f"Dense reporting window ({dense_dates[0]:%b %d} → {dense_dates[-1]:%b %d})"
        )
        ax2.legend()

    ax2.set_ylabel("kg")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    for label in ax2.get_xticklabels():
        label.set_rotation(30)

    for ax in (ax1, ax2):
        ax.set_facecolor("white")
        ax.set_axisbelow(True)
        ax.minorticks_on()
        ax.grid(True, which="major", color="#d0d0d0", lw=0.8)
        ax.grid(True, which="minor", color="#f2f2f2", lw=0.3)

    leg = ax2.get_legend()
    if leg:
        leg.get_frame().set_facecolor("white")
        leg.get_frame().set_alpha(0.9)
        leg.get_frame().set_edgecolor("#dddddd")

    fig.suptitle(f"Updated {now:%Y-%m-%d %H:%M} UTC", fontsize=9, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig("chart.png", dpi=140, facecolor="white")
    with open("stats.json", "w") as f:
        json.dump({
            "updated_at": now.isoformat(),
            "latest_kg": round(weights[-1], 2) if weights else None,
            "latest_date": str(dates[-1]) if dates else None,
            "dense_start": str(dense_dates[0]) if dense_dates else None,
            "trend_kg_per_week": round(slope_wk, 3) if dense_dates else None,
            "target_kg_per_week": -0.4536,
        }, f, indent=2)
    print(f"chart saved; trend={slope_wk:+.2f} kg/wk; n_dense={len(dense_dates)}")


if __name__ == "__main__":
    main()
