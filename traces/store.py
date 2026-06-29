import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config.settings import settings
from traces.schema import TraceEvent

logger = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS traces (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,
    issue_number        INTEGER NOT NULL,
    repo_name           TEXT NOT NULL,
    type_label          TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    agent_prompt        TEXT NOT NULL,
    agent_output        TEXT NOT NULL,
    human_action        TEXT,
    human_content       TEXT,
    rework_cycle        INTEGER DEFAULT 0,
    spec_was_edited     INTEGER DEFAULT 0,
    outcome             TEXT,
    spec_quality_score  REAL,
    impl_quality_score  REAL,
    overall_score       REAL
);
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_traces_issue
ON traces (repo_name, issue_number);
"""


@contextmanager
def _conn():
    path = settings.traces_db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(CREATE_TABLE)
        conn.execute(CREATE_INDEX)
        conn.commit()
        yield conn
    finally:
        conn.close()


def save_event(event: TraceEvent) -> int:
    with _conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO traces (
                timestamp, issue_number, repo_name, type_label,
                event_type, agent_prompt, agent_output,
                human_action, human_content, rework_cycle,
                spec_was_edited, outcome,
                spec_quality_score, impl_quality_score, overall_score
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                event.timestamp.isoformat(),
                event.issue_number,
                event.repo_name,
                event.type_label,
                event.event_type,
                event.agent_prompt,
                event.agent_output,
                event.human_action,
                event.human_content,
                event.rework_cycle,
                int(event.spec_was_edited),
                event.outcome,
                event.spec_quality_score,
                event.impl_quality_score,
                event.overall_score,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_events_for_issue(repo_name: str, issue_number: int) -> list[TraceEvent]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM traces WHERE repo_name = ? AND issue_number = ? ORDER BY id",
            (repo_name, issue_number),
        ).fetchall()
    return [_row_to_event(r) for r in rows]


def update_scores(
    trace_id: int,
    spec_quality_score: float,
    impl_quality_score: float,
    overall_score: float,
    outcome: str,
) -> None:
    with _conn() as conn:
        conn.execute(
            """
            UPDATE traces SET
                spec_quality_score = ?,
                impl_quality_score = ?,
                overall_score = ?,
                outcome = ?
            WHERE id = ?
            """,
            (spec_quality_score, impl_quality_score, overall_score, outcome, trace_id),
        )
        conn.commit()


def _row_to_event(row: sqlite3.Row) -> TraceEvent:
    from datetime import datetime
    return TraceEvent(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        issue_number=row["issue_number"],
        repo_name=row["repo_name"],
        type_label=row["type_label"],
        event_type=row["event_type"],
        agent_prompt=row["agent_prompt"],
        agent_output=row["agent_output"],
        human_action=row["human_action"],
        human_content=row["human_content"],
        rework_cycle=row["rework_cycle"],
        spec_was_edited=bool(row["spec_was_edited"]),
        outcome=row["outcome"],
        spec_quality_score=row["spec_quality_score"],
        impl_quality_score=row["impl_quality_score"],
        overall_score=row["overall_score"],
    )
