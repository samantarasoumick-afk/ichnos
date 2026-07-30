"""
Makes the Ecosystem View's "10 days instead of 3 months" onboarding
claim measurable rather than asserted: a fixed, ordered set of real
actions a new analyst takes while actually using the map (seeing the
whole estate, exploring each tier, tracing a report's provenance,
using semantic search), each recorded at most once per user the first
time it happens.

Milestone keys are deliberately plain strings (not a DB enum) so a new
one can be added without a migration - same free-text-key convention
DatasetLineage.transformation_type already uses in this codebase.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.onboarding import OnboardingMilestoneEvent
from app.models.user import User


class UnknownMilestoneError(Exception):
    pass


# Ordered the way an onboarding analyst would actually encounter them
# using the Ecosystem View - not alphabetical - so a progress list
# reads as a natural sequence rather than a shuffled set of facts.
MILESTONES: list[dict] = [
    {
        "key": "VIEWED_ECOSYSTEM_MAP",
        "label": "Saw the whole data estate on one map",
    },
    {
        "key": "EXPLORED_FRONT_OFFICE",
        "label": "Explored a front-office system (where data originates)",
    },
    {
        "key": "EXPLORED_MIDDLE_OFFICE",
        "label": "Explored a middle-office processing hop",
    },
    {
        "key": "EXPLORED_BACK_OFFICE",
        "label": "Explored a back-office report",
    },
    {
        "key": "TRACED_PROVENANCE",
        "label": "Traced a dataset's lineage hop by hop",
    },
    {
        "key": "USED_SEMANTIC_SEARCH",
        "label": "Used semantic search to jump straight to a dataset",
    },
]

MILESTONE_KEYS = {m["key"] for m in MILESTONES}


def record_milestone(db: Session, user: User, milestone_key: str) -> None:
    """
    Idempotent: the unique (user_id, milestone_key) constraint means
    hitting an already-recorded milestone again is a harmless no-op,
    not a duplicate row - callers don't need to check first.
    """

    if milestone_key not in MILESTONE_KEYS:
        raise UnknownMilestoneError(f"Unknown onboarding milestone: {milestone_key}")

    existing = (
        db.query(OnboardingMilestoneEvent)
        .filter(
            OnboardingMilestoneEvent.user_id == user.id,
            OnboardingMilestoneEvent.milestone_key == milestone_key,
        )
        .first()
    )
    if existing is not None:
        return

    db.add(OnboardingMilestoneEvent(
        organization_id=user.organization_id,
        user_id=user.id,
        milestone_key=milestone_key,
        achieved_at=datetime.utcnow(),
    ))
    db.commit()


def get_progress(db: Session, user: User) -> dict:
    """
    Returns each milestone's completion state plus a headline: once
    every milestone is hit, the number of calendar days between the
    first and the last is the literal, measured ramp-up time for this
    person - the thing the "10 days" claim can actually point to
    instead of just asserting.
    """

    events = (
        db.query(OnboardingMilestoneEvent)
        .filter(OnboardingMilestoneEvent.user_id == user.id)
        .all()
    )
    achieved_at_by_key = {e.milestone_key: e.achieved_at for e in events}

    milestones = [
        {
            "key": m["key"],
            "label": m["label"],
            "completed": m["key"] in achieved_at_by_key,
            "achieved_at": achieved_at_by_key.get(m["key"]),
        }
        for m in MILESTONES
    ]

    completed_count = sum(1 for m in milestones if m["completed"])
    total_count = len(milestones)
    percent_complete = round((completed_count / total_count) * 100) if total_count else 0

    ramp_days = None
    if completed_count == total_count and events:
        timestamps = [e.achieved_at for e in events]
        ramp_days = (max(timestamps).date() - min(timestamps).date()).days + 1

    return {
        "milestones": milestones,
        "completed_count": completed_count,
        "total_count": total_count,
        "percent_complete": percent_complete,
        "ramp_days": ramp_days,
    }
