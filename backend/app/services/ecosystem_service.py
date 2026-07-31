"""
Powers the Ecosystem View - a capability that shows an organization's
entire data estate as one map: front office (where data originates)
through middle office (processing/modeling) to back office
(reporting), and lets someone trace a number on a report all the way
back to the system it came from, or trace a raw table all the way
forward to every report it feeds - in both directions, from either
end.

The three tiers are deliberately computed from the real lineage graph's
topology rather than tagged by hand or inferred from source type:

  FRONT_OFFICE  - nothing upstream of it (an origin: nothing feeds it)
  BACK_OFFICE   - has upstream, nothing downstream (a terminus: a
                  report or final output nothing else consumes)
  MIDDLE_OFFICE - has both upstream and downstream (a processing hop)
  STANDALONE    - no lineage edges at all yet (nothing to place)

This means the tiering is a live consequence of whatever lineage
actually exists for this organization, not a static label - connect a
new downstream report to something and it stops being "back office"
automatically. That's the "graph capability" this view is meant to
show off: the tiers, the whole map, and the trace direction are all
derived by walking the DatasetLineage graph, not read off a stored
field.

Sources are the top-level nodes in the map (so "Salesforce CRM has 3
datasets, 30 columns" reads the way an onboarding analyst would expect
to see it) with their constituent datasets rolled up into aggregate
counts; the frontend can drill into a source to see its individual
datasets, each with the same rich detail (DQ, PII, classification,
policies, lineage, contract status) already computed on the Dataset
model and exposed via DatasetResponse.

Beyond the lineage-derived front/middle/back-office layer, the map
also surfaces the governance layer that cuts across it - business
processes and glossary terms are both many-to-many linked to
datasets (BusinessProcessLink / GlossaryTermLink), so they're returned
as their own node lists plus the edges connecting them to whichever
datasets they touch, the same shape as the lineage edges. Contracts
are deliberately NOT a third linked-node type - a contract belongs to
exactly one dataset, so it's just a fact about that dataset (already
in dataset_nodes as contract_status) rather than a separate thing
with its own connections; the full contracts list is still returned
so the frontend can show version/owner/breach detail without a
second API round-trip.
"""

from sqlalchemy.orm import Session

from app.models.business_process import BusinessProcess
from app.models.business_process import BusinessProcessLink
from app.models.data_contract import DataContract
from app.models.dataset import Dataset
from app.models.glossary_link import GlossaryTermLink
from app.models.governance import BusinessGlossaryTerm
from app.models.lineage import DatasetLineage
from app.models.source import DataSource


TIER_FRONT_OFFICE = "FRONT_OFFICE"
TIER_MIDDLE_OFFICE = "MIDDLE_OFFICE"
TIER_BACK_OFFICE = "BACK_OFFICE"
TIER_STANDALONE = "STANDALONE"

# Worse-to-better ordering so a source's "worst" governance status
# across its datasets is a simple min() by index rather than a
# separate lookup table.
_GOVERNANCE_SEVERITY = ["CRITICAL", "REVIEW_REQUIRED", "HEALTHY"]


def dataset_tier(dataset_id: str, has_upstream: set, has_downstream: set) -> str:
    upstream = dataset_id in has_upstream
    downstream = dataset_id in has_downstream

    if upstream and downstream:
        return TIER_MIDDLE_OFFICE
    if downstream and not upstream:
        return TIER_FRONT_OFFICE
    if upstream and not downstream:
        return TIER_BACK_OFFICE
    return TIER_STANDALONE


