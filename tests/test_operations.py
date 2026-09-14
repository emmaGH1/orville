"""Operation-level gates for the new agent entry points (offline fakes)."""

from dataclasses import replace

from orville.operations import GuardedOperations
from orville.planner import PlanChoice
from tests.test_eval import HARBOR_REPORT, fresh_clients, make_cfg


def selected(number=1):
    return PlanChoice("existing", number, 0.95, False, "synthetic match")


def test_out_of_order_tools_cannot_write(tmp_path):
    clients = fresh_clients()
    ops = GuardedOperations("ORDER-1", HARBOR_REPORT, make_cfg(tmp_path), clients)
    assert ops.publish_team_update()["status"] == "blocked"
    assert ops.create_customer_followup()["status"] == "blocked"
    assert not clients["github"].comments[1]
    assert not clients["trello"].cards
    assert not clients["discord"].messages


def test_three_operations_each_permit_one_new_stage_and_retry_reuses(tmp_path):
    clients = fresh_clients()
    ops = GuardedOperations("STAGED-1", HARBOR_REPORT, make_cfg(tmp_path), clients)
    assert [c["number"] for c in ops.inspect_candidates()] == [1, 2]

    gh = ops.record_engineering_handoff(selected())
    assert gh["apps"]["github"]["verified"]
    assert len(clients["github"].comments[1]) == 1
    assert not clients["trello"].cards and not clients["discord"].messages

    tr = ops.create_customer_followup()
    assert tr["apps"]["trello"]["verified"]
    assert len(clients["trello"].cards) == 1 and not clients["discord"].messages

    dc = ops.publish_team_update()
    assert dc["status"] == "complete"
    counts = (len(clients["github"].comments[1]), len(clients["trello"].cards), len(clients["discord"].messages))
    assert ops.publish_team_update()["status"] == "complete"
    assert counts == (len(clients["github"].comments[1]), len(clients["trello"].cards), len(clients["discord"].messages))


def test_fabricated_issue_rejected_before_any_write(tmp_path):
    clients = fresh_clients()
    ops = GuardedOperations("FAKE-1", HARBOR_REPORT, make_cfg(tmp_path), clients)
    result = ops.record_engineering_handoff(selected(999))
    assert result["status"] == "needs_human"
    assert not clients["github"].comments[1] and not clients["trello"].cards


def test_changed_report_binding_rejected_before_trello_write(tmp_path):
    clients = fresh_clients()
    cfg = make_cfg(tmp_path)
    original = GuardedOperations("SCOPE-1", HARBOR_REPORT, cfg, clients)
    assert original.record_engineering_handoff(selected())["apps"]["github"]["verified"]
    changed = GuardedOperations("SCOPE-1", HARBOR_REPORT + " changed", cfg, clients)
    result = changed.create_customer_followup()
    assert result["status"] == "needs_human"
    assert not clients["trello"].cards

    changed_destination = GuardedOperations("SCOPE-1", HARBOR_REPORT, replace(cfg, trello_list_id="other"), clients)
    result = changed_destination.create_customer_followup()
    assert result["status"] == "needs_human"
    assert not clients["trello"].cards
