"""Orville CLI.

Run a guarded handoff:
    python -m orville run --report-id HARBOR-EXPORT-01 --text-file eval/reports/harbor_export_01.txt

Show persisted state for a report:
    python -m orville show --report-id HARBOR-EXPORT-01
"""

import argparse
import json
import sys

from .config import load_config
from .runner import run


def _print_result(result: dict) -> None:
    trace = result.pop("trace", [])
    print(json.dumps(result, indent=2))
    print("--- trace ---")
    for e in trace:
        kind = e.get("kind", "?")
        if kind == "refused":
            print(f"REFUSED  {e['request']}  ({e['reason'][:80]})")
        elif kind == "planned":
            print(f"PLANNED  {e['action']} -> {e['target']}")
        elif kind == "outcome":
            print(f"OUTCOME  {e['action']} ok={e['ok']} {e['detail']}")
        elif kind == "readback":
            print(f"READBACK {e['target']} ok={e['ok']} {e['detail']}")
        elif kind == "note":
            print(f"NOTE     {e['detail']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orville")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for command, help_text in (("run", "run the legacy guarded handoff"),
                               ("run-strands", "run the Strands guarded handoff")):
        p_run = sub.add_parser(command, help=help_text)
        p_run.add_argument("--report-id", required=True)
        src = p_run.add_mutually_exclusive_group(required=True)
        src.add_argument("--text-file", help="file containing the report text")
        src.add_argument("--text", help="report text inline")

    p_show = sub.add_parser("show", help="show persisted state for a report")
    p_show.add_argument("--report-id", required=True)

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.cmd == "show":
        from .state import RunState

        entry = RunState(cfg.state_dir).get(args.report_id)
        print(json.dumps(entry, indent=2))
        return 0

    text = args.text if args.text else open(args.text_file, "r", encoding="utf-8").read()
    if args.cmd == "run-strands":
        from .discord_client import DiscordClient
        from .github_client import GitHubClient
        from .strands_runtime import run_strands
        from .trello_client import TrelloClient

        clients = {
            "github": GitHubClient(cfg.github_repo, cfg.github_token),
            "trello": TrelloClient(cfg.trello_api_key, cfg.trello_token),
            "discord": DiscordClient(cfg.discord_webhook_url),
        }
        result = run_strands(args.report_id, text, cfg, clients)
    else:
        result = run(args.report_id, text, cfg)
    _print_result(result)
    if result["status"] == "complete":
        return 0
    if result["status"] == "needs_human":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
