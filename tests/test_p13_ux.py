"""Tests for P13.x: UX & Personalization — Dashboard Layout, Onboarding, Snapshots."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ui_prefs import (
    SECTION_LABELS,
    TOUR_STEPS,
    _DEFAULT_SECTIONS,
    get_prefs,
    get_section_expanded,
    get_sections,
    is_first_run,
    mark_onboarding_complete,
    reset_to_defaults,
    save_prefs,
    set_section_expanded,
    set_section_visibility,
    update_pref,
)
from history import (
    delete_snapshot,
    diff_snapshots,
    list_snapshots,
    load_snapshot,
    save_named_snapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_prefs(tmp_path, monkeypatch):
    monkeypatch.setattr("ui_prefs._DATA_DIR", tmp_path)
    monkeypatch.setattr("ui_prefs._PREFS_FILE", tmp_path / "ui_prefs.json")
    return tmp_path


@pytest.fixture
def tmp_snapshots(tmp_path, monkeypatch):
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    monkeypatch.setattr("history._DATA_DIR", tmp_path)
    monkeypatch.setattr("history._SNAPSHOTS_DIR", snap_dir)
    return snap_dir


# ---------------------------------------------------------------------------
# P13.1: Dashboard Layout tests
# ---------------------------------------------------------------------------


class TestDashboardLayout:
    def test_default_sections_all_visible(self, tmp_prefs):
        sections = get_sections()
        assert all(visible for visible in sections.values())

    def test_section_labels_match_defaults(self):
        for key in _DEFAULT_SECTIONS:
            assert key in SECTION_LABELS

    def test_set_section_visibility(self, tmp_prefs):
        set_section_visibility("chat", False)
        sections = get_sections()
        assert sections["chat"] is False

    def test_set_section_visibility_toggle(self, tmp_prefs):
        set_section_visibility("risk_guardrails", False)
        assert get_sections()["risk_guardrails"] is False
        set_section_visibility("risk_guardrails", True)
        assert get_sections()["risk_guardrails"] is True

    def test_set_section_expanded(self, tmp_prefs):
        set_section_expanded("factor_engine", False)
        assert get_section_expanded("factor_engine") is False

    def test_get_section_expanded_default(self, tmp_prefs):
        # Unknown section should return default
        result = get_section_expanded("unknown_section", default=True)
        assert result is True

    def test_reset_to_defaults(self, tmp_prefs):
        set_section_visibility("chat", False)
        reset_to_defaults()
        sections = get_sections()
        assert sections["chat"] is True

    def test_update_pref(self, tmp_prefs):
        update_pref("compact_mode", True)
        prefs = get_prefs()
        assert prefs["compact_mode"] is True

    def test_prefs_persist(self, tmp_prefs):
        save_prefs({"sections": {"chat": False}, "onboarding_completed": True})
        prefs = get_prefs()
        assert prefs["sections"]["chat"] is False

    def test_prefs_merge_with_defaults(self, tmp_prefs):
        # Save only some keys, should merge with defaults
        prefs_file = tmp_prefs / "ui_prefs.json"
        prefs_file.write_text(json.dumps({"onboarding_completed": True}))

        prefs = get_prefs()
        # Should have default sections
        assert "sections" in prefs
        assert "chat" in prefs["sections"]


# ---------------------------------------------------------------------------
# P13.2: Onboarding tests
# ---------------------------------------------------------------------------


class TestOnboarding:
    def test_is_first_run_default(self, tmp_prefs):
        assert is_first_run() is True

    def test_mark_onboarding_complete(self, tmp_prefs):
        mark_onboarding_complete()
        assert is_first_run() is False

    def test_tour_steps_structure(self):
        assert len(TOUR_STEPS) >= 3
        for step in TOUR_STEPS:
            assert "step" in step
            assert "title" in step
            assert "description" in step
            assert isinstance(step["title"], str)
            assert len(step["title"]) > 0

    def test_tour_steps_sequential(self):
        steps = [s["step"] for s in TOUR_STEPS]
        assert steps == list(range(1, len(TOUR_STEPS) + 1))


# ---------------------------------------------------------------------------
# P13.3: Named Analysis Snapshots tests
# ---------------------------------------------------------------------------


class TestSnapshots:
    def test_save_and_load(self, tmp_snapshots):
        filename = save_named_snapshot(
            symbol="AAPL",
            name="My Test Snapshot",
            metrics={"price": 150.0, "pe": 25.0},
            factor_scores={"trend": 80, "valuation": 65},
            risk={"risk_score": 35, "risk_level": "Moderate", "flags": []},
            claude_output="Bullish outlook.",
        )
        assert filename != ""

        snapshot = load_snapshot(filename)
        assert snapshot is not None
        assert snapshot["symbol"] == "AAPL"
        assert snapshot["name"] == "My Test Snapshot"
        assert snapshot["metrics"]["price"] == 150.0

    def test_list_snapshots_empty(self, tmp_snapshots):
        snapshots = list_snapshots()
        assert snapshots == []

    def test_list_snapshots_filtered(self, tmp_snapshots):
        save_named_snapshot(
            "AAPL",
            "AAPL Snapshot",
            {"price": 150},
            {"trend": 70},
            {"risk_score": 30, "risk_level": "Low", "flags": []},
        )
        save_named_snapshot(
            "MSFT",
            "MSFT Snapshot",
            {"price": 350},
            {"trend": 75},
            {"risk_score": 40, "risk_level": "Moderate", "flags": []},
        )

        aapl_snaps = list_snapshots(symbol="AAPL")
        assert len(aapl_snaps) == 1
        assert aapl_snaps[0]["symbol"] == "AAPL"

        all_snaps = list_snapshots()
        assert len(all_snaps) == 2

    def test_list_snapshots_newest_first(self, tmp_snapshots):
        # Use 2-second sleep to ensure different timestamps in filename
        save_named_snapshot(
            "AAPL", "Old", {}, {}, {"risk_score": 30, "risk_level": "Low", "flags": []}
        )
        time.sleep(1.1)
        save_named_snapshot(
            "AAPL", "New", {}, {}, {"risk_score": 35, "risk_level": "Low", "flags": []}
        )

        snapshots = list_snapshots("AAPL")
        # Snapshots are sorted by filename (newest = higher timestamp)
        assert len(snapshots) == 2
        names = [s["name"] for s in snapshots]
        assert names.index("New") < names.index("Old")

    def test_delete_snapshot(self, tmp_snapshots):
        filename = save_named_snapshot(
            "AAPL",
            "To Delete",
            {},
            {},
            {"risk_score": 30, "risk_level": "Low", "flags": []},
        )
        assert Path(tmp_snapshots / filename).exists()

        result = delete_snapshot(filename)
        assert result is True
        assert not Path(tmp_snapshots / filename).exists()

    def test_delete_nonexistent_snapshot(self, tmp_snapshots):
        result = delete_snapshot("nonexistent.json")
        assert result is True  # unlink with missing_ok=True

    def test_load_nonexistent_snapshot(self, tmp_snapshots):
        result = load_snapshot("nonexistent.json")
        assert result is None

    def test_snapshot_filename_safe_chars(self, tmp_snapshots):
        filename = save_named_snapshot(
            "AAPL",
            "Test with <special> chars & more!",
            {},
            {},
            {"risk_score": 30, "risk_level": "Low", "flags": []},
        )
        # Filename should not contain special chars
        assert "<" not in filename
        assert ">" not in filename
        assert "&" not in filename

    def test_diff_snapshots_score_change(self, tmp_snapshots):
        snap_a = {
            "symbol": "AAPL",
            "name": "Snapshot A",
            "date": "2024-01-01",
            "composite_score": 60,
            "factor_scores": {"trend": 70, "valuation": 60},
            "risk": {"risk_level": "Moderate"},
            "metrics": {"price": 140.0},
        }
        snap_b = {
            "symbol": "AAPL",
            "name": "Snapshot B",
            "date": "2024-02-01",
            "composite_score": 75,
            "factor_scores": {"trend": 85, "valuation": 60},
            "risk": {"risk_level": "Low"},
            "metrics": {"price": 165.0},
        }

        diff = diff_snapshots(snap_a, snap_b)

        assert diff["score_change"] == pytest.approx(15, abs=0.1)
        assert diff["risk_change"] is not None
        assert diff["risk_change"]["before"] == "Moderate"
        assert diff["risk_change"]["after"] == "Low"

    def test_diff_snapshots_factor_changes(self):
        snap_a = {
            "symbol": "AAPL",
            "name": "A",
            "date": "2024-01-01",
            "composite_score": 60,
            "factor_scores": {"trend": 60, "valuation": 70},
            "risk": {"risk_level": "Moderate"},
            "metrics": {},
        }
        snap_b = {
            "symbol": "AAPL",
            "name": "B",
            "date": "2024-02-01",
            "composite_score": 70,
            "factor_scores": {"trend": 80, "valuation": 70},
            "risk": {"risk_level": "Moderate"},
            "metrics": {},
        }

        diff = diff_snapshots(snap_a, snap_b)

        # Trend changed by 20 (≥5 threshold)
        changed_factors = {c["factor"]: c for c in diff["changed_factors"]}
        assert "trend" in changed_factors
        assert changed_factors["trend"]["change"] == 20

    def test_diff_snapshots_no_change(self):
        snap = {
            "symbol": "AAPL",
            "name": "Same",
            "date": "2024-01-01",
            "composite_score": 65,
            "factor_scores": {"trend": 70},
            "risk": {"risk_level": "Moderate"},
            "metrics": {"price": 150.0},
        }
        diff = diff_snapshots(snap, snap.copy())
        assert diff["changed_factors"] == []
        assert diff["risk_change"] is None
        assert diff["score_change"] == pytest.approx(0, abs=0.1)
