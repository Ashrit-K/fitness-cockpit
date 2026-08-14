# Volume Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add training-volume analytics (weekly sets + tonnage per muscle group, target heatmap) to the weight-tracker GitHub Pages dashboard.

**Architecture:** Extend the existing fetch → chart → commit pipeline. New `fetch.py` pulls workout history + custom exercises from Liftosaur MCP. A vendored Liftosaur exercise DB (`data/exercises.ts`) provides built-in exercise → muscle mapping; `lifto_parse.py` parses Liftohistory text; `volume.py` aggregates to 10 broad muscle groups and renders 3 PNG charts.

**Tech Stack:** Python 3.12, matplotlib, numpy, GitHub Actions, GitHub Pages, JSON-RPC over HTTPS (Liftosaur MCP).

## Global Constraints

- All charts: seaborn white style (`plt.style.use("seaborn-v0_8-whitegrid")`), white background, major grid visible (`#d0d0d0`, lw 0.8), minor grid faint (`#f2f2f2`, lw 0.3), **no top spine, no right spine** (`ax.spines["top"].set_visible(False)`, same for `"right"`)
- 10 muscle groups, exact names: `Chest, Back, Shoulders, Biceps, Triceps, Quads, Hamstrings, Glutes, Core, Calves`
- Sets target band: 10–20 sets/week (green inside, yellow below, red above)
- Week bucketing: Monday-start weeks, computed from record UTC timestamps
- lb → kg: `lb * 0.453592`
- Unilateral `1x8|8` = 1 set, weight counted once
- Warmups excluded from all volume metrics
- Workflow cron: `30 2 * * *` (unchanged); secret `LIFTOSAUR_TOKEN`
- No top/right spines applies to ALL charts including existing weight chart

---

### Task 1: Vendor Liftosaur exercise DB + muscle map builder

**Files:**
- Create: `data/exercises.ts` (downloaded, committed verbatim)
- Create: `muscle_map.py`
- Create: `muscle_map.json` (generated artifact)

**Interfaces:**
- Consumes: nothing
- Produces: `muscle_map.json` — `{ "<exercise name incl. equipment suffix>": ["Muscle1", "Muscle2"] }` (target muscles only); custom exercises are NOT in this file (they override at runtime from `custom_exercises.json`)

- [ ] **Step 1: Download upstream DB**

```bash
curl -sL https://raw.githubusercontent.com/astashov/liftosaur/master/src/data/exercises.ts -o data/exercises.ts
wc -l data/exercises.ts
```

Expected: file exists, thousands of lines, contains `Lat Pulldown` and `Lateral Raise, Cable`.

- [ ] **Step 2: Inspect format**

```bash
grep -n "Lateral Raise, Cable\|Lat Pulldown" data/exercises.ts | head -5
```

Note the per-exercise structure (fields: name, equipment, targetMuscles, synergistMuscles, etc.). `muscle_map.py` must parse this TS file with regex, not TypeScript.

- [ ] **Step 3: Write `muscle_map.py`**

Parse `data/exercises.ts` and emit `muscle_map.json`:

```python
import json
import re

def load_exercises_ts(path="data/exercises.ts"):
    src = open(path).read()
    entries = []
    for block in re.findall(r"\{[^{}]*?\}", src):
        if "name:" not in block or "targetMuscles" not in block:
            continue
        name = re.search(r"name:\s*[\"']([^\"']+)[\"']", block)
        muscles = re.findall(r"[\"']([A-Z][A-Za-z ]+)[\"']\s*,", block)
        if not name or not muscles:
            continue
        entries.append((name.group(1), muscles))
    out = {}
    for name, muscles in entries:
        out[name] = muscles
    return out

if __name__ == "__main__":
    data = load_exercises_ts()
    with open("muscle_map.json", "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    print(f"mapped {len(data)} exercises")
```

- [ ] **Step 4: Run + verify coverage of known exercises**

```bash
python3 muscle_map.py
python3 -c "import json; m=json.load(open('muscle_map.json')); print(m.get('Lat Pulldown')); print(m.get('Lateral Raise, Cable')); print(m.get('Bench Press'))"
```

