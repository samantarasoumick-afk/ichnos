"""
Records every question asked on the Ask page and every query typed
into the global search bar, then aggregates them into an admin-facing
report of what's being asked most and, more usefully, what's *not*
landing - the questions people ask that the assistant or search comes
up empty on. The idea (per the user's original framing) is that
patterns in that gap list are exactly what's worth promoting into a
built-in intent, a glossary term, or an FAQ entry, instead of staying
invisible.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.query_log import QueryLog


# The assistant's few fixed "I don't have enough to go on" messages
# (see app/services/assistant_service.py) - kept here rather than
# embedded in that already heavily-tested module, so a confidence
# signal can be derived from the answer text without touching it.
# Doesn't (and can't cheaply) catch an LLM-backed answer that hedges
# in its own words - this is a coarse signal, not a correctness grade.
_ASK_UNANSWERED_MARKERS = (
    "There's nothing in your catalog yet",
    "I can answer ownership questions once you name a specific dataset",
    "I can answer lineage questions once you name a specific dataset",
    "I couldn't find anything in your catalog that matches this question",
)


def classify_ask_answer(answer_text: str) -> bool:
    """True if the assistant gave something more than one of its fixed
    give-up messages - used as the `matched` value when logging an Ask
    query."""

    if not answer_text:
        return False

    return not any(answer_text.startswith(marker) for marker in _ASK_UNANSWERED_MARKERS)


def log_query_event(
    db: Session,
    organization_id: str,
    source: str,
    query_text: str,
    matched: bool,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    result_count: int | None = None,
) -> None:
    """Records one query. Commits immediately (same convention as
    dataset_view_service.record_view) since this is a side effect of a
    read-only request with no other pending writes to share a
    transaction with."""

    trimmed = query_text.strip()
    if not trimmed:
        return

    db.add(
        QueryLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            source=source,
            query_text=trimmed,
            matched=matched,
            result_count=result_count,
        )
    )
    db.commit()


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _group_and_rank(rows: list[QueryLog], limit: int) -> list[dict]:
    groups: dict[str, dict] = {}

    for row in rows:
        key = _normalize(row.query_text)
        if not key:
            continue

        group = groups.setdefault(
            key,
            {
                "query_text": row.query_text,
                "count": 0,
                "sources": set(),
                "last_asked_at": row.created_at,
            },
        )
        group["count"] += 1
        group["sources"].add(row.source)
        if row.created_at > group["last_asked_at"]:
            group["last_asked_at"] = row.created_at
            # Prefer the most recently-asked casing/phrasing for display.
            group["query_text"] = row.query_text

    ranked = sorted(
        groups.values(),
        key=lambda g: (-g["count"], -g["last_asked_at"].timestamp()),
    )

    for group in ranked:
        group["sources"] = sorted(group["sources"])

    return ranked[:limit]


def build_query_log_report(
    db: Session,
    organization_id: str,
    days: int = 30,
    limit: int = 20,
) -> dict:

    cutoff = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(QueryLog)
        .filter(
            QueryLog.organization_id == organization_id,
            QueryLog.created_at >= cutoff,
        )
        .all()
    )

    total_queries = len(rows)
    unanswered_rows = [row for row in rows if not row.matched]
    unanswered_count = len(unanswered_rows)
    unanswered_rate = (
        round((unanswered_count / total_queries) * 100, 1) if total_queries else 0.0
    )

    return {
        "window_days": days,
        "total_queries": total_queries,
        "unanswered_count": unanswered_count,
        "unanswered_rate": unanswered_rate,
        "top_unanswered": _group_and_rank(unanswered_rows, limit),
        "top_overall": _group_and_rank(rows, limit),
    }
