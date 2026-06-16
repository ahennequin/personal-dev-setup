import logging

from graph.state import SpecKitState

logger = logging.getLogger(__name__)


async def implement(state: SpecKitState) -> dict:
    """
    Node: implement
    - Creates git branch
    - Invokes OpenCode with the implementation prompt
    - Opens a draft PR on GitHub
    - Updates labels: spec-approved → in-progress (then removed on PR open)
    Returns state delta.
    """
    logger.info(f"[implement] #{state['issue_number']} in {state['repo_name']}")

    # TODO: implement
    # 1. from agent.prompts.implement import build_impl_prompt
    # 2. git checkout -b {branch_name}
    # 3. from agent.runner import run_opencode
    # 4. gh pr create --draft
    # 5. from github.client import update_labels

    return {
        "status": "in-progress",
        "branch_name": "",      # filled by implementation
        "pr_number": None,
        "agent_output": "",
        "error": None,
    }
