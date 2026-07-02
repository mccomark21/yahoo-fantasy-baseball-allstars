"""``leagues.json`` must carry a per-league URL ``slug``.

The frontend gives each league its own shareable hash route (#/<slug>), so the
league index it reads has to name a slug for every league. Slugs come from
``config.yaml``'s ``league_slugs`` map; a league without a configured slug falls
back to its id (so the URL still works, just uglier).
"""

from __future__ import annotations

import json


def test_write_leagues_index_emits_configured_and_fallback_slugs(monkeypatch, tmp_path):
    import common
    import fetch_all

    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    fetch_all.write_leagues_index([
        {"id": "12239", "name": "Sega Memorial Fantasy Baseball", "seasons": [2025, 2026]},
        {"id": "14078", "name": "League of Champions", "seasons": [2026]},
        {"id": "99999", "name": "Unmapped League", "seasons": [2026]},
    ])

    data = json.loads((tmp_path / "leagues.json").read_text(encoding="utf-8"))
    slugs = {lg["id"]: lg["slug"] for lg in data["leagues"]}

    # Configured slugs (config.yaml → league_slugs).
    assert slugs["12239"] == "sega"
    assert slugs["14078"] == "loc"
    # Unmapped league falls back to its id so the route still resolves.
    assert slugs["99999"] == "99999"

    # Every league carries a non-empty slug.
    assert all(lg.get("slug") for lg in data["leagues"])
