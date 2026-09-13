"""Stateful in-memory fakes for the evaluation and regression cases.

They exercise failure and retry paths locally only; live three-app runs are
performed separately against the real apps.
"""

from orville.discord_client import DiscordOutcome


class FakeGitHub:
    def __init__(self, issues: dict[int, str], fail_list_comments: bool = False,
                 fail_get_issue: bool = False, fail_get_issue_times: int = 0,
                 lose_create: bool = False) -> None:
        self._next = 1000  # comment ids
        self.issues = {n: {"title": t, "body": "", "html_url": f"https://github.test/issue/{n}"} for n, t in issues.items()}
        self.comments: dict[int, list[dict]] = {n: [] for n in self.issues}
        self.deleted: list = []
        self.fail_list_comments = fail_list_comments
        self.fail_get_issue = fail_get_issue
        self.fail_get_issue_times = fail_get_issue_times
        self.lose_create = lose_create

    def list_open_issues(self, per_page: int = 20) -> list[dict]:
        return [{"number": n, "title": d["title"], "body": d["body"], "html_url": d["html_url"]}
                for n, d in self.issues.items()]

    def create_comment(self, issue_number: int, body: str) -> dict:
        if issue_number not in self.comments:
            raise RuntimeError(f"issue {issue_number} not found")
        self._next += 1
        c = {"id": self._next, "body": body, "issue_number": issue_number,
             "html_url": f"https://github.test/issue/{issue_number}#comment-{self._next}"}
        self.comments[issue_number].append(c)
        return {"id": c["id"], "html_url": c["html_url"]}

    def get_comment(self, comment_id: int) -> dict:
        for issue_number, cs in self.comments.items():
            for c in cs:
                if c["id"] == comment_id:
                    return {"id": c["id"], "body": c["body"], "issue_number": issue_number,
                            "html_url": c["html_url"]}
        raise RuntimeError(f"comment {comment_id} not found")

    def create_issue(self, title: str, body: str) -> dict:
        n = max(self.issues, default=0) + 1
        self.issues[n] = {"title": title, "body": body, "html_url": f"https://github.test/issue/{n}"}
        self.comments[n] = []
        if self.lose_create:
            # Simulate the issue being created but the POST response being lost.
            raise ConnectionError("connection reset after GitHub accepted the create")
        return {"number": n, "id": n * 10, "html_url": f"https://github.test/issue/{n}"}

    def get_issue(self, issue_number: int) -> dict:
        if self.fail_get_issue:
            raise RuntimeError("simulated github outage on issue read")
        if self.fail_get_issue_times > 0:
            self.fail_get_issue_times -= 1
            raise RuntimeError("simulated github outage on first issue read")
        if issue_number not in self.issues:
            raise RuntimeError(f"issue {issue_number} not found")
        d = self.issues[issue_number]
        return {"number": issue_number, "title": d["title"], "body": d["body"], "html_url": d["html_url"]}

    def list_comments(self, issue_number: int, per_page: int = 50) -> list[dict]:
        if self.fail_list_comments:
            raise RuntimeError("simulated github outage on comment list")
        return list(self.comments.get(issue_number, []))

    def delete_issue(self, n: int) -> None:  # exists only to prove it is never called
        self.deleted.append(n)


class FakeTrello:
    def __init__(self, fail_next_create: int = 0, fail_list_cards: bool = False) -> None:
        self.cards: list[dict] = []
        self.fail_next_create = fail_next_create
        self.fail_list_cards = fail_list_cards
        self.deleted: list = []

    def create_card(self, list_id: str, name: str, desc: str) -> dict:
        if self.fail_next_create > 0:
            self.fail_next_create -= 1
            raise RuntimeError("simulated trello outage")
        c = {"id": f"card{len(self.cards) + 1}", "idList": list_id, "name": name, "desc": desc,
             "url": f"https://trello.test/c/{len(self.cards) + 1}"}
        self.cards.append(c)
        return {"id": c["id"], "url": c["url"]}

    def get_card(self, card_id: str) -> dict:
        for c in self.cards:
            if c["id"] == card_id:
                return dict(c)
        raise RuntimeError(f"card {card_id} not found")

    def list_cards(self, list_id: str) -> list[dict]:
        if self.fail_list_cards:
            raise RuntimeError("simulated trello outage on card list")
        return [{"id": c["id"], "name": c["name"], "desc": c["desc"]} for c in self.cards if c["idList"] == list_id]

    def delete_card(self, n: str) -> None:  # exists only to prove it is never called
        self.deleted.append(n)


class FakeDiscord:
    """mode: ok | fail | uncertain | lost.
    "lost" simulates a message delivered and then the response connection
    reset: the message exists, but the caller receives an exception with no ID."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.mode = "ok"  # ok | fail | uncertain | lost

    def post_message(self, content: str) -> DiscordOutcome:
        if self.mode == "lost":
            m = {"id": f"msg{len(self.messages) + 1}", "channel_id": "chan1", "content": content}
            self.messages.append(m)
            raise ConnectionError("connection reset after Discord accepted the message")
        if self.mode == "fail":
            return DiscordOutcome("failed", detail="simulated discord 500")
        if self.mode == "uncertain":
            return DiscordOutcome("uncertain", detail="timeout without message ID")
        m = {"id": f"msg{len(self.messages) + 1}", "channel_id": "chan1", "content": content}
        self.messages.append(m)
        return DiscordOutcome("posted", message={"id": m["id"], "channel_id": m["channel_id"]})

    def get_message(self, message_id: str) -> dict:
        for m in self.messages:
            if m["id"] == message_id:
                return dict(m)
        raise RuntimeError(f"message {message_id} not found")
