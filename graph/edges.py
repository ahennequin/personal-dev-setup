from graph.state import SpecKitState


def route_entry(state: SpecKitState) -> str:
    """Route at graph entry: skip collect_spec if spec_text is already provided."""
    if state.get("status") == "spec-approved" and state.get("spec_text"):
        return "implement"
    if state.get("status") == "spec-draft" and state.get("spec_text"):
        return "await_spec_approval"
    return "collect_spec"


def route_after_implement(state: SpecKitState) -> str:
    """Route after implement node completes."""
    if state["error"]:
        return "handle_error"
    return "await_review"


def route_after_spec_approval(state: SpecKitState) -> str:
    """Route from await_spec_approval checkpoint."""
    if state["error"]:
        return "handle_error"
    if state["status"] == "spec-approved":
        return "implement"
    if state["status"] == "needs-spec":
        return "collect_spec"
    return "await_spec_approval"   # still waiting


def route_after_review(state: SpecKitState) -> str:
    """Route from await_review checkpoint."""
    if state["error"]:
        return "handle_error"
    if state["status"] == "needs-rework":
        return "rework"
    if state["status"] == "done":
        return "__end__"
    return "await_review"           # still waiting
