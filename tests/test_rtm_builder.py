"""Tests for skuld.rtm_builder — TDD RED phase."""
from __future__ import annotations

import pytest

from skuld.models import AcceptanceCriterion, RTMEntry, TestCase
from skuld.rtm_builder import build_rtm, find_gaps, rtm_to_matrix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tc(
    id: str,
    story_id: str = "S-1",
    ac_ids: list[str] | None = None,
    test_type: str = "functional",
    priority: str = "P1",
) -> TestCase:
    return TestCase(
        id=id,
        story_id=story_id,
        ac_ids=ac_ids if ac_ids is not None else ["AC-1"],
        test_type=test_type,
        priority=priority,
        preconditions="none",
        steps=["step"],
        expected_result="pass",
    )


def _ac(id: str, criticality: str = "medium") -> AcceptanceCriterion:
    return AcceptanceCriterion(id=id, description=f"Desc for {id}", criticality=criticality)


# ===================================================================
# build_rtm
# ===================================================================

class TestBuildRTM:
    def test_single_tc_single_ac(self):
        entries = build_rtm([_tc("TC-1", ac_ids=["AC-1"])], [_ac("AC-1")])
        assert len(entries) == 1
        assert entries[0].ac_id == "AC-1"
        assert entries[0].test_case_id == "TC-1"

    def test_tc_covering_multiple_acs(self):
        tc = _tc("TC-1", ac_ids=["AC-1", "AC-2", "AC-3"])
        entries = build_rtm([tc], [_ac("AC-1"), _ac("AC-2"), _ac("AC-3")])
        assert len(entries) == 3
        ac_ids = {e.ac_id for e in entries}
        assert ac_ids == {"AC-1", "AC-2", "AC-3"}

    def test_multiple_tcs_same_ac(self):
        tc1 = _tc("TC-1", ac_ids=["AC-1"])
        tc2 = _tc("TC-2", ac_ids=["AC-1"], test_type="negative")
        entries = build_rtm([tc1, tc2], [_ac("AC-1")])
        assert len(entries) == 2
        tc_ids = {e.test_case_id for e in entries}
        assert tc_ids == {"TC-1", "TC-2"}

    def test_empty_test_cases(self):
        entries = build_rtm([], [_ac("AC-1")])
        assert entries == []

    def test_empty_acs_still_builds_from_tc_ac_ids(self):
        entries = build_rtm([_tc("TC-1", ac_ids=["AC-1"])], [])
        assert len(entries) == 1
        assert entries[0].ac_id == "AC-1"

    def test_story_id_propagated(self):
        tc = _tc("TC-1", story_id="S-42", ac_ids=["AC-1"])
        entries = build_rtm([tc], [_ac("AC-1")])
        assert entries[0].story_id == "S-42"

    def test_test_type_propagated(self):
        tc = _tc("TC-1", test_type="edge-case", ac_ids=["AC-1"])
        entries = build_rtm([tc], [_ac("AC-1")])
        assert entries[0].test_type == "edge-case"

    def test_tc_with_empty_ac_ids_produces_no_entries(self):
        tc = _tc("TC-1", ac_ids=[])
        entries = build_rtm([tc], [_ac("AC-1")])
        assert entries == []


# ===================================================================
# rtm_to_matrix
# ===================================================================