Expected: `Lat Pulldown` → includes `Latissimus Dorsi`; `Lateral Raise, Cable` → includes `Deltoid Lateral`; `Bench Press` → includes `Pectoralis Major Sternal Head`. If regex produces wrong/empty muscle lists, refine `muscles` regex against the real block structure (inspect with `grep -A 12 "name: \"Lat Pulldown\"" data/exercises.ts`).

- [ ] **Step 5: Commit**

```bash
git add data/exercises.ts muscle_map.py muscle_map.json
git commit -m "feat: vendor Liftosaur exercise DB and build muscle map"
```

---

### Task 2: Liftohistory parser

**Files:**
- Create: `lifto_parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: record text from `history.json` (Task 3)
- Produces:
  - `parse_record(text: str) -> dict` with keys: `date` (ISO str), `program`, `day_name`, `week`, `day_in_week`, `duration_s`, `exercises`: list of `{name, sets: [{reps, weight_kg, unilateral}], warmup_sets: [{reps, weight_kg, unilateral}]}`
  - Raises `ParseError` on malformed input (caller skips + warns)
  - `parse_weight(s: str) -> float` kg value (`"50kg"` → 50.0, `"152lb"` → 68.95)

- [ ] **Step 1: Write failing tests**

`tests/test_parse.py`:

```python
import pytest
from lifto_parse import parse_record, parse_weight, ParseError

SAMPLE = """2026-08-11 08:27:48 +00:00 / program: "4-Day V-Taper Full Body" / dayName: "Week 2 - Day 1 — V Pull + H Press" / week: 2 / dayInWeek: 1 / duration: 4143s / exercises: {
  // Going lighter to avoid inflaming left mild bicep
  Lat Pulldown / 1x8 50kg, 1x6 50kg, 1x7 47.5kg / warmup: 1x12 45kg, 1x12 47.5kg / target: 4x8-12 5kg @8 120s
  Reverse Lunge / 1x8|8 16kg, 2x9|9 16kg / warmup: 1x8|8 14kg / target: 4x8-12 16kg @8 30s
  Bird Dog / 2x4 0kg / target: 2x4 0kg 15s
}"""


def test_parse_weight():
    assert parse_weight("50kg") == 50.0
    assert parse_weight("152lb") == pytest.approx(68.95, abs=0.01)
    assert parse_weight("0kg") == 0.0


def test_parse_record_header():
    r = parse_record(SAMPLE)
    assert r["program"] == "4-Day V-Taper Full Body"
    assert r["week"] == 2
    assert r["day_in_week"] == 1
    assert r["duration_s"] == 4143
    assert len(r["exercises"]) == 3


def test_parse_sets_unilateral_and_warmup():
    r = parse_record(SAMPLE)
    pulldown = r["exercises"][0]
    assert pulldown["name"] == "Lat Pulldown"
    assert len(pulldown["sets"]) == 3
    assert pulldown["sets"][0] == {"reps": 8, "weight_kg": 50.0, "unilateral": False}
    assert len(pulldown["warmup_sets"]) == 2
    lunge = r["exercises"][1]
    assert lunge["sets"][0] == {"reps": 8, "weight_kg": 16.0, "unilateral": True}
    assert len(lunge["warmup_sets"]) == 1


def test_bodyweight_zero_kg():
    r = parse_record(SAMPLE)
    bird = r["exercises"][2]
    assert bird["sets"][0]["weight_kg"] == 0.0


def test_comment_lines_ignored():
    r = parse_record(SAMPLE)
    assert all("Going lighter" not in e["name"] for e in r["exercises"])


def test_malformed_raises():
    with pytest.raises(ParseError):
        parse_record("not a liftohistory record")
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python3 -m pytest tests/test_parse.py -v
```

Expected: all FAIL (module missing).

- [ ] **Step 3: Implement `lifto_parse.py`**

```python
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

SET_RE = re.compile(r"(\d+)x(\d+)(?:\|(\d+))?\s+([\d.]+)(kg|lb)")

