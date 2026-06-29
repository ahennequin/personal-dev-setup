import logging
import time
from datetime import datetime, timezone

import httpx
import jwt

from config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"

# Bot token cache (GitHub App installation tokens expire after 1 hour)
_bot_token: str | None = None
_bot_token_expires_at: float = 0


async def _fetch_installation_token() -> tuple[str, float]:
    """Exchange a GitHub App JWT for an installation access token."""
    now = int(time.time())
    jwt_payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": settings.github_app_id,
    }
    private_key = settings.github_app_private_key_path.read_text()
    app_jwt = jwt.encode(jwt_payload, private_key, algorithm="RS256")

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/app/installations/{settings.github_app_installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        r.raise_for_status()
        data = r.json()

    expires_at = (
        datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    logger.info(f"Fetched new GitHub App installation token (expires at {data['expires_at']})")
    return data["token"], expires_at


async def _get_bot_token() -> str:
    """Get a valid installation token, refreshing the cached one if needed."""
    global _bot_token, _bot_token_expires_at

    if _bot_token and time.time() < _bot_token_expires_at - 120:
        return _bot_token

    _bot_token, _bot_token_expires_at = await _fetch_installation_token()
    return _bot_token


async def _get_token() -> str:
    """Return the bot installation token if configured, otherwise the user PAT."""
    if settings.has_bot_identity:
        return await _get_bot_token()
    return settings.github_pat


async def _headers() -> dict:
    token = await _get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def post_issue_comment(repo_full_name: str, issue_number: int, body: str) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/comments"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=await _headers(), json={"body": body})
        r.raise_for_status()
        return r.json()


async def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> dict:
    return await post_issue_comment(repo_full_name, pr_number, body)


async def add_labels(repo_full_name: str, issue_number: int, labels: list[str]) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/labels"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=await _headers(), json={"labels": labels})
        r.raise_for_status()
        return r.json()


async def remove_label(repo_full_name: str, issue_number: int, label: str) -> None:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/labels/{label}"
    async with httpx.AsyncClient() as client:
        r = await client.delete(url, headers=await _headers())
        if r.status_code == 404:
            logger.warning(f"Label '{label}' not found on #{issue_number} — skipping")
            return
        r.raise_for_status()


async def get_issue(repo_full_name: str, issue_number: int) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=await _headers())
        r.raise_for_status()
        return r.json()


async def get_issue_comments(repo_full_name: str, issue_number: int) -> list[dict]:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/comments"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=await _headers())
        r.raise_for_status()
        return r.json()


async def get_pr_review_comments(repo_full_name: str, pr_number: int) -> list[dict]:
    url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}/comments"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=await _headers())
        r.raise_for_status()
        return r.json()


async def get_issue_labels(repo_full_name: str, issue_number: int) -> list[str]:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/labels"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=await _headers())
        r.raise_for_status()
        return [lb["name"] for lb in r.json()]


async def list_pr_reviews(repo_full_name: str, pr_number: int) -> list[dict]:
    url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}/reviews"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=await _headers())
        r.raise_for_status()
        return r.json()


async def list_open_issues_with_label(
    repo_full_name: str,
    label: str,
    sort: str = "created",
    direction: str = "asc",
) -> list[dict]:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues"
    params = {
        "state": "open",
        "labels": label,
        "sort": sort,
        "direction": direction,
        "per_page": 100,
    }
    all_issues: list[dict] = []
    page = 1
    async with httpx.AsyncClient() as client:
        while True:
            params["page"] = page
            r = await client.get(url, headers=await _headers(), params=params)
            r.raise_for_status()
            issues = r.json()
            if not issues:
                break
            all_issues.extend(issues)
            page += 1
    return all_issues


async def get_label_names(issue: dict) -> list[str]:
    return [label["name"] for label in issue.get("labels", [])]


async def get_repo(repo_full_name: str) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=await _headers())
        r.raise_for_status()
        return r.json()


async def create_pull_request(
    repo_full_name: str,
    title: str,
    body: str,
    head: str,
    base: str,
    draft: bool = True,
) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}/pulls"
    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
        "draft": draft,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=await _headers(), json=payload)
        r.raise_for_status()
        return r.json()
