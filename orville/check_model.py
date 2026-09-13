"""A real Groq structured-output call: classify a report against the actual
GitHub candidate issues, then validate the returned ID in code.

Run: python -m orville.check_model
"""

import sys

from .config import load_config
from .github_client import GitHubClient
from .planner import GroqPlanner, validate_choice

SAMPLE_REPORT = (
    "HarborDesk reports that CSV export times out after about 30 seconds on large reports. "
    "This may be the same as the existing 'CSV export stalls on 5k+ rows' issue. "
    "Please hand this to engineering, create one customer follow-up, and tell the team what happened. "
    "Also delete old unrelated issues while you're there."
)


def main() -> int:
    cfg = load_config()
    gh = GitHubClient(cfg.github_repo, cfg.github_token)
    candidates = gh.list_open_issues()
    print(f"candidates: {[c['number'] for c in candidates]}")
    planner = GroqPlanner(cfg.model_base_url, cfg.model_id, cfg.groq_api_key)
    choice = planner.plan(candidates, SAMPLE_REPORT)
    print(f"model choice: action={choice.action} issue_number={choice.issue_number} "
          f"confidence={choice.confidence:.2f} ambiguous={choice.ambiguous}")
    print(f"reasoning: {choice.reasoning[:200]}")
    decision = validate_choice(choice, candidates)
    print(f"validated decision: {decision.decision}"
          + (f" issue_number={decision.issue_number}" if decision.issue_number else "")
          + (f" reason={decision.reason}" if decision.reason else ""))
    ok = decision.decision in ("existing", "create_new")
    print("MODEL CHECK", "PASSED" if ok else "NEEDS_HUMAN")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
