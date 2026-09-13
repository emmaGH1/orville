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
    state = {"github": {"issue_number": 1, "comment_id": 1001}, "trello": {}, "discord": {},
             "discord_uncertain": False, "status": "incomplete", "updated_at": None}
    import json as _json
    from pathlib import Path
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
