"""Trace of planned actions, API outcomes, read-back assertions, and refusals.

All secrets are redacted before any output or persistence.
"""

import json
import os

from .config import SECRET_KEYS


def redact(text: str) -> str:
    """Replace any configured secret value found in text with [REDACTED]."""
    secrets = [os.getenv(k, "").strip() for k in SECRET_KEYS]
    secrets = [s for s in secrets if s]
    # Webhook URLs embed their token; also redact the webhook path itself.
    for s in secrets:
        text = text.replace(s, "[REDACTED]")
    return text


class Trace:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def add(self, kind: str, **detail) -> None:
        self.events.append({"kind": kind, **detail})

    def planned(self, action: str, target: str) -> None:
        self.add("planned", action=action, target=target)

    def outcome(self, action: str, target: str, ok: bool, detail: str = "") -> None:
        self.add("outcome", action=action, target=target, ok=ok, detail=redact(detail))

    def assertion(self, target: str, ok: bool, detail: str = "") -> None:
        self.add("readback", target=target, ok=ok, detail=redact(detail))

    def refused(self, request: str, reason: str) -> None:
        self.add("refused", request=request, reason=reason)

    def note(self, detail: str) -> None:
        self.add("note", detail=redact(detail))

    def rendered(self) -> list[dict]:
        return [json.loads(redact(json.dumps(e))) for e in self.events]
