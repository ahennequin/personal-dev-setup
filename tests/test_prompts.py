from agent.prompts.spec import build_spec_prompt
from agent.prompts.implement import build_implement_prompt
from agent.prompts.rework import build_rework_prompt


def test_spec_prompt_contains_type_label():
    prompt = build_spec_prompt(
        type_label="type: feature",
        issue_title="Add login",
        issue_body="Users need to log in.",
    )
    assert "type: feature" in prompt
    assert "Add login" in prompt
    assert "Users need to log in." in prompt
    assert "## Summary" in prompt
    assert "## Acceptance Criteria" in prompt


def test_spec_prompt_handles_empty_body():
    prompt = build_spec_prompt(
        type_label="type: bug",
        issue_title="App crashes on startup",
        issue_body="",
    )
    assert "no description provided" in prompt


def test_implement_prompt_contains_issue_number():
    prompt = build_implement_prompt(
        type_label="type: feature",
        issue_title="Add login",
        issue_number=42,
        branch_name="feat/issue-42-add-login",
        spec_text="## Summary\nUsers need login.",
    )
    assert "#42" in prompt
    assert "feat/issue-42-add-login" in prompt
    assert "## Summary" in prompt


def test_rework_prompt_formats_comments():
    comments = [
        {
            "path": "src/auth.py",
            "line": 12,
            "diff_hunk": "@@ -10,6 +10,7 @@",
            "body": "This doesn't handle None",
        }
    ]
    prompt = build_rework_prompt(
        issue_number=42,
        issue_title="Add login",
        branch_name="feat/issue-42-add-login",
        rework_cycle=1,
        review_comments=comments,
    )
    assert "src/auth.py" in prompt
    assert "This doesn't handle None" in prompt
    assert "cycle 1" in prompt


def test_rework_prompt_empty_comments():
    prompt = build_rework_prompt(
        issue_number=1,
        issue_title="Test",
        branch_name="feat/issue-1-test",
        rework_cycle=0,
        review_comments=[],
    )
    assert "no comments found" in prompt
