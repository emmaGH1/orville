"""Trello REST client scoped to the configured list.

Write surface is limited to creating cards. No delete, archive, or move.
"""

import httpx

API = "https://api.trello.com/1"
UA = "orville/0.1 (support-handoff-agent)"


class TrelloError(RuntimeError):
    pass


class TrelloClient:
    def __init__(self, api_key: str, token: str) -> None:
        self._params = {"key": api_key, "token": token}

    def _request(self, method: str, path: str, extra: dict | None = None, **kwargs) -> httpx.Response:
        params = {**self._params, **(extra or {})}
        with httpx.Client(params=params, timeout=30, headers={"User-Agent": UA}) as client:
            return client.request(method, f"{API}{path}", **kwargs)

    def create_card(self, list_id: str, name: str, desc: str) -> dict:
        r = self._request("POST", "/cards", extra={"idList": list_id, "name": name, "desc": desc})
        if r.status_code != 200:
            raise TrelloError(f"create card failed: HTTP {r.status_code} {r.text[:200]}")
        data = r.json()
        return {"id": data["id"], "url": data.get("url") or data.get("shortUrl")}

    def get_card(self, card_id: str) -> dict:
        r = self._request("GET", f"/cards/{card_id}")
        if r.status_code != 200:
            raise TrelloError(f"get card failed: HTTP {r.status_code}")
        data = r.json()
        return {"id": data["id"], "idList": data["idList"], "name": data["name"], "desc": data.get("desc", ""), "url": data.get("url") or data.get("shortUrl")}

    def list_cards(self, list_id: str) -> list[dict]:
        r = self._request("GET", f"/lists/{list_id}/cards")
        if r.status_code != 200:
            raise TrelloError(f"list cards failed: HTTP {r.status_code}")
        return [{"id": c["id"], "name": c["name"], "desc": c.get("desc", "")} for c in r.json()]
