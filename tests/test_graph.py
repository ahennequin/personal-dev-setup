
from graph.state import SpecKitState


def make_state(**overrides) -> SpecKitState:
    base: SpecKitState = {
        "issue_number": 1,
        "repo_name": "test-repo",
        "repo_full_name": "ahennequin/test-repo",
        "type_label": "type: feature",
        "priority_label": "priority: normal",
        "issue_title": "Add authentication",
        "issue_body": "We need user login.",
        "spec_text": "",
        "branch_name": "",
        "pr_number": None,
        "review_comments": [],
        "status": "needs-spec",
        "agent_output": "",
        "rework_cycle": 0,
        "error": None,
    }
    return {**base, **overrides}


def test_state_construction():
    state = make_state()
    assert state["issue_number"] == 1
    assert state["rework_cycle"] == 0
    assert state["error"] is None


def test_route_after_implement_ok():
    from graph.edges import route_after_implement
    state = make_state(status="spec-approved")
    assert route_after_implement(state) == "await_review"


def test_route_after_implement_error():
    from graph.edges import route_after_implement
    state = make_state(status="spec-approved", error="something broke")
    assert route_after_implement(state) == "handle_error"


def test_route_after_spec_approval_approved():
    from graph.edges import route_after_spec_approval
    state = make_state(status="spec-approved")
    assert route_after_spec_approval(state) == "implement"


def test_route_after_spec_approval_waiting():
    from graph.edges import route_after_spec_approval
    state = make_state(status="spec-draft")
    assert route_after_spec_approval(state) == "await_spec_approval"


def test_route_after_spec_approval_re_spec():
    from graph.edges import route_after_spec_approval
    state = make_state(status="needs-spec")
    assert route_after_spec_approval(state) == "collect_spec"


def test_route_after_spec_approval_error():
    from graph.edges import route_after_spec_approval
    state = make_state(status="spec-draft", error="Something went wrong")
    assert route_after_spec_approval(state) == "handle_error"


def test_route_after_review_changes_requested():
    from graph.edges import route_after_review
    state = make_state(status="needs-rework")
    assert route_after_review(state) == "rework"


def test_route_after_review_approved():
    from graph.edges import route_after_review
    state = make_state(status="done")
    assert route_after_review(state) == "__end__"


def test_route_after_review_waiting():
    from graph.edges import route_after_review
    state = make_state(status="in-progress")
    assert route_after_review(state) == "await_review"


def test_route_entry_needs_spec():
    from graph.edges import route_entry
    state = make_state(status="needs-spec")
    assert route_entry(state) == "collect_spec"


def test_route_entry_spec_approved_with_spec():
    from graph.edges import route_entry
    state = make_state(status="spec-approved", spec_text="Some spec")
    assert route_entry(state) == "implement"


def test_route_entry_spec_draft_with_spec():
    from graph.edges import route_entry
    state = make_state(status="spec-draft", spec_text="Some spec")
    assert route_entry(state) == "await_spec_approval"


def test_route_entry_spec_draft_no_spec():
    from graph.edges import route_entry
    state = make_state(status="spec-draft", spec_text="")
    assert route_entry(state) == "collect_spec"
