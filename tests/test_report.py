import pytest

import report
from groups import muscles_for, synergists_for, weighted_groups


def rec(date, body, duration=3600):
    """Build one raw history record. `body` is the exercises block."""
    return {"id": date, "text": (
        f'{date} +00:00 / program: "P" / dayName: "D" / week: 1 / dayInWeek: 1 '
        f"/ duration: {duration}s / exercises: {{\n{body}\n}}"
    )}


def sessions(*records):
    return report.load_sessions(list(records))


# --------------------------------------------------------------- ingest

def test_cardio_excluded():
    s = sessions(rec("2026-01-05 09:00:00",
                     "  Incline Walking / 1x30 0kg\n  Bench Press / 3x8 60kg"))
    assert len(s) == 1
    assert [n for n, _ in report.all_sets(s[0])] == ["Bench Press"] * 3


def test_cardio_only_session_dropped():
    assert sessions(rec("2026-01-05 09:00:00", "  Incline Walking / 1x30 0kg")) == []


def test_warmups_excluded():
    s = sessions(rec("2026-01-05 09:00:00",
                     "  Bench Press / 2x8 60kg / warmup: 1x12 40kg"))
    assert report.n_sets(s[0]) == 2


def test_sessions_sorted_oldest_first():
    s = sessions(rec("2026-03-01 09:00:00", "  Bench Press / 1x8 60kg"),
                 rec("2026-01-01 09:00:00", "  Bench Press / 1x8 60kg"))
    assert [x["date"].month for x in s] == [1, 3]


# --------------------------------------------------------------- calendar

def test_calendar_buckets_by_iso_week():
    # 2026-01-05 and 2026-01-08 are both in ISO week 2 of 2026.
    s = sessions(rec("2026-01-05 09:00:00", "  Bench Press / 3x8 60kg"),
                 rec("2026-01-08 09:00:00", "  Bench Press / 2x8 60kg"))
    cells = report.calendar_cells(s)
    assert len(cells) == 1
    assert cells[0]["y"] == 2026 and cells[0]["w"] == 2
    assert cells[0]["n"] == 2 and cells[0]["s"] == 5
    assert cells[0]["d"] == "2026-01-05"   # the Monday of that week


def test_layoff_boundary_is_exclusive_at_21_days():
    body = "  Bench Press / 1x8 60kg"
    s = sessions(rec("2026-01-01 09:00:00", body),
                 rec("2026-01-22 09:00:00", body),   # exactly 21 days — not a layoff
                 rec("2026-02-20 09:00:00", body))   # 29 days — a layoff
    gaps = report.layoffs(s)
    assert len(gaps) == 1
    assert gaps[0] == {"from": "2026-01-22", "to": "2026-02-20", "days": 29}


def test_layoffs_use_distinct_days_not_records():
    body = "  Bench Press / 1x8 60kg"
    s = sessions(rec("2026-01-01 09:00:00", body),
                 rec("2026-01-01 18:00:00", body))
    assert report.layoffs(s) == []


# --------------------------------------------------------------- monthly

def test_monthly_fills_empty_months():
    body = "  Bench Press / 2x8 60kg"
    s = sessions(rec("2026-01-05 09:00:00", body),
                 rec("2026-04-05 09:00:00", body))
    mon = report.monthly(s)
    assert [m["m"] for m in mon] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert [m["sessions"] for m in mon] == [1, 0, 0, 1]


def test_monthly_avg12_is_trailing():
    body = "  Bench Press / 1x8 60kg"
    s = sessions(rec("2026-01-05 09:00:00", body),
                 rec("2026-02-05 09:00:00", body),
                 rec("2026-02-06 09:00:00", body))
    mon = report.monthly(s)
    assert mon[0]["avg12"] == 1.0          # one month, one session
    assert mon[1]["avg12"] == 1.5          # (1 + 2) / 2


# --------------------------------------------------------------- yearly

def test_yearly_bodyweight_share_and_density():
    s = sessions(rec("2026-01-05 09:00:00",
                     "  Pull Up / 3x8 0kg\n  Bench Press / 1x8 60kg", duration=3000))
    y = report.yearly(s)[0]
    assert y["sets"] == 4
    assert y["spy"] == 4.0
    assert y["bw_share"] == 75.0
    assert y["median_min"] == 50
    assert y["tonnage"] == pytest.approx(8 * 60)


