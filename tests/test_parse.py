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


def test_no_warmup_no_target_double_count():
    text = ("2026-08-12 09:00:00 +00:00 / program: \"P\" / dayName: \"D\" / "
            "week: 1 / dayInWeek: 1 / duration: 3000s / exercises: {\n"
            "  Bird Dog / 1x4 0kg / target: 1x4 0kg 15s\n"
            "}")
    r = parse_record(text)
    assert len(r["exercises"][0]["sets"]) == 1


def test_amrap_plus_set_parsed():
    text = ("2026-08-12 09:00:00 +00:00 / program: \"P\" / dayName: \"D\" / "
            "week: 1 / dayInWeek: 1 / duration: 3000s / exercises: {\n"
            "  Bench Press / 3x8 60kg, 1x5+ 70kg / target: 3x8-12 60kg @8 90s\n"
            "}")
    r = parse_record(text)
    sets = r["exercises"][0]["sets"]
    assert len(sets) == 4
    assert sets[3] == {"reps": 5, "weight_kg": 70.0, "unilateral": False}
