import json
import pytest
from datetime import datetime
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
    res = aggregate(history_path=hp, custom_path=cp, map_path=mp,
                    now=datetime(2026, 8, 14).date())
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
    res = aggregate(history_path=hp, custom_path=cp, map_path=mp,
                    now=datetime(2026, 8, 14).date())
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
    res = aggregate(history_path=hp, custom_path=cp, map_path=mp,
                    now=datetime(2026, 8, 14).date())
    assert any("Mystery Lift" in w for w in res["warnings"])

def test_custom_exercise_targets_only(tmp_path):
    hp = write(tmp_path, "history.json", {})
    rec = {"records": [{"id": "1", "text": (
        "2026-08-11 08:27:48 +00:00 / program: \"P\" / dayName: \"D\" / week: 2 / dayInWeek: 1 / duration: 3600s / exercises: {\n"
        "  Bird Dog / 2x4 0kg / target: 2x4 0kg 15s\n"
        "}"
    )}]}
    with open(hp, "w") as f:
        json.dump(rec, f)
    cp = write(tmp_path, "custom_exercises.json", {"exercises": [
        {"id": "x", "name": "Bird Dog",
         "targetMuscles": ["Erector Spinae", "Gluteus Maximus"],
         "synergistMuscles": ["Obliques"]}
    ]})
    mp = write(tmp_path, "muscle_map.json", {})
    res = aggregate(history_path=hp, custom_path=cp, map_path=mp,
                    now=datetime(2026, 8, 14).date())
    assert res["groups"]["Back"][-1] == 2      # Erector Spinae
    assert res["groups"]["Glutes"][-1] == 2    # Gluteus Maximus
    assert res["groups"]["Core"][-1] == 0      # Obliques is synergist — excluded
