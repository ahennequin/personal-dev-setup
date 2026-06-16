import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config.settings import settings
from graph.state import SpecKitState
from graph.edges import route_after_spec_approval, route_after_review
from graph.nodes.collect_spec import collect_spec
from graph.nodes.implement import implement
from graph.nodes.rework import rework
from graph.nodes.handle_error import handle_error

logger = logging.getLogger(__name__)


def _checkpoint_node(name: str):
    """
    A checkpoint node suspends the graph and persists state.
    It does nothing itself — the next webhook resumes from here.
    """
    async def node(state: SpecKitState) -> dict:
        logger.info(f"[checkpoint:{name}] Suspended. Waiting for next event.")
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
    workflow.add_edge("implement", "await_review")
    workflow.add_edge("rework", "await_review")

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

    # Error always terminates (handle_error is a dead end — human re-triggers)
    workflow.add_edge("handle_error", END)

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
