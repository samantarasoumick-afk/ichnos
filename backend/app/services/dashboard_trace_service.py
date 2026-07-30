"""
Powers "trace this dashboard" - the provenance explainer for the
Ecosystem View. Given any dataset (typically a back-office report, but
it works from any node), walks the real lineage graph hop by hop in
one direction and produces:

  1. A structured, leveled trace (always available, no external
     dependency) - depth 0 is the dataset itself, depth 1 its
     immediate neighbors in the requested direction, depth 2 the next
     hop out, and so on - each dataset annotated with the same
     governance/quality/PII/contract facts the Ecosystem View shows,
     plus the edges connecting each level with their transformation
     type/description.
  2. A plain-English narrative walking that structure end to end -
     "where did this report's numbers actually come from, and were
     there any data quality or governance concerns along the way."

The narrative generation follows the exact fallback convention already
established in assistant_service.py: a deterministic template built
straight from the structured trace always works with zero
configuration; when ANTHROPIC_API_KEY is set, the same structured
trace is handed to a real LLM call (via assistant_service's
_call_anthropic_api, reused rather than duplicated) to turn into a
more natural, context-aware explanation, strictly grounded in the
trace data so it can't invent systems or numbers that aren't there.
Any failure (missing key, network, bad response) falls straight back
to the template - never raises, never returns nothing.
"""

import os

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.lineage import DatasetLineage
from app.models.source import DataSource

from app.services.assistant_service import _call_anthropic_api
from app.services.ecosystem_service import dataset_tier

DIRECTION_UPSTREAM = "upstream"
DIRECTION_DOWNSTREAM = "downstream"

MAX_DEPTH = 25  # generous hop cap - guards against a pathological/cyclic graph, not a realistic one


class DatasetNotFoundError(Exception):
    pass


def _dataset_summary(dataset: Dataset, source: DataSource | None, tier: str) -> dict:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "schema_name": dataset.schema_name,
        "source_id": dataset.source_id,
        "source_name": source.name if source else "Unknown system",
        "source_type": source.type if source else None,
        "tier": tier,
        "owner": dataset.owner,
        "governance_status": dataset.governance_status,
        "quality_score": dataset.quality_score,
        "pii_columns": dataset.pii_columns,
        "sensitivity_score": dataset.sensitivity_score,
        "contract_status": dataset.contract_status,
        "freshness_status": dataset.freshness_status,
    }


def _label(summary: dict) -> str:
    return f"{summary['schema_name']}.{summary['name']}"


