"""Adapter fail-closed cases; actual Strands/model routing is probed separately."""

from types import SimpleNamespace

import orville.strands_runtime as runtime
from tests.test_eval import HARBOR_REPORT, fresh_clients, make_cfg


class ScriptedAgent:
    calls = []

    def __init__(self, *, tools, **kwargs):
        self.tools = {fn.__name__: fn for fn in tools}

    def __call__(self, prompt, **kwargs):
        for name in self.calls:
            self.tools[name]()
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
