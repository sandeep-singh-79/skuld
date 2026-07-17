"""Comment filter for Skuld — removes noise, keeps signal from story comments."""
from __future__ import annotations

import re

# Strip HTML tags for pattern matching (not for output — we keep original text)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Noise patterns (case-insensitive regex)
_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*(moved|transferred)\s+(to|from)\s+sprint", re.IGNORECASE),
    re.compile(r"^\s*(status|state)\s+(changed|updated)", re.IGNORECASE),
    re.compile(r"\bPR\s*#?\d+\b.*\b(created|merged|closed|opened)\b", re.IGNORECASE),
    re.compile(r"\b(build|pipeline|ci|cd)\s+(passed|failed|running|succeeded)\b", re.IGNORECASE),
    re.compile(r"^\s*@\w+\s+(please|can you|could you)", re.IGNORECASE),
    re.compile(r"^\s*(assigned|unassigned|reassigned)\s+to\b", re.IGNORECASE),
    re.compile(r"^\s*(done|complete|finished|closed|resolved)\s*[.!]?\s*$", re.IGNORECASE),
    re.compile(r"\b(estimation|story\s*points?|sprint\s*planning)\b.*\b(updated|changed|set)\b", re.IGNORECASE),
    re.compile(r"^\s*(blocked|unblocked)\s+by\b", re.IGNORECASE),
    re.compile(r"\b(deployed|deployment)\s+(to|on)\s+(staging|prod|production|dev)\b", re.IGNORECASE),
]

# Signal patterns (if ANY match, always keep the comment regardless of noise patterns)
_SIGNAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bwhat\s+(if|about|happens)\b", re.IGNORECASE),
    re.compile(r"\bshould\s+we\b", re.IGNORECASE),
    re.compile(r"\b(edge\s*case|corner\s*case|boundary)\b", re.IGNORECASE),
    re.compile(r"\b(out\s+of\s+scope|not\s+supported|explicitly\s+excluded)\b", re.IGNORECASE),
    re.compile(r"\b(must\s+not|cannot|can'?t|won'?t|shouldn'?t)\b", re.IGNORECASE),
    re.compile(r"\b(rate\s*limit|timeout|expir|overflow|truncat)\b", re.IGNORECASE),
    re.compile(r"\b(similar\s+bug|regression|defect|incident)\b", re.IGNORECASE),
    re.compile(r"\?", re.IGNORECASE),  # Any question
]


def filter_comments(comments: list[str]) -> list[str]:
    """Filter story comments: keep signal, remove noise.

    Rules:
    1. If a comment matches ANY signal pattern -> keep (even if it also matches noise)
    2. If a comment matches ANY noise pattern and no signal -> remove
    3. If a comment matches neither -> keep (benefit of the doubt)

    HTML tags are stripped before pattern matching (Jira exports often wrap
    comments in markup), but the original text is preserved in output.

    Args:
        comments: Raw comment strings from story input.

    Returns:
        Filtered list of comments likely to contain useful test context.
    """
    result: list[str] = []
    for comment in comments:
        if not comment or not comment.strip():
            continue
        plain = _strip_html(comment)
        if _matches_any(plain, _SIGNAL_PATTERNS):
            result.append(comment)
        elif _matches_any(plain, _NOISE_PATTERNS):
            continue  # noise, skip
        else:
            result.append(comment)  # neither -> keep
    return result


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags for pattern matching."""
    return _HTML_TAG_RE.sub("", text)


def _matches_any(text: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in patterns)