# --------------------------------------------------------------- rep bins

@pytest.mark.parametrize("reps,expected", [
    (1, "1–5"), (5, "1–5"), (6, "6–8"), (8, "6–8"), (9, "9–12"),
    (12, "9–12"), (13, "13–20"), (20, "13–20"), (21, "21+"), (60, "21+"),
])
def test_rep_bin_edges(reps, expected):
    s = sessions(rec("2026-01-05 09:00:00", f"  Bench Press / 1x{reps} 60kg"))
    dist = report.rep_shares(s)
    assert dist["overall"][expected] == 100.0


# --------------------------------------------------------------- strength

def test_epley():
    assert report.epley(100, 0) == 100
    assert report.epley(60, 10) == pytest.approx(80.0)


@pytest.mark.parametrize("name,free", [
    ("Bench Press, Dumbbell", True),
    ("Overhead Press", True),
    ("Seated Row, Leverage Machine", False),
    ("Lateral Raise, Cable", False),
    ("Lat Pulldown", False),
    ("Triceps Pushdown", False),
])
def test_free_weight_filter(name, free):
    assert report.is_free_weight(name) is free


def _many(name, days, reps=10, weight=60):
    out = []
    for i in range(days):
        out.append(rec("2026-01-%02d 09:00:00" % (i + 1),
                       f"  {name} / 1x{reps} {weight}kg"))
    return out


def test_e1rm_needs_minimum_days():
    s = sessions(*_many("Bench Press", report.MIN_E1RM_DAYS - 1))
    assert report.e1rm_panels(s) == []


def test_e1rm_takes_best_set_of_the_day_and_skips_high_reps():
    days = _many("Bench Press", report.MIN_E1RM_DAYS)
    days[0] = rec("2026-01-01 09:00:00",
                  "  Bench Press / 1x10 60kg, 1x5 70kg, 1x20 100kg")
    panels = report.e1rm_panels(sessions(*days))
    assert panels[0]["points"][0]["v"] == pytest.approx(81.7, abs=0.05)  # 70×(1+5/30)


def test_e1rm_excludes_machines():
    s = sessions(*_many("Seated Row, Leverage Machine", 30))
    assert report.e1rm_panels(s) == []


# --------------------------------------------------------------- bodyweight

def test_bodyweight_moves_need_mostly_unloaded_sets():
    loaded = [rec("2026-02-%02d 09:00:00" % (i + 1), "  Pull Up / 1x10 20kg")
              for i in range(28)]
    unloaded = [rec("2026-01-%02d 09:00:00" % (i + 1), "  Pull Up / 2x10 0kg")
                for i in range(28)]
    assert report.bodyweight_moves(sessions(*unloaded))["order"] == ["Pull Up"]
    assert report.bodyweight_moves(sessions(*(unloaded + loaded)))["order"] == []


def test_bodyweight_series_converts_pounds():
    series = report.bodyweight_series({"values": [
        {"date": "2026-01-01T00:00:00Z", "value": "100lb"},
        {"date": "2026-01-02T00:00:00Z", "value": "70kg"},
        {"date": "2026-01-02T12:00:00Z", "value": "72kg"},
    ]})
    assert series[0]["kg"] == pytest.approx(45.36, abs=0.01)
    assert series[1]["kg"] == pytest.approx(71.0)


# --------------------------------------------------------------- rotation

def test_lifespans_bounds_and_floor():
    rare = rec("2026-01-01 09:00:00", "  Front Raise / 1x10 10kg")
    common = [rec("2026-0%d-01 09:00:00" % m, "  Bench Press / 5x8 60kg")
              for m in (1, 2, 3)]
    life = report.lifespans(sessions(rare, *common), {}, {})
    assert [r["name"] for r in life] == ["Bench Press"]
    assert life[0]["first"] == "2026-01-01"
    assert life[0]["last"] == "2026-03-01"
    assert life[0]["sets"] == 15


# --------------------------------------------------------------- timing

