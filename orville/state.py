"""Persisted run state: returned destination IDs saved immediately per report_id.

Cross-process retry key. Stored in an ignored local directory. Losing this
state is disclosed honestly: app-side markers allow dedupe recovery for GitHub
and Trello, but Discord exactly-once cannot be guaranteed after local state
loss, so an unverified Discord step is reconciled, never blind-reposted.
"""

import json
import os
from datetime import datetime, timezone


def _empty() -> dict:
    return {
        "github": {},       # issue_number, comment_id, html_url
        "trello": {},       # card_id, url
        "discord": {},      # message_id, channel_id
        "discord_uncertain": False,
        "status": "incomplete",
        "updated_at": None,
    }


class RunState:
    def __init__(self, state_dir: str) -> None:
        self.path = os.path.join(state_dir, "runs.json")
        os.makedirs(state_dir, exist_ok=True)
        self._data: dict[str, dict] = {}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def get(self, report_id: str) -> dict:
        return self._data.get(report_id, _empty())

    def update(self, report_id: str, status: str | None = None, **apps) -> None:
        entry = self._data.setdefault(report_id, _empty())
        for key in ("github", "trello", "discord"):
            if key in apps:
                entry[key].update(apps[key])
        if "discord_uncertain" in apps:
            entry["discord_uncertain"] = apps["discord_uncertain"]
        if status:
            entry["status"] = status
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
