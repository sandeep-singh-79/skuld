"""Tests for skuld.rtm_store — T5b RTM Store (persistent RTM)."""
from __future__ import annotations

import os
import textwrap

import pytest
import yaml

from skuld.models import GapInfo, MergeResult, RTMEntry
from skuld.rtm_store import RTMStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    ac_id: str = "AC-1",
    test_case_id: str = "TC-1",
    test_type: str = "functional",
    story_id: str | None = "S-1",
    status: str = "active",
    added_date: str | None = None,
    added_by_run: str | None = None,
) -> RTMEntry:
    return RTMEntry(
        ac_id=ac_id,
        test_case_id=test_case_id,
        test_type=test_type,
        story_id=story_id,
        status=status,
        added_date=added_date,
        added_by_run=added_by_run,
    )


# ===================================================================
# RTMStore.load
# ===================================================================

class TestRTMStoreLoad:
    def test_load_nonexistent_creates_empty_store(self, tmp_path):
        store = RTMStore.load(str(tmp_path / "rtm.yaml"))
        assert store.entries == []
        assert store.active_entries == []

    def test_load_existing_file_parses_entries(self, tmp_path):
        rtm_path = tmp_path / "rtm.yaml"
        data = {
            "metadata": {"rtm_version": "1.0", "project_id": "proj-1"},
            "entries": [
                {
                    "ac_id": "AC-1",
                    "test_case_id": "TC-1",
                    "test_type": "functional",
                    "story_id": "S-1",
                    "status": "active",
                    "added_date": "2026-07-16",
                    "added_by_run": "run-001",
                },
                {
                    "ac_id": "AC-2",
                    "test_case_id": "TC-2",
                    "test_type": "negative",
                    "story_id": "S-1",
                    "status": "deprecated",
                    "added_date": "2026-07-15",
                    "added_by_run": "run-000",
                },
            ],
        }
        rtm_path.write_text(yaml.dump(data, sort_keys=False))

        store = RTMStore.load(str(rtm_path))
        assert len(store.entries) == 2
        assert store.entries[0].ac_id == "AC-1"
        assert store.entries[0].status == "active"
        assert store.entries[1].status == "deprecated"

    def test_load_and_save_roundtrip(self, tmp_path):
        rtm_path = tmp_path / "rtm.yaml"

        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional")],
            story_id="S-1",
            run_id="run-001",
        )
        store.save(str(rtm_path))

        reloaded = RTMStore.load(str(rtm_path))
        assert len(reloaded.entries) == 1
        e = reloaded.entries[0]
        assert e.ac_id == "AC-1"
        assert e.test_case_id == "TC-1"
        assert e.test_type == "functional"
        assert e.story_id == "S-1"
        assert isinstance(e.added_date, str)
        assert e.status == "active"
        assert e.added_by_run == "run-001"

    def test_added_date_survives_roundtrip_as_string(self, tmp_path):
        """added_date must be str after save->load, not datetime.date."""
        store = RTMStore()
        entry = RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional",
                         story_id="S-1", added_date="2026-07-16", status="active")
        store._entries.append(entry)
        p = str(tmp_path / "rtm.yaml")
        store.save(p)
        reloaded = RTMStore.load(p)
        e = reloaded.entries[0]
        assert isinstance(e.added_date, str)
        assert e.added_date == "2026-07-16"

    def test_load_malformed_entry_raises(self, tmp_path):
        """YAML entry missing required keys raises ValueError."""
        p = tmp_path / "bad.yaml"
        p.write_text("entries:\n  - ac_id: AC-1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required key"):
            RTMStore.load(str(p))

    def test_large_rtm_file_rejected(self, tmp_path):
        """RTM files over 10MB are rejected."""
        p = tmp_path / "huge.yaml"
        p.write_text("x" * 11_000_000, encoding="utf-8")
        with pytest.raises(ValueError, match="exceeds maximum size"):
            RTMStore.load(str(p))


# ===================================================================
# RTMStore.merge
# ===================================================================

