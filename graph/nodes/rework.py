import logging

from graph.state import SpecKitState

logger = logging.getLogger(__name__)


async def rework(state: SpecKitState) -> dict:
    """
    Node: rework
    - Reads review_comments from state
    - Invokes OpenCode with the rework prompt
    - Pushes commits to existing branch
    - Posts "rework complete" comment on PR
    - Removes needs-rework label
    Returns state delta.
    """
    logger.info(
        f"[rework] #{state['issue_number']} in {state['repo_name']} "
        f"(cycle {state['rework_cycle'] + 1})"
    )

    # TODO: implement
    # 1. from agent.prompts.rework import build_rework_prompt
    # 2. from agent.runner import run_opencode
    # 3. git push (no force)
    # 4. from github.client import post_pr_comment, remove_label

    return {
        "status": "in-progress",
        "rework_cycle": state["rework_cycle"] + 1,
        "agent_output": "",
        "error": None,
    }
