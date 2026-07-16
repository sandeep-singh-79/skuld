"""RTM (Requirements Traceability Matrix) builder for Skuld."""
from __future__ import annotations

from skuld.models import AcceptanceCriterion, RTMEntry, TestCase


def build_rtm(
    test_cases: list[TestCase],
    acceptance_criteria: list[AcceptanceCriterion],
) -> list[RTMEntry]:
    """Create an RTMEntry for every (test_case, ac_id) pair."""
    entries: list[RTMEntry] = []
    for tc in test_cases:
        for ac_id in tc.ac_ids:
            entries.append(
                RTMEntry(
                    ac_id=ac_id,
                    test_case_id=tc.id,
                    test_type=tc.test_type,
                    story_id=tc.story_id,
                )
            )
    return entries


def rtm_to_matrix(
    rtm_entries: list[RTMEntry],
    ac_list: list[AcceptanceCriterion],
    test_case_list: list[TestCase],
) -> dict:
    """Build a coverage matrix and detect orphan tests.

    Returns ``{"matrix": {ac_id: {tc_id: test_type}}, "orphan_test_ids": [...]}``.
    """
    matrix: dict[str, dict[str, str]] = {ac.id: {} for ac in ac_list}
    valid_ac_ids = {ac.id for ac in ac_list}

    referenced_tc_ids: set[str] = set()
    for entry in rtm_entries:
        if entry.ac_id in valid_ac_ids:
            matrix[entry.ac_id][entry.test_case_id] = entry.test_type
        referenced_tc_ids.add(entry.test_case_id)

    orphan_test_ids = [
        tc.id for tc in test_case_list
        if not any(ac_id in valid_ac_ids for ac_id in tc.ac_ids)
    ]

    return {"matrix": matrix, "orphan_test_ids": orphan_test_ids}


def find_gaps(
    rtm_entries: list[RTMEntry],
    ac_list: list[AcceptanceCriterion],
) -> list[str]:
    """Identify coverage gaps — missing test types per AC."""
    # Build {ac_id: set of test_types} from entries
    coverage: dict[str, set[str]] = {}
    for entry in rtm_entries:
        coverage.setdefault(entry.ac_id, set()).add(entry.test_type)

    gaps: list[str] = []
    for ac in sorted(ac_list, key=lambda a: a.id):
        types = coverage.get(ac.id, set())
        if not types:
            gaps.append(f"{ac.id}: no test coverage")
            continue
        if "negative" not in types:
            gaps.append(f"{ac.id}: no negative test")
        if "edge-case" not in types:
            gaps.append(f"{ac.id}: no edge-case test")

    return gaps