class TestRTMStoreMerge:
    def test_merge_into_empty_store(self):
        store = RTMStore()
        result = store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1")],
            story_id="S-1",
            run_id="run-001",
        )
        assert len(store.entries) == 1
        assert result.added == 1

    def test_merge_adds_entries_with_metadata(self):
        store = RTMStore()
        result = store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1")],
            story_id="S-1",
            run_id="run-42",
        )
        entry = store.entries[0]
        assert entry.added_by_run == "run-42"
        assert entry.added_date is not None  # today's date
        assert entry.status == "active"

    def test_merge_supersedes_duplicate_ac_tc_pair(self):
        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional")],
            story_id="S-1",
            run_id="run-001",
        )
        result = store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1", test_type="negative")],
            story_id="S-1",
            run_id="run-002",
        )
        assert result.superseded == 1
        assert result.added == 1
        active = store.active_entries
        assert len(active) == 1
        assert active[0].added_by_run == "run-002"
        assert active[0].test_type == "negative"
        # Old entry still exists but superseded
        superseded = [e for e in store.entries if e.status == "superseded"]
        assert len(superseded) == 1

    def test_merge_returns_correct_counts(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1"),
                _entry(ac_id="AC-2", test_case_id="TC-2"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        result = store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1"),  # supersedes
                _entry(ac_id="AC-3", test_case_id="TC-3"),  # new
            ],
            story_id="S-1",
            run_id="run-002",
        )
        assert result.added == 2
        assert result.superseded == 1
        assert result.conflicts == []

    def test_merge_different_story_no_conflict(self):
        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1")],
            story_id="S-1",
            run_id="run-001",
        )
        # Same AC-TC pair but from a different story context — still supersedes
        result = store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1")],
            story_id="S-2",
            run_id="run-002",
        )
        assert result.superseded == 1

    def test_intra_batch_duplicate_last_wins(self):
        """Two entries with same (ac_id, tc_id) in one merge — last wins, no self-supersede."""
        store = RTMStore()
        entries = [
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="negative"),
        ]
        result = store.merge(entries, story_id="S-1", run_id="run-1")
        active = store.active_entries
        assert len(active) == 1
        assert active[0].test_type == "negative"  # last wins

    def test_cross_story_supersede_reports_conflict(self):
        """Superseding entry from different story appears in conflicts."""
        store = RTMStore()
        e1 = RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional", story_id="S-1")
        store.merge([e1], story_id="S-1", run_id="run-1")
        e2 = RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional", story_id="S-2")
        result = store.merge([e2], story_id="S-2", run_id="run-2")
        assert len(result.conflicts) >= 1
        assert "S-1" in result.conflicts[0]

    def test_merge_preserves_existing_entries(self):
        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1")],
            story_id="S-1",
            run_id="run-001",
        )
        store.merge(
            [_entry(ac_id="AC-2", test_case_id="TC-2")],
            story_id="S-1",
            run_id="run-002",
        )
        assert len(store.active_entries) == 2
        tc_ids = {e.test_case_id for e in store.active_entries}
        assert tc_ids == {"TC-1", "TC-2"}


# ===================================================================
# RTMStore.deprecate
# ===================================================================

