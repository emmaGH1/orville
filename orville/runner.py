"""Guarded runner: one report -> verified writes in GitHub, Trello, Discord.

Contract enforced here:
- report_id is the caller-supplied retry key; destinations come from config.
- Model chooses only among API-returned candidate issues; ambiguous or
  fabricated choices stop as needs_human before any write.
- Deletion/unrelated-modification requests are recorded as refused; the
  execution layer exposes no such operation.
- Idempotency markers are embedded in GitHub and Trello content and checked
  before each write; returned IDs are persisted immediately.
- Write order is GitHub, Trello, Discord; the Discord status links only
  verified GitHub/Trello records.
- Every write is followed by an independent read-back; complete requires all
  three verified. A Discord send that times out without an ID is uncertain and
  pauses for reconciliation instead of reposting.
"""

import datetime as _dt
import json
import os
import re
import uuid

from .config import Config
from .discord_client import DiscordClient
from .github_client import GitHubClient
from .guard import scan_refusals
from .planner import PlanDecision, GroqPlanner, validate_choice
from .state import RunState
from .trace import Trace, redact

REPORT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class RunResult(dict):
    """Result is a plain dict; see run() for the shape."""


def _marker(report_id: str) -> str:
    return f"[orville:{report_id}]"


def _title_from_report(report_text: str) -> str:
    first_line = report_text.strip().splitlines()[0][:72].rstrip(".")
    return f"Customer report: {first_line}"