def _parse_sets(text):
    out = []
    for m in SET_RE.finditer(text):
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
        work, _, rest = detail.partition(" / warmup:")
        warm = rest.partition(" / target:")[0].strip()
        exercises.append({
            "name": name.strip(),
            "sets": _parse_sets(work),
            "warmup_sets": _parse_sets(warm),
        })
    meta["exercises"] = exercises
    return meta
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python3 -m pytest tests/test_parse.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add lifto_parse.py tests/test_parse.py
git commit -m "feat: Liftohistory parser with unilateral/warmup/unit handling"
```

---

### Task 3: Fetch history + custom exercises (rename fetch_weights.py → fetch.py)

**Files:**
- Create: `fetch.py` (contents of current `fetch_weights.py`, extended)
- Delete: `fetch_weights.py`
- Test: `tests/test_muscle_groups.py` (not network — see Step 1 note)

**Interfaces:**
- Consumes: env `LIFTOSAUR_TOKEN`
- Produces: `weights.json` (unchanged shape), `history.json` — `{"records": [{"id": str, "text": str}]}`, `custom_exercises.json` — `{"exercises": [{"id", "name", "targetMuscles", "synergistMuscles", "types"}]}`

- [ ] **Step 1: Copy fetch_weights.py → fetch.py, extend**

```bash
cp fetch_weights.py fetch.py
git rm fetch_weights.py
```

Add two functions to `fetch.py` after the existing `get_all_weights`:

```python
def get_all_history():
    records = []
    cursor = None
    while True:
        args = {"limit": "200"}
        if cursor:
            args["cursor"] = cursor
        res = call("tools/call", {"name": "get_history", "arguments": args})
        content = json.loads(res["result"]["content"][0]["text"])
        records.extend(content["records"])
        if content.get("hasMore") and content.get("nextCursor"):
            cursor = content["nextCursor"]
        else:
            break
    return records


def get_custom_exercises():
    res = call("tools/call", {"name": "list_custom_exercises", "arguments": {}})
    return json.loads(res["result"]["content"][0]["text"])
```

Extend `main()`:

```python
def main():
    with open("weights.json", "w") as f:
        json.dump({"updated_at": None, "values": get_all_weights()}, f, indent=2)
    with open("history.json", "w") as f:
        json.dump({"records": get_all_history()}, f, indent=2)
    with open("custom_exercises.json", "w") as f:
        json.dump(get_custom_exercises(), f, indent=2)
    print("fetched weights + history + custom exercises")
```

- [ ] **Step 2: Run locally, verify outputs**

```bash
LIFTOSAUR_TOKEN=$LIFTOSAUR_TOKEN python3 fetch.py
python3 -c "import json; h=json.load(open('history.json')); print(len(h['records'])); print(h['records'][-1]['text'][:120])"
python3 -c "import json; c=json.load(open('custom_exercises.json')); print(len(c['exercises']))"
```

Expected: history record count > 50, custom exercises ≥ 2 (Bird Dog, Dead Bug).

- [ ] **Step 3: Commit**

```bash
git add fetch.py history.json custom_exercises.json
git rm --cached fetch_weights.py 2>/dev/null; git commit -m "feat: fetch workout history and custom exercises from Liftosaur"
```

---

### Task 4: Muscle group aggregation (`volume.py` core)

**Files:**
- Create: `volume.py` (aggregation only this task; charts in Task 5)
- Test: `tests/test_volume.py`

**Interfaces:**
- Consumes: `history.json`, `custom_exercises.json`, `muscle_map.json`, `lifto_parse.parse_record`
- Produces: `aggregate(history_path="history.json", custom_path="custom_exercises.json", map_path="muscle_map.json") -> dict` with keys:
  - `weeks`: list of ISO Monday dates (ascending, contiguous over last 8 weeks ending current week)
  - `groups`: dict group → list of 8 ints (sets per week)
  - `tonnage`: dict group → list of 8 floats (kg per week)
  - `warnings`: list of strings (unmapped exercises)

- [ ] **Step 1: Write failing tests**

`tests/test_volume.py` (fixtures built inline with tmp_path):

```python
import json
import pytest
from volume import aggregate, BROAD_GROUPS

def write(tmp, name, obj):
    p = tmp / name
    p.write_text(json.dumps(obj))
    return str(p)

def make_history(path):
    rec = {
        "records": [{"id": "1", "text": (
            "2026-08-11 08:27:48 +00:00 / program: \"P\" / dayName: \"D\" / week: 2 / dayInWeek: 1 / duration: 3600s / exercises: {\n"
            "  Bench Press / 3x8 60kg / target: 3x8-12 60kg @8 90s\n"
            "  Lat Pulldown / 3x10 50kg / warmup: 1x12 45kg / target: 3x8-12 50kg @8 90s\n"
            "  Mystery Lift / 2x10 20kg / target: 2x10 20kg @8 60s\n"
            "}"
        )}]
    }
    with open(path, "w") as f:
        json.dump(rec, f)

