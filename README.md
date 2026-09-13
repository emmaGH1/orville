# Orville — guarded support handoff

Orville turns one messy customer bug report into a coordinated, verified handoff for a small software team: it routes the report to the correct existing GitHub issue (or creates one), records exactly one linked customer follow-up card in Trello, and posts one status message to Discord with links to both records. Every write is independently read back before Orville claims success, and the report itself is treated as untrusted data — requests to delete or modify unrelated records are refused, never executed.

The distinctive part is the guarding: the model may only choose among issue IDs returned by the GitHub API, ambiguous matches stop for a human before any write, every write carries an idempotency marker keyed by a stable `report_id`, and `complete` is reported only after all three app states have been re-read from the apps themselves — not from the model's own summary.

## Try it as a judge

The repository is currently private; request access to `emmaGH1/orville` from the repository owner before judging. Then:

1. **Prerequisites:** Python 3.11+, Git. Orville writes to the maintainer's GitHub test repository, Trello board, and Discord channel using the maintainer's credentials, so judges can run it read-only by following the verification steps below, or do a full run with their own credentials (step 3).

2. **Setup (full run with your own apps):**
   ```bash
   git clone <this repository> && cd multi-app-agent-hackathon-2026
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt      # POSIX: .venv/bin/pip ...
   copy .env.example .env                              # POSIX: cp .env.example .env
   ```
   Fill `.env` with your own values (names only, no secrets, in the committed `.env.example`): a GitHub fine-grained token with Issues read/write on one test repository (`GITHUB_REPO`, `GITHUB_TOKEN`), a Trello key/token and the ID of one test list (`TRELLO_API_KEY`, `TRELLO_TOKEN`, `TRELLO_LIST_ID`), a Discord incoming-webhook URL for one test channel (`DISCORD_WEBHOOK_URL`), and a Groq API key (`GROQ_API_KEY`; the default model is the free-plan `openai/gpt-oss-120b`).

3. **Action — one command, one report:**
   ```bash
   .venv\Scripts\python -m orville run --report-id HARBOR-EXPORT-01 --text-file eval/reports/harbor_export_01.txt
   ```
   The sample report matches the seeded CSV-export issue, includes an unrelated deletion request, and is a fictional customer scenario. The run makes three real writes to the three apps you configured.

4. **Expected result:** JSON with `"status": "complete"`, a `refused` entry for the deletion request, and one verified GitHub comment, one Trello card, and one Discord message ID. The trace lines show planned actions, real API outcomes, and three `READBACK ... ok=True` lines — the model's summary is never the proof. In a repository with no matching issue (e.g., your own empty test repo), Orville instead creates a new issue, comments on it, and continues — the status is still `complete` with the same three verified writes.

5. **Verification:** open the printed GitHub comment URL, Trello card URL, and check the Discord channel: the comment sits on the matching issue, the card is in the configured list and contains the GitHub link, and the Discord message contains both links. Then re-run the exact same command: the output reuses the same three IDs (`reused comment/card/message`) and creates nothing new.

6. **Failure behavior (tested):** an ambiguous match stops as `"needs_human"` before any write; a failed duplicate-check read blocks the write (`partial` with a retryable reason); a Discord send whose outcome is unknown is marked `uncertain` and is never reposted automatically; re-running a completed report creates no duplicates. All of these are covered by `python -m pytest tests/ -q` (16 tests, local fakes only).

## How it works

- **Planner:** a Groq structured-output call classifies the report and selects only among candidate issue IDs fetched from the GitHub API, or `create_new`; Python validates the choice (fabricated IDs and low confidence become `needs_human`).
- **Guard:** deletion/close/unrelated-modification phrases in the report are recorded as refused; the execution layer exposes no such operations, so they cannot be routed anywhere.
- **Runner:** fixed write order GitHub → Trello → Discord; each write persists its returned ID immediately to ignored local state (`state/runs.json`, the retry key is `report_id`); each write is followed by an independent read-back that checks ID, destination, marker, and cross-links (the Trello card must contain the verified GitHub link; the Discord message must contain both verified links). Later steps are deferred until the records they link are verified, so the status message can never falsely claim an unverified step succeeded.

## Reliability and limitations (honest)

- **Verified:** one live end-to-end run per path (route-to-existing-issue and create-new-issue) returned `complete` with three independently read-back records; a re-run reused all three records. 16 tests pass locally using in-memory fakes for failure paths (duplicate-check failure, trello outage retry, lost Discord response, unreadable new issue, ambiguity, refusal, redaction).
- **Simulation:** the failure-path tests use stateful fakes, not the real apps. The live evidence covers the happy path and duplicate-retry, not every failure mode.
- **Known limits:** GitHub candidate and comment searches are bounded (first 20 open issues; first 50 comments per issue) with no pagination — reports beyond that are not matched. Duplicate recovery for GitHub/Trello relies on app-side markers plus local state; if local state is lost and the app search also fails, Orville fails closed rather than risk a duplicate. A Discord send whose outcome is unknown is never retried automatically — it stays `uncertain` until a human reconciles; exactly-once Discord delivery cannot be guaranteed after local state loss. Marker checks assume no one edits Orville's records between runs.
- The judge demo records show the maintainer's configured apps; all sample data is fictional and labeled in the repositories.

## Credits

Built for the Multi-App Agent Hackathon, September 13, 2026. Runtime model: `openai/gpt-oss-120b` served by Groq (free plan). Apps: GitHub REST API, Trello REST API, Discord webhooks. Everything else is original code in this repository.
