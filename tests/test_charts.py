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