class TestRTMToMatrix:
    def test_basic_matrix_structure(self):
        entries = [RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional")]
        result = rtm_to_matrix(entries, [_ac("AC-1")], [_tc("TC-1", ac_ids=["AC-1"])])
        assert result["matrix"]["AC-1"]["TC-1"] == "functional"

    def test_uncovered_ac_has_empty_dict(self):
        result = rtm_to_matrix([], [_ac("AC-1")], [])
        assert result["matrix"]["AC-1"] == {}

    def test_orphan_test_detected(self):
        # TC-99 covers AC-99 which is NOT in ac_list → TC-99 is an orphan
        orphan_tc = _tc("TC-99", ac_ids=["AC-99"])
        result = rtm_to_matrix([], [_ac("AC-1")], [orphan_tc])
        assert "TC-99" in result["orphan_test_ids"]

    def test_empty_inputs(self):
        result = rtm_to_matrix([], [], [])
        assert result["matrix"] == {}
        assert result["orphan_test_ids"] == []

    def test_multiple_types_per_ac(self):
        entries = [
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
        ]
        acs = [_ac("AC-1")]
        tcs = [
            _tc("TC-1", ac_ids=["AC-1"]),
            _tc("TC-2", ac_ids=["AC-1"], test_type="negative"),
        ]
        result = rtm_to_matrix(entries, acs, tcs)
        assert result["matrix"]["AC-1"]["TC-1"] == "functional"
        assert result["matrix"]["AC-1"]["TC-2"] == "negative"

    def test_tc_with_empty_ac_ids_detected_as_orphan(self):
        tc = _tc("TC-1", ac_ids=[])
        entries = build_rtm([tc], [_ac("AC-1")])
        result = rtm_to_matrix(entries, [_ac("AC-1")], [tc])
        assert "TC-1" in result["orphan_test_ids"]

    def test_entry_referencing_unknown_ac_not_in_matrix(self):
        from skuld.models import RTMEntry
        entries = [RTMEntry(ac_id="AC-PHANTOM", test_case_id="TC-1", test_type="functional")]
        result = rtm_to_matrix(entries, [_ac("AC-1")], [_tc("TC-1")])
        assert "AC-PHANTOM" not in result["matrix"]
        assert "AC-1" in result["matrix"]

    def test_orphan_detected_in_integrated_flow(self):
        """Test mapping to nonexistent AC is orphan when using build_rtm + rtm_to_matrix."""
        acs = [_ac("AC-1")]
        tcs = [_tc("TC-1", ac_ids=["AC-1"]), _tc("TC-99", ac_ids=["AC-BOGUS"])]
        entries = build_rtm(tcs, acs)
        result = rtm_to_matrix(entries, acs, tcs)
        assert "TC-99" in result["orphan_test_ids"]
        assert "TC-1" not in result["orphan_test_ids"]


# ===================================================================
# find_gaps
# ===================================================================

class TestFindGaps:
    def test_no_gaps_when_fully_covered(self):
        entries = [
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
        ]
        gaps = find_gaps(entries, [_ac("AC-1")])
        assert gaps == []

    def test_ac_with_no_test_at_all(self):
        gaps = find_gaps([], [_ac("AC-1")])
        assert any("AC-1" in g and "no test coverage" in g for g in gaps)

    def test_ac_missing_negative(self):
        entries = [
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
        ]
        gaps = find_gaps(entries, [_ac("AC-1")])
        assert any("AC-1" in g and "no negative test" in g for g in gaps)

    def test_ac_missing_edge_case(self):
        entries = [
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
        ]
        gaps = find_gaps(entries, [_ac("AC-1")])
        assert any("AC-1" in g and "no edge-case test" in g for g in gaps)

    def test_multiple_gaps_sorted_by_ac_id(self):
        acs = [_ac("AC-3"), _ac("AC-1"), _ac("AC-2")]
        gaps = find_gaps([], acs)
        # Extract AC ids from gap strings and verify sort order
        ac_ids_in_order = []
        for g in gaps:
            for ac in ["AC-1", "AC-2", "AC-3"]:
                if ac in g and ac not in ac_ids_in_order:
                    ac_ids_in_order.append(ac)
        assert ac_ids_in_order == ["AC-1", "AC-2", "AC-3"]

    def test_all_gap_types_for_one_ac(self):
        """An AC with zero coverage should report ONE gap (no test coverage), not three."""
        entries = []  # no entries at all
        acs = [_ac("AC-1")]
        gaps = find_gaps(entries, acs)
        assert len(gaps) == 1
        assert "no test coverage" in gaps[0]

    def test_ac_with_only_functional_missing_both(self):
        """AC with only functional coverage should report missing negative AND edge-case."""
        entries = [RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional")]
        acs = [_ac("AC-1")]
        gaps = find_gaps(entries, acs)
        assert len(gaps) == 2
        assert any("negative" in g for g in gaps)
        assert any("edge-case" in g for g in gaps)
