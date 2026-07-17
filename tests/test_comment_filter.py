"""Tests for skuld.comment_filter — noise removal from story comments."""
from __future__ import annotations

import pytest


class TestFilterComments:
    """Comment filter: signal kept, noise removed, edge cases handled."""

    # ---- Signal kept ----

    def test_question_kept(self):
        from skuld.comment_filter import filter_comments

        comments = ["What if session expires mid-flow?"]
        result = filter_comments(comments)
        assert comments[0] in result

    def test_edge_case_mention_kept(self):
        from skuld.comment_filter import filter_comments

        comments = ["Dev: edge case — empty cart checkout"]
        result = filter_comments(comments)
        assert comments[0] in result

    def test_scope_exclusion_kept(self):
        from skuld.comment_filter import filter_comments

        comments = ["PM: biometric login out of scope"]
        result = filter_comments(comments)
        assert comments[0] in result

    def test_constraint_kept(self):
        from skuld.comment_filter import filter_comments

        comments = ["Rate limit is 100 req/min"]
        result = filter_comments(comments)
        assert comments[0] in result

    def test_regression_reference_kept(self):
        from skuld.comment_filter import filter_comments

        comments = ["Similar bug in PROJ-456"]
        result = filter_comments(comments)
        assert comments[0] in result

    # ---- Noise removed ----

    def test_sprint_move_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ["Moved to Sprint 14"]
        result = filter_comments(comments)
        assert len(result) == 0

    def test_pr_created_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ["PR #234 created"]
        result = filter_comments(comments)
        assert len(result) == 0

    def test_status_update_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ["Status changed to In Progress"]
        result = filter_comments(comments)
        assert len(result) == 0

    def test_done_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ["Done"]
        result = filter_comments(comments)
        assert len(result) == 0

    def test_deployment_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ["Deployed to staging"]
        result = filter_comments(comments)
        assert len(result) == 0

    def test_assignment_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ["Assigned to john"]
        result = filter_comments(comments)
        assert len(result) == 0

    # ---- Edge cases ----

    def test_empty_list_returns_empty(self):
        from skuld.comment_filter import filter_comments

        assert filter_comments([]) == []

    def test_empty_string_comments_stripped(self):
        from skuld.comment_filter import filter_comments

        result = filter_comments(["", "  ", "\n"])
        assert result == []

    def test_signal_overrides_noise(self):
        from skuld.comment_filter import filter_comments

        # Has both signal ('?') and noise ('deployment to staging')
        comment = "What if deployment to staging fails?"
        result = filter_comments([comment])
        assert comment in result

    def test_neutral_comment_kept(self):
        from skuld.comment_filter import filter_comments

        # No signal, no noise → kept (benefit of the doubt)
        comment = "The API returns JSON format"
        result = filter_comments([comment])
        assert comment in result

    # ---- HTML/markup handling ----

    def test_html_wrapped_noise_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ["<p>Moved to Sprint 14</p>"]
        result = filter_comments(comments)
        assert len(result) == 0

    def test_html_wrapped_signal_kept(self):
        from skuld.comment_filter import filter_comments

        comments = ["<p>What if the session expires?</p>"]
        result = filter_comments(comments)
        assert comments[0] in result

    def test_complex_html_noise_removed(self):
        from skuld.comment_filter import filter_comments

        comments = ['<div class="comment"><b>Status</b> changed to Done</div>']
        result = filter_comments(comments)
        assert len(result) == 0

    def test_html_signal_preserves_original_text(self):
        from skuld.comment_filter import filter_comments

        comment = "<em>Edge case</em>: empty list input"
        result = filter_comments([comment])
        # Original text (with HTML) is preserved in output
        assert result[0] == comment

    # ---- Multi-line comments ----

    def test_multiline_comment_with_signal_kept(self):
        from skuld.comment_filter import filter_comments

        comment = "Sprint planning notes:\nWhat if the API rate limit is hit?"
        result = filter_comments([comment])
        assert comment in result

    def test_multiline_noise_only_removed(self):
        from skuld.comment_filter import filter_comments

        comment = "Deployed to staging\nBuild passed"
        result = filter_comments([comment])
        assert len(result) == 0

    # ---- Non-English comments ----

    def test_hindi_comment_kept(self):
        from skuld.comment_filter import filter_comments

        comment = "यह API timeout 30 सेकंड के बाद होता है"
        result = filter_comments([comment])
        assert comment in result

    def test_chinese_comment_kept(self):
        from skuld.comment_filter import filter_comments

        comment = "当用户输入为空时，系统应该返回错误消息"
        result = filter_comments([comment])
        assert comment in result

    def test_mixed_language_signal_kept(self):
        from skuld.comment_filter import filter_comments

        # Hindi with English signal keyword
        comment = "यह edge case है — empty input"
        result = filter_comments([comment])
        assert comment in result
