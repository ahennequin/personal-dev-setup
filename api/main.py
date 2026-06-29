import asyncio
import json
import logging
import sys

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from langgraph.types import Command

from api.signature import verify_github_signature
from config.settings import settings

from github.client import (
    get_issue_comments,
    get_issue_labels,
    get_pr_review_comments,
    list_open_issues_with_label,
    list_pr_reviews,
)
from graph.graph import compile_graph, list_graph_threads, thread_id
from graph.nodes.collect_spec import SPEC_DRAFT_MARKER
from graph.state import SpecKitState

# Ensure project loggers reach stderr regardless of uvicorn's logging config

class _ColorFormatter(logging.Formatter):
    _level_colors = {
        logging.ERROR: "\033[31m",
        logging.WARNING: "\033[33m",
        logging.INFO: "\033[37m",
    }
    _job_color = "\033[32m"
    _reset = "\033[0m"
    _grey = "\033[90m"

    def format(self, record: logging.LogRecord) -> str:
        level_color = self._level_colors.get(record.levelno, self._reset)
        msg_color = level_color
        if (
            record.levelno == logging.INFO
            and hasattr(record, "msg")
            and "job" in str(record.msg).lower()
        ):
            msg_color = self._job_color
        formatted = self._grey + "%(asctime)s " + self._reset
        formatted += level_color + "[%(levelname)s] " + self._reset
        formatted += msg_color + "%(name)s: %(message)s" + self._reset
        return logging.Formatter(fmt=formatted).format(record)


_log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

root = logging.getLogger()
root.setLevel(logging.INFO)
# Avoid duplicate handlers on reload
if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(_ColorFormatter(_log_format))
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

_backfill_done = False


@app.on_event("startup")
async def startup():
    global graph, _backfill_done
    settings.ensure_data_dir()
    graph = await compile_graph()
    logger.info(f"Personal-Dev-Setup started. Data dir: {settings.speckit_data_path}")
    if not _backfill_done:
        _backfill_done = True
        _run_background(backfill_incomplete_issues())


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

        elif x_github_event == "issue_comment":
            await handle_issue_comment_event(action, payload)

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

    elif review["state"] == "approved":
        logger.info(f"PR #{pr['number']} approved in {repo['name']}")
        await trigger_approve(pr, repo, review)


async def handle_issue_comment_event(action: str, payload: dict) -> None:
    """Re-run spec collection when a human comments on a spec-draft issue."""
    if action != "created":
        return

    issue = payload["issue"]
    repo = payload["repository"]
    comment = payload["comment"]

    current_labels = [lb["name"] for lb in issue.get("labels", [])]
    if "spec-draft" not in current_labels:
        return

    comment_author = comment["user"]["login"]
    bot_username = settings.github_bot_username or settings.github_username
    if comment_author == bot_username or SPEC_DRAFT_MARKER in comment.get("body", ""):
        logger.info(f"Issue_comment by bot on #{issue['number']} — skipping re-spec")
        return

    logger.info(
        f"Human comment on #{issue['number']} in {repo['name']} — "
        f"re-running spec collection"
    )

    config = {"configurable": {"thread_id": thread_id(repo["name"], issue["number"])}}
    _run_background(graph.ainvoke(Command(resume="re-spec"), config))


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
            "issue_body": issue.get("body", "") or "",
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

    # Check if a graph thread already exists.
    thread_exists = False
    try:
        snapshot = await graph.aget_state(config)
        thread_exists = bool(snapshot.values)
        if thread_exists and snapshot.tasks and snapshot.next:
            # Normal case: thread exists and is waiting at a checkpoint.
            # NOTE: Command.update is deliberately NOT used here. In langgraph
            # >=1.0, Command.update is applied at the END of ainvoke and would
            # overwrite any intermediate state changes (like handle_error
            # clearing the error). Instead, the checkpoint node returns the
            # status update when it sees the resume value.
            _run_background(graph.ainvoke(
                Command(resume="approved"),
                config,
            ))
            return
    except Exception:
        thread_exists = False

    if not thread_exists:
        # No thread yet — user pre-wrote a spec draft. Start fresh, skipping
        # collect_spec and going straight to implement.
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
            "issue_body": issue.get("body", "") or "",
            "spec_text": issue.get("body", "") or "",
            "branch_name": "",
            "pr_number": None,
            "review_comments": [],
            "status": "spec-approved",
            "agent_output": "",
            "rework_cycle": 0,
            "error": None,
        }

        logger.info(
            f"Fresh thread for #{issue['number']} in {repo['name']} — "
            f"jumpstarting from spec-approved with issue body as spec"
        )
        _run_background(graph.ainvoke(initial_state, config))
        return

    # Thread exists but has no pending interrupt (completed or crashed).
    logger.warning(
        f"No pending graph state for #{issue['number']} in {repo['name']} "
        f"(next={snapshot.next}, tasks={len(snapshot.tasks)}) — can't resume"
    )


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
    # NOTE: Command.update with status is not used — _await_review
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


