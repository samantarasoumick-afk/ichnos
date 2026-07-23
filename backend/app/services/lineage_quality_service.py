from sqlalchemy.orm import Session

from app.models.data_quality import DataQuality
from app.models.lineage import DatasetLineage


# How much a fully-documented (score 1.0) vs fully-undocumented (score 0.0)
# upstream edge can shift the inherited score, in either direction.
# At exactly 0.5 documentation completeness the adjustment is zero, so a
# "typically" documented edge neither helps nor hurts.
MAX_ADJUSTMENT = 5.0

# Minimum length (after stripping whitespace) for a free-text field to be
# considered "substantive" documentation rather than a token placeholder.
MIN_TEXT_LENGTH = 15


def documentation_completeness(edge: DatasetLineage) -> float:
    """Score how well a lineage edge documents its transformation, 0.0-1.0.

    Weighted: 40% transformation_type present, 30% transformation_description
    substantive, 30% filter_logic substantive. This is what lets a
    well-documented edge lift a downstream dataset's effective quality score
    above what a flat inheritance would give it.
    """

    score = 0.0

    if edge.transformation_type and edge.transformation_type.strip():
        score += 0.4

    if edge.transformation_description and len(edge.transformation_description.strip()) >= MIN_TEXT_LENGTH:
        score += 0.3

    if edge.filter_logic and len(edge.filter_logic.strip()) >= MIN_TEXT_LENGTH:
        score += 0.3

    return round(score, 2)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def compute_effective_quality(dataset_id: str, db: Session) -> dict:
    """Recursively compute a lineage-adjusted effective quality score.

    A dataset's own DataQuality.overall_score is its intrinsic score. If it
    has upstream lineage edges, each edge contributes the upstream dataset's
    own effective score, shifted by up to +/-5 points depending on how well
    that edge documents its transformation and filter logic (see
    documentation_completeness). Those contributions are averaged into an
    "inherited" score, which is then blended 50/50 with the dataset's own
    intrinsic score if it has one - or used directly if it doesn't (e.g. a
    downstream reporting table that has never been profiled itself).

    Example matching the product spec: a source with overall_score=50 and a
    fully-documented outgoing edge (doc_completeness=1.0, adjustment=+5)
    lifts an unprofiled downstream dataset to an effective score of 55.

    Cycle-safe via a visiting set, following the same DFS pattern as
    LineageService.upstream/downstream. Memoized per-call via a cache dict
    so diamond-shaped graphs aren't recomputed exponentially.
    """

    cache: dict = {}
    visiting: set = set()

    def resolve(current_id: str) -> dict:
        if current_id in cache:
            return cache[current_id]

        dq = db.query(DataQuality).filter(DataQuality.dataset_id == current_id).first()
        own_score = dq.overall_score if dq and dq.overall_score is not None else None

        if current_id in visiting:
            # Cycle detected - stop recursing on this path, fall back to
            # this dataset's own score (or None) with no further inheritance.
            return {
                "dataset_id": current_id,
                "own_score": own_score,
                "effective_score": own_score,
                "contributing_edges": [],
            }

        visiting.add(current_id)

        upstream_edges = (
            db.query(DatasetLineage)
            .filter(DatasetLineage.downstream_dataset_id == current_id)
            .all()
        )

        contributing_edges = []
        contribution_values = []

        for edge in upstream_edges:
            upstream_result = resolve(str(edge.upstream_dataset_id))
            upstream_effective = upstream_result["effective_score"]

            if upstream_effective is None:
                continue

            doc_completeness = documentation_completeness(edge)
            adjustment = round((doc_completeness - 0.5) * (2 * MAX_ADJUSTMENT), 2)
            contribution = round(_clamp(upstream_effective + adjustment), 2)

            contribution_values.append(contribution)
            contributing_edges.append({
                "edge_id": str(edge.id),
                "upstream_dataset_id": str(edge.upstream_dataset_id),
                "upstream_effective_score": round(upstream_effective, 2),
                "documentation_completeness": round(doc_completeness * 100),
                "adjustment": adjustment,
                "contribution": contribution,
            })

        visiting.discard(current_id)

        if not contribution_values:
            effective_score = own_score
        else:
            inherited = sum(contribution_values) / len(contribution_values)
            if own_score is None:
                effective_score = round(inherited, 2)
            else:
                effective_score = round((own_score + inherited) / 2, 2)

        result = {
            "dataset_id": current_id,
            "own_score": round(own_score, 2) if own_score is not None else None,
            "effective_score": effective_score,
            "contributing_edges": contributing_edges,
        }
        cache[current_id] = result
        return result

    return resolve(str(dataset_id))
