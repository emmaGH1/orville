"""First-milestone probe: one scoped real write plus independent read-back in
each destination, through Orville's own clients.

Run: python -m orville.probe
"""

import sys
import time
import uuid

from .config import load_config
from .discord_client import DiscordClient
from .github_client import GitHubClient
from .trello_client import TrelloClient


def check(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    return ok


def main() -> int:
    cfg = load_config()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    results: list[bool] = []

    # GitHub: comment on fixture issue #1, then GET the comment back.
    gh = GitHubClient(cfg.github_repo, cfg.github_token)
    body = f"[orville-probe:{stamp}] scoped write/read-back check. Safe to ignore."
    try:
        c = gh.create_comment(1, body)
        got = gh.get_comment(c["id"])
        results.append(check(
            "github",
            got["id"] == c["id"] and "[orville-probe:" in got["body"],
            f"comment id={c['id']} url={c['html_url']} readback={'ok' if got['id'] == c['id'] else 'mismatch'}",
        ))
    except Exception as e:
        results.append(check("github", False, str(e)))

    # Trello: one card in the configured list, then GET it back.
    tr = TrelloClient(cfg.trello_api_key, cfg.trello_token)
    name = f"[orville-probe:{stamp}] write/read-back check"
    try:
        card = tr.create_card(cfg.trello_list_id, name, "Probe card. Safe to archive manually after checks.")
        got = tr.get_card(card["id"])
        results.append(check(
            "trello",
            got["id"] == card["id"] and got["idList"] == cfg.trello_list_id,
            f"card id={card['id']} url={card['url']} list={'ok' if got['idList'] == cfg.trello_list_id else 'mismatch'}",
        ))
    except Exception as e:
        results.append(check("trello", False, str(e)))

    # Discord: webhook send with wait=true, then fetch the message by ID.
    dc = DiscordClient(cfg.discord_webhook_url)
    nonce = uuid.uuid4().hex[:8]
    try:
        outcome = dc.post_message(f"[orville-probe:{stamp}:{nonce}] write/read-back check. Safe to ignore.")
        if outcome.status != "posted":
            results.append(check("discord", False, f"send status={outcome.status} {outcome.detail}"))
        else:
            mid = outcome.message["id"]
            got = dc.get_message(mid)
            results.append(check(
                "discord",
                got["id"] == mid and nonce in got["content"],
                f"message id={mid} readback={'ok' if nonce in got['content'] else 'content mismatch'}",
            ))
    except Exception as e:
        results.append(check("discord", False, str(e)))

    ok = all(results)
    print("PROBE", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
