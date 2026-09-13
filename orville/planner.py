"""Issue-choice planner.

The model classifies the report and selects only among candidate issue IDs
returned by the GitHub API, or chooses create_new. Code validates the
structured choice; the model cannot invent an issue number the API did not
return. A stub planner covers tests so eval cases do not need network access.
"""

import json

CONFIDENCE_FLOOR = 0.7

CHOICE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "issue_choice",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["existing", "create_new"]},
                "issue_number": {"type": ["integer", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "ambiguous": {"type": "boolean"},
                "reasoning": {"type": "string"},
            },
            "required": ["action", "issue_number", "confidence", "ambiguous", "reasoning"],
            "additionalProperties": False,
        },
    },
}


class PlanChoice:
    def __init__(self, action: str, issue_number: int | None, confidence: float, ambiguous: bool, reasoning: str) -> None:
        self.action = action
        self.issue_number = issue_number
        self.confidence = confidence
        self.ambiguous = ambiguous
        self.reasoning = reasoning


class PlanDecision:
    """Code-validated outcome: proceed_with (number|None) or needs_human."""

    def __init__(self, decision: str, issue_number: int | None = None, reason: str = "") -> None:
        self.decision = decision  # "existing" | "create_new" | "needs_human"
        self.issue_number = issue_number
        self.reason = reason


class GroqPlanner:
    def __init__(self, base_url: str, model_id: str, api_key: str) -> None:
        from openai import OpenAI

        self.model_id = model_id
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def plan(self, candidates: list[dict], report_text: str) -> PlanChoice:
        listing = "\n".join(
            f"- number: {c['number']} | title: {c['title']} | body: {c['body'][:200]}" for c in candidates
        )
        prompt = (
            "A customer bug report must be routed to an existing GitHub issue or routed to a new issue.\n"
            "Candidate issues (the only IDs that exist):\n"
            f"{listing}\n\n"
            "Choose exactly one action:\n"
            '- "existing": the report matches one candidate; set issue_number to that candidate\'s number.\n'
            '- "create_new": no candidate matches; set issue_number to null.\n'
            "Set ambiguous=true if two or more candidates look equally plausible or confidence is low.\n"
            "Respond only with the structured choice.\n\n"
            f"Customer report:\n{report_text}"
        )
        resp = self._client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            response_format=CHOICE_SCHEMA,
            temperature=0,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        return PlanChoice(
            action=data["action"],
            issue_number=data["issue_number"],
            confidence=float(data["confidence"]),
            ambiguous=bool(data["ambiguous"]),
            reasoning=data["reasoning"],
        )


class StubPlanner:
    """Deterministic planner for tests. Rules: prefer candidate whose title
    contains 'csv'; support forced ambiguity or an invalid fabricated number."""

    def __init__(self, mode: str = "normal") -> None:
        self.mode = mode  # normal | ambiguous | fabricated | create_new

    def plan(self, candidates: list[dict], report_text: str) -> PlanChoice:
        if self.mode == "fabricated":
            return PlanChoice("existing", 999, 0.95, False, "stub fabricated")
        if self.mode == "ambiguous":
            return PlanChoice("existing", candidates[0]["number"], 0.9, True, "stub ambiguous")
        if self.mode == "create_new":
            return PlanChoice("create_new", None, 0.95, False, "stub create")
        for c in candidates:
            if "csv" in c["title"].lower():
                return PlanChoice("existing", c["number"], 0.95, False, "stub csv match")
        return PlanChoice("create_new", None, 0.9, False, "stub fallback")


def validate_choice(choice: PlanChoice, candidates: list[dict]) -> PlanDecision:
    """Validate the model's choice in code. Never trust a model-supplied ID."""
    numbers = {c["number"] for c in candidates}
    if choice.ambiguous:
        return PlanDecision("needs_human", reason=f"model flagged ambiguous match: {choice.reasoning}")
    if choice.action == "existing":
        if choice.issue_number is None or choice.issue_number not in numbers:
            return PlanDecision("needs_human", reason=f"model returned ID {choice.issue_number} not among candidates {sorted(numbers)}")
        if choice.confidence < CONFIDENCE_FLOOR:
            return PlanDecision("needs_human", reason=f"confidence {choice.confidence:.2f} below floor {CONFIDENCE_FLOOR}")
        return PlanDecision("existing", issue_number=choice.issue_number)
    if choice.action == "create_new":
        if choice.confidence < CONFIDENCE_FLOOR:
            return PlanDecision("needs_human", reason=f"confidence {choice.confidence:.2f} below floor {CONFIDENCE_FLOOR}")
        return PlanDecision("create_new")
    return PlanDecision("needs_human", reason=f"unknown action {choice.action!r}")