async def trigger_approve(pr: dict, repo: dict, review: dict) -> None:
    """Resume a graph instance waiting at await_review after a PR approval."""
    thread = thread_id(repo["name"], pr["number"])
    config = {"configurable": {"thread_id": thread}}
    logger.info(f"Resuming graph for PR #{pr['number']} in {repo['name']} (approved)")
    _run_background(graph.ainvoke(Command(resume="approved"), config))


async def _extract_spec_from_issue(repo_full_name: str, issue_number: int) -> str:
    """Extract spec text from the spec-draft comment posted by collect_spec."""
    comments = await get_issue_comments(repo_full_name, issue_number)
    for comment in reversed(comments):
        body = comment.get("body", "")
        if SPEC_DRAFT_MARKER in body:
            if body.startswith("## Spec Draft\n"):
                body = body[len("## Spec Draft\n"):]
            parts = body.split("\n---\n")
            return parts[0].strip()
    return ""


async def _has_human_feedback_on_spec_draft(repo_full_name: str, issue_number: int) -> bool:
    """Check if a human commented on a spec-draft issue after the spec was posted."""
    comments = await get_issue_comments(repo_full_name, issue_number)
    found_spec = False
    for comment in comments:
        if SPEC_DRAFT_MARKER in comment.get("body", ""):
            found_spec = True
            continue
        if found_spec:
            return True
    return False


async def _resolve_interrupted_thread(
    tid: str,
    config: dict,
    state: dict,
    snapshot,
) -> int:
    """Resolve a thread waiting at an interrupt by checking current GitHub state.
    Returns 1 if an action was taken, 0 otherwise."""
    status = state.get("status", "")
    issue_number = state.get("issue_number")
    repo_full_name = state.get("repo_full_name")
    repo_name = state.get("repo_name")

    if not issue_number or not repo_full_name:
        return 0

    if status == "spec-draft":
        # Check if label changed to spec-approved
        github_labels = await get_issue_labels(repo_full_name, issue_number)
        if "spec-approved" in github_labels:
            logger.info(f"Backfill: GitHub label is spec-approved for thread {tid} — resuming implement")
            issue = {"number": issue_number, "title": state.get("issue_title", "")}
            repo = {"name": repo_name, "full_name": repo_full_name}
            await trigger_implement(issue, repo)
            return 1
        # Check if human commented (re-spec)
        if await _has_human_feedback_on_spec_draft(repo_full_name, issue_number):
            logger.info(f"Backfill: human feedback on spec-draft for thread {tid} — re-running spec")
            _run_background(graph.ainvoke(Command(resume="re-spec"), config))
            return 1
        return 0

    if status == "in-progress":
        pr_number = state.get("pr_number")
        if not pr_number:
            return 0
        reviews = await list_pr_reviews(repo_full_name, pr_number)
        if not reviews:
            return 0
        latest = reviews[-1]["state"]
        if latest == "changes_requested":
            logger.info(f"Backfill: PR #{pr_number} has changes_requested for thread {tid} — resuming rework")
            raw = await get_pr_review_comments(repo_full_name, pr_number)
            review_comments = [
                {
                    "path": c["path"],
                    "line": c.get("line"),
                    "body": c["body"],
                    "diff_hunk": c["diff_hunk"],
                }
                for c in raw
            ]
            _run_background(graph.ainvoke(
                Command(resume="rework", update={"review_comments": review_comments}),
                config,
            ))
            return 1
        if latest == "approved":
            logger.info(f"Backfill: PR #{pr_number} approved for thread {tid} — resuming")
            _run_background(graph.ainvoke(Command(resume="approved"), config))
            return 1
        return 0

    return 0


