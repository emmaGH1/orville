"""Guarded runner: one report -> verified writes in GitHub, Trello, Discord.

Contract enforced here:
- report_id is the caller-supplied retry key; destinations come from config.
- Model chooses only among API-returned candidate issues; ambiguous or
  fabricated choices stop as needs_human before any write.
- Deletion/unrelated-modification requests are recorded as refused; the
  execution layer exposes no such operation.
- Idempotency markers are embedded in GitHub and Trello content and checked
  before each write. A failed pre-write dedupe read fails closed: no write to
  that destination, honest partial result, retryable reason.
- Returned IDs are persisted immediately. Write order is GitHub, Trello,
  Discord; later steps are deferred until the records they link are verified,
  so a status message can never claim an unverified step succeeded.
- Every write is followed by an independent read-back including ownership and
  cross-link checks. `complete` requires all three verified. A Discord send
  whose outcome is unknown is uncertain and pauses for reconciliation instead
  of reposting.
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


def _config_secrets(cfg: Config) -> list[str]:
    return [v for v in (cfg.github_token, cfg.trello_api_key, cfg.trello_token,
                        cfg.discord_webhook_url, cfg.groq_api_key) if v]


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

    trace = trace or Trace(secrets=_config_secrets(cfg))
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

    def fail(app: str, message: str) -> None:
        result["errors"].append(message)
        trace.outcome(f"{app}_error", "runner", False, message)

    for r in scan_refusals(report_text):
        trace.refused(r["request"], r["matched"])
        result["refused"].append(r)

    apps = result["apps"]
    marker = _marker(report_id)
    gh_ver = tr_ver = dc_ver = False

    # ---- GitHub ----------------------------------------------------------
    trace.planned("github_comment", cfg.github_repo)
    prior_gh = prior["github"]
    if prior_gh.get("comment_id"):
        comment = prior_gh["comment_id"]
        trace.note(f"retry: reusing recorded github comment {comment}")
        try:
            got = clients["github"].get_comment(comment)
            gh_ver = (got["id"] == comment and marker in got["body"]
                      and (prior_gh.get("issue_number") is None or got.get("issue_number") == prior_gh["issue_number"]))
            trace.assertion("github", gh_ver, f"reused comment {comment} on issue {got.get('issue_number')}")
            apps["github"] = {"id": comment, "url": got["html_url"], "verified": gh_ver,
                              "issue_number": got.get("issue_number") or prior_gh.get("issue_number")}
            if not gh_ver:
                result["errors"].append("github read-back of recorded comment failed ownership or marker check")
        except Exception as e:
            trace.outcome("github_reuse", cfg.github_repo, False, str(e))
            fail("github", f"github reuse read-back failed (retryable): {e}")
    else:
        issue_number = prior_gh.get("issue_number")
        issue_from_prior = issue_number is not None
        issue_create_uncertain = bool(prior.get("github_create_uncertain"))
        if issue_number is None and issue_create_uncertain:
            # A create POST returned no ID, so whether the issue exists is
            # unknown. Reconcile by the report marker before any new create.
            try:
                candidates = clients["github"].list_open_issues()
                matches = [c["number"] for c in candidates if marker in (c.get("body") or "")]
            except Exception as e:
                matches = None
                trace.outcome("github_reconcile", cfg.github_repo, False, str(e))
                fail("github", f"github reconciliation search failed; create withheld (retryable): {e}")
                apps["github"] = {"verified": False}
            if matches is not None:
                if len(matches) == 1:
                    issue_number = matches[0]
                    issue_from_prior = True
                    state.update(report_id, github={"issue_number": issue_number},
                                 github_create_uncertain=False)
                    trace.note(f"reconciled uncertain creation to issue #{issue_number} by report marker")
                elif len(matches) == 0:
                    state.update(report_id, github_create_uncertain=False)
                    trace.note("reconciliation found no marker; creation did not take; proceeding with planning")
                else:
                    result["status"] = "needs_human"
                    result["reason"] = f"report marker matches multiple issues {sorted(matches)}; human review required"
                    result["errors"] = [redact(e, secrets=_config_secrets(cfg)) for e in result["errors"]]
                    result["trace"] = trace.rendered()
                    return RunResult(result)
        if issue_number is None and not bool(prior.get("github_create_uncertain")):
            candidates = clients["github"].list_open_issues()
            choice = planner.plan(candidates, report_text)
            decision: PlanDecision = validate_choice(choice, candidates)
            trace.note(f"planner decision: {decision.decision} "
                       + (f"issue #{decision.issue_number}" if decision.issue_number else "")
                       + (f"; {decision.reason}" if decision.reason else ""))
            if decision.decision == "needs_human":
                result["status"] = "needs_human"
                result["reason"] = decision.reason
                result["errors"] = [redact(e, secrets=_config_secrets(cfg)) for e in result["errors"]]
                result["trace"] = trace.rendered()
                return RunResult(result)
            if decision.decision == "create_new":
                try:
                    created = clients["github"].create_issue(_title_from_report(report_text),
                                                             f"{marker}\n\n{report_text}")
                except Exception as e:
                    trace.outcome("github_create_issue", cfg.github_repo, False, str(e))
                    fail("github", f"github issue creation returned no ID; marked uncertain, reconcile on retry (retryable): {e}")
                    state.update(report_id, github_create_uncertain=True)
                    created = None
                if created is not None and created.get("number") is not None:
                    # Persist the returned number immediately, unverified, so a
                    # retry verifies this same issue instead of creating another.
                    issue_number = created["number"]
                    issue_from_prior = True
                    state.update(report_id, github={"issue_number": issue_number,
                                                    "html_url": created.get("html_url")})
                elif created is not None:
                    trace.outcome("github_create_issue", cfg.github_repo, False, "response without issue number")
                    fail("github", "github issue creation returned no ID; marked uncertain, reconcile on retry (retryable)")
                    state.update(report_id, github_create_uncertain=True)
            else:
                issue_number = decision.issue_number

        if issue_number is not None and not apps.get("github", {}).get("verified", False):
            if issue_from_prior:
                # The issue number was recorded, not just returned: verify this
                # exact issue before any new POST against it.
                try:
                    got = clients["github"].get_issue(issue_number)
                    issue_ok = (got["number"] == issue_number and marker in got["body"])
                    trace.assertion("github", issue_ok,
                                    f"recorded issue #{issue_number} in {cfg.github_repo} carries the report marker")
                    if not issue_ok:
                        fail("github", f"recorded issue #{issue_number} read-back mismatch; no write until verified")
                        apps["github"] = {"verified": False, "issue_number": issue_number}
                        issue_number = None
                except Exception as e:
                    trace.outcome("github_issue_readback", cfg.github_repo, False, str(e))
                    fail("github", f"recorded issue #{issue_number} read-back failed; no write until verified (retryable): {e}")
                    apps["github"] = {"verified": False, "issue_number": issue_number}
                    issue_number = None

        if issue_number is not None and not apps.get("github", {}).get("verified", False):
            target = issue_number
            # App-side dedupe: search target issue comments for the marker.
            # A failed search fails closed: no write until the check succeeds.
            try:
                existing = [c for c in clients["github"].list_comments(target) if marker in c["body"]]
            except Exception as e:
                trace.outcome("github_dedupe_search", f"issue #{target}", False, str(e))
                fail("github", f"github marker search failed; write withheld until it succeeds (retryable): {e}")
                apps["github"] = {"verified": False, "issue_number": target,
                                  "reason": "pre-write dedupe check failed; write withheld"}
                existing = None
            if existing is not None:
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
                        fail("github", f"github comment failed (retryable): {e}")
                        apps["github"] = {"verified": False, "issue_number": target}
                        comment = None
                if comment:
                    try:
                        got = clients["github"].get_comment(comment)
                        gh_ver = (got["id"] == comment and marker in got["body"]
                                  and (got.get("issue_number") is None or got["issue_number"] == target))
                        trace.assertion("github", gh_ver, f"comment {comment} on issue #{target}")
                        apps["github"] = {"id": comment, "url": got["html_url"], "verified": gh_ver,
                                          "issue_number": target}
                        if not gh_ver:
                            result["errors"].append("github read-back mismatch (id, marker, or owning issue)")
                    except Exception as e:
                        trace.outcome("github_readback", f"issue #{target}", False, str(e))
                        fail("github", f"github read-back failed (retryable): {e}")
                        apps["github"] = {"id": comment, "verified": False, "issue_number": target}

    # ---- Trello ----------------------------------------------------------
    trace.planned("trello_card", cfg.trello_list_id)
    gh_url = apps.get("github", {}).get("url") or prior_gh.get("html_url")
    card_id = prior["trello"].get("card_id")
    if card_id:
        trace.note(f"retry: reusing recorded trello card {card_id}")
        try:
            got = clients["trello"].get_card(card_id)
            tr_ver = (got["id"] == card_id and got["idList"] == cfg.trello_list_id
                      and marker in (got["name"] + got["desc"])
                      and not (gh_url and gh_url not in got["desc"]))
            trace.assertion("trello", tr_ver, f"reused card {card_id} in configured list")
            apps["trello"] = {"id": card_id, "url": got.get("url"), "verified": tr_ver}
            if not tr_ver:
                result["errors"].append("trello read-back of recorded card failed list, marker, or link check")
        except Exception as e:
            trace.outcome("trello_reuse", cfg.trello_list_id, False, str(e))
            fail("trello", f"trello reuse read-back failed (retryable): {e}")
    elif not gh_ver:
        trace.note("trello deferred: github anchor not verified, so no card was written")
        result["errors"].append("trello deferred because the github step is not verified")
    else:
        # App-side dedupe: search the configured list for the marker.
        # A failed search fails closed: no write until the check succeeds.
        try:
            existing = [c for c in clients["trello"].list_cards(cfg.trello_list_id)
                        if marker in (c["name"] + c["desc"])]
        except Exception as e:
            trace.outcome("trello_dedupe_search", cfg.trello_list_id, False, str(e))
            fail("trello", f"trello marker search failed; write withheld until it succeeds (retryable): {e}")
            apps["trello"] = {"verified": False, "reason": "pre-write dedupe check failed; write withheld"}
            existing = None
        if existing is not None:
            if existing:
                card_id = existing[0]["id"]
                trace.note(f"marker found in list; reusing card {card_id}")
            else:
                name = f"{marker} Customer follow-up: {report_id}"
                desc = (f"Customer follow-up for report `{report_id}`.\n\n"
                        f"GitHub: {gh_url or '(github record not linked)'}\n\n{report_text}")
                try:
                    created = clients["trello"].create_card(cfg.trello_list_id, name, desc)
                    card_id = created["id"]
                    trace.outcome("trello_card", cfg.trello_list_id, True, f"card {card_id}")
                    state.update(report_id, trello={"card_id": card_id, "url": created["url"]})
                except Exception as e:
                    trace.outcome("trello_card", cfg.trello_list_id, False, str(e))
                    fail("trello", f"trello create failed (retryable): {e}")
                    apps["trello"] = {"verified": False}
                    card_id = None
            if card_id:
                try:
                    got = clients["trello"].get_card(card_id)
                    tr_ver = (got["id"] == card_id and got["idList"] == cfg.trello_list_id
                              and marker in (got["name"] + got["desc"])
                              and not (gh_url and gh_url not in got["desc"]))
                    trace.assertion("trello", tr_ver, f"card {card_id} in configured list with github link")
                    apps["trello"] = {"id": card_id, "url": got.get("url"), "verified": tr_ver}
                    if not tr_ver:
                        result["errors"].append("trello read-back mismatch (list, marker, or github link)")
                except Exception as e:
                    trace.outcome("trello_readback", cfg.trello_list_id, False, str(e))
                    fail("trello", f"trello read-back failed (retryable): {e}")
                    apps["trello"] = {"id": card_id, "verified": False}

    # ---- Discord ---------------------------------------------------------
    trace.planned("discord_status", "configured webhook")
    dc = prior["discord"]
    if dc.get("message_id"):
        message_id = dc["message_id"]
        trace.note(f"retry: reusing recorded discord message {message_id}")
        try:
            got = clients["discord"].get_message(message_id)
            # Same proof as a fresh send: marker plus both verified links.
            tr_url = prior["trello"].get("url") or apps.get("trello", {}).get("url")
            links_ok = (bool(gh_url) and gh_url in got["content"]
                        and bool(tr_url) and tr_url in got["content"])
            dc_ver = (got["id"] == message_id and marker in got["content"] and links_ok)
            trace.assertion("discord", dc_ver, f"reused message {message_id} with marker and both verified links")
            apps["discord"] = {"id": message_id, "verified": dc_ver}
            if not dc_ver:
                result["errors"].append("discord read-back of recorded message failed marker or verified-link check")
        except Exception as e:
            trace.outcome("discord_reuse", "webhook", False, str(e))
            fail("discord", f"discord reuse read-back failed (retryable): {e}")
    elif prior["discord_uncertain"]:
        result["errors"].append("discord uncertain: an earlier send had no verifiable outcome; reconcile manually before any resend")
        trace.note("discord remains uncertain; refusing blind repost")
    elif gh_ver and tr_ver:
        gh_link = apps["github"]["url"]
        tr_link = apps["trello"]["url"]
        content = (f"{marker} Customer report `{report_id}` handed off.\n"
                   f"GitHub: {gh_link}\nTrello: {tr_link}")
        try:
            outcome = clients["discord"].post_message(content)
        except Exception as e:
            # Whether Discord accepted the message is unknown; treat as uncertain.
            trace.outcome("discord_status", "webhook", False, f"send raised: {e}")
            outcome = None
            state.update(report_id, discord_uncertain=True)
            result["errors"].append("discord uncertain: send raised without a message ID; reconcile manually before any resend")
        if outcome is not None:
            if outcome.status == "posted":
                message_id = outcome.message.get("id")
                state.update(report_id, discord={"message_id": message_id,
                                                 "channel_id": outcome.message.get("channel_id")})
                try:
                    got = clients["discord"].get_message(message_id)
                    dc_ver = (got["id"] == message_id and marker in got["content"]
                              and gh_link in got["content"] and tr_link in got["content"])
                    trace.assertion("discord", dc_ver, f"message {message_id} with both verified links")
                    apps["discord"] = {"id": message_id, "verified": dc_ver}
                    if not dc_ver:
                        result["errors"].append("discord read-back mismatch (marker or verified links)")
                except Exception as e:
                    trace.outcome("discord_readback", "webhook", False, str(e))
                    fail("discord", f"discord read-back failed (retryable): {e}")
                    apps["discord"] = {"id": message_id, "verified": False}
            elif outcome.status == "uncertain":
                state.update(report_id, discord_uncertain=True)
                result["errors"].append(f"discord uncertain, needs reconciliation: {outcome.detail}")
                trace.outcome("discord_status", "webhook", False, outcome.detail)
            else:
                trace.outcome("discord_status", "webhook", False, outcome.detail)
                result["errors"].append(f"discord post failed (retryable): {outcome.detail}")
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
    result["status"] = "complete" if (gh_ver and tr_ver and dc_ver) else "partial"
    secrets = _config_secrets(cfg)
    result["errors"] = [redact(e, secrets=secrets) for e in result["errors"]]
    state.update(report_id, status=result["status"])
    result["trace"] = trace.rendered()
    return RunResult(result)
