"""Strip personal contact details out of transcribed candidate statements.

Candidates write their own statements, and a fair number sign off with a
personal address — "contact me at someone@example.com". The county publishes
those statements verbatim, so the address is already a public record and
reproducing it is lawful.

It is still a personal mailbox, and a voter guide has no use for it: nobody
reads a guide in order to email a candidate, and a published repo is a far
more durable, more scrapeable home for an address than a county PDF. So the
addresses are removed at ingest, before anything is written to disk, which
means a rebuild cannot quietly put them back.

Phone numbers are deliberately left alone: in these statements they are
almost always campaign numbers printed alongside a campaign website, not
personal lines.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

PLACEHOLDER = "[email removed]"


def redact_text(s: str) -> str:
    """Remove email addresses from one string."""
    if not isinstance(s, str) or "@" not in s:
        return s
    # Replace only the address, never the surrounding words. Swallowing the
    # label too ("contact me at ...") reads fine when the address ends the
    # sentence and mangles it when it does not.
    s = EMAIL.sub(PLACEHOLDER, s)
    # Collapse whitespace the substitution may have stranded.
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s+([.,;])", r"\1", s)
    return s


def redact(obj):
    """Recursively redact every string in a nested dict/list structure."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def count(obj) -> int:
    """How many distinct addresses are present (for reporting)."""
    import json

    return len(set(EMAIL.findall(json.dumps(obj, ensure_ascii=False))))