def test_broad_groups_const():
    assert set(BROAD_GROUPS) == {"Chest", "Back", "Shoulders", "Biceps",
        "Triceps", "Quads", "Hamstrings", "Glutes", "Core", "Calves"}

def test_aggregate_sets_and_tonnage(tmp_path):
    hp = write(tmp_path, "history.json", {})
    make_history(hp)
    cp = write(tmp_path, "custom_exercises.json", {"exercises": []})
    mp = write(tmp_path, "muscle_map.json", {
        "Bench Press": ["Pectoralis Major Sternal Head", "Triceps Brachii", "Deltoid Anterior"],
        "Lat Pulldown": ["Latissimus Dorsi", "Biceps Brachii"],
    })
    res = aggregate(history_path=hp, custom_path=cp, map_path=mp)
    i = -1  # last week = week containing 2026-08-11
    assert res["groups"]["Chest"][i] == 3
    assert res["groups"]["Back"][i] == 3
    assert res["groups"]["Triceps"][i] == 3
    assert res["groups"]["Biceps"][i] == 3
    assert res["groups"]["Shoulders"][i] == 3
    assert res["tonnage"]["Chest"][i] == pytest.approx(3 * 8 * 60.0)
    assert res["tonnage"]["Back"][i] == pytest.approx(3 * 10 * 50.0)

def test_warmup_excluded(tmp_path):
    hp = write(tmp_path, "history.json", {})
    make_history(hp)
    cp = write(tmp_path, "custom_exercises.json", {"exercises": []})
    mp = write(tmp_path, "muscle_map.json", {
        "Bench Press": ["Pectoralis Major Sternal Head"],
        "Lat Pulldown": ["Latissimus Dorsi"],
        "Mystery Lift": ["Latissimus Dorsi"],
    })
    res = aggregate(history_path=hp, custom_path=cp, map_path=mp)
    assert res["groups"]["Back"][-1] == 5  # 3 pulldown + 2 mystery, no warmup
    assert res["groups"]["Chest"][-1] == 3

def test_unmapped_warning(tmp_path):
    hp = write(tmp_path, "history.json", {})
    make_history(hp)
    cp = write(tmp_path, "custom_exercises.json", {"exercises": []})
    mp = write(tmp_path, "muscle_map.json", {
        "Bench Press": ["Pectoralis Major Sternal Head"],
        "Lat Pulldown": ["Latissimus Dorsi"],
    })
    res = aggregate(history_path=hp, custom_path=cp, map_path=mp)
    assert any("Mystery Lift" in w for w in res["warnings"])
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python3 -m pytest tests/test_volume.py -v
```

Expected: FAIL (module missing).

- [ ] **Step 3: Implement aggregation core in `volume.py`**

```python
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
              map_path="muscle_map.json"):
    with open(history_path) as f:
        records = json.load(f)["records"]
    with open(custom_path) as f:
        customs = {e["name"]: e for e in json.load(f)["exercises"]}
    with open(map_path) as f:
        builtins = json.load(f)

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
                muscles = custom.get("targetMuscles") or custom.get("synergistMuscles")
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
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python3 -m pytest tests/test_volume.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add volume.py tests/test_volume.py
git commit -m "feat: weekly sets/tonnage aggregation by muscle group"
```

---

### Task 5: Volume charts (stacked bars + target heatmap)

**Files:**
- Modify: `volume.py` (add `main()` + chart functions)
- Test: `tests/test_charts.py`

**Interfaces:**
- Consumes: `aggregate()` (Task 4)
- Produces: `chart_sets.png`, `chart_tonnage.png`, `chart_targets.png`, `volume_stats.json` — `{"updated_at", "weeks", "sets": groups, "tonnage": groups, "warnings"}`

- [ ] **Step 1: Write failing tests**

`tests/test_charts.py`:

```python
import json
import os
import pytest
import volume


@pytest.fixture
def agg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return volume