async def backfill_incomplete_issues() -> None:
    """On startup, scan for incomplete issues and resume or start their pipelines."""
    logger.info("Backfilling incomplete issues...")
    processed = 0

    # ── Phase 1: GitHub issues without graph threads ──────────────────────
    for repo_full in settings.github_repos:
        repo_short = repo_full.split("/", 1)[1]
        repo = {"name": repo_short, "full_name": repo_full}

        for label in ("needs-spec", "spec-draft", "spec-approved"):
            try:
                issues = await list_open_issues_with_label(repo_full, label)
            except Exception as e:
                logger.warning(
                    f"Backfill: could not list {label} issues for {repo_full}: {e}"
                )
                continue

            for issue in issues:
                tid = thread_id(repo_short, issue["number"])
                config = {"configurable": {"thread_id": tid}}
                try:
                    snapshot = await graph.aget_state(config)
                    if snapshot.values:
                        continue  # thread already exists
                except Exception:
                    pass

                current_labels = [lb["name"] for lb in issue.get("labels", [])]
                type_label = next(
                    (lb for lb in current_labels if lb.startswith("type:")),
                    "type: feature",
                )
                priority_label = next(
                    (lb for lb in current_labels if lb.startswith("priority:")),
                    "priority: normal",
                )

                if label == "needs-spec":
                    logger.info(
                        f"Backfill: starting collect_spec for #{issue['number']} in {repo_full}"
                    )
                    await trigger_collect_spec(issue, repo)

                elif label == "spec-draft":
                    spec_text = await _extract_spec_from_issue(repo_full, issue["number"])
                    if not spec_text:
                        logger.warning(
                            f"Backfill: no spec found for #{issue['number']} "
                            f"in {repo_full} — treating as needs-spec"
                        )
                        await trigger_collect_spec(issue, repo)
                        processed += 1
                        continue

                    logger.info(
                        f"Backfill: creating thread for spec-draft #{issue['number']} in {repo_full}"
                    )
                    initial_state: SpecKitState = {
                        "issue_number": issue["number"],
                        "repo_name": repo_short,
                        "repo_full_name": repo_full,
                        "type_label": type_label,
                        "priority_label": priority_label,
                        "issue_title": issue["title"],
                        "issue_body": issue.get("body", "") or "",
                        "spec_text": spec_text,
                        "branch_name": "",
                        "pr_number": None,
                        "review_comments": [],
                        "status": "spec-draft",
                        "agent_output": "",
                        "rework_cycle": 0,
                        "error": None,
                    }
                    _run_background(graph.ainvoke(initial_state, config))

                elif label == "spec-approved":
                    logger.info(
                        f"Backfill: jumpstarting spec-approved #{issue['number']} in {repo_full}"
                    )
                    await trigger_implement(issue, repo)

                processed += 1

    # ── Phase 2: existing graph threads ───────────────────────────────────
    thread_ids = await list_graph_threads()
    for tid in thread_ids:
        config = {"configurable": {"thread_id": tid}}
        try:
            snapshot = await graph.aget_state(config)
        except Exception:
            continue

        state = snapshot.values
        status = state.get("status", "")
        issue_number = state.get("issue_number")
        repo_name = state.get("repo_name")
        repo_full_name = state.get("repo_full_name")

        # ── 2a. Thread at END (completed or crashed) ──────────────────────
        if not snapshot.next:
            if status in ("needs-spec", "error") and not state.get("spec_text"):
                if issue_number is not None and repo_name is not None and repo_full_name is not None:
                    logger.info(
                        f"Backfill: restarting stalled thread {tid} "
                        f"(status={status}, no spec_text)"
                    )
                    issue = {"number": issue_number, "title": state.get("issue_title", "")}
                    repo = {"name": repo_name, "full_name": repo_full_name}
                    await trigger_collect_spec(issue, repo)
                    processed += 1
                else:
                    logger.warning(
                        f"Backfill: thread {tid} stalled but missing state keys — skipping"
                    )
            elif status == "error" and state.get("spec_text"):
                # Error occurred after spec was collected — restart from
                # await_spec_approval by creating a fresh spec-draft thread.
                if issue_number is not None and repo_name is not None and repo_full_name is not None:
                    logger.info(
                        f"Backfill: restarting errored thread {tid} "
                        f"(has spec_text, status=error) from spec-draft"
                    )
                    await graph.aupdate_state(config, {"status": "spec-draft", "error": None})
                    # Thread is at END, so we need to invoke to restart.
                    # The entry point will route to await_spec_approval.
                    _run_background(graph.ainvoke(None, config))
                    processed += 1
            continue

        # ── 2b. Thread with pending tasks ─────────────────────────────────
        if not snapshot.tasks:
            # Orphaned (no tasks, but has next) — crashed mid-node
            if status in ("needs-spec", "spec-draft", "spec-approved", "in-progress", "needs-rework"):
                if "rework" in snapshot.next and not state.get("review_comments"):
                    pr_number = state.get("pr_number")
                    if pr_number and repo_full_name:
                        raw = await get_pr_review_comments(repo_full_name, pr_number)
                        review_comments = [
                            {
                                "path": c["path"],
                                "line": c.get("line"),
                                "body": c["body"],
                                "diff_hunk": c["diff_hunk"],
                            }
                            for c in raw
                        ]
                        if review_comments:
                            await graph.aupdate_state(config, {"review_comments": review_comments})
                logger.info(f"Backfill: continuing orphaned thread {tid} (status={status})")
                _run_background(graph.ainvoke(None, config))
                processed += 1
            continue

        # ── 2c. Thread waiting at interrupt ──────────────────────────────
        has_interrupt = any(getattr(t, "interrupts", ()) for t in snapshot.tasks)

        if not has_interrupt:
            # Pending task that isn't at an interrupt (crashed mid-node)
            if status in ("needs-spec", "spec-draft", "spec-approved", "in-progress", "needs-rework"):
                if not issue_number:
                    logger.warning(
                        f"Backfill: thread {tid} has pending task but "
                        f"missing issue_number — skipping"
                    )
                    continue
                logger.info(
                    f"Backfill: resuming pending thread {tid} (status={status}, "
                    f"next={snapshot.next})"
                )
                _run_background(graph.ainvoke(None, config))
                processed += 1
            continue

        # ── 2d. Thread genuinely waiting at an interrupt ──────────────────
        # Resolve by checking current GitHub state
        taken = await _resolve_interrupted_thread(tid, config, state, snapshot)
        processed += taken
        if not taken:
            # Fall back to old handlers for spec-approved / needs-rework
            if status == "spec-approved" and issue_number is not None and repo_name is not None and repo_full_name is not None:
                logger.info(f"Backfill: resuming implement for thread {tid}")
                issue = {"number": issue_number, "title": state.get("issue_title", "")}
                repo = {"name": repo_name, "full_name": repo_full_name}
                await trigger_implement(issue, repo)
                processed += 1

            elif status == "needs-rework":
                review_comments = state.get("review_comments")
                if not review_comments:
                    pr_number = state.get("pr_number")
                    if pr_number and repo_full_name:
                        raw = await get_pr_review_comments(repo_full_name, pr_number)
                        review_comments = [
                            {
                                "path": c["path"],
                                "line": c.get("line"),
                                "body": c["body"],
                                "diff_hunk": c["diff_hunk"],
                            }
                            for c in raw
                        ]
                if review_comments:
                    logger.info(f"Backfill: resuming rework for thread {tid}")
                    _run_background(graph.ainvoke(
                        Command(resume="rework", update={"review_comments": review_comments}),
                        config,
                    ))
                    processed += 1

    logger.info(f"Backfill complete: {processed} issues processed")


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=False,
    )
