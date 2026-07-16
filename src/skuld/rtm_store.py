"""Persistent Requirements Traceability Matrix store for Skuld."""
from __future__ import annotations

import datetime
import os
import tempfile
from pathlib import Path

import yaml

from skuld.models import GapInfo, MergeResult, RTMEntry

_REQUIRED_TYPES = {"functional", "negative", "edge-case"}


class RTMStore:
    """Persistent Requirements Traceability Matrix store."""

    def __init__(self) -> None:
        self._entries: list[RTMEntry] = []
        self._metadata: dict = {"rtm_version": "1.0", "project_id": None}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> RTMStore:
        """Load an existing rtm.yaml file, or create empty store if missing."""
        store = cls()
        p = Path(path)
        if not p.exists():
            return store

        MAX_RTM_FILE_SIZE = 10_485_760  # 10MB
        file_size = p.stat().st_size
        if file_size > MAX_RTM_FILE_SIZE:
            raise ValueError(f"RTM file exceeds maximum size of 10MB ({file_size} bytes)")

        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not data:
            return store

        store._metadata = data.get("metadata", store._metadata)

        version = store._metadata.get("rtm_version", "unknown")
        if version != "1.0":
            raise ValueError(f"Unsupported RTM version '{version}' in '{path}' (expected '1.0')")

        required_keys = ("ac_id", "test_case_id", "test_type")
        for i, raw in enumerate(data.get("entries", [])):
            for key in required_keys:
                if key not in raw:
                    raise ValueError(f"Entry {i} in '{path}' missing required key '{key}'")
            store._entries.append(
                RTMEntry(
                    ac_id=raw["ac_id"],
                    test_case_id=raw["test_case_id"],
                    test_type=raw["test_type"],
                    story_id=raw.get("story_id"),
                    added_date=str(raw["added_date"]) if raw.get("added_date") is not None else None,
                    added_by_run=raw.get("added_by_run"),
                    status=raw.get("status", "active"),
                )
            )
        return store

    def save(self, path: str) -> None:
        """Write the store to rtm.yaml."""
        data = {
            "metadata": self._metadata,
            "entries": [
                {
                    "ac_id": e.ac_id,
                    "test_case_id": e.test_case_id,
                    "test_type": e.test_type,
                    "story_id": e.story_id,
                    "added_date": e.added_date,
                    "added_by_run": e.added_by_run,
                    "status": e.status,
                }
                for e in self._entries
            ],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        dir_name = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.dump(data, fh, default_flow_style=False, sort_keys=False)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(
        self,
        new_entries: list[RTMEntry],
        story_id: str,
        run_id: str,
        force: bool = False,
    ) -> MergeResult:
        """Merge new entries from a generation run.

        - Adds each entry with *run_id*, today's date, and ``status="active"``.
        - ``force=False`` (default): AC-level merge — only supersedes existing
          active entries whose ``ac_id`` is in the incoming batch AND whose
          ``story_id`` matches.  Entries for ACs not in the batch are retained.
        - ``force=True``: supersedes ALL active entries for the *story_id*
          (the legacy full-regeneration behaviour).
        - Cross-story overlap: if an incoming AC already has active entries
          from a *different* story, a warning is appended to ``conflicts``.
        """
        today = datetime.date.today().isoformat()
        added = 0
        superseded = 0
        retained = 0
        conflicts: list[str] = []

        # Deduplicate: last entry wins for same (ac_id, test_case_id)
        seen: dict[tuple[str, str], RTMEntry] = {}
        for entry in new_entries:
            seen[(entry.ac_id, entry.test_case_id)] = entry
        deduped = list(seen.values())

        incoming_ac_ids = {e.ac_id for e in deduped}

        # --- Cross-story overlap warnings ---
        # Build map: ac_id → story_id for active entries from OTHER stories
        cross_story_map: dict[str, str] = {}
        for existing in self._entries:
            if (
                existing.status == "active"
                and existing.story_id
                and existing.story_id != story_id
                and existing.ac_id in incoming_ac_ids
            ):
                cross_story_map.setdefault(existing.ac_id, existing.story_id)

        for ac_id, other_story in cross_story_map.items():
            conflicts.append(f"{ac_id} already covered by story {other_story}")

        # --- Supersede phase ---
        if force:
            # Force mode: supersede ALL active entries for this story_id
            for existing in self._entries:
                if existing.status == "active" and existing.story_id == story_id:
                    existing.status = "superseded"
                    superseded += 1
        else:
            # AC-level merge: only supersede entries whose ac_id is in the
            # incoming batch AND belong to the same story_id
            for existing in self._entries:
                if (
                    existing.status == "active"
                    and existing.story_id == story_id
                    and existing.ac_id in incoming_ac_ids
                ):
                    existing.status = "superseded"
                    superseded += 1

            # Count retained: active entries for this story whose AC is NOT in
            # the incoming batch (they survive untouched)
            for existing in self._entries:
                if (
                    existing.status == "active"
                    and existing.story_id == story_id
                    and existing.ac_id not in incoming_ac_ids
                ):
                    retained += 1

        # --- Add phase ---
        for incoming in deduped:
            self._entries.append(
                RTMEntry(
                    ac_id=incoming.ac_id,
                    test_case_id=incoming.test_case_id,
                    test_type=incoming.test_type,
                    story_id=incoming.story_id or story_id,
                    added_date=today,
                    added_by_run=run_id,
                    status="active",
                )
            )
            added += 1

        return MergeResult(
            added=added,
            superseded=superseded,
            conflicts=conflicts,
            retained=retained,
        )

    # ------------------------------------------------------------------
    # Deprecate
    # ------------------------------------------------------------------

    def deprecate(self, test_case_ids: list[str]) -> int:
        """Mark active entries for given test-case IDs as deprecated."""
        ids = set(test_case_ids)
        count = 0
        for entry in self._entries:
            if entry.status == "active" and entry.test_case_id in ids:
                entry.status = "deprecated"
                count += 1
        return count

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    def query_gaps(self, ac_ids: list[str] | None = None) -> list[GapInfo]:
        """Find ACs with incomplete coverage among active entries.

        If *ac_ids* is provided, also report ACs that have zero entries.
        """
        # Build coverage map from active entries
        coverage: dict[str, set[str]] = {}
        story_map: dict[str, str | None] = {}
        for e in self.active_entries:
            coverage.setdefault(e.ac_id, set()).add(e.test_type)
            if e.ac_id not in story_map:
                story_map[e.ac_id] = e.story_id

        # Determine which AC IDs to analyse
        all_ac_ids: set[str] = set(coverage.keys())
        if ac_ids is not None:
            all_ac_ids |= set(ac_ids)

        # TODO: populate gap_since by tracking when coverage was last complete for each AC
        gaps: list[GapInfo] = []
        for ac_id in sorted(all_ac_ids):
            types = coverage.get(ac_id, set())
            missing = sorted(_REQUIRED_TYPES - types)
            if missing:
                gaps.append(
                    GapInfo(
                        ac_id=ac_id,
                        story_id=story_map.get(ac_id),
                        missing_types=missing,
                        gap_since=None,
                    )
                )
        return gaps

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def coverage_summary(self) -> dict:
        """Aggregate stats over active entries only."""
        active = self.active_entries
        return {
            "total_entries": len(active),
            "total_stories": len({e.story_id for e in active if e.story_id}),
            "total_test_cases": len({e.test_case_id for e in active}),
            "unique_acs": len({e.ac_id for e in active}),
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def entries(self) -> list[RTMEntry]:
        """All entries (all statuses)."""
        return list(self._entries)

    @property
    def active_entries(self) -> list[RTMEntry]:
        """Only active entries."""
        return [e for e in self._entries if e.status == "active"]
