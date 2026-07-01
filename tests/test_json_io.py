"""Serialization tests for ``common.dump_json`` (issue #20).

Yahoo reports ERA/WHIP as ``float('inf')`` on zero innings. The default
``json.dump`` writes non-finite floats as bare ``Infinity`` / ``-Infinity`` /
``NaN`` tokens — valid JavaScript but illegal JSON — so the browser's strict
``JSON.parse`` throws on them. ``dump_json`` must coerce them to ``null`` at the
source and never emit those tokens. All fully offline.
"""

from __future__ import annotations

import json
import math


# -- _json_safe: every non-finite float becomes None, everything else intact -- #
def test_json_safe_replaces_non_finite_with_none():
    from common import _json_safe

    out = _json_safe(
        {
            "era": float("inf"),
            "neg": float("-inf"),
            "nan": float("nan"),
            "rate": 1.5,
            "count": 0,
            "label": "INF",  # a real string, not a number — must survive
            "nested": [float("inf"), 2, {"whip": float("nan")}],
        }
    )

    assert out == {
        "era": None,
        "neg": None,
        "nan": None,
        "rate": 1.5,
        "count": 0,
        "label": "INF",
        "nested": [None, 2, {"whip": None}],
    }


# -- dump_json: output is strict, valid JSON with no Infinity/NaN tokens ------ #
def test_dump_json_emits_strict_json_for_infinite_era(tmp_path):
    from common import dump_json

    path = tmp_path / "player_stats.json"
    dump_json(path, {"season_totals": {"t1": {"p1": {"26": float("inf"), "27": float("nan")}}}})

    text = path.read_text(encoding="utf-8")
    assert "Infinity" not in text and "NaN" not in text

    # Strict parse (no parse_constant override) — what the browser does.
    loaded = json.loads(text)
    assert loaded["season_totals"]["t1"]["p1"] == {"26": None, "27": None}


# -- dump_json: finite values round-trip unchanged ---------------------------- #
def test_dump_json_preserves_finite_values(tmp_path):
    from common import dump_json

    path = tmp_path / "out.json"
    payload = {"a": 1, "b": 2.5, "c": "x", "d": [0.0, 1.0], "e": None, "f": True}
    dump_json(path, payload)

    assert json.loads(path.read_text(encoding="utf-8")) == payload


# -- committed data files contain no non-finite tokens (regression guard) ----- #
def test_committed_player_stats_files_are_strict_json():
    from common import DATA_DIR

    files = list(DATA_DIR.glob("*/*/player_stats.json"))
    assert files, "expected committed player_stats.json files to validate"
    for path in files:
        text = path.read_text(encoding="utf-8")
        # parse_constant fires only on bare Infinity/-Infinity/NaN tokens.
        json.loads(text, parse_constant=_reject_non_finite)


def _reject_non_finite(token):  # pragma: no cover - only runs on failure
    raise AssertionError(f"non-finite JSON token in committed data: {token!r}")


def test_math_isfinite_contract():
    # The sanitizer's correctness rests on math.isfinite distinguishing these.
    assert math.isfinite(0.0) and not math.isfinite(float("inf"))
    assert not math.isfinite(float("nan"))
