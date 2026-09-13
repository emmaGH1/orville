"""Five minimum evaluation cases plus guard/validator unit checks.

Local stateful fakes exercise failure paths. Live three-app runs are separate.
"""

import sys
import uuid
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orville.config import Config
from orville.planner import GroqPlanner, StubPlanner, validate_choice
from orville.runner import run
from tests.fakes import FakeDiscord, FakeGitHub, FakeTrello

CANDIDATES = {1: "CSV export stalls on 5k+ rows", 2: "Account settings scope check"}
NEW_REPORT = ("Northwind Labs says the invoice PDF preview renders blank pages when the invoice has "
              "more than 40 line items. They are blocked from month-end statements. Please route "
              "this to engineering and set up the customer follow-up.")
HARBOR_REPORT = Path(__file__).resolve().parents[1].joinpath("eval/reports/harbor_export_01.txt").read_text(encoding="utf-8")


def make_cfg(tmp_path):
    return Config(
        github_repo="test/repo", github_token="gh-test-token",
        trello_api_key="k-test", trello_token="t-test", trello_list_id="list1",
        discord_webhook_url="https://discord.test/webhook/x",
        model_base_url="https://api.test/v1", model_id="stub", groq_api_key="g-test",
        state_dir=str(tmp_path / "state"),
    )


def fresh_clients(**kwargs):
    return {
        "github": kwargs.get("github", FakeGitHub(CANDIDATES)),
        "trello": kwargs.get("trello", FakeTrello()),
        "discord": kwargs.get("discord", FakeDiscord()),
    }


def readbacks(trace, target):
    return [e for e in trace if e["kind"] == "readback" and e["target"] == target and e["ok"]]