def run(
    report_id: str,
    report_text: str,
    cfg: Config,
    clients: dict | None = None,
    planner=None,
    trace: Trace | None = None,
) -> RunResult:
    if not report_id or not report_id.strip() or not report_text or not report_text.strip():
        return RunResult({"status": "error", "reason": "report_id and report text must be nonempty"})
    report_id = report_id.strip()
    if not REPORT_ID_RE.match(report_id):
        return RunResult({"status": "error", "reason": "report_id must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}"})

    trace = trace or Trace()
    if clients is None:
        from .trello_client import TrelloClient

        clients = {
            "github": GitHubClient(cfg.github_repo, cfg.github_token),
            "trello": TrelloClient(cfg.trello_api_key, cfg.trello_token),
            "discord": DiscordClient(cfg.discord_webhook_url),
        }
    if planner is None:
        planner = GroqPlanner(cfg.model_base_url, cfg.model_id, cfg.groq_api_key)

    state = RunState(cfg.state_dir)
    prior = state.get(report_id)
    result: dict = {
        "report_id": report_id,
        "status": "partial",
        "allowed": [],
        "refused": [],
        "apps": {},
        "errors": [],
        "trace": [],
    }

    for r in scan_refusals(report_text):
        trace.refused(r["request"], r["matched"])
        result["refused"].append(r)

    apps = result["apps"]
    gh_ver = tr_ver = dc_ver = False

    # ---- GitHub ----------------------------------------------------------
    trace.planned("github_comment", cfg.github_repo)
    marker = _marker(report_id)
    comment = prior["github"].get("comment_id")
    if comment:
        trace.note(f"retry: reusing recorded github comment {comment}")
        try:
            got = clients["github"].get_comment(comment)
            gh_ver = got["id"] == comment and marker in got["body"]
            trace.assertion("github", gh_ver, f"reused comment {comment}")
            apps["github"] = {"id": comment, "url": got["html_url"], "verified": gh_ver,
                              "issue_number": prior["github"].get("issue_number")}
            if not gh_ver:
                result["errors"].append("github read-back of recorded comment failed")
        except Exception as e:
            trace.outcome("github_reuse", cfg.github_repo, False, str(e))
            result["errors"].append(f"github reuse failed: {e}")
    else:
        issue_number = prior["github"].get("issue_number")
        if issue_number is None:
            candidates = clients["github"].list_open_issues()
            choice = planner.plan(candidates, report_text)
            decision: PlanDecision = validate_choice(choice, candidates)
            trace.note(f"planner decision: {decision.decision} "
                       + (f"issue #{decision.issue_number}" if decision.issue_number else "")
                       + (f"; {decision.reason}" if decision.reason else ""))
            if decision.decision == "needs_human":
                result["status"] = "needs_human"
                result["reason"] = decision.reason
                result["trace"] = trace.rendered()
                return RunResult(result)
            if decision.decision == "create_new":
                created = clients["github"].create_issue(_title_from_report(report_text),
                                                         f"{marker}\n\n{report_text}")
                issue_number = created["number"]
                trace.outcome("github_create_issue", cfg.github_repo, True, f"issue #{issue_number}")
                state.update(report_id, github={"issue_number": issue_number, "html_url": created["html_url"]})
            else:
                issue_number = decision.issue_number

        # App-side dedupe: search target issue comments for the marker.
        target = issue_number
        try:
            existing = [c for c in clients["github"].list_comments(target) if marker in c["body"]]
        except Exception as e:
            result["errors"].append(f"github marker search failed: {e}")
            existing = []
        if existing:
            comment = existing[0]["id"]
            trace.note(f"marker found on issue #{target}; reusing comment {comment}")
        else:
            body = (f"{marker}\n\nCustomer report `{report_id}` handed off to engineering.\n\n---\n\n"
                    f"{report_text}")
            try:
                created = clients["github"].create_comment(target, body)
                comment = created["id"]
                trace.outcome("github_comment", f"issue #{target}", True, f"comment {comment}")
                state.update(report_id, github={"issue_number": target, "comment_id": comment,
                                                "html_url": created["html_url"]})
            except Exception as e:
                trace.outcome("github_comment", f"issue #{target}", False, str(e))
                result["errors"].append(f"github comment failed: {e}")
                apps["github"] = {"verified": False}

        if comment:
            try:
                got = clients["github"].get_comment(comment)
                gh_ver = got["id"] == comment and marker in got["body"]
                trace.assertion("github", gh_ver, f"comment {comment} on issue #{target}")
                apps["github"] = {"id": comment, "url": got["html_url"], "verified": gh_ver,
                                  "issue_number": target}
                if not gh_ver:
                    result["errors"].append("github read-back mismatch")
            except Exception as e:
                result["errors"].append(f"github read-back failed: {e}")
                apps["github"] = {"id": comment, "verified": False}
        elif not any("github" in e for e in result["errors"]):
            result["errors"].append("github comment missing after write attempt")

    # ---- Trello ----------------------------------------------------------
    trace.planned("trello_card", cfg.trello_list_id)
    card_id = prior["trello"].get("card_id")
    if card_id:
        trace.note(f"retry: reusing recorded trello card {card_id}")
        try:
            got = clients["trello"].get_card(card_id)
            tr_ver = got["id"] == card_id and got["idList"] == cfg.trello_list_id and marker in (got["name"] + got["desc"])
            trace.assertion("trello", tr_ver, f"reused card {card_id}")
            apps["trello"] = {"id": card_id, "url": got.get("url"), "verified": tr_ver}
            if not tr_ver:
                result["errors"].append("trello read-back of recorded card failed")
        except Exception as e:
            trace.outcome("trello_reuse", cfg.trello_list_id, False, str(e))
            result["errors"].append(f"trello reuse failed: {e}")
    else:
        # App-side dedupe: search the configured list for the marker.
        try:
            existing = [c for c in clients["trello"].list_cards(cfg.trello_list_id)
                        if marker in (c["name"] + c["desc"])]
        except Exception as e:
            result["errors"].append(f"trello marker search failed: {e}")
            existing = []
        if existing:
            card_id = existing[0]["id"]
            trace.note(f"marker found in list; reusing card {card_id}")
        else:
            gh_link = apps.get("github", {}).get("url", "")
            name = f"{marker} Customer follow-up: {report_id}"
            desc = (f"Customer follow-up for report `{report_id}`.\n\n"
                    f"GitHub: {gh_link or '(github step not verified)'}\n\n{report_text}")
            try:
                created = clients["trello"].create_card(cfg.trello_list_id, name, desc)
                card_id = created["id"]
                trace.outcome("trello_card", cfg.trello_list_id, True, f"card {card_id}")
                state.update(report_id, trello={"card_id": card_id, "url": created["url"]})
            except Exception as e:
                trace.outcome("trello_card", cfg.trello_list_id, False, str(e))
                result["errors"].append(f"trello create failed: {e}")
                apps["trello"] = {"verified": False}
        if card_id:
            try:
                got = clients["trello"].get_card(card_id)
                tr_ver = got["id"] == card_id and got["idList"] == cfg.trello_list_id and marker in (got["name"] + got["desc"])
                trace.assertion("trello", tr_ver, f"card {card_id} in configured list")
                apps["trello"] = {"id": card_id, "url": got.get("url"), "verified": tr_ver}
                if not tr_ver:
                    result["errors"].append("trello read-back mismatch")
            except Exception as e:
                result["errors"].append(f"trello read-back failed: {e}")
                apps["trello"] = {"id": card_id, "verified": False}
        elif not any("trello" in e for e in result["errors"]):
            result["errors"].append("trello card missing after write attempt")

    # ---- Discord ---------------------------------------------------------
    trace.planned("discord_status", "configured webhook")
    message_id = prior["discord"].get("message_id")
    if message_id:
        trace.note(f"retry: reusing recorded discord message {message_id}")
        try:
            got = clients["discord"].get_message(message_id)
            dc_ver = got["id"] == message_id and marker in got["content"]
            trace.assertion("discord", dc_ver, f"reused message {message_id}")
            apps["discord"] = {"id": message_id, "verified": dc_ver}
            if not dc_ver:
                result["errors"].append("discord read-back of recorded message failed")
        except Exception as e:
            trace.outcome("discord_reuse", "webhook", False, str(e))
            result["errors"].append(f"discord reuse failed: {e}")
    elif prior["discord_uncertain"]:
        result["errors"].append("discord uncertain: earlier send timed out without an ID; reconcile manually before any resend")
        trace.note("discord remains uncertain; refusing blind repost")
    elif gh_ver and tr_ver:
        links = [f"GitHub: {apps['github']['url']}", f"Trello: {apps['trello']['url']}"]
        content = f"{marker} Customer report `{report_id}` handed off.\n" + "\n".join(links)
        outcome = clients["discord"].post_message(content)
        if outcome.status == "posted":
            message_id = outcome.message.get("id")
            state.update(report_id, discord={"message_id": message_id, "channel_id": outcome.message.get("channel_id")})
            try:
                got = clients["discord"].get_message(message_id)
                dc_ver = got["id"] == message_id and marker in got["content"]
                trace.assertion("discord", dc_ver, f"message {message_id}")
                apps["discord"] = {"id": message_id, "verified": dc_ver}
                if not dc_ver:
                    result["errors"].append("discord read-back mismatch")
            except Exception as e:
                result["errors"].append(f"discord read-back failed: {e}")
                apps["discord"] = {"id": message_id, "verified": False}
        else:
            trace.outcome("discord_status", "webhook", False, outcome.detail)
            if outcome.status == "uncertain":
                state.update(report_id, discord_uncertain=True)
                result["errors"].append(f"discord uncertain, needs reconciliation: {outcome.detail}")
            else:
                result["errors"].append(f"discord post failed: {outcome.detail}")
    else:
        trace.note("discord deferred: github and trello must both be verified before a status is posted")
        result["errors"].append("discord deferred because a required earlier step is not verified")

    # ---- Status ----------------------------------------------------------
    if gh_ver:
        result["allowed"].append("github_comment")
    if tr_ver:
        result["allowed"].append("trello_card")
    if dc_ver:
        result["allowed"].append("discord_status")
    if gh_ver and tr_ver and dc_ver:
        result["status"] = "complete"
    elif result["status"] != "needs_human":
        result["status"] = "partial"
    state.update(report_id, status=result["status"])
    result["trace"] = trace.rendered()
    return RunResult(result)
