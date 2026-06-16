import json
import logging
import sys

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

from api.signature import verify_github_signature
from config.settings import settings

from graph.graph import compile_graph, thread_id
from graph.state import SpecKitState

# Ensure project loggers reach stderr regardless of uvicorn's logging config
_log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

root = logging.getLogger()
root.setLevel(logging.INFO)
# Avoid duplicate handlers on reload
if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter(_log_format))
    _handler.setLevel(logging.INFO)
    root.addHandler(_handler)

logger = logging.getLogger(__name__)

graph = None

app = FastAPI(title="Personal-Dev-Setup", version="0.1.0")


@app.on_event("startup")
async def startup():
    global graph
    settings.ensure_data_dir()
    graph = await compile_graph()
    logger.info(f"Personal-Dev-Setup started. Data dir: {settings.speckit_data_path}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/github-events")
@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
):
    logger.info(f"Webhook received: event={x_github_event}")

    try:
        body = await verify_github_signature(request)
    except HTTPException:
        logger.exception("Signature verification failed — check GITHUB_WEBHOOK_SECRET match")
        raise

    payload = json.loads(body)
    action = payload.get("action")

    logger.info(f"Received event: {x_github_event} / {action}")

    try:
        # Route by event type
        if x_github_event == "issues":
            await handle_issues_event(action, payload)

        elif x_github_event == "pull_request_review":
            await handle_review_event(action, payload)

    except Exception:
        logger.exception(f"Unhandled error processing {x_github_event} event")

    return {"ok": True}


async def handle_issues_event(action: str, payload: dict) -> None:
    """Route issue events to the appropriate graph transition."""
    issue = payload["issue"]
    repo = payload["repository"]

    # When an issue is created with labels, GitHub sends "opened" (not "labeled")
    if action == "opened":
        labels = [l["name"] for l in issue.get("labels", [])]
        if "needs-spec" in labels:
            logger.info(f"Issue #{issue['number']} opened with needs-spec on {repo['name']}")
            await trigger_collect_spec(issue, repo)
        return

    if action != "labeled":
        return

    label = payload["label"]["name"]

    logger.info(f"Issue #{issue['number']} labeled: {label} on {repo['name']}")

    if label == "needs-spec":
        await trigger_collect_spec(issue, repo)

    elif label == "spec-approved":
        await trigger_implement(issue, repo)


async def handle_review_event(action: str, payload: dict) -> None:
    """Route PR review events."""
    if action != "submitted":
        return

    review = payload["review"]
    pr = payload["pull_request"]
    repo = payload["repository"]

    if review["state"] == "changes_requested":
        logger.info(f"Changes requested on PR #{pr['number']} in {repo['name']}")
        await trigger_rework(pr, repo, review)


async def trigger_collect_spec(issue: dict, repo: dict) -> None:
    labels = [l["name"] for l in issue.get("labels", [])]

    type_label = next(
        (l for l in labels if l.startswith("type:")),
        "type: feature"
    )
    priority_label = next(
        (l for l in labels if l.startswith("priority:")),
        "priority: normal"
    )

    initial_state: SpecKitState = {
        "issue_number": issue["number"],
        "repo_name": repo["name"],
        "repo_full_name": repo["full_name"],
        "type_label": type_label,
        "priority_label": priority_label,
        "issue_title": issue["title"],
        "issue_body": issue["body"] or "",
        "spec_text": "",
        "branch_name": "",
        "pr_number": None,
        "review_comments": [],
        "status": "needs-spec",
        "agent_output": "",
        "rework_cycle": 0,
        "error": None,
    }

    config = {"configurable": {"thread_id": thread_id(repo["name"], issue["number"])}}

    logger.info(f"Invoking graph for #{issue['number']} in {repo['name']}")

    # Run in background — don't block the webhook response
    import asyncio
    asyncio.create_task(graph.ainvoke(initial_state, config))


async def trigger_implement(issue: dict, repo: dict) -> None:
    # TODO: resume LangGraph instance at spec-approved checkpoint
    logger.info(f"[STUB] trigger_implement: #{issue['number']} in {repo['name']}")


async def trigger_rework(pr: dict, repo: dict, review: dict) -> None:
    # TODO: resume LangGraph instance at needs-rework checkpoint
    logger.info(f"[STUB] trigger_rework: PR #{pr['number']} in {repo['name']}")


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=False,
    )
