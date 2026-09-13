"""Load and validate Orville configuration from .env.

Destinations (repo, list, webhook) come only from configuration, never from
report text.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

REQUIRED = (
    "GITHUB_REPO",
    "GITHUB_TOKEN",
    "TRELLO_API_KEY",
    "TRELLO_TOKEN",
    "TRELLO_LIST_ID",
    "DISCORD_WEBHOOK_URL",
    "MODEL_BASE_URL",
    "MODEL_ID",
    "GROQ_API_KEY",
)

# Secrets that must never appear in output, logs, or traces.
SECRET_KEYS = ("GITHUB_TOKEN", "TRELLO_API_KEY", "TRELLO_TOKEN", "DISCORD_WEBHOOK_URL", "GROQ_API_KEY")


@dataclass(frozen=True)
class Config:
    github_repo: str
    github_token: str
    trello_api_key: str
    trello_token: str
    trello_list_id: str
    discord_webhook_url: str
    model_base_url: str
    model_id: str
    groq_api_key: str
    state_dir: str = "state"


def load_config(env_file: str | None = None) -> Config:
    load_dotenv(env_file) if env_file else load_dotenv()
    missing = [k for k in REQUIRED if not os.getenv(k, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required .env values: {', '.join(missing)}")
    return Config(
        github_repo=os.getenv("GITHUB_REPO", "").strip(),
        github_token=os.getenv("GITHUB_TOKEN", "").strip(),
        trello_api_key=os.getenv("TRELLO_API_KEY", "").strip(),
        trello_token=os.getenv("TRELLO_TOKEN", "").strip(),
        trello_list_id=os.getenv("TRELLO_LIST_ID", "").strip(),
        discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        model_base_url=os.getenv("MODEL_BASE_URL", "").strip(),
        model_id=os.getenv("MODEL_ID", "").strip(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
    )
