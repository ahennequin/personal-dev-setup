import asyncio
import json
import logging
import sys

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from langgraph.types import Command

from api.signature import verify_github_signature
from config.settings import settings

from github.client import get_pr_review_comments
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

# Dedup set: prevent duplicate graph invocations for the same issue
# GitHub often sends both "opened" and "labeled" events at issue creation
_processing: set[str] = set()

_background_tasks: set[asyncio.Task] = set()


def _run_background(coro):
    """Schedule a background task with error logging and keep a reference
    (to prevent asyncio from silently dropping Task exceptions on GC)."""
    task = asyncio.create_task(coro)

    def _log_exception(t):
        _background_tasks.discard(t)
        try:
            exc = t.exception()
            if exc is not None:
                logger.exception(f"Background task failed: {exc}")
        except asyncio.InvalidStateError:
            pass

    task.add_done_callback(_log_exception)
    _background_tasks.add(task)


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

    if action == "opened":
        labels = [lb["name"] for lb in issue.get("labels", [])]
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
    key = f"{repo['name']}/{issue['number']}"
    if key in _processing:
        logger.info(f"Skipping duplicate trigger_collect_spec for {key}")
        return
    _processing.add(key)

    try:
        current_labels = [lb["name"] for lb in issue.get("labels", [])]

        type_label = next(
            (lb for lb in current_labels if lb.startswith("type:")),
            "type: feature"
        )
        priority_label = next(
            (lb for lb in current_labels if lb.startswith("priority:")),
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

        _run_background(graph.ainvoke(initial_state, config))

    finally:
        _processing.discard(key)


async def trigger_implement(issue: dict, repo: dict) -> None:
    config = {"configurable": {"thread_id": thread_id(repo["name"], issue["number"])}}
    logger.info(f"Resuming graph for #{issue['number']} in {repo['name']} (spec-approved)")

    # Verify the thread exists and has a pending interrupt before resuming.
    try:
        state = await graph.aget_state(config)
        if not state.tasks or not state.next:
            logger.warning(
                f"No pending graph state for #{issue['number']} in {repo['name']} "
                f"(next={state.next}, tasks={len(state.tasks)}) — can't resume"
            )
            return
    except Exception:
        logger.warning(
            f"Could not load graph state for #{issue['number']} in {repo['name']} — "
            f"the thread may not exist. Add needs-spec label to start fresh."
        )
        return

    # NOTE: Command.update is deliberately NOT used here. In langgraph >=1.0,
    # Command.update is applied at the END of ainvoke and would overwrite any
    # intermediate state changes (like handle_error clearing the error).
    # Instead, _checkpoint_node returns the status update when it sees
    # the resume value "approved".
    _run_background(graph.ainvoke(
        Command(resume="approved"),
        config,
    ))


async def trigger_rework(pr: dict, repo: dict, review: dict) -> None:
    config = {"configurable": {"thread_id": thread_id(repo["name"], pr["number"])}}
    raw_comments = await get_pr_review_comments(repo["full_name"], pr["number"])
    review_comments = [
        {
            "path": c["path"],
            "line": c.get("line"),
            "body": c["body"],
            "diff_hunk": c["diff_hunk"],
        }
        for c in raw_comments
    ]
    logger.info(
        f"Resuming graph for PR #{pr['number']} in {repo['name']} "
        f"({len(review_comments)} review comments)"
    )
    # NOTE: Command.update with status is not used — _checkpoint_node
    # returns {"status": "needs-rework"} when it sees resume="rework".
    # review_comments are passed via Command.update because they come from
    # the webhook payload, not from the checkpoint node.
    _run_background(graph.ainvoke(
        Command(
            resume="rework",
            update={"review_comments": review_comments},
        ),
        config,
    ))


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=False,
    )
