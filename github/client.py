import logging
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.github_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def post_issue_comment(repo_full_name: str, issue_number: int, body: str) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/comments"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_headers(), json={"body": body})
        r.raise_for_status()
        return r.json()


async def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> dict:
    # PRs and issues share the same comments endpoint on GitHub
    return await post_issue_comment(repo_full_name, pr_number, body)


async def add_labels(repo_full_name: str, issue_number: int, labels: list[str]) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/labels"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_headers(), json={"labels": labels})
        r.raise_for_status()
        return r.json()


async def remove_label(repo_full_name: str, issue_number: int, label: str) -> None:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/labels/{label}"
    async with httpx.AsyncClient() as client:
        r = await client.delete(url, headers=_headers())
        if r.status_code == 404:
            logger.warning(f"Label '{label}' not found on #{issue_number} — skipping")
            return
        r.raise_for_status()


async def get_issue(repo_full_name: str, issue_number: int) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        r.raise_for_status()
        return r.json()


async def get_issue_comments(repo_full_name: str, issue_number: int) -> list[dict]:
    url = f"{BASE_URL}/repos/{repo_full_name}/issues/{issue_number}/comments"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        r.raise_for_status()
        return r.json()


async def get_pr_review_comments(repo_full_name: str, pr_number: int) -> list[dict]:
    url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}/comments"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
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
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


async def get_label_names(issue: dict) -> list[str]:
    return [label["name"] for label in issue.get("labels", [])]


async def get_repo(repo_full_name: str) -> dict:
    url = f"{BASE_URL}/repos/{repo_full_name}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
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
        r = await client.post(url, headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()
