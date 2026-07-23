"""
Records dataset detail-page views, deduplicated within a short window
so the count reflects genuine visits rather than every page refresh
or React effect re-run inflating the number.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.dataset_view import DatasetView


# Repeat views from the same person within this window don't count as
# a new visit - chosen loosely (long enough to absorb refreshes and
# React StrictMode double-effects, short enough that coming back
# later the same day still registers as real re-engagement).
DEDUP_WINDOW_MINUTES = 30


def record_view(db: Session, dataset: Dataset, user_id: str) -> None:

    cutoff = datetime.utcnow() - timedelta(minutes=DEDUP_WINDOW_MINUTES)

    recent_view = (
        db.query(DatasetView)
        .filter(
            DatasetView.dataset_id == dataset.id,
            DatasetView.user_id == user_id,
            DatasetView.viewed_at >= cutoff,
        )
        .first()
    )

    if recent_view is not None:
        return

    db.add(
        DatasetView(
            dataset_id=dataset.id,
            user_id=user_id,
        )
    )

    db.commit()