def compute_source_rollup(source_datasets: list[Dataset]) -> dict:
    """
    Aggregate counts for everything under one source: how many
    datasets it has, how many columns total, how many of those carry
    PII, and the single worst governance status among its datasets.
    Extracted so this isn't computed one way here (for the Ecosystem
    View's source nodes) and a slightly different way anywhere else
    that needs "how big/risky is this system" - currently also used by
    catalog_search_service.py's source search-result documents, so a
    source shows the same numbers whether you found it by browsing the
    map or by searching for it.
    """

    governance_statuses = [d.governance_status for d in source_datasets]
    worst_governance = None
    for level in _GOVERNANCE_SEVERITY:
        if level in governance_statuses:
            worst_governance = level
            break

    return {
        "dataset_count": len(source_datasets),
        "total_columns": sum(d.total_columns for d in source_datasets),
        "pii_columns": sum(d.pii_columns for d in source_datasets),
        "worst_governance_status": worst_governance,
    }


def _source_tier(dataset_tiers: list[str]) -> str:
    """
    A source's tier is the tier its datasets actually sit at. Most
    real sources are uniform (a CRM's tables are all front office, a
    dbt project's models are all middle office) - "MIXED" only shows
    up if a single connected source genuinely spans more than one tier
    (e.g. a warehouse that both ingests raw exports and also serves as
    the final reporting layer), which is worth surfacing rather than
    hiding behind a single arbitrary label.
    """

    non_standalone = [t for t in dataset_tiers if t != TIER_STANDALONE]
    distinct = set(non_standalone)

    if not distinct:
        return TIER_STANDALONE
    if len(distinct) == 1:
        return next(iter(distinct))
    return "MIXED"


