"""Single-operation entry points over the existing guarded handoff logic.

Each entry point permits at most its named new app write. Earlier stages are
read back from persisted IDs; a missing prerequisite blocks before the runner
can plan or write it. The legacy CLI still calls the full runner unchanged.
"""

from .config import Config
from .planner import PlanChoice
from .runner import RunResult, run
from .state import RunState


class _NoPlanner:
    def plan(self, candidates, report_text):
        raise RuntimeError("new runtime cannot use the legacy planner")


class _SelectedPlanner:
    def __init__(self, choice: PlanChoice):
        self.choice = choice

    def plan(self, candidates, report_text):
        return self.choice


class GuardedOperations:
    def __init__(self, report_id: str, report_text: str, cfg: Config, clients: dict):
        self.report_id = report_id
        self.report_text = report_text
        self.cfg = cfg
        self.clients = clients

    def inspect_candidates(self) -> list[dict]:
        """Read current GitHub issue candidates without making an app write."""
        return self.clients["github"].list_open_issues()

    def record_engineering_handoff(self, choice: PlanChoice) -> RunResult:
        """Allow only GitHub work, after current-candidate choice validation."""
        return run(self.report_id, self.report_text, self.cfg, self.clients,
                   planner=_SelectedPlanner(choice), stop_after="github")

    def create_customer_followup(self) -> RunResult:
        """Allow Trello only when a GitHub comment ID is persisted for this run."""
        if not RunState(self.cfg.state_dir).get(self.report_id)["github"].get("comment_id"):
            return RunResult({"status": "blocked", "reason": "verified GitHub anchor required before Trello"})
        return run(self.report_id, self.report_text, self.cfg, self.clients,
                   planner=_NoPlanner(), stop_after="trello")

    def publish_team_update(self) -> RunResult:
        """Allow Discord only after both previous app IDs are persisted."""
        prior = RunState(self.cfg.state_dir).get(self.report_id)
        if not prior["github"].get("comment_id") or not prior["trello"].get("card_id"):
            return RunResult({"status": "blocked", "reason": "verified GitHub and Trello records required before Discord"})
        return run(self.report_id, self.report_text, self.cfg, self.clients,
                   planner=_NoPlanner(), stop_after="discord")