def test_main_generates_artifacts(agg):
    agg.main()
    for name in ["chart_sets.png", "chart_tonnage.png", "chart_targets.png",
                 "volume_stats.json"]:
        assert os.path.exists(name), name
        assert os.path.getsize(name) > 100, name
    stats = json.load(open("volume_stats.json"))
    assert set(stats["sets"]) == set(volume.BROAD_GROUPS)
    assert "warnings" in stats
```

- [ ] **Step 2: Run tests, verify fail**

```bash
python3 -m pytest tests/test_charts.py -v
```

Expected: FAIL (`main` missing).

- [ ] **Step 3: Implement charts + `main()` in `volume.py`**

Append to `volume.py`:

```python
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

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
            ax.text(c, r, f"{mat[r, c]:.0f}", ha="center", va="center",
                    fontsize=9)
    ax.set_xticks(range(len(weeks)))
    ax.set_xticklabels(labels)
    ax.set_yticks(range(len(BROAD_GROUPS)))
    ax.set_yticklabels(BROAD_GROUPS)
    ax.set_title("Sets per muscle group per week (green = 10–20 target range)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=140, facecolor="white")
    plt.close(fig)


def main():
    res = aggregate()
    _stacked_bars(res, "sets", "Weekly sets by muscle group", "sets",
                  "chart_sets.png")
    _stacked_bars(res, "tonnage", "Weekly tonnage by muscle group", "kg",
                  "chart_tonnage.png")
    _heatmap(res, "chart_targets.png")
    with open("volume_stats.json", "w") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": res["weeks"],
            "sets": res["sets"] if "sets" in res else res["groups"],
            "tonnage": res["tonnage"],
            "warnings": res["warnings"],
        }, f, indent=2)
    print("volume charts saved")


if __name__ == "__main__":
    main()
```

Note: `res["sets"]` fallback — `aggregate()` returns `groups`; update `main()` to read `res["groups"]` consistently: use `res["sets"] = res.pop("groups")` before calling helpers. Adjust in Step 3 code accordingly (write it with `res["sets"] = res.pop("groups")`).

- [ ] **Step 4: Run tests, verify pass**

```bash
python3 -m pytest tests/test_charts.py -v
```

Expected: PASS (fixtures absent → aggregation of empty/whatever history.json exists locally; test only asserts artifacts).

- [ ] **Step 5: Commit**

```bash
git add volume.py tests/test_charts.py chart_sets.png chart_tonnage.png chart_targets.png volume_stats.json
git commit -m "feat: volume charts — stacked sets/tonnage + target heatmap"
```

---

### Task 6: Weight chart updates (spines + full history + Jul 2026 zoom)

**Files:**
- Modify: `chart.py`

**Interfaces:**
- Consumes: `weights.json`
- Produces: `chart.png`, `stats.json` (existing shapes, plus `history_start` field)

- [ ] **Step 1: Apply spine removal + panel adjustments**

In `chart.py`:
1. In the loop `for ax in (ax1, ax2):` add `ax.spines["top"].set_visible(False)` and `ax.spines["right"].set_visible(False)`.
2. Panel 1 (`ax1`): keep plotting ALL daily-averaged records (already does — earliest record 2018-02-23). Change title to `"Body weight — full history"`.
3. Panel 2 (`ax2`): change cut window filter from `d >= datetime(2026, 7, 1)` — keep as-is (Jul 2026 zoom). Verify title says `Current cut window (Jul 2026 → now)`.
4. In `stats.json` add `"history_start": str(dates[0])` if `dates`.

- [ ] **Step 2: Run + verify**

```bash
python3 chart.py
```

Expected: `chart saved; trend=... kg/wk` printed; `chart.png` regenerated.

- [ ] **Step 3: Commit**

```bash
git add chart.py chart.png stats.json
git commit -m "style: no top/right spines; full history panel + Jul 2026 zoom"
```

---

### Task 7: Dashboard page update

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `chart.png`, `chart_sets.png`, `chart_tonnage.png`, `chart_targets.png`, `stats.json`, `volume_stats.json`

- [ ] **Step 1: Rewrite body sections**

Replace the single `<img>` block with sections:

```html
<h1>Weight Tracker</h1>
<div class="meta">Last updated: <span id="updated">—</span> · Latest: <span id="latest">—</span> kg · Trend: <span id="trend">—</span> kg/week · Target: −0.45 kg/week</div>

