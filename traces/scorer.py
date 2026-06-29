import logging

from traces.store import get_events_for_issue, update_scores

logger = logging.getLogger(__name__)


def score_issue(repo_name: str, issue_number: int, outcome: str = "success") -> None:
    """
    Compute quality scores for all trace events of a completed issue.
    Called when a PR is merged or an issue is closed.

    Scores:
      spec_quality_score: 1.0 if spec approved without edits, 0.5 if edited
      impl_quality_score: 1 / (max_rework_cycle + 1)
      overall_score:      weighted average (60% impl, 40% spec)
    """
    events = get_events_for_issue(repo_name, issue_number)
    if not events:
        logger.warning(f"No trace events found for {repo_name}#{issue_number}")
        return

    spec_was_edited = any(e.spec_was_edited for e in events)
    spec_quality_score = 0.5 if spec_was_edited else 1.0

    max_rework = max((e.rework_cycle for e in events), default=0)
    impl_quality_score = round(1 / (max_rework + 1), 3)

    overall_score = round(
        0.4 * spec_quality_score + 0.6 * impl_quality_score, 3
    )

    logger.info(
        f"Scores for {repo_name}#{issue_number}: "
        f"spec={spec_quality_score} impl={impl_quality_score} overall={overall_score}"
    )

    for event in events:
        if event.id is not None:
            update_scores(
                trace_id=event.id,
                spec_quality_score=spec_quality_score,
                impl_quality_score=impl_quality_score,
                overall_score=overall_score,
                outcome=outcome,
            )
