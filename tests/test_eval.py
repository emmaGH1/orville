"""Five minimum evaluation cases plus guard/validator unit checks.

Local stateful fakes exercise failure paths. Live three-app runs are separate.
"""

import sys
import uuid
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
    cl = fresh_clients()
    r = run("RED-1", NEW_REPORT, cfg, clients=cl, planner=StubPlanner("create_new"))
    dumped = str(r["trace"]) + str(cl["discord"].messages[0]["content"])
    assert "gh-test-token" not in dumped and "g-test" not in dumped and "k-test" not in dumped


def test_empty_inputs_rejected(tmp_path):
    cfg = make_cfg(tmp_path)
    r = run("", NEW_REPORT, cfg, clients=fresh_clients(), planner=StubPlanner("normal"))
    assert r["status"] == "error"
    r = run("X-1", "   ", cfg, clients=fresh_clients(), planner=StubPlanner("normal"))
    assert r["status"] == "error"