<h2>Weight</h2>
<img src="chart.png" alt="Weight trend">

<h2>Volume — Sets</h2>
<img src="chart_sets.png" alt="Weekly sets by muscle group">

<h2>Volume — Tonnage</h2>
<img src="chart_tonnage.png" alt="Weekly tonnage by muscle group">

<h2>Sets vs Target</h2>
<img src="chart_targets.png" alt="Sets per muscle group vs 10-20 target">
```

Update the fetch block to also load `volume_stats.json` and print warnings:

```js
fetch("stats.json").then(r => r.json()).then(s => {
  document.getElementById("updated").textContent = s.updated_at.replace("T", " ");
  document.getElementById("latest").textContent = s.latest_kg;
  document.getElementById("trend").textContent = (s.trend_kg_per_week ?? 0).toFixed(2);
}).catch(() => {});
fetch("volume_stats.json").then(r => r.json()).then(v => {
  if (v.warnings && v.warnings.length) {
    const p = document.createElement("p");
    p.className = "meta";
    p.textContent = "Warnings: " + v.warnings.slice(0, 10).join("; ");
    document.querySelector(".wrap").appendChild(p);
  }
}).catch(() => {});
```

CSS: add `h2 { font-size: 1.1rem; margin: 20px 0 8px; }`.

- [ ] **Step 2: Commit**

```bash
git add index.html
git commit -m "feat: dashboard sections for weight, sets, tonnage, targets"
```

---

### Task 8: Workflow update + deploy verification

**Files:**
- Modify: `.github/workflows/update.yml`

- [ ] **Step 1: Update workflow steps**

Replace the "Generate chart" step block with:

```yaml
      - name: Fetch data
        env:
          LIFTOSAUR_TOKEN: ${{ secrets.LIFTOSAUR_TOKEN }}
        run: python fetch.py

      - name: Build muscle map
        run: python muscle_map.py

      - name: Generate charts
        run: |
          python chart.py
          python volume.py

      - name: Run tests
        run: python -m pip install pytest && python -m pytest tests/ -q
```

Commit step: add `volume_stats.json chart_sets.png chart_tonnage.png chart_targets.png history.json custom_exercises.json muscle_map.json` to `git add`.

- [ ] **Step 2: Local end-to-end dry run**

```bash
LIFTOSAUR_TOKEN=<token> python3 fetch.py
python3 muscle_map.py
python3 chart.py
python3 volume.py
python3 -m pytest tests/ -q
```

Expected: all steps succeed; 4 PNGs + 4 JSON artifacts present.

- [ ] **Step 3: Commit + push + dispatch**

```bash
git add -A && git commit -m "ci: full analytics pipeline in daily workflow"
git push
gh workflow run update.yml --repo Ashrit-K/weight-tracker
```

- [ ] **Step 4: Verify live**

```bash
sleep 90
curl -sf https://ashrit-k.github.io/weight-tracker/stats.json
curl -sf https://ashrit-k.github.io/weight-tracker/volume_stats.json
curl -s -o /dev/null -w "%{http_code}\n" https://ashrit-k.github.io/weight-tracker/chart_sets.png
```

Expected: `stats.json` has `history_start` = 2018 date; `volume_stats.json` has 8 weeks; all images HTTP 200. Page shows 4 sections.

---

## Self-Review Notes

- Spec coverage: weight full-history + Jul 2026 zoom (Task 6), sets stacked (Task 5), tonnage stacked (Task 5), heatmap 10–20 band (Task 5), 10 broad groups (Task 4), vendored DB (Task 1), custom exercise override (Task 4), warmup exclusion (Task 2/4), unilateral (Task 2/4), lb→kg (Task 2), unmapped → warning (Task 4), spine removal everywhere (Tasks 5/6), daily cron (Task 8), error handling (warnings + pytest in CI).
- Placeholder scan: none.
- Type consistency: `aggregate()` returns `groups`/`tonnage`/`weeks`/`warnings`; Task 5 `main()` pops `groups` → `sets`; `volume_stats.json` uses `sets` key; `tests/test_charts.py` asserts `stats["sets"]`. Task 4 tests assert `res["groups"]`. Consistent.
