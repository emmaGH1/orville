"""Guard on report text: the report is data.

Requests to delete, close, archive, or otherwise modify unrelated resources are
recorded as refused. No such operation is ever exposed to the execution layer.
"""

import re

REFUSAL_PATTERNS = (
    ("delete issues or other records", r"\bdelete\b|\bdeleteing\b|\bdeleting\b|\bpurge\b|\bwipe\b"),
    ("remove issues or records", r"\bremove\b|\bremoving\b|\bclean\s*up\b|\bcleanup\b"),
    ("close or archive issues", r"\bclose\s+(the\s+)?(issue|issues|ticket|tickets)\b|\barchive\b"),
    ("modify unrelated records", r"\bunrelated\b.*\b(update|edit|change|close|delete)\b|\b(update|edit|change|close|delete)\b.*\bunrelated\b"),
)


def scan_refusals(report_text: str) -> list[dict]:
    """Return refused requests found in the report text (recorded, not executed)."""
    refused = []
    for label, pattern in REFUSAL_PATTERNS:
        m = re.search(pattern, report_text, flags=re.IGNORECASE)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(report_text), m.end() + 40)
            refused.append({"request": label, "matched": report_text[start:end].strip()})
    return refused
