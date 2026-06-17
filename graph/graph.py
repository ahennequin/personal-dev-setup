import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt

from config.settings import settings
from graph.state import SpecKitState
from graph.edges import route_after_spec_approval, route_after_review, route_after_implement
from graph.nodes.collect_spec import collect_spec
from graph.nodes.implement import implement
from graph.nodes.rework import rework
from graph.nodes.handle_error import handle_error

logger = logging.getLogger(__name__)


def _checkpoint_node(name: str):
    """
    Suspends the graph with interrupt() and persists state.
    The next webhook resumes from here via Command(resume=..., update=...).

    In langgraph >=1.0, the node re-executes from the start on resume.
    `interrupt()` returns the resume value on re-execution, so the node
    uses that to set status rather than relying on Command.update
    (which is applied at the end and would overwrite handle_error's work).
    """
    async def node(state: SpecKitState) -> dict:
        logger.info(f"[checkpoint:{name}] Suspended. Waiting for next event.")
        result = interrupt("waiting")
        logger.info(f"[checkpoint:{name}] Resumed with: {result}")
        if result == "approved":
            return {"status": "spec-approved"}
        if result == "rework":
            return {"status": "needs-rework", "rework_cycle": state.get("rework_cycle", 0) + 1}
        return {}
    node.__name__ = name
    return node


def build_graph() -> StateGraph:
    workflow = StateGraph(SpecKitState)

    # Nodes
    workflow.add_node("collect_spec", collect_spec)
    workflow.add_node("await_spec_approval", _checkpoint_node("await_spec_approval"))
    workflow.add_node("implement", implement)
    workflow.add_node("await_review", _checkpoint_node("await_review"))
    workflow.add_node("rework", rework)
    workflow.add_node("handle_error", handle_error)

    # Entry point
    workflow.set_entry_point("collect_spec")

    # Linear edges
    workflow.add_edge("collect_spec", "await_spec_approval")
    workflow.add_edge("rework", "await_review")

    # Conditional edge after implement (errors route to handle_error)
    workflow.add_conditional_edges(
        "implement",
        route_after_implement,
        {
            "await_review": "await_review",
            "handle_error": "handle_error",
        },
    )

    # Conditional edges (resume points after webhooks)
    workflow.add_conditional_edges(
        "await_spec_approval",
        route_after_spec_approval,
        {
            "implement": "implement",
            "await_spec_approval": "await_spec_approval",
            "handle_error": "handle_error",
        },
    )

    workflow.add_conditional_edges(
        "await_review",
        route_after_review,
        {
            "rework": "rework",
            "__end__": END,
            "await_review": "await_review",
            "handle_error": "handle_error",
        },
    )

    # Error routes back to await_spec_approval so the human can re-add
    # spec-approved to retry without restarting from scratch.
    workflow.add_edge("handle_error", "await_spec_approval")

    return workflow


async def compile_graph():
    """Compile the graph with async SQLite persistence."""
    settings.ensure_data_dir()
    import aiosqlite
    conn = await aiosqlite.connect(settings.state_db_path)
    checkpointer = AsyncSqliteSaver(conn)
    return build_graph().compile(checkpointer=checkpointer)


def thread_id(repo_name: str, issue_number: int) -> str:
    """Stable identifier for a graph instance (one per issue per repo)."""
    return f"{repo_name}-{issue_number}"