def test_dow_matrix_applies_ist_offset():
    # 2026-01-05 is a Monday. 20:00 UTC + 5:30 = 01:30 Tuesday.
    s = sessions(rec("2026-01-05 20:00:00", "  Bench Press / 1x8 60kg"))
    m = report.dow_matrix(s)
    assert m[1][1] == 1
    assert sum(sum(row) for row in m) == 1


def test_dow_matrix_shape():
    s = sessions(rec("2026-01-05 09:00:00", "  Bench Press / 1x8 60kg"))
    m = report.dow_matrix(s)
    assert len(m) == 7 and all(len(row) == 24 for row in m)


# --------------------------------------------------------------- categories

MAP = {"Bench Press": ["Pectoralis Major Sternal Head", "Triceps Brachii"],
       "Lat Pulldown": ["Latissimus Dorsi"]}


def test_category_share_counts_a_set_once_per_category():
    s = sessions(rec("2026-01-05 09:00:00", "  Bench Press / 1x8 60kg"))
    cats = report.category_shares(s, {}, MAP)
    assert cats["raw"]["Chest"] == [1]
    assert cats["raw"]["Arms"] == [1]
    assert cats["byYear"]["Chest"] == [50.0]


def test_equipment_suffix_falls_back_to_base_name():
    assert muscles_for("Lat Pulldown, Leverage Machine", {}, MAP) == ["Latissimus Dorsi"]
    assert muscles_for("Nothing At All, Cable", {}, MAP) == []


def test_unmapped_names_are_reported():
    s = sessions(rec("2026-01-05 09:00:00", "  Mystery Lift / 1x8 60kg"))
    assert report.category_shares(s, {}, MAP)["unmapped"] == ["Mystery Lift"]


# --------------------------------------------------------------- set credit

# the shape muscle_map.py writes now: target and synergist muscles per exercise
MAP2 = {
    "Pull Up": {"target": ["Latissimus Dorsi"],
                "synergist": ["Biceps Brachii", "Brachialis", "Teres Major"]},
    "Incline Bench Press": {"target": ["Pectoralis Major Clavicular Head"],
                            "synergist": ["Pectoralis Major Sternal Head",
                                          "Triceps Brachii", "Deltoid Anterior"]},
}


def test_a_targeted_group_scores_one_and_an_assisted_group_a_half():
    w = weighted_groups("Pull Up", {}, MAP2)
    assert w == {"Back": 1.0, "Biceps": 0.5}


def test_a_group_that_is_both_target_and_synergist_scores_one():
    # both pec heads map to Chest — one is the target, so Chest is not halved
    w = weighted_groups("Incline Bench Press", {}, MAP2)
    assert w["Chest"] == 1.0
    assert w["Triceps"] == 0.5
    assert w["Shoulders"] == 0.5


def test_flat_legacy_map_still_reads_as_targets_only():
    assert weighted_groups("Bench Press", {}, MAP) == {"Chest": 1.0, "Triceps": 1.0}
    assert synergists_for("Bench Press", {}, MAP) == []


def test_custom_exercise_synergists_score_a_half():
    customs = {"Bird Dog": {"name": "Bird Dog",
                            "targetMuscles": ["Erector Spinae"],
                            "synergistMuscles": ["Obliques"]}}
    assert weighted_groups("Bird Dog", customs, {}) == {"Back": 1.0, "Core": 0.5}


def test_equipment_suffix_falls_back_for_the_weighted_lookup():
    assert weighted_groups("Pull Up, Band", {}, MAP2) == {"Back": 1.0, "Biceps": 0.5}


def test_weekly_volume_credits_targets_fully_and_assists_by_half():
    s = sessions(rec("2026-01-05 09:00:00", "  Pull Up / 4x8 0kg"))
    w = report.weekly_volume(s, {}, MAP2, weeks=1,
                             now=report.datetime(2026, 1, 7).date())
    assert w["sets"]["Back"] == [4.0]
    assert w["sets"]["Biceps"] == [2.0]
    assert w["direct"]["Back"] == [4] and w["indirect"]["Back"] == [0]
    assert w["direct"]["Biceps"] == [0] and w["indirect"]["Biceps"] == [4]