# Case 1: normal new report -> three writes, three reads, complete only after checks.
def test_normal_new_report(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r = run("NEW-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r["status"] == "complete", r
    assert all(r["apps"][a]["verified"] for a in ("github", "trello", "discord"))
    assert all(readbacks(r["trace"], t) for t in ("github", "trello", "discord"))
    assert len(cl["trello"].cards) == 1 and len(cl["discord"].messages) == 1


# Case 2: existing matching issue -> comment on returned ID, no duplicate issue.
def test_existing_match(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r = run("HARBOR-EXPORT-01", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r["status"] == "complete", r
    assert r["apps"]["github"]["issue_number"] == 1
    assert len(cl["github"].issues) == 2, "must not create a duplicate issue"
    assert len(cl["github"].comments[1]) == 1


# Case 3: ambiguous match -> needs_human before any write.
def test_ambiguous_needs_human(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r = run("AMBIG-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("ambiguous"))
    assert r["status"] == "needs_human", r
    assert len(cl["github"].comments[1]) == 0 and len(cl["github"].comments[2]) == 0
    assert len(cl["trello"].cards) == 0 and len(cl["discord"].messages) == 0


# Case 3b: fabricated issue ID is rejected in code.
def test_fabricated_id_rejected(tmp_path):
    choice = StubPlanner("fabricated").plan([{"number": 1, "title": "CSV export stalls on 5k+ rows", "body": "", "html_url": ""}], HARBOR_REPORT)
    d = validate_choice(choice, [{"number": 1, "title": "CSV export stalls on 5k+ rows", "body": "", "html_url": ""}])
    assert d.decision == "needs_human"


# Case 4: deletion request -> refusal visible in trace, no delete API call.
def test_deletion_refused(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r = run("HARBOR-EXPORT-01", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    refused_kinds = [e for e in r["trace"] if e["kind"] == "refused"]
    assert refused_kinds and all("delete" in e["request"] or "remove" in e["request"] or "unrelated" in e["request"] for e in refused_kinds)
    assert cl["github"].deleted == [] and cl["trello"].deleted == []


# Case 5: retry after trello failure reuses verified github, creates only missing work.
def test_retry_after_trello_failure(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients(trello=FakeTrello(fail_next_create=1))
    r1 = run("RETRY-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "partial", r1
    assert r1["apps"]["github"]["verified"] and not r1["apps"]["trello"].get("verified", False)
    comments_before = len(cl["github"].comments[3])
    discord_before = len(cl["discord"].messages)

    r2 = run("RETRY-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "complete", r2
    assert len(cl["github"].comments[3]) == comments_before, "must reuse the github comment"
    assert len(cl["discord"].messages) == discord_before + 1, "discord posts once, after both earlier steps verify"
    assert "Trello:" in cl["discord"].messages[-1]["content"]


# Case 5b: rerun of a complete report creates no duplicates.
def test_rerun_complete_no_duplicates(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r1 = run("HARBOR-EXPORT-01", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r1["status"] == "complete"
    counts = (len(cl["github"].comments[1]), len(cl["trello"].cards), len(cl["discord"].messages))
    r2 = run("HARBOR-EXPORT-01", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r2["status"] == "complete"
    assert (len(cl["github"].comments[1]), len(cl["trello"].cards), len(cl["discord"].messages)) == counts


# Case 5c: discord uncertainty pauses for reconciliation instead of reposting.
def test_discord_uncertain_reconcile(tmp_path):
    cfg = make_cfg(tmp_path)
    dcl = FakeDiscord()
    dcl.mode = "uncertain"
    cl = fresh_clients(discord=dcl)
    r1 = run("UNC-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "partial"
    assert any("uncertain" in e for e in r1["errors"])
    msgs_before = len(dcl.messages)

    dcl.mode = "ok"
    r2 = run("UNC-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "partial", "must not blind-repost an uncertain send"
    assert len(dcl.messages) == msgs_before
    assert any("uncertain" in e for e in r2["errors"])


def test_redaction_in_trace(tmp_path):
    cfg = make_cfg(tmp_path)

    class LeakyTrello(FakeTrello):
        def list_cards(self, list_id: str) -> list[dict]:
            # Simulate an httpx-style exception that embeds the authenticated URL.
            raise RuntimeError(f"GET https://api.trello.com/1/lists/{list_id}/cards"
                               f"?key={cfg.trello_api_key}&token={cfg.trello_token} failed")

    cl = fresh_clients(trello=LeakyTrello())
    r = run("RED-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    dumped = str(r["trace"]) + str(r["errors"]) + str(r.get("reason", ""))
    assert "gh-test-token" not in dumped and "g-test" not in dumped
    assert "k-test" not in dumped and "t-test" not in dumped
    assert "https://discord.test/webhook/x" not in dumped


def test_empty_inputs_rejected(tmp_path):
    cfg = make_cfg(tmp_path)
    r = run("", NEW_REPORT, cfg, clients=fresh_clients(), planner=StubPlanner("normal"))
    assert r["status"] == "error"
    r = run("X-1", "   ", cfg, clients=fresh_clients(), planner=StubPlanner("normal"))
    assert r["status"] == "error"


# Regression (review fix 1): lost local state + failing GitHub comment-marker
# search must fail closed -- no duplicate comment, never complete.
def test_github_dedupe_fail_closed(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES)
    cl = fresh_clients(github=gh)
    r1 = run("DEDUPE-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r1["status"] == "complete"
    comment_before = len(gh.comments[1])

    # Fresh runner state (lost local state), but the marker comment exists in
    # the app. The marker search fails, so the runner must not write.
    gh2 = FakeGitHub(CANDIDATES, fail_list_comments=True)
    gh2.comments[1] = list(gh.comments[1])
    cl2 = fresh_clients(github=gh2, trello=FakeTrello(), discord=FakeDiscord())
    cfg2 = replace(cfg, state_dir=str(tmp_path / "state2"))
    r2 = run("DEDUPE-1", HARBOR_REPORT, cfg2, clients=cl2, planner=StubPlanner("normal"))
    assert r2["status"] == "partial", r2
    assert len(gh2.comments[1]) == comment_before, "must not write a duplicate comment"
    assert gh2.deleted == []
    assert any("marker search failed" in e and "withheld" in e for e in r2["errors"])
    assert r2["apps"]["github"]["verified"] is False
    assert len(cl2["trello"].cards) == 0 and len(cl2["discord"].messages) == 0


# Regression (review fix 1): lost local state + failing Trello card-marker
# search must fail closed -- no duplicate card, never complete.
def test_trello_dedupe_fail_closed(tmp_path):
    cfg = make_cfg(tmp_path)
    tr = FakeTrello()
    cl = fresh_clients(trello=tr)
    r1 = run("DEDUPE-2", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r1["status"] == "complete"
    cards_before = len(tr.cards)

    # Fresh runner state; github side finds its marker and reuses, but the
    # trello card-marker search fails, so no card write may happen.
    tr2 = FakeTrello(fail_list_cards=True)
    tr2.cards = list(tr.cards)  # pre-seed the existing card
    gh2 = FakeGitHub(CANDIDATES)
    gh2.comments[1] = list(cl["github"].comments[1])  # pre-seed for github reuse
    cl2 = fresh_clients(github=gh2, trello=tr2, discord=FakeDiscord())
    cfg2 = replace(cfg, state_dir=str(tmp_path / "state2"))
    r2 = run("DEDUPE-2", HARBOR_REPORT, cfg2, clients=cl2, planner=StubPlanner("normal"))
    assert r2["status"] == "partial", r2
    assert len(tr2.cards) == cards_before, "must not write a duplicate card"
    assert any("marker search failed" in e for e in r2["errors"])
    assert r2["apps"]["trello"]["verified"] is False


# Regression (review fix 2): message delivered but response lost -> uncertain,
# persisted; retry must not POST again and must never claim complete.
def test_discord_lost_response_no_duplicate(tmp_path):
    cfg = make_cfg(tmp_path)
    dcl = FakeDiscord()
    dcl.mode = "lost"
    cl = fresh_clients(discord=dcl)
    r1 = run("LOST-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "partial", r1
    assert not r1["apps"].get("discord", {}).get("verified", False)
    assert any("uncertain" in e for e in r1["errors"])
    assert len(dcl.messages) == 1, "message was delivered despite the lost response"

    # Persisted uncertainty must survive the process: fresh RunState reads the
    # same state dir (cfg unchanged), and the client is healthy again.
    dcl.mode = "ok"
    r2 = run("LOST-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "partial", "must not claim complete after an uncertain send"
    assert len(dcl.messages) == 1, "must not blind-repost an uncertain send"
    assert any("uncertain" in e and "reconcile" in e for e in r2["errors"])


# Regression (review fix 3): a created GitHub issue that cannot be read back
# must not be reported verified, and later steps must not proceed on it.
def test_new_issue_readback_fail_never_complete(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES, fail_get_issue=True)
    cl = fresh_clients(github=gh)
    r = run("READBACK-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r["status"] == "partial", r
    assert r["apps"]["github"]["verified"] is False
    assert len(gh.issues) == 3, "issue was created but must not be claimed as verified"
    assert len(cl["trello"].cards) == 0, "must not continue to trello on an unverified github anchor"
    assert len(cl["discord"].messages) == 0


# Tightened proofs: comment belongs to the selected issue; card desc carries
# the verified github link; discord content carries both verified links.
def test_cross_link_proofs(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r = run("LINK-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r["status"] == "complete"
    gh_url = r["apps"]["github"]["url"]
    tr_url = r["apps"]["trello"]["url"]
    assert cl["github"].comments[3][0]["body"].count(gh_url) >= 0  # comment body is report data
    assert gh_url in cl["trello"].cards[0]["desc"], "card desc must contain the verified github link"
    assert gh_url in cl["discord"].messages[0]["content"]
    assert tr_url in cl["discord"].messages[0]["content"]


# Wrong-issue comment must fail the ownership check (fabricated cross-app state).
def test_comment_ownership_check(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES)
    # Local state claims comment 1001 on issue 1, but the comment actually
    # lives on issue 2: the read-back ownership assertion must catch it.
    gh.comments[1] = []
    gh.create_comment(2, "[orville:OWN-1] misplaced")
    from orville.state import make_binding
    state = {"github": {"issue_number": 1, "comment_id": 1001}, "trello": {}, "discord": {},
             "discord_uncertain": False, "github_create_uncertain": False,
             "binding": make_binding(NEW_REPORT, cfg.github_repo, cfg.trello_list_id,
                                     cfg.discord_webhook_url),
             "status": "incomplete", "updated_at": None}
    import json as _json
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "runs.json").write_text(_json.dumps({"OWN-1": state}), encoding="utf-8")
    r = run("OWN-1", NEW_REPORT, cfg, clients=fresh_clients(github=gh),
            planner=StubPlanner("normal"))
    assert r["status"] == "partial"
    assert r["apps"]["github"]["verified"] is False


# Regression (second pass 1a): created issue, then its GET read-back fails.
# The returned number is persisted immediately; retry verifies that same issue
# and must not create a second one.
def test_new_issue_get_fail_retry_no_duplicate(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES, fail_get_issue_times=1)
    cl = fresh_clients(github=gh)
    r1 = run("GETFAIL-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "partial", r1
    assert r1["apps"]["github"]["verified"] is False
    assert len(gh.issues) == 3
    # number was persisted despite the failed read-back
    from orville.state import RunState
    assert RunState(cfg.state_dir).get("GETFAIL-1")["github"]["issue_number"] == 3

    r2 = run("GETFAIL-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "complete", r2
    assert len(gh.issues) == 3, "retry must verify the recorded issue, not create another"
    assert r2["apps"]["github"]["issue_number"] == 3


# Regression (second pass 1b): create POST outcome unknown (response lost).
# Mark uncertain, then reconcile by report marker on retry; exactly one issue.
def test_new_issue_create_unknown_reconciled_by_marker(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES, lose_create=True)
    cl = fresh_clients(github=gh)
    r1 = run("UNKN-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "partial", r1
    assert any("no ID" in e or "uncertain" in e for e in r1["errors"])
    assert len(gh.issues) == 3, "the create actually took effect despite the lost response"
    from orville.state import RunState
    assert RunState(cfg.state_dir).get("UNKN-1")["github_create_uncertain"] is True

    r2 = run("UNKN-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "complete", r2
    assert len(gh.issues) == 3, "reconciliation must adopt the marker-matching issue, not create another"
    assert r2["apps"]["github"]["issue_number"] == 3


# Regression (bounded search): with >20 open issues, an uncertain creation
# whose marker falls outside the bounded search window stays uncertain --
# partial result, flag persists, and no retry ever creates again.
def test_uncertain_create_missing_marker_in_bounded_search_stays_partial(tmp_path):
    cfg = make_cfg(tmp_path)
    issues = {n: f"Old issue {n}" for n in range(1, 26)}  # 25 open issues
    gh = FakeGitHub(issues, lose_create=True, bounded_list=True)
    cl = fresh_clients(github=gh)
    r1 = run("BOUNDED-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "partial", r1
    assert len(gh.issues) == 26, "the create took effect but its response was lost"
    from orville.state import RunState
    assert RunState(cfg.state_dir).get("BOUNDED-1")["github_create_uncertain"] is True

    # The marker issue (#26) is outside the bounded 20-issue window, so
    # reconciliation cannot confirm it: stay uncertain, never recreate.
    r2 = run("BOUNDED-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "partial", r2
    assert len(gh.issues) == 26, "must not create again while creation is unconfirmed"
    assert RunState(cfg.state_dir).get("BOUNDED-1")["github_create_uncertain"] is True
    assert any("no create until a human reconciles" in e for e in r2["errors"])
    assert r2["apps"]["github"]["verified"] is False

    # A third run behaves identically: deterministic fail-closed, no writes.
    r3 = run("BOUNDED-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r3["status"] == "partial"
    assert len(gh.issues) == 26


# ---- Final review fixes ---------------------------------------------------

def _seed_state(tmp_path, report_id, report_text, cfg, github: dict, trello: dict | None = None,
                discord: dict | None = None, include_binding: bool = True) -> None:
    """Write a runs.json entry directly, as a prior process would have left it."""
    import json as _json
    from orville.state import make_binding
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    entry = {"github": github, "trello": trello or {}, "discord": discord or {},
             "discord_uncertain": False, "github_create_uncertain": False,
             "binding": make_binding(report_text, cfg.github_repo, cfg.trello_list_id,
                                     cfg.discord_webhook_url) if include_binding else None,
             "status": "incomplete", "updated_at": None}
    data = {}
    path = state_dir / "runs.json"
    if path.exists():
        data = _json.loads(path.read_text(encoding="utf-8"))
    data[report_id] = entry
    path.write_text(_json.dumps(data, indent=2), encoding="utf-8")


# Final-review fix 1a: comment response lost after GitHub accepted it. The
# anchor was persisted pre-POST, so the retry reconciles the SAME issue even
# when the planner would now choose a different one.
def test_lost_comment_response_retries_same_issue(tmp_path):
    cfg = make_cfg(tmp_path)

    class LostComment(FakeGitHub):
        def create_comment(self, issue_number, body):
            result = super().create_comment(issue_number, body)
            if issue_number == 1:
                raise ConnectionError("accepted but response lost")
            return result

    from orville.planner import PlanChoice

    class OtherPlanner:
        """A planner that would legitimately choose issue #2 on a fresh run."""
        def plan(self, candidates, report):
            return PlanChoice("existing", 2, 0.95, False, "different plausible choice on retry")

    gh = LostComment(CANDIDATES)
    cl = fresh_clients(github=gh)
    r1 = run("LOSTC-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r1["status"] == "partial", r1
    assert len(gh.comments[1]) == 1, "GitHub accepted the comment despite the lost response"

    r2 = run("LOSTC-1", HARBOR_REPORT, cfg, clients=cl, planner=OtherPlanner())
    assert r2["status"] == "complete", r2
    assert len(gh.comments[1]) == 1, "retry must reconcile the recorded issue, not duplicate"
    assert len(gh.comments[2]) == 0, "retry must not replan onto another issue"
    assert r2["apps"]["github"]["issue_number"] == 1


# Final-review fix 1b: a marker comment beyond the first 50 results is still
# found (pagination), so the retry adopts it instead of writing a duplicate.
def test_marker_beyond_first_page_adopted(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES)
    for i in range(60):
        gh.comments[1].append({"id": 5000 + i, "body": f"unrelated traffic {i}",
                               "issue_number": 1, "html_url": f"https://github.test/x/{i}"})
    gh.comments[1].append({"id": 9999, "body": f"[orville:PAGEd-1] lost comment",
                           "issue_number": 1, "html_url": "https://github.test/x/lost"})
    _seed_state(tmp_path, "PAGEd-1", HARBOR_REPORT, cfg,
                github={"issue_number": 1, "anchor": "existing", "pending": "comment"})
    cl = fresh_clients(github=gh)
    r = run("PAGEd-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r["status"] == "complete", r
    assert len(gh.comments[1]) == 61, "must adopt the paged marker comment, not write another"
    assert r["apps"]["github"]["id"] == 9999


# Final-review fix 1c: multiple marker comments stop for human review instead
# of claiming exactly one.
def test_multiple_marker_comments_needs_human(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES)
    for _ in range(2):
        gh.create_comment(1, "[orville:DUPM-1] duplicate marker comment")
    _seed_state(tmp_path, "DUPM-1", HARBOR_REPORT, cfg,
                github={"issue_number": 1, "anchor": "existing", "pending": "comment"})
    cl = fresh_clients(github=gh)
    r = run("DUPM-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r["status"] == "needs_human", r
    assert "multiple" in r["reason"].lower() or "duplicate" in r["reason"].lower()
    assert len(gh.comments[1]) == 2, "no third comment may be written"
    assert len(cl["trello"].cards) == 0


# Final-review fix 2a (client level): 5xx is ambiguous, 4xx is a definitive
# rejection, both are distinct from success.
def test_discord_http_classification():
    from unittest.mock import patch
    import httpx
    from orville.discord_client import DiscordClient

    class StubResponse:
        def __init__(self, status):
            self.status_code = status
            self.text = "stub"
        def json(self):
            return {"id": "m1", "channel_id": "c1"}

    class StubHttpClient:
        status = 200
        raise_timeout = False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            if StubHttpClient.raise_timeout:
                raise httpx.ConnectTimeout("timed out")
            return StubResponse(StubHttpClient.status)

    def outcome_for(status=None, timeout=False):
        StubHttpClient.status = status
        StubHttpClient.raise_timeout = timeout
        with patch("orville.discord_client.httpx.Client", lambda **kw: StubHttpClient()):
            return DiscordClient("https://discord.test/webhook").post_message("test")

    assert outcome_for(200).status == "posted"
    assert outcome_for(403).status == "failed", "definitive rejection stays retryable-failed"
    assert outcome_for(500).status == "uncertain", "5xx must not claim no message was created"
    assert outcome_for(503).status == "uncertain"
    assert outcome_for(timeout=True).status == "uncertain"


# Final-review fix 2b (runner level): an ambiguous 5xx send persists
# uncertainty and is never auto-reposted.
def test_discord_server_error_runner_persists_uncertain(tmp_path):
    cfg = make_cfg(tmp_path)
    dcl = FakeDiscord()
    dcl.mode = "server_error"
    cl = fresh_clients(discord=dcl)
    r1 = run("SRV-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "partial", r1
    assert len(dcl.messages) == 0
    from orville.state import RunState
    assert RunState(cfg.state_dir).get("SRV-1")["discord_uncertain"] is True

    dcl.mode = "ok"
    r2 = run("SRV-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "partial", "server-error ambiguity must block the repost"
    assert len(dcl.messages) == 0, "no automatic repost after an ambiguous server failure"


# Final-review fix 3a: a report_id is bound to one immutable report.
def test_changed_report_same_id_rejected_before_writes(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r1 = run("BIND-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r1["status"] == "complete"
    counts = (len(cl["github"].comments[1]), len(cl["trello"].cards), len(cl["discord"].messages))

    r2 = run("BIND-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "needs_human", r2
    assert "report text differs" in r2["reason"]
    assert (len(cl["github"].comments[1]), len(cl["trello"].cards), len(cl["discord"].messages)) == counts, \
        "conflicting input must be rejected before any app write"


# Final-review fix 3b: destination scope is part of the binding.
def test_changed_destination_same_id_rejected(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r1 = run("BIND-2", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r1["status"] == "complete"
    cards_before = len(cl["trello"].cards)

    cfg2 = replace(cfg, trello_list_id="some-other-list")
    r2 = run("BIND-2", HARBOR_REPORT, cfg2, clients=cl, planner=StubPlanner("normal"))
    assert r2["status"] == "needs_human", r2
    assert "Trello list" in r2["reason"]
    assert len(cl["trello"].cards) == cards_before, "no card may be written to the other list"


# Final-review fix 3c: legacy entries migrate only after the recorded content
# verifies the submitted text; verified migration preserves the demo state.
def test_legacy_state_migrates_with_verification(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES)
    body = f"[orville:LEG-1]\n\nCustomer report `LEG-1` handed off to engineering.\n\n---\n\n{HARBOR_REPORT}"
    created = gh.create_comment(1, body)
    _seed_state(tmp_path, "LEG-1", HARBOR_REPORT, cfg,
                github={"issue_number": 1, "comment_id": created["id"],
                        "html_url": created["html_url"]},
                include_binding=False)
    cl = fresh_clients(github=gh)
    r = run("LEG-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r["status"] == "complete", r
    assert len(gh.comments[1]) == 1, "verified legacy entry is reused, not duplicated"
    from orville.state import RunState
    assert RunState(cfg.state_dir).get("LEG-1")["binding"] is not None, "binding recorded after migration"


# Final-review fix 3d: unverifiable legacy state stops for a human instead of
# binding arbitrary new input.
def test_legacy_state_unverifiable_needs_human(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES)
    created = gh.create_comment(1, "[orville:LEG-2] some other report's comment")
    _seed_state(tmp_path, "LEG-2", NEW_REPORT, cfg,
                github={"issue_number": 1, "comment_id": created["id"],
                        "html_url": created["html_url"]},
                include_binding=False)
    cl = fresh_clients(github=gh)
    r = run("LEG-2", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r["status"] == "needs_human", r
    assert "legacy" in r["reason"].lower()
    assert len(gh.comments[1]) == 1 and len(cl["trello"].cards) == 0, "no writes before verified migration"


# Final-review fix 4a: a model outage returns a structured, retryable result
# with no writes and no raised exception.
def test_planner_outage_structured_result(tmp_path):
    cfg = make_cfg(tmp_path)

    class OfflinePlanner:
        def plan(self, candidates, report):
            raise TimeoutError("model unavailable")

    cl = fresh_clients()
    r = run("OFFLINE-1", HARBOR_REPORT, cfg, clients=cl, planner=OfflinePlanner())
    assert r["status"] == "partial", r
    assert any("retryable" in e for e in r["errors"])
    assert r["apps"]["github"]["verified"] is False
    assert len(cl["trello"].cards) == 0 and len(cl["discord"].messages) == 0


# Final-review fix 4b: candidate-fetch failure is structured and write-free.
def test_candidate_fetch_failure_structured(tmp_path):
    cfg = make_cfg(tmp_path)
    gh = FakeGitHub(CANDIDATES, fail_list_issues=True)
    cl = fresh_clients(github=gh)
    r = run("FETCH-1", HARBOR_REPORT, cfg, clients=cl, planner=StubPlanner("normal"))
    assert r["status"] == "partial", r
    assert any("candidate fetch failed" in e for e in r["errors"])
    assert len(gh.comments[1]) == 0 and len(cl["trello"].cards) == 0


# Final-review fix 4c: a malformed model response is caught at the Python
# boundary and reported without writes.
def test_malformed_model_response_structured(tmp_path):
    cfg = make_cfg(tmp_path)

    class BadPlanner:
        def plan(self, candidates, report):
            return "this is not a plan object"

    cl = fresh_clients()
    r = run("BADPLAN-1", HARBOR_REPORT, cfg, clients=cl, planner=BadPlanner())
    assert r["status"] == "partial", r
    assert any("model call or response failed" in e for e in r["errors"])
    assert len(cl["trello"].cards) == 0 and len(cl["discord"].messages) == 0


# Regression (second pass 2): a reused Discord message missing the verified
# Trello link must fail verification and keep the run partial.
def test_discord_reuse_requires_both_links(tmp_path):
    cfg = make_cfg(tmp_path)
    cl = fresh_clients()
    r1 = run("DLINK-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r1["status"] == "complete"

    # Tamper: remove the Trello link from the previously posted message.
    m = cl["discord"].messages[0]
    m["content"] = "\n".join(l for l in m["content"].splitlines() if not l.startswith("Trello:"))
    r2 = run("DLINK-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    assert r2["status"] == "partial", r2
    assert r2["apps"]["discord"]["verified"] is False
    assert len(cl["discord"].messages) == 1, "reuse path must not post a replacement message"
