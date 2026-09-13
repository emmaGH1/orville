"""Trace of planned actions, API outcomes, read-back assertions, and refusals.

All secrets are redacted before any output or persistence. Secrets are the
configured credential values (and anything embedded in them, such as a webhook
token inside its URL); they are supplied by the caller or taken from .env.
"""

import json
import os

from .config import SECRET_KEYS


def redact(text: str, secrets: list[str] | None = None) -> str:
    """Replace any configured secret value found in text with [REDACTED]."""
    if secrets is None:
        secrets = [os.getenv(k, "").strip() for k in SECRET_KEYS]
    for s in secrets:
        if s:
            text = text.replace(s, "[REDACTED]")
    return text


class Trace:
    def __init__(self, secrets: list[str] | None = None) -> None:
        self.secrets = secrets if secrets is not None else [os.getenv(k, "").strip() for k in SECRET_KEYS]
        self.events: list[dict] = []

    def _clean(self, text: str) -> str:
        return redact(text, secrets=self.secrets)

    def add(self, kind: str, **detail) -> None:
        self.events.append({"kind": kind, **detail})

    def planned(self, action: str, target: str) -> None:
        self.add("planned", action=action, target=self._clean(target))

    def outcome(self, action: str, target: str, ok: bool, detail: str = "") -> None:
        self.add("outcome", action=action, target=self._clean(target), ok=ok, detail=self._clean(detail))

    def assertion(self, target: str, ok: bool, detail: str = "") -> None:
        self.add("readback", target=self._clean(target), ok=ok, detail=self._clean(detail))

    def refused(self, request: str, reason: str) -> None:
        self.add("refused", request=request, reason=self._clean(reason))

    def note(self, detail: str) -> None:
        self.add("note", detail=self._clean(detail))

    def rendered(self) -> list[dict]:
        return [json.loads(self._clean(json.dumps(e))) for e in self.events]
