REWORK_PROMPT_TEMPLATE = """\
You are addressing code review feedback on a pull request.

Read AGENTS.md and CLAUDE.md at the project root before making any changes.

Issue: #{issue_number} — {issue_title}
Branch: {branch_name}
Rework cycle: {rework_cycle}

The following review comments require changes.
Each entry includes the file, line, surrounding diff context, and the reviewer's comment.

---
{formatted_comments}
---

Instructions:
  1. Address every comment listed above
  2. Do not change code unrelated to the review comments
  3. Run all tests after making changes — they must pass
  4. If a comment is ambiguous, make your best interpretation
     and document it in the commit message
  5. Commit with: fix: address review comments on #{issue_number} (cycle {rework_cycle})
  6. Do not force-push — regular push only

Output a brief summary: what you changed per comment.
"""


def build_rework_prompt(
    issue_number: int,
    issue_title: str,
    branch_name: str,
    rework_cycle: int,
    review_comments: list[dict],
) -> str:
    formatted = _format_review_comments(review_comments)
    return REWORK_PROMPT_TEMPLATE.format(
        issue_number=issue_number,
        issue_title=issue_title,
        branch_name=branch_name,
        rework_cycle=rework_cycle,
        formatted_comments=formatted,
    )


def _format_review_comments(comments: list[dict]) -> str:
    if not comments:
        return "(no comments found)"

    blocks = []
    for c in comments:
        blocks.append(
            f"File: {c.get('path', 'unknown')}, line {c.get('line', '?')}\n"
            f"Diff context:\n{c.get('diff_hunk', '')}\n"
            f"Comment: {c.get('body', '')}"
        )
    return "\n---\n".join(blocks)
