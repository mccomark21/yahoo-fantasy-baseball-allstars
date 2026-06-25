"""Test harness shared fixtures.

Puts ``scripts/`` on the import path and provides a credential-free
``YahooClient`` whose network boundary (``query``) is stubbed per-test, so the
whole suite runs offline with no Yahoo OAuth.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def yahoo_client(monkeypatch):
    """A ``YahooClient`` built with throwaway credentials.

    ``__init__`` makes no network calls; it only validates that the three
    credential env vars are present. Tests stub ``client.query`` to inject a
    fake query object, so no real Yahoo request is ever made.
    """
    monkeypatch.setenv("YAHOO_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("YAHOO_CONSUMER_SECRET", "test-secret")
    monkeypatch.setenv("YAHOO_REFRESH_TOKEN", "test-refresh")

    from yahoo_client import YahooClient

    return YahooClient()
