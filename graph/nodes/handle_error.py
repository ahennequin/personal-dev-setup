import logging

from graph.state import SpecKitState

logger = logging.getLogger(__name__)


async def handle_error(state: SpecKitState) -> dict:
    """
    Node: handle_error
    - Posts failure comment on the issue or PR
    - Removes any in-progress labels
    - Resets to a recoverable state so the human can re-trigger
    Returns state delta.
    """
    error = state.get("error", "Unknown error")
    issue_number = state["issue_number"]
    repo_full_name = state["repo_full_name"]
    status = state["status"]

    logger.error(f"[handle_error] #{issue_number} in {repo_full_name}: {error}")

    # TODO: implement
    # 1. from github.client import post_issue_comment, remove_label, add_label
    # 2. Post comment with error + re-trigger instructions
    # 3. Remove in-progress / rework-in-progress label
    # 4. Re-add the triggering label so the human can retry

    recovery_label = {
        "in-progress": "spec-approved",
        "rework-in-progress": "needs-rework",
        "spec-draft": "needs-spec",
    }.get(status, "needs-spec")

    logger.info(f"[handle_error] Recovery label for retry: {recovery_label}")

    return {
        "status": "error",
        "error": error,
    }