def test_weekly_volume_reports_sets_performed_separately_from_credit():
    s = sessions(rec("2026-01-05 09:00:00", "  Pull Up / 4x8 0kg"))
    w = report.weekly_volume(s, {}, MAP2, weeks=1,
                             now=report.datetime(2026, 1, 7).date())
    credited = sum(w["sets"][g][0] for g in w["sets"])
    assert w["performed"] == [4]          # four sets were done
    assert credited == 6.0                # they credit six group-sets


def test_weekly_tonnage_is_credited_the_same_way():
    s = sessions(rec("2026-01-05 09:00:00", "  Incline Bench Press / 2x10 50kg"))
    w = report.weekly_volume(s, {}, MAP2, weeks=1,
                             now=report.datetime(2026, 1, 7).date())
    assert w["tonnage"]["Chest"] == [2 * 10 * 50]
    assert w["tonnage"]["Triceps"] == [2 * 10 * 50 * 0.5]


def test_recent_sessions_carry_the_direct_count_for_the_tooltip():
    s = sessions(rec("2026-01-05 09:00:00", "  Pull Up / 3x8 0kg"))
    out = report.recent_sessions(s, {}, MAP2, n=1)
    assert out[0]["groups"] == {"Back": 3.0, "Biceps": 1.5}
    assert out[0]["direct"] == {"Back": 3}


# --------------------------------------------------------------- goal

def test_goal_block_measures_the_gap_to_the_goal():
    series = [{"d": "2026-01-01", "kg": 72.0}, {"d": "2026-03-01", "kg": 69.5}]
    g = report.goal_block(series)
    assert g["high"] == report.GOAL_KG
    assert g["to_goal_kg"] == round(69.5 - report.GOAL_KG, 1)
    assert g["reached"] is False
    assert g["peak_kg"] == 72.0
    assert g["lost_kg"] == 2.5
    assert g["progress_pct"] == pytest.approx(
        100 * 2.5 / (72.0 - report.GOAL_KG), abs=0.1)


def test_goal_block_reports_the_goal_as_reached_at_or_under_it():
    g = report.goal_block([{"d": "2026-01-01", "kg": 70.0},
                           {"d": "2026-03-01", "kg": report.GOAL_KG}])
    assert g["reached"] is True
    assert g["progress_pct"] == 100.0
    below = report.goal_block([{"d": "2026-01-01", "kg": 70.0},
                               {"d": "2026-03-01", "kg": report.GOAL_KG - 1}])
    assert below["reached"] is True


def test_goal_block_survives_an_empty_series():
    assert report.goal_block([]) == {"low": report.GOAL_KG, "high": report.GOAL_KG}


# --------------------------------------------------------------- weekly volume

def test_weekly_volume_counts_a_set_once_per_group():
    # Bench Press maps to Chest and Arms-side Triceps; each gets one count per set.
    s = sessions(rec("2026-01-05 09:00:00", "  Bench Press / 2x8 60kg"))
    w = report.weekly_volume(s, {}, MAP, weeks=2,
                             now=report.datetime(2026, 1, 7).date())
    assert w["weeks"] == ["2025-12-29", "2026-01-05"]
    assert w["sets"]["Chest"] == [0, 2]
    assert w["sets"]["Triceps"] == [0, 2]
    assert w["tonnage"]["Chest"] == [0, 2 * 8 * 60]
    assert w["sessions"] == [0, 1]


def test_weekly_volume_does_not_double_count_two_heads_of_one_group():
    both_heads = {"Incline Press": ["Pectoralis Major Clavicular Head",
                                    "Pectoralis Major Sternal Head"]}
    s = sessions(rec("2026-01-05 09:00:00", "  Incline Press / 3x8 40kg"))
    w = report.weekly_volume(s, {}, both_heads, weeks=1,
                             now=report.datetime(2026, 1, 7).date())
    assert w["sets"]["Chest"] == [3]


def test_weekly_volume_window_ends_on_the_current_week():
    s = sessions(rec("2026-01-05 09:00:00", "  Bench Press / 1x8 60kg"),
                 rec("2025-11-03 09:00:00", "  Bench Press / 1x8 60kg"))
    w = report.weekly_volume(s, {}, MAP, weeks=4,
                             now=report.datetime(2026, 1, 8).date())
    assert w["weeks"][-1] == "2026-01-05"
    assert len(w["weeks"]) == 4
    assert sum(w["sets"]["Chest"]) == 1          # the November session falls outside


