IMPLEMENT_PROMPT_TEMPLATE = """\
You are implementing a software task. Follow these instructions precisely.

Read AGENTS.md and CLAUDE.md at the project root before writing any code.
They define mandatory conventions, architecture decisions, and constraints.

Issue type: {type_label}
Issue title: {issue_title}
Issue number: #{issue_number}
Branch: {branch_name} (already checked out — do not create it)

Approved spec:
---
{spec_text}
---

Instructions by issue type:

type: feature
  1. Write failing tests first (TDD — red before green)
  2. Implement until all tests pass
  3. Follow acceptance criteria from the spec strictly
  4. Do not implement anything not in the spec

type: bug
  1. Write a failing test that reproduces the bug first
  2. Fix the bug with the minimal necessary change
  3. Confirm the test passes
  4. Do not refactor unrelated code

type: refactor
  1. Run existing tests before touching anything — confirm they pass
  2. Make structural changes only — no behavior change
  3. Run tests after each significant change
  4. If a test breaks, stop and explain before continuing

type: chore
  1. Execute what the spec describes
  2. Keep changes minimal and focused
  3. No tests required unless the spec says otherwise

Commit conventions:
  - Use conventional commits: feat|fix|refactor|chore: description (#issue_number)
  - Commit in logical increments — do not bundle unrelated changes
  - All tests must pass before committing

When done:
  - All tests must pass
  - Do not open the PR — automation handles that
  - Output a brief summary: what you implemented, what tests cover it
"""


def build_implement_prompt(
    type_label: str,
    issue_title: str,
    issue_number: int,
    branch_name: str,
    spec_text: str,
) -> str:
    return IMPLEMENT_PROMPT_TEMPLATE.format(
        type_label=type_label,
        issue_title=issue_title,
        issue_number=issue_number,
        branch_name=branch_name,
        spec_text=spec_text,
    )