def build_ecosystem_graph(db: Session, organization_id: str) -> dict:
    """
    Returns {"sources": [...], "datasets": [...], "edges": [...]} for
    one organization - the full payload the Ecosystem View's graph and
    detail panel need in a single call, rather than the N+1 a naive
    frontend rollup of GET /api/sources + GET /api/datasets + per-
    dataset column fetches would require.
    """

    sources = db.query(DataSource).filter(DataSource.organization_id == organization_id).all()
    datasets = db.query(Dataset).filter(Dataset.organization_id == organization_id).all()
    edges = (
        db.query(DatasetLineage)
        .join(Dataset, Dataset.id == DatasetLineage.upstream_dataset_id)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    has_upstream = {edge.downstream_dataset_id for edge in edges}
    has_downstream = {edge.upstream_dataset_id for edge in edges}

    dataset_by_id = {dataset.id: dataset for dataset in datasets}
    tier_by_dataset_id = {
        dataset.id: dataset_tier(dataset.id, has_upstream, has_downstream)
        for dataset in datasets
    }

    datasets_by_source: dict[str, list[Dataset]] = {}
    for dataset in datasets:
        datasets_by_source.setdefault(dataset.source_id, []).append(dataset)

    source_nodes = []
    for source in sources:
        source_datasets = datasets_by_source.get(source.id, [])
        tiers = [tier_by_dataset_id[d.id] for d in source_datasets]

        source_nodes.append({
            "id": source.id,
            "name": source.name,
            "type": source.type,
            "tier": _source_tier(tiers),
            **compute_source_rollup(source_datasets),
            "dataset_ids": [d.id for d in source_datasets],
        })

    dataset_nodes = [
        {
            "id": dataset.id,
            "source_id": dataset.source_id,
            "name": dataset.name,
            "schema_name": dataset.schema_name,
            "tier": tier_by_dataset_id[dataset.id],
            "owner": dataset.owner,
            "steward": dataset.steward,
            "domain": dataset.domain,
            "certification": dataset.certification,
            "system_role": dataset.system_role,
            "data_category": dataset.data_category,
            "sensitivity_score": dataset.sensitivity_score,
            "governance_status": dataset.governance_status,
            "governance_score": dataset.governance_score,
            "total_columns": dataset.total_columns,
            "pii_columns": dataset.pii_columns,
            "quality_score": dataset.quality_score,
            "freshness_status": dataset.freshness_status,
            "contract_status": dataset.contract_status,
            "purpose": dataset.purpose,
            "consent_status": dataset.consent_status,
            "retention_status": dataset.retention_status,
            "privacy_score": dataset.privacy_score,
        }
        for dataset in datasets
    ]

    dataset_edges = [
        {
            "id": edge.id,
            "upstream_dataset_id": edge.upstream_dataset_id,
            "downstream_dataset_id": edge.downstream_dataset_id,
            "transformation_type": edge.transformation_type,
        }
        for edge in edges
        if edge.upstream_dataset_id in dataset_by_id and edge.downstream_dataset_id in dataset_by_id
    ]

    # Roll dataset-level edges up to source-level edges (deduplicated)
    # for the source-rollup view of the map - a source-to-source edge
    # exists if ANY of their datasets are lineage-connected.
    source_edge_pairs = set()
    for edge in dataset_edges:
        upstream_dataset = dataset_by_id.get(edge["upstream_dataset_id"])
        downstream_dataset = dataset_by_id.get(edge["downstream_dataset_id"])
        if not upstream_dataset or not downstream_dataset:
            continue
        if upstream_dataset.source_id == downstream_dataset.source_id:
            continue
        source_edge_pairs.add((upstream_dataset.source_id, downstream_dataset.source_id))

    source_edges = [
        {"upstream_source_id": upstream_id, "downstream_source_id": downstream_id}
        for upstream_id, downstream_id in source_edge_pairs
    ]

    processes = db.query(BusinessProcess).filter(BusinessProcess.organization_id == organization_id).all()
    process_links = (
        db.query(BusinessProcessLink)
        .join(Dataset, Dataset.id == BusinessProcessLink.dataset_id)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    process_dataset_ids: dict[str, list[str]] = {}
    for link in process_links:
        process_dataset_ids.setdefault(link.process_id, []).append(link.dataset_id)

    process_nodes = [
        {
            "id": process.id,
            "name": process.name,
            "description": process.description,
            "owner": process.owner,
            "dataset_ids": process_dataset_ids.get(process.id, []),
        }
        for process in processes
    ]

    process_edges = [
        {"process_id": link.process_id, "dataset_id": link.dataset_id}
        for link in process_links
    ]

    terms = (
        db.query(BusinessGlossaryTerm)
        .filter(BusinessGlossaryTerm.organization_id == organization_id)
        .all()
    )
    term_links = (
        db.query(GlossaryTermLink)
        .join(Dataset, Dataset.id == GlossaryTermLink.dataset_id)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    # A term can link to the same dataset more than once (one row per
    # column it defines there) - the graph only shows dataset-level
    # edges, so dedupe (term_id, dataset_id) pairs before turning them
    # into edges, same principle as the source-edge rollup above.
    term_dataset_ids: dict[str, set] = {}
    term_edge_pairs: set = set()
    for link in term_links:
        term_dataset_ids.setdefault(link.term_id, set()).add(link.dataset_id)
        term_edge_pairs.add((link.term_id, link.dataset_id))

    glossary_nodes = [
        {
            "id": term.id,
            "term": term.term,
            "domain": term.domain,
            "dataset_ids": sorted(term_dataset_ids.get(term.id, set())),
        }
        for term in terms
    ]

    glossary_edges = [
        {"term_id": term_id, "dataset_id": dataset_id}
        for term_id, dataset_id in term_edge_pairs
    ]

    contracts = (
        db.query(DataContract)
        .join(Dataset, Dataset.id == DataContract.dataset_id)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    contract_nodes = [
        {
            "id": contract.id,
            "dataset_id": contract.dataset_id,
            "version": contract.version,
            "status": contract.status,
            "owner": contract.owner,
            "last_status": contract.last_status,
            "last_breach_details": contract.last_breach_details,
        }
        for contract in contracts
    ]

    return {
        "sources": source_nodes,
        "source_edges": source_edges,
        "datasets": dataset_nodes,
        "edges": dataset_edges,
        "processes": process_nodes,
        "process_edges": process_edges,
        "glossary_terms": glossary_nodes,
        "glossary_edges": glossary_edges,
        "contracts": contract_nodes,
    }
