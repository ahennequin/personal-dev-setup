from typing import Optional
from typing_extensions import TypedDict


class ReviewComment(TypedDict):
    path: str
    line: Optional[int]
    body: str
    diff_hunk: str


class SpecKitState(TypedDict):
    # Identity
    issue_number: int
    repo_name: str
    repo_full_name: str         # e.g. ahennequin/epf-doc-autofilling

    # Classification
    type_label: str             # type: feature | bug | refactor | chore
    priority_label: str         # priority: critical | high | normal | backlog

    # Content
    issue_title: str
    issue_body: str
    spec_text: str
    branch_name: str
    pr_number: Optional[int]
    review_comments: list[ReviewComment]

    # Execution
    status: str                 # mirrors GitHub label: needs-spec | spec-draft |
                                # spec-approved | in-progress | needs-rework |
                                # rework-in-progress | done
    agent_output: str           # raw OpenCode stdout
    rework_cycle: int           # 0 = first attempt, increments per rework
    error: Optional[str]        # set if a node fails
