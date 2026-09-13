"""GitHub REST client scoped to the configured repository.

Write surface is limited to issue comments, issue creation, and reads. There is
no delete or close operation in this client by design.
"""

import re

import httpx

API = "https://api.github.com"
UA = "orville/0.1 (support-handoff-agent)"


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": UA,
        }

    def _url(self, path: str) -> str:
        return f"{API}/repos/{self.repo}/{path}"

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        with httpx.Client(headers=self._headers, timeout=30) as client:
            return client.request(method, self._url(path), **kwargs)

    def list_open_issues(self, per_page: int = 20) -> list[dict]:
        r = self._request("GET", "issues", params={"state": "open", "per_page": per_page})
        if r.status_code != 200:
            raise GitHubError(f"list issues failed: HTTP {r.status_code}")
        return [
            {
                "number": i["number"],
                "title": i["title"],
                "body": (i.get("body") or "")[:400],
                "html_url": i["html_url"],
            }
            for i in r.json()
            if "pull_request" not in i
        ]

    def create_comment(self, issue_number: int, body: str) -> dict:
        r = self._request("POST", f"issues/{issue_number}/comments", json={"body": body})
        if r.status_code != 201:
            raise GitHubError(f"comment failed: HTTP {r.status_code} {r.text[:200]}")
        data = r.json()
        return {"id": data["id"], "html_url": data["html_url"]}

    def get_comment(self, comment_id: int) -> dict:
        r = self._request("GET", f"issues/comments/{comment_id}")
        if r.status_code != 200:
            raise GitHubError(f"get comment failed: HTTP {r.status_code}")
        data = r.json()
        # issue_url ends with /issues/<number>; proves which issue owns the comment.
        m = re.search(r"/issues/(\d+)$", data.get("issue_url") or "")
        return {
            "id": data["id"],
            "body": data["body"],
            "html_url": data["html_url"],
            "issue_number": int(m.group(1)) if m else None,
        }

    def create_issue(self, title: str, body: str) -> dict:
        r = self._request("POST", "issues", json={"title": title, "body": body})
        if r.status_code != 201:
            raise GitHubError(f"create issue failed: HTTP {r.status_code} {r.text[:200]}")
        data = r.json()
        return {"number": data["number"], "id": data["id"], "html_url": data["html_url"]}

    def get_issue(self, issue_number: int) -> dict:
        r = self._request("GET", f"issues/{issue_number}")
        if r.status_code != 200:
            raise GitHubError(f"get issue failed: HTTP {r.status_code}")
        data = r.json()
        return {
            "number": data["number"],
            "title": data["title"],
            "body": data.get("body") or "",
            "html_url": data["html_url"],
        }

    def list_comments(self, issue_number: int, per_page: int = 50, page: int = 1) -> list[dict]:
        r = self._request("GET", f"issues/{issue_number}/comments",
                          params={"per_page": per_page, "page": page})
        if r.status_code != 200:
            raise GitHubError(f"list comments failed: HTTP {r.status_code}")
        return [{"id": c["id"], "body": c["body"]} for c in r.json()]