# --------------------------------------------------------------- sessions

def test_recent_sessions_keeps_the_tail_in_order():
    records = _many("Bench Press", 30)
    out = report.recent_sessions(sessions(*records), {}, MAP, n=5)
    assert len(out) == 5
    assert [o["d"] for o in out] == ["2026-01-%02d" % d for d in range(26, 31)]
    assert out[0]["sets"] == 1
    assert out[0]["groups"] == {"Chest": 1, "Triceps": 1}
    assert out[0]["minutes"] == 60


# --------------------------------------------------------------- strength watch

def _on(date, name, reps, weight):
    return rec(date + " 09:00:00", "  %s / 1x%d %skg" % (name, reps, weight))


def test_strength_watch_compares_recent_against_the_year_before():
    base = [_on("2026-01-%02d" % (i + 1), "Bench Press", 10, 60) for i in range(4)]
    recent = [_on("2026-06-%02d" % (i + 1), "Bench Press", 10, 66) for i in range(4)]
    out = report.strength_watch(sessions(*(base + recent)),
                                report.datetime(2026, 6, 20).date())
    assert len(out) == 1
    assert out[0]["name"] == "Bench Press"
    assert out[0]["base"] == pytest.approx(80.0)
    assert out[0]["now"] == pytest.approx(88.0)
    assert out[0]["delta_pct"] == pytest.approx(10.0)
    assert out[0]["days"] == 4


def test_strength_watch_needs_both_windows():
    only_recent = [_on("2026-06-%02d" % (i + 1), "Bench Press", 10, 60) for i in range(4)]
    assert report.strength_watch(sessions(*only_recent),
                                 report.datetime(2026, 6, 20).date()) == []


def test_strength_watch_skips_machines():
    name = "Seated Row, Leverage Machine"
    base = [_on("2026-01-%02d" % (i + 1), name, 10, 60) for i in range(4)]
    recent = [_on("2026-06-%02d" % (i + 1), name, 10, 70) for i in range(4)]
    assert report.strength_watch(sessions(*(base + recent)),
                                 report.datetime(2026, 6, 20).date()) == []


# --------------------------------------------------------------- assembly

def test_build_produces_every_section():
    records = _many("Bench Press", 20) + [
        rec("2026-02-01 09:00:00", "  Pull Up / 3x10 0kg")]
    out = report.build(records, {"values": []}, {}, MAP,
                       now=report.datetime(2026, 2, 2).date())
    for key in ("meta", "goal", "weekly", "recent", "watch", "vtaper", "groups",
                "facts", "calendar", "layoffs", "months", "years", "categories",
                "reps", "e1rm", "bodyweightMoves", "lifespans", "dow", "weight",
                "notes"):
        assert key in out
    assert out["vtaper"] == ["Back", "Shoulders", "Chest"]
    assert out["meta"]["sessions"] == 21
    assert out["meta"]["active_now"] == 2


def test_build_rejects_empty_history():
    with pytest.raises(ValueError):
        report.build([], {"values": []}, {}, {})


# --------------------------------------------------------------- re-weighs

def test_a_reweigh_minutes_later_replaces_the_reading():
    series = report.bodyweight_series({"values": [
        {"date": "2026-08-15T03:14:00.000Z", "value": "69kg"},
        {"date": "2026-08-15T03:18:00.000Z", "value": "69.5kg"},
    ]})
    assert series == [{"d": "2026-08-15", "kg": 69.5}]


def test_readings_hours_apart_still_average():
    series = report.bodyweight_series({"values": [
        {"date": "2026-08-10T00:40:00.000Z", "value": "70.7kg"},
        {"date": "2026-08-10T17:00:00.000Z", "value": "70.2kg"},
    ]})
    assert series == [{"d": "2026-08-10", "kg": 70.45}]


def test_a_run_of_reweighs_keeps_only_the_last():
    series = report.bodyweight_series({"values": [
        {"date": "2026-08-15T03:00:00.000Z", "value": "70kg"},
        {"date": "2026-08-15T03:05:00.000Z", "value": "69.8kg"},
        {"date": "2026-08-15T03:10:00.000Z", "value": "69.5kg"},
    ]})
    assert series == [{"d": "2026-08-15", "kg": 69.5}]
