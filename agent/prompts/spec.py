SPEC_PROMPT_TEMPLATE = """\
You are performing the spec collection phase of a software development task.

Read AGENTS.md and CLAUDE.md at the project root before doing anything else.
They define the project conventions, architecture, and constraints you must follow.

Issue type: {type_label}
Issue title: {issue_title}
Issue body:
---
{issue_body}
---

Your task depends on the issue type:

type: feature
  → Produce a full spec following Spec-Kit structure.
    Ask no clarifying questions unless the issue is genuinely ambiguous.
    Make reasonable assumptions and state them explicitly.

type: bug
  → Identify the likely root cause from the description.
    Spec the fix, including how to reproduce and verify resolution.

type: refactor
  → Define the scope precisely. List what must NOT change behaviorally.
    The spec must make the boundaries of change explicit.

type: chore
  → Summarize what needs to be done concisely. No full spec required.
    List the steps the implementer should follow.

Output format — use these exact sections, in this order:

## Summary
One paragraph. What this task achieves and why.

## Acceptance Criteria
Bulleted list. Each criterion is testable and unambiguous.
Leave empty only for type: chore.

## Technical Approach
How the implementation should proceed. Reference specific files,
functions, or patterns from the codebase where relevant.

## Open Questions
List only genuine blockers — things you cannot reasonably assume.
Leave empty if none.

Output only the spec document. No preamble, no explanation, no markdown fences.
"""


def build_spec_prompt(
    type_label: str,
    issue_title: str,
    issue_body: str,
) -> str:
    return SPEC_PROMPT_TEMPLATE.format(
        type_label=type_label,
        issue_title=issue_title,
        issue_body=issue_body or "(no description provided)",
    )
