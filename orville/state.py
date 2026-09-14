"""Persisted run state: returned destination IDs saved immediately per report_id.

Cross-process retry key. Stored in an ignored local directory. Each entry is
bound to the immutable report content and the configured destinations: a
report_id reused with different text or a different destination scope is
rejected before any app write. Destination secrets (the Discord webhook token)
are stored only as hashes, never raw. Losing this state is disclosed honestly:
app-side markers allow dedupe recovery for GitHub and Trello, but Discord
exactly-once cannot be guaranteed after local state loss, so an unverified
Discord step is reconciled, never blind-reposted.
"""

import hashlib
import json
import os
from datetime import datetime, timezone


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_binding(report_text: str, github_repo: str, trello_list_id: str,
                 discord_webhook_url: str) -> dict:
    """Immutable scope for a report_id: content plus destination identities.

    The webhook URL embeds a secret token, so only its hash is persisted.
    """
    return {
        "content": _sha(_normalize(report_text)),
        "github_repo": github_repo,
        "trello_list_id": trello_list_id,
        "discord_webhook_hash": _sha(discord_webhook_url),
    }


def _empty() -> dict:
    return {
        "github": {},       # issue_number, comment_id, html_url, anchor
        "trello": {},       # card_id, url
        "discord": {},      # message_id, channel_id
        "discord_uncertain": False,
        "github_create_uncertain": False,
        "binding": None,    # make_binding(...) once known
        "review": None,     # pending human decision; never an approval token
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
        if "github_create_uncertain" in apps:
            entry["github_create_uncertain"] = apps["github_create_uncertain"]
        if "binding" in apps:
            entry["binding"] = apps["binding"]
        if "review" in apps:
            entry["review"] = apps["review"]
        if status:
            entry["status"] = status
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def _save(self) -> None:
        # Atomic replacement so a crash mid-write cannot corrupt prior state.
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self.path)
