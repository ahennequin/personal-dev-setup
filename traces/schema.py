from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TraceEvent:
    # Identity
    issue_number: int
    repo_name: str
    type_label: str

    # What happened
    event_type: str             # spec_generated | spec_approved | spec_edited |
                                # implementation_started | pr_opened |
                                # review_requested_changes | review_approved |
                                # rework_completed | merged | error

    # Agent interaction
    agent_prompt: str           # exact prompt sent to OpenCode
    agent_output: str           # exact output received

    # Human interaction
    human_action: Optional[str] = None     # approved | edited | commented | merged
    human_content: Optional[str] = None    # the edit diff, comment text, etc.

    # Quality signals
    rework_cycle: int = 0               # 0 = first attempt
    spec_was_edited: bool = False       # did human edit the spec before approving?
    outcome: Optional[str] = None       # success | abandoned (filled on close)

    # Scores (filled by scorer.py after merge)
    spec_quality_score: Optional[float] = None    # 1.0 = approved as-is
    impl_quality_score: Optional[float] = None    # 1 / (rework_cycles + 1)
    overall_score: Optional[float] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None            # set after DB insert
