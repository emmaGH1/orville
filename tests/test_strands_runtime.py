"""Adapter fail-closed cases; actual Strands/model routing is probed separately."""

from types import SimpleNamespace

import orville.strands_runtime as runtime
from orville.state import RunState, make_binding
from tests.test_eval import HARBOR_REPORT, fresh_clients, make_cfg


class ScriptedAgent:
    calls = []

    def __init__(self, *, tools, **kwargs):
        self.tools = {fn.__name__: fn for fn in tools}

    def __call__(self, prompt, **kwargs):
        for call in self.calls:
            name, arguments = call if isinstance(call, tuple) else (call, {})
            self.tools[name](**arguments)
        return SimpleNamespace(stop_reason="end_turn", message={"content": [{"text": "All done"}]})


def test_model_claim_of_completion_without_tools_stays_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "tool", lambda fn: fn)
    monkeypatch.setattr(runtime, "Agent", ScriptedAgent)
    ScriptedAgent.calls = []
    clients = fresh_clients()
    result = runtime.run_strands("FALSE-1", HARBOR_REPORT, make_cfg(tmp_path), clients, model=object())
    assert result["status"] == "partial"
    assert not clients["github"].comments[1]
    assert not clients["trello"].cards and not clients["discord"].messages


def test_model_calls_discord_first_no_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "tool", lambda fn: fn)
    monkeypatch.setattr(runtime, "Agent", ScriptedAgent)
    ScriptedAgent.calls = ["publish_team_update"]
    clients = fresh_clients()
    result = runtime.run_strands("ORDER-AGENT-1", HARBOR_REPORT, make_cfg(tmp_path), clients, model=object())
    assert result["status"] == "partial"
    assert result["tool_events"] == [{"tool": "publish_team_update", "status": "blocked"}] * 2
    assert result["strands_invocations"] == 2
    assert not clients["github"].comments[1]
    assert not clients["trello"].cards and not clients["discord"].messages


def test_operator_choice_rechecked_then_resumed_by_strands_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "tool", lambda fn: fn)
    monkeypatch.setattr(runtime, "Agent", ScriptedAgent)
    ScriptedAgent.calls = ["record_engineering_handoff", "create_customer_followup", "publish_team_update"]
    cfg = make_cfg(tmp_path)
    clients = fresh_clients()
    RunState(cfg.state_dir).update(
        "REVIEW-1", binding=make_binding(HARBOR_REPORT, cfg.github_repo, cfg.trello_list_id,
                                         cfg.discord_webhook_url),
        review={"kind": "candidate_choice", "reason": "two plausible issues", "candidate_numbers": [1, 2]})

    changed = runtime.run_strands("REVIEW-1", HARBOR_REPORT + " changed", cfg, clients,
                                  model=object(), review_issue_number=1)
    assert changed["status"] == "needs_human"
    assert not clients["github"].comments[1]

    rejected = runtime.run_strands("REVIEW-1", HARBOR_REPORT, cfg, clients,
                                   model=object(), review_issue_number=999)
    assert rejected["status"] == "needs_human"
    assert not clients["github"].comments[1]

    resumed = runtime.run_strands("REVIEW-1", HARBOR_REPORT, cfg, clients,
                                  model=object(), review_issue_number=1)
    assert resumed["status"] == "complete"
    assert resumed["apps"]["github"]["issue_number"] == 1
    assert RunState(cfg.state_dir).get("REVIEW-1")["review"] is None
    assert len(clients["github"].comments[1]) == len(clients["trello"].cards) == len(clients["discord"].messages) == 1


def test_ambiguous_choice_persists_review_without_app_write(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "tool", lambda fn: fn)
    monkeypatch.setattr(runtime, "Agent", ScriptedAgent)
    ScriptedAgent.calls = [
        "inspect_report_context",
        ("select_issue", {"action": "existing", "issue_number": 1,
                          "confidence": 0.9, "ambiguous": True, "reasoning": "two matching exports"}),
        "record_engineering_handoff",
    ]
    cfg = make_cfg(tmp_path)
    clients = fresh_clients()
    result = runtime.run_strands("AMBIG-STRANDS-1", HARBOR_REPORT, cfg, clients, model=object())
    assert result["status"] == "needs_human"
    review = RunState(cfg.state_dir).get("AMBIG-STRANDS-1")
    assert review["review"]["kind"] == "candidate_choice"
    assert review["review"]["candidate_numbers"] == [1, 2]
    assert review["binding"] == make_binding(HARBOR_REPORT, cfg.github_repo, cfg.trello_list_id,
                                               cfg.discord_webhook_url)
    assert not clients["github"].comments[1]
    assert not clients["trello"].cards and not clients["discord"].messages


def test_connected_scope_blocks_create_new_before_write(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "tool", lambda fn: fn)
    monkeypatch.setattr(runtime, "Agent", ScriptedAgent)
    ScriptedAgent.calls = [
        "inspect_report_context",
        ("select_issue", {"action": "create_new", "issue_number": None,
                          "confidence": 0.95, "ambiguous": False, "reasoning": "no match"}),
        "record_engineering_handoff",
    ]
    clients = fresh_clients()
    result = runtime.run_strands("SCOPE-STRANDS-1", HARBOR_REPORT, make_cfg(tmp_path),
                                 clients, model=object(), only_existing_issue=1)
    assert result["status"] == "needs_human"
    assert len(clients["github"].issues) == 2
    assert not clients["github"].comments[1]
    assert not clients["trello"].cards and not clients["discord"].messages