def build_trace(db: Session, organization_id: str, dataset_id: str, direction: str = DIRECTION_UPSTREAM) -> dict:
    """
    Returns the structured, leveled trace described above for one
    dataset, scoped to its own organization. Raises
    DatasetNotFoundError if the dataset doesn't exist or belongs to a
    different org - callers translate that to a 404.
    """

    target = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.organization_id == organization_id)
        .first()
    )
    if target is None:
        raise DatasetNotFoundError(f"Dataset {dataset_id} not found in this organization")

    all_datasets = db.query(Dataset).filter(Dataset.organization_id == organization_id).all()
    dataset_by_id = {d.id: d for d in all_datasets}

    all_edges = (
        db.query(DatasetLineage)
        .join(Dataset, Dataset.id == DatasetLineage.upstream_dataset_id)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    sources = db.query(DataSource).filter(DataSource.organization_id == organization_id).all()
    source_by_id = {s.id: s for s in sources}

    has_upstream = {e.downstream_dataset_id for e in all_edges}
    has_downstream = {e.upstream_dataset_id for e in all_edges}

    # direction=upstream: walk from downstream_dataset_id back to
    # upstream_dataset_id (where did this come from).
    # direction=downstream: walk from upstream_dataset_id forward to
    # downstream_dataset_id (what does this feed).
    neighbors_by_dataset: dict[str, list[DatasetLineage]] = {}
    for edge in all_edges:
        anchor = edge.downstream_dataset_id if direction == DIRECTION_UPSTREAM else edge.upstream_dataset_id
        neighbors_by_dataset.setdefault(anchor, []).append(edge)

    def _other_side(edge: DatasetLineage) -> str:
        return edge.upstream_dataset_id if direction == DIRECTION_UPSTREAM else edge.downstream_dataset_id

    visited = {dataset_id}
    levels: list[dict] = [{
        "depth": 0,
        "datasets": [_dataset_summary(target, source_by_id.get(target.source_id), dataset_tier(target.id, has_upstream, has_downstream))],
    }]
    trace_edges: list[dict] = []

    frontier = [dataset_id]
    depth = 0

    while frontier and depth < MAX_DEPTH:
        depth += 1
        next_frontier: list[str] = []
        next_level_datasets: list[dict] = []

        for current_id in frontier:
            for edge in neighbors_by_dataset.get(current_id, []):
                other_id = _other_side(edge)
                other_dataset = dataset_by_id.get(other_id)
                if other_dataset is None:
                    continue

                trace_edges.append({
                    "id": edge.id,
                    "upstream_dataset_id": edge.upstream_dataset_id,
                    "downstream_dataset_id": edge.downstream_dataset_id,
                    "transformation_type": edge.transformation_type,
                    "transformation_description": edge.transformation_description,
                })

                if other_id in visited:
                    continue
                visited.add(other_id)
                next_frontier.append(other_id)
                next_level_datasets.append(
                    _dataset_summary(
                        other_dataset,
                        source_by_id.get(other_dataset.source_id),
                        dataset_tier(other_dataset.id, has_upstream, has_downstream),
                    )
                )

        if next_level_datasets:
            levels.append({"depth": depth, "datasets": next_level_datasets})
        frontier = next_frontier

    narrative, narrative_source = _build_narrative(levels, trace_edges, direction, _label(levels[0]["datasets"][0]))

    return {
        "dataset_id": dataset_id,
        "direction": direction,
        "levels": levels,
        "edges": trace_edges,
        "narrative": narrative,
        "narrative_source": narrative_source,
    }


def _flag_notes(summary: dict) -> list[str]:
    """Plain-English call-outs for anything worth a new analyst's
    attention at this hop - used by both the template and as
    structured grounding fed to the LLM."""

    notes = []
    if summary["governance_status"] == "CRITICAL":
        notes.append(f"{_label(summary)} has a CRITICAL governance status")
    elif summary["governance_status"] == "REVIEW_REQUIRED":
        notes.append(f"{_label(summary)} is flagged REVIEW_REQUIRED")
    if summary["pii_columns"]:
        notes.append(f"{_label(summary)} carries {summary['pii_columns']} PII column(s)")
    if summary["contract_status"] == "BREACHED":
        notes.append(f"{_label(summary)}'s data contract is currently BREACHED")
    if summary["quality_score"] is not None and summary["quality_score"] < 60:
        notes.append(f"{_label(summary)} has a low data quality score ({summary['quality_score']}/100)")
    if summary["freshness_status"] == "STALE":
        notes.append(f"{_label(summary)} hasn't been rescanned recently (STALE)")
    return notes


def _edge_description(edge: dict) -> str:
    if edge.get("transformation_description"):
        return edge["transformation_description"]
    return edge.get("transformation_type") or "an undocumented transformation"


def _build_template_narrative(levels: list[dict], edges: list[dict], direction: str, target_label: str) -> str:

    if len(levels) == 1:
        verb = "coming from" if direction == DIRECTION_UPSTREAM else "feeding"
        return f"{target_label} has no recorded {'upstream' if direction == DIRECTION_UPSTREAM else 'downstream'} lineage yet - nothing is currently documented as {verb} it."

    edge_by_pair = {}
    for edge in edges:
        edge_by_pair[(edge["upstream_dataset_id"], edge["downstream_dataset_id"])] = edge

    lines = []
    verb_phrase = "traces back through" if direction == DIRECTION_UPSTREAM else "flows forward through"
    lines.append(f"{target_label} {verb_phrase} {len(levels) - 1} hop(s) of recorded lineage:")

    all_notes: list[str] = []

    for level in levels[1:]:
        depth = level["depth"]
        hop_label = "Immediate" if depth == 1 else f"Hop {depth}"
        for summary in level["datasets"]:
            all_notes.extend(_flag_notes(summary))
            source_bit = f" in {summary['source_name']}" if summary["source_name"] else ""
            lines.append(
                f"- {hop_label} {'upstream' if direction == DIRECTION_UPSTREAM else 'downstream'}: "
                f"{_label(summary)}{source_bit} ({summary['tier'].replace('_', ' ').lower()})"
            )

    lines.append("")
    if all_notes:
        lines.append("Worth knowing before you rely on this: " + "; ".join(all_notes) + ".")
    else:
        lines.append("No data quality, governance, or contract issues detected anywhere along this chain.")

    return "\n".join(lines)


def _build_narrative(levels: list[dict], edges: list[dict], direction: str, target_label: str) -> tuple[str, str]:

    template = _build_template_narrative(levels, edges, direction, target_label)

    if not os.getenv("ANTHROPIC_API_KEY") or len(levels) == 1:
        return template, "template"

    context_lines = [f"Tracing {target_label} in the {direction} direction."]
    for level in levels:
        for summary in level["datasets"]:
            context_lines.append(
                f"Depth {level['depth']}: {_label(summary)} | system={summary['source_name']} "
                f"({summary['source_type']}) | tier={summary['tier']} | governance={summary['governance_status']} "
                f"| quality={summary['quality_score']}/100 | pii_columns={summary['pii_columns']} "
                f"| contract={summary['contract_status']} | freshness={summary['freshness_status']}"
            )
    for edge in edges:
        context_lines.append(
            f"Edge: {edge['upstream_dataset_id']} -> {edge['downstream_dataset_id']} via {_edge_description(edge)}"
        )

    system_prompt = (
        "You are the embedded assistant inside DataFe, a data catalog and governance platform, "
        "helping a newly onboarded analyst understand where a report or dataset's data actually "
        "comes from (or where it flows to). Using ONLY the structured trace data below, write a "
        "short, plain-English walkthrough, hop by hop, from " + ("origin to this dataset" if direction == DIRECTION_UPSTREAM else "this dataset to where it ends up") + ". "
        "Explicitly call out any governance, data quality, PII, or contract concerns you see in the "
        "data. Never invent a system, dataset, or number that isn't present in the trace data. Keep "
        "it under 200 words.\n\n" + "\n".join(context_lines)
    )

    answer = _call_anthropic_api(system_prompt, [{"role": "user", "content": "Explain this trace."}])
    if answer is None:
        return template, "template"

    return answer, "llm"
