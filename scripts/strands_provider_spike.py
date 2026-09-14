"""Phase 0: synthetic, read-only proof of Strands/Groq tool-result routing."""

import json
import logging
import os
import secrets
import time

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.openai import OpenAIModel


logging.disable(logging.CRITICAL)
load_dotenv()
key = os.getenv("GROQ_API_KEY")
if not key:
    raise SystemExit("GROQ_API_KEY_MISSING")

candidate_id = "SYN-" + secrets.token_hex(4).upper()
candidate_marker = "MARK-" + secrets.token_hex(4).upper()
events = []


@tool
def lookup_candidate(topic: str) -> dict:
    """Look up the matching synthetic support candidate.

    Args:
        topic: The support report topic to search.
    """
    events.append({"tool": "lookup_candidate", "topic": topic})
    return {"candidate_id": candidate_id, "marker": candidate_marker, "topic": "export"}


@tool
def confirm_candidate(candidate_id_arg: str, marker: str) -> dict:
    """Confirm a candidate using the exact ID and marker from lookup_candidate.

    Args:
        candidate_id_arg: Candidate ID returned by lookup_candidate.
        marker: Marker returned by lookup_candidate.
    """
    valid = candidate_id_arg == candidate_id and marker == candidate_marker
    events.append({"tool": "confirm_candidate", "valid": valid})
    return {"confirmed": valid, "candidate_id": candidate_id_arg if valid else None}


model = OpenAIModel(
    client_args={"api_key": key, "base_url": "https://api.groq.com/openai/v1", "timeout": 30.0},
    model_id="openai/gpt-oss-120b",
    params={"max_tokens": 600, "temperature": 0},
)
agent = Agent(model=model, tools=[lookup_candidate, confirm_candidate], callback_handler=lambda **kwargs: None)
started = time.monotonic()
try:
    result = agent(
        "This is a synthetic support report about an export failure. "
        "First call lookup_candidate with topic export. Then use the returned ID and marker "
        "to call confirm_candidate. Finally say whether that exact candidate was confirmed."
    )
except Exception as exc:
    print(json.dumps({"status": "ERROR", "error_type": type(exc).__name__, "duration_s": round(time.monotonic() - started, 2), "events": events}))
    raise SystemExit(2)

message = result.message.get("content", [])
final_text = " ".join(block.get("text", "") for block in message if isinstance(block, dict))
passed = (
    len(events) == 2
    and events[0]["tool"] == "lookup_candidate"
    and events[1]["tool"] == "confirm_candidate"
    and events[1]["valid"]
    and candidate_id in final_text
)
print(json.dumps({"status": "PASS" if passed else "FAIL", "duration_s": round(time.monotonic() - started, 2), "events": events, "final_mentions_lookup_id": candidate_id in final_text, "stop_reason": str(getattr(result, "stop_reason", "unknown"))}))
raise SystemExit(0 if passed else 1)