class TestRTMStoreDeprecate:
    def test_deprecate_changes_status(self):
        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1")],
            story_id="S-1",
            run_id="run-001",
        )
        store.deprecate(["TC-1"])
        assert store.entries[0].status == "deprecated"

    def test_deprecate_returns_count(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1"),
                _entry(ac_id="AC-2", test_case_id="TC-1"),  # same TC, different AC
                _entry(ac_id="AC-3", test_case_id="TC-2"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        count = store.deprecate(["TC-1"])
        assert count == 2  # two entries for TC-1

    def test_deprecate_nonexistent_id_returns_zero(self):
        store = RTMStore()
        count = store.deprecate(["TC-999"])
        assert count == 0

    def test_deprecated_entries_excluded_from_active(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1"),
                _entry(ac_id="AC-2", test_case_id="TC-2"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        store.deprecate(["TC-1"])
        assert len(store.active_entries) == 1
        assert store.active_entries[0].test_case_id == "TC-2"


# ===================================================================
# RTMStore.query_gaps
# ===================================================================

class TestRTMStoreQueryGaps:
    def test_no_gaps_when_fully_covered(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
                _entry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
                _entry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        gaps = store.query_gaps()
        assert gaps == []

    def test_gap_detected_for_missing_negative(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
                _entry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        gaps = store.query_gaps()
        assert len(gaps) == 1
        assert gaps[0].ac_id == "AC-1"
        assert "negative" in gaps[0].missing_types

    def test_gap_detected_for_completely_uncovered_ac(self):
        """When ac_ids parameter is provided, ACs with zero entries are reported."""
        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional")],
            story_id="S-1",
            run_id="run-001",
        )
        gaps = store.query_gaps(ac_ids=["AC-1", "AC-2"])
        ac_ids_with_gaps = {g.ac_id for g in gaps}
        # AC-1 missing negative + edge-case, AC-2 missing all
        assert "AC-2" in ac_ids_with_gaps
        ac2_gap = [g for g in gaps if g.ac_id == "AC-2"][0]
        assert "functional" in ac2_gap.missing_types
        assert "negative" in ac2_gap.missing_types
        assert "edge-case" in ac2_gap.missing_types

    def test_deprecated_entries_excluded_from_gap_analysis(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
                _entry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
                _entry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        # Deprecate the negative test — now there's a gap
        store.deprecate(["TC-2"])
        gaps = store.query_gaps()
        assert len(gaps) == 1
        assert gaps[0].ac_id == "AC-1"
        assert "negative" in gaps[0].missing_types


# ===================================================================
# RTMStore.coverage_summary
# ===================================================================

class TestRTMStoreCoverageSummary:
    def test_empty_store_summary(self):
        store = RTMStore()
        summary = store.coverage_summary()
        assert summary["total_entries"] == 0
        assert summary["total_stories"] == 0
        assert summary["total_test_cases"] == 0
        assert summary["unique_acs"] == 0

    def test_summary_counts_active_only(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1", story_id="S-1"),
                _entry(ac_id="AC-2", test_case_id="TC-2", story_id="S-1"),
                _entry(ac_id="AC-3", test_case_id="TC-3", story_id="S-2"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        summary = store.coverage_summary()
        assert summary["total_entries"] == 3
        assert summary["total_stories"] == 2
        assert summary["total_test_cases"] == 3
        assert summary["unique_acs"] == 3

    def test_summary_with_mixed_statuses(self):
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1", story_id="S-1"),
                _entry(ac_id="AC-2", test_case_id="TC-2", story_id="S-1"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        store.deprecate(["TC-2"])
        summary = store.coverage_summary()
        assert summary["total_entries"] == 1
        assert summary["total_test_cases"] == 1
        assert summary["unique_acs"] == 1


# ===================================================================
# Real-world workflow scenarios
# ===================================================================


class TestRTMStoreWorkflows:
    """Scenarios a real user would trigger over time through the CLI/pipeline."""

    def test_multi_sprint_accumulation(self):
        """5 different stories over weeks — RTM accumulates all."""
        store = RTMStore()
        for i in range(1, 6):
            store.merge(
                [_entry(ac_id=f"AC-{i}", test_case_id=f"TC-{i}", test_type="functional", story_id=None)],
                story_id=f"STORY-{i}",
                run_id=f"run-{i:03d}",
            )
        summary = store.coverage_summary()
        assert summary["total_entries"] == 5
        assert summary["total_stories"] == 5
        assert summary["total_test_cases"] == 5
        assert summary["unique_acs"] == 5

    def test_rerun_same_story_supersedes_old_entries(self):
        """Re-generating tests for the same story should supersede, not duplicate."""
        store = RTMStore()
        # First run: 3 test cases for story S-1
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
                _entry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
                _entry(ac_id="AC-2", test_case_id="TC-3", test_type="functional"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        assert len(store.active_entries) == 3

        # Second run for same story: TC-1 and TC-3 regenerated, TC-2 dropped
        result = store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
                _entry(ac_id="AC-2", test_case_id="TC-3", test_type="negative"),  # type changed
            ],
            story_id="S-1",
            run_id="run-002",
        )
        assert result.superseded == 2  # TC-1 and TC-3 superseded
        assert result.added == 2
        # TC-2 from run-001 is still active (not superseded — different test case ID)
        active_ids = {e.test_case_id for e in store.active_entries}
        assert "TC-2" in active_ids
        # Active TC-1 and TC-3 should be from run-002
        for e in store.active_entries:
            if e.test_case_id in ("TC-1", "TC-3"):
                assert e.added_by_run == "run-002"

    def test_deprecate_then_readd(self):
        """Deprecate TC-1, later re-add it — both entries coexist, new one is active."""
        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional")],
            story_id="S-1",
            run_id="run-001",
        )
        store.deprecate(["TC-1"])
        assert len(store.active_entries) == 0

        # Re-add TC-1 in a new run
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1", test_type="functional")],
            story_id="S-1",
            run_id="run-002",
        )
        assert len(store.active_entries) == 1
        assert store.active_entries[0].added_by_run == "run-002"
        # Deprecated entry still in full list
        deprecated = [e for e in store.entries if e.status == "deprecated"]
        assert len(deprecated) == 1

    def test_empty_store_query_gaps_with_ac_ids(self):
        """Brand new project, no entries — query_gaps with ac_ids reports all missing."""
        store = RTMStore()
        gaps = store.query_gaps(ac_ids=["AC-1", "AC-2", "AC-3"])
        assert len(gaps) == 3
        for gap in gaps:
            assert set(gap.missing_types) == {"functional", "negative", "edge-case"}

    def test_coverage_summary_after_deprecation(self):
        """Summary should only reflect active entries, not deprecated."""
        store = RTMStore()
        store.merge(
            [
                _entry(ac_id="AC-1", test_case_id="TC-1"),
                _entry(ac_id="AC-2", test_case_id="TC-2"),
                _entry(ac_id="AC-3", test_case_id="TC-3"),
            ],
            story_id="S-1",
            run_id="run-001",
        )
        store.deprecate(["TC-1", "TC-2"])
        summary = store.coverage_summary()
        assert summary["total_entries"] == 1
        assert summary["total_test_cases"] == 1
        assert summary["unique_acs"] == 1

    def test_save_to_nested_directory_creates_parents(self, tmp_path):
        """Save to a path where parent directories don't exist yet."""
        deep_path = tmp_path / "reports" / "2026" / "Q3" / "rtm.yaml"
        store = RTMStore()
        store.merge(
            [_entry(ac_id="AC-1", test_case_id="TC-1")],
            story_id="S-1",
            run_id="run-001",
        )
        store.save(str(deep_path))
        assert deep_path.exists()
        # Verify it can be loaded back
        reloaded = RTMStore.load(str(deep_path))
        assert len(reloaded.entries) == 1
