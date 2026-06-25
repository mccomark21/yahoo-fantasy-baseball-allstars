"""Behavior tests for ``season_is_complete`` — the value-aware ``--resume`` gate.

The trap this guards against: the old historical-stats bug wrote full-size files
full of ``0.0`` values, so a size/existence check called those seasons "done"
and ``--resume`` skipped re-fetching them. Completeness must therefore require a
genuine non-zero stat value, not just the four files being present.
"""

from __future__ import annotations

import common
import fetch_all


_FILES = ("stat_categories.json", "rosters.json", "player_stats.json", "matchups.json")


def _write_season(data_dir, league_id, season, season_totals):
    """Lay down a full set of four season files with the given season_totals."""
    sdir = data_dir / str(league_id) / str(season)
    for name in _FILES:
        if name == "player_stats.json":
            common.dump_json(sdir / name, {"season_totals": season_totals})
        else:
            common.dump_json(sdir / name, {})
    return sdir


def test_season_with_real_values_is_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    _write_season(tmp_path, "12239", 2024,
                  {"t1": {"422.p.8967": {"7": "89", "12": "25"}}})

    assert fetch_all.season_is_complete("12239", 2024) is True


def test_all_zero_and_sentinel_values_are_not_complete(tmp_path, monkeypatch):
    # The old bug: archived game_keys served "-" for everything → 0.0/sentinels.
    # Files exist and are full-size, but there is no real data → re-fetch needed.
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    _write_season(tmp_path, "12239", 2019,
                  {"t1": {"388.p.8967": {"7": "0", "12": "0.0", "16": "-"}}})

    assert fetch_all.season_is_complete("12239", 2019) is False


def test_missing_file_is_not_complete(tmp_path, monkeypatch):
    # A partially-written season (one of the four files never landed) is not
    # complete, even though the stats it does have are real.
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    sdir = _write_season(tmp_path, "12239", 2023,
                         {"t1": {"431.p.8967": {"7": "89"}}})
    (sdir / "matchups.json").unlink()

    assert fetch_all.season_is_complete("12239", 2023) is False
