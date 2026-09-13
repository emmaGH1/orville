"""Discord incoming-webhook client.

Sends use ?wait=true so Discord returns the message, giving a message ID to
verify. A timeout without an ID is returned as `uncertain`, never retried
blindly here. A normal User-Agent is required; a generic one gets HTTP 403.
"""

import httpx

UA = "Orville/0.1 (support-handoff-agent)"


class DiscordError(RuntimeError):
    pass


class DiscordOutcome:
    def __init__(self, status: str, message: dict | None = None, detail: str = "") -> None:
        self.status = status  # "posted" | "uncertain" | "failed"
        self.message = message or {}
        self.detail = detail


class DiscordClient:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url.rstrip("/")

    def post_message(self, content: str) -> DiscordOutcome:
        with httpx.Client(timeout=15, headers={"User-Agent": UA, "Content-Type": "application/json"}) as client:
            try:
                r = client.post(f"{self.webhook_url}?wait=true", json={"content": content})
            except httpx.TimeoutException as e:
                return DiscordOutcome("uncertain", detail=f"timeout without message ID: {e}")
            if r.status_code not in (200, 204):
                return DiscordOutcome("failed", detail=f"HTTP {r.status_code} {r.text[:200]}")
            if r.status_code == 200:
                data = r.json()
                return DiscordOutcome("posted", message={"id": data["id"], "channel_id": data["channel_id"]})
            # 204 should not happen with wait=true; without an ID we cannot verify.
            return DiscordOutcome("uncertain", detail="HTTP 204 without message ID")

    def get_message(self, message_id: str) -> dict:
        with httpx.Client(timeout=15, headers={"User-Agent": UA}) as client:
            r = client.get(f"{self.webhook_url}/messages/{message_id}")
            if r.status_code != 200:
                raise DiscordError(f"get message failed: HTTP {r.status_code}")
            data = r.json()
            return {"id": data["id"], "channel_id": data["channel_id"], "content": data["content"]}
