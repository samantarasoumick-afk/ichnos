"""
Progressive, step-by-step version of the guided demo tour's data.

demo_data_service.seed_demo_data() builds the entire demo estate in
one shot - right for "explore the catalog on my own." This module
instead builds up just ONE tour scenario's story incrementally, so
the catalog visibly comes alive as each step (frontend TourContext +
tourScenarios.ts) is reached, rather than existing fully formed
before the tour even starts.

Every _ensure_* helper and every _sN_* checkpoint below is idempotent
(get-or-create) by design, since advancing to tour step N re-runs
every checkpoint up to and including N - a later step's data can
depend on an earlier step's, and the checkpoint list below is NOT a
1:1 map to UI step order. Two real dependencies cut against click
order:
  - Scenario 1's "glossary" step links a term to both the
    system-of-record and system-of-reference datasets, which means
    both must already exist by then even though their own reveal
    steps come later in the tour.
  - Scenario 2's "lineage" step shows the chain ending at a Tableau
    report, so that report must already exist even though its own
    "propagation" step comes next.
Rather than force a strict build-then-narrate order, each checkpoint
calls its own prerequisite checkpoint(s) first - cheap and safe since
they're idempotent - so ensure_tour_step() can just look up "the
checkpoint for step N" and call it.

Reuses the platform's real ingestion pipelines (ingest_dataset_info,
ingest_dbt_project, ingest_tableau_workbooks - already idempotent as
written) the same way seed_demo_data() does. If an organization
already ran the full bulk seed first, every checkpoint here just
finds its data already present and no-ops through to the reveal -
this only does net-new work on a tour-first, otherwise-empty org.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.business_process import BusinessProcess, BusinessProcessLink
from app.models.column_lineage import ColumnLineage
from app.models.control import Control
from app.models.data_contract import DataContract
from app.models.dataset import Dataset
from app.models.governance import BusinessGlossaryTerm
from app.models.glossary_link import GlossaryTermLink
from app.models.governance_thread import GovernanceThread
from app.models.lineage import DatasetLineage
from app.models.risk import Risk, RiskControlLink, RiskDatasetLink, RiskProcessLink
from app.models.source import DataSource
from app.models.user import User

from app.auth.security import hash_password
from app.services.data_contract_service import evaluate_contract
from app.services.dataset_ingestion_service import ingest_dataset_info
from app.services.dbt_ingestion_service import ingest_dbt_project
from app.services.tableau_ingestion_service import ingest_tableau_workbooks


class UnknownTourScenarioError(Exception):
    pass


# --------------------------------------------------------------- #
# Idempotent get-or-create helpers
# --------------------------------------------------------------- #

def _ensure_source(db: Session, organization_id: str, name: str, source_type: str, connection_config: dict) -> DataSource:
    source = (
        db.query(DataSource)
        .filter(DataSource.organization_id == organization_id, DataSource.name == name)
        .first()
    )
    if source:
        return source
    source = DataSource(
        name=name, type=source_type, connection_config=connection_config,
        organization_id=organization_id, is_seed_data=True,
    )
    db.add(source)
    db.flush()
    return source


def _ensure_team_member(db: Session, organization_id: str, email: str, role: str) -> User:
    member = db.query(User).filter(User.email == email).first()
    if member:
        return member
    member = User(
        email=email, password_hash=hash_password("password123"), role=role,
        organization_id=organization_id, is_active=True, is_seed_data=True,
    )
    db.add(member)
    db.flush()
    return member


def _ensure_glossary_term(db: Session, organization_id: str, term: str, definition: str, domain: str, owner: str) -> BusinessGlossaryTerm:
    existing = (
        db.query(BusinessGlossaryTerm)
        .filter(BusinessGlossaryTerm.organization_id == organization_id, BusinessGlossaryTerm.term == term)
        .first()
    )
    if existing:
        return existing
    term_row = BusinessGlossaryTerm(
        term=term, definition=definition, domain=domain, owner=owner,
        organization_id=organization_id, status="APPROVED", is_seed_data=True,
    )
    db.add(term_row)
    db.flush()
    return term_row


def _ensure_term_link(db: Session, term: BusinessGlossaryTerm, dataset: Dataset) -> None:
    existing = (
        db.query(GlossaryTermLink)
        .filter(
            GlossaryTermLink.term_id == term.id,
            GlossaryTermLink.dataset_id == dataset.id,
            GlossaryTermLink.column_id.is_(None),
        )
        .first()
    )
    if existing:
        return
    db.add(GlossaryTermLink(term_id=term.id, dataset_id=dataset.id))


def _ensure_business_process(db: Session, organization_id: str, name: str, description: str, owner: str, narrative: str | None = None) -> BusinessProcess:
    existing = (
        db.query(BusinessProcess)
        .filter(BusinessProcess.organization_id == organization_id, BusinessProcess.name == name)
        .first()
    )
    if existing:
        return existing
    process = BusinessProcess(
        name=name, description=description, narrative=narrative, owner=owner,
        organization_id=organization_id, is_seed_data=True,
    )
    db.add(process)
    db.flush()
    return process


def _ensure_process_link(db: Session, process: BusinessProcess, dataset: Dataset) -> None:
    existing = (
        db.query(BusinessProcessLink)
        .filter(BusinessProcessLink.process_id == process.id, BusinessProcessLink.dataset_id == dataset.id)
        .first()
    )
    if existing:
        return
    db.add(BusinessProcessLink(process_id=process.id, dataset_id=dataset.id))


def _ensure_lineage(db: Session, upstream: Dataset, downstream: Dataset, transformation_type: str, description: str | None = None) -> None:
    existing = (
        db.query(DatasetLineage)
        .filter(
            DatasetLineage.upstream_dataset_id == upstream.id,
            DatasetLineage.downstream_dataset_id == downstream.id,
        )
        .first()
    )
    if existing:
        return
    db.add(DatasetLineage(
        upstream_dataset_id=upstream.id, downstream_dataset_id=downstream.id,
        transformation_type=transformation_type, transformation_description=description,
        documentation_source="AUTO",
    ))


def _ensure_column_lineage(db: Session, upstream: Dataset, upstream_column: str, downstream: Dataset, downstream_column: str, transformation_type: str, description: str | None = None) -> None:
    existing = (
        db.query(ColumnLineage)
        .filter(
            ColumnLineage.upstream_dataset_id == upstream.id,
            ColumnLineage.upstream_column_name == upstream_column,
            ColumnLineage.downstream_dataset_id == downstream.id,
            ColumnLineage.downstream_column_name == downstream_column,
        )
        .first()
    )
    if existing:
        return
    db.add(ColumnLineage(
        upstream_dataset_id=upstream.id, upstream_column_name=upstream_column,
        downstream_dataset_id=downstream.id, downstream_column_name=downstream_column,
        transformation_type=transformation_type, transformation_description=description,
        documentation_source="AUTO",
    ))


def _ensure_contract(db: Session, dataset: Dataset, owner: str, schema_expectations: dict, quality_thresholds: dict | None = None, freshness_sla_hours: int | None = None) -> DataContract:
    existing = (
        db.query(DataContract)
        .filter(DataContract.dataset_id == dataset.id, DataContract.status == "ACTIVE")
        .first()
    )
    if existing:
        return existing
    contract = DataContract(
        dataset_id=dataset.id, version=1, status="ACTIVE", owner=owner,
        schema_expectations=schema_expectations, quality_thresholds=quality_thresholds,
        freshness_sla_hours=freshness_sla_hours,
    )
    db.add(contract)
    db.flush()
    return contract


def _ensure_thread(db: Session, organization_id: str, dataset: Dataset, thread_type: str, title: str, body: str, created_by: str, raised_for_user_id: str | None = None) -> GovernanceThread:
    existing = (
        db.query(GovernanceThread)
        .filter(GovernanceThread.dataset_id == dataset.id, GovernanceThread.title == title)
        .first()
    )
    if existing:
        return existing
    thread = GovernanceThread(
        organization_id=organization_id, dataset_id=dataset.id, thread_type=thread_type,
        title=title, body=body, status="OPEN", created_by=created_by,
        raised_for_user_id=raised_for_user_id, created_at=datetime.utcnow() - timedelta(hours=4),
    )
    db.add(thread)
    db.flush()
    return thread


def _ensure_risk(db: Session, organization_id: str, title: str, description: str, category: str, likelihood: str, impact: str, created_by: str, owner_user_id: str | None = None) -> Risk:
    existing = db.query(Risk).filter(Risk.organization_id == organization_id, Risk.title == title).first()
    if existing:
        return existing
    risk = Risk(
        organization_id=organization_id, title=title, description=description, category=category,
        likelihood=likelihood, impact=impact, status="OPEN", owner_user_id=owner_user_id,
        created_by=created_by, is_seed_data=True,
    )
    db.add(risk)
    db.flush()
    return risk


def _ensure_control(db: Session, organization_id: str, name: str, description: str, control_type: str, created_by: str, owner_user_id: str | None = None) -> Control:
    existing = db.query(Control).filter(Control.organization_id == organization_id, Control.name == name).first()
    if existing:
        return existing
    control = Control(
        organization_id=organization_id, name=name, description=description, control_type=control_type,
        status="NOT_TESTED", owner_user_id=owner_user_id, created_by=created_by, is_seed_data=True,
    )
    db.add(control)
    db.flush()
    return control


def _ensure_risk_links(db: Session, risk: Risk, dataset: Dataset | None = None, process: BusinessProcess | None = None, control: Control | None = None) -> None:
    if dataset and not db.query(RiskDatasetLink).filter(RiskDatasetLink.risk_id == risk.id, RiskDatasetLink.dataset_id == dataset.id).first():
        db.add(RiskDatasetLink(risk_id=risk.id, dataset_id=dataset.id))
    if process and not db.query(RiskProcessLink).filter(RiskProcessLink.risk_id == risk.id, RiskProcessLink.process_id == process.id).first():
        db.add(RiskProcessLink(risk_id=risk.id, process_id=process.id))
    if control and not db.query(RiskControlLink).filter(RiskControlLink.risk_id == risk.id, RiskControlLink.control_id == control.id).first():
        db.add(RiskControlLink(risk_id=risk.id, control_id=control.id))


def _get_or_raise(db: Session, organization_id: str, schema_name: str, table_name: str) -> Dataset:
    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.organization_id == organization_id,
            Dataset.schema_name == schema_name,
            Dataset.name == table_name,
        )
        .first()
    )
    if dataset is None:
        raise RuntimeError(
            f"Guided tour expected a dataset at {schema_name}.{table_name} but it wasn't created - "
            "this is a bug in a checkpoint function, not something a user did."
        )
    return dataset


# --------------------------------------------------------------- #
# Scenario 1: discovery-bottleneck
# --------------------------------------------------------------- #

def _s1_dbt_marts(db: Session, current_user: User) -> dict:
    org_id = current_user.organization_id

    storefront = _ensure_source(db, org_id, "Storefront Postgres", "postgres", {
        "host": "storefront-db.internal", "port": 5432, "database": "storefront", "user": "readonly_demo",
    })
    customers = ingest_dataset_info(db, storefront, {
        "schema_name": "public", "table_name": "customers",
        "columns": [
            ("customer_id", "integer", "NO"), ("full_name", "varchar", "NO"),
            ("email", "varchar", "NO"), ("phone_number", "varchar", "YES"), ("signup_date", "date", "YES"),
        ],
        "row_count": 500,
        "column_stats": {
            "customer_id": {"non_null": 500, "distinct": 500}, "full_name": {"non_null": 500, "distinct": 495},
            "email": {"non_null": 500, "distinct": 500}, "phone_number": {"non_null": 480, "distinct": 480},
            "signup_date": {"non_null": 500, "distinct": 365},
        },
        "column_samples": {
            "customer_id": [str(i) for i in range(1, 6)],
            "full_name": ["Ava Patel", "Liam Chen", "Noor Khan", "Diego Ramirez", "Mei Tanaka"],
            "email": ["ava.patel@example.com", "liam.chen@example.com", "noor.khan@example.com"],
            "phone_number": ["9876543210", "9123456780", "9988776655"],
            "signup_date": ["2024-01-15", "2024-02-20", "2024-03-05"],
        },
    }, current_user)
    customers.owner = "Growth Team"
    customers.domain = "E-Commerce"
    customers.steward = "Priya Sharma"
    customers.certification = "VERIFIED"
    customers.tags = "crm,customers,pii"

    salesforce = _ensure_source(db, org_id, "Salesforce CRM", "salesforce", {
        "instance_url": "https://acme.my.salesforce.com",
    })
    leads = ingest_dataset_info(db, salesforce, {
        "schema_name": "salesforce", "table_name": "leads",
        "columns": [
            ("lead_id", "varchar", "NO"), ("contact_email", "varchar", "NO"),
            ("company", "varchar", "YES"), ("status", "varchar", "YES"), ("created_date", "date", "YES"),
        ],
        "row_count": 800,
        "column_stats": {
            "lead_id": {"non_null": 800, "distinct": 800}, "contact_email": {"non_null": 800, "distinct": 750},
            "company": {"non_null": 700, "distinct": 400}, "status": {"non_null": 800, "distinct": 5},
            "created_date": {"non_null": 800, "distinct": 300},
        },
        "column_samples": {
            "lead_id": ["00Q1", "00Q2", "00Q3"],
            "contact_email": ["ava.patel@example.com", "new.prospect@example.com"],
            "company": ["Acme Retail", "Globex"], "status": ["Open", "Qualified", "Converted", "Lost"],
            "created_date": ["2024-06-01", "2024-07-15"],
        },
    }, current_user)
    leads.owner = "Sales Ops"
    leads.domain = "Sales"
    leads.tags = "crm,leads"
    leads.last_scanned_at = datetime.utcnow() - timedelta(days=35)

    dbt_source = _ensure_source(db, org_id, "Analytics Warehouse (dbt)", "dbt", {
        "project_name": "analytics", "target": "prod",
    })
    manifest = {
        "nodes": {
            "model.analytics.stg_customers": {
                "resource_type": "model", "alias": "stg_customers", "schema": "staging",
                "description": "Cleaned, deduplicated customer records straight from the storefront database.",
                "depends_on": {"nodes": []},
                "columns": {"customer_id": {}, "full_name": {}, "email": {}, "signup_date": {}},
            },
            "model.analytics.dim_customers": {
                "resource_type": "model", "alias": "dim_customers", "schema": "analytics_marts",
                "description": "Reporting-layer customer dimension - the copy every dashboard and report reads from.",
                "depends_on": {"nodes": ["model.analytics.stg_customers"]},
                "columns": {"customer_id": {}, "full_name": {}, "email": {}, "signup_date": {}, "lifetime_orders": {}},
            },
        }
    }
    ingest_dbt_project(db, dbt_source, manifest, {}, current_user)

    stg_customers = _get_or_raise(db, org_id, "staging", "stg_customers")
    dim_customers = _get_or_raise(db, org_id, "analytics_marts", "dim_customers")

    _ensure_lineage(db, customers, stg_customers, "ETL_INGESTION",
                     "Nightly EL job loads confirmed customer records into staging, unchanged.")
    _ensure_lineage(db, leads, stg_customers, "ETL_INGESTION",
                     "CRM leads are matched against confirmed customers by email during the nightly merge.")
    _ensure_column_lineage(db, customers, "email", stg_customers, "email", "PASSTHROUGH")
    _ensure_column_lineage(db, leads, "contact_email", stg_customers, "email", "MERGE",
                            "Matched to the confirmed customer record by email.")
    _ensure_column_lineage(db, stg_customers, "email", dim_customers, "email", "PASSTHROUGH")

    db.commit()
    return {
        "storefront": storefront, "customers": customers, "salesforce": salesforce, "leads": leads,
        "dbt_source": dbt_source, "stg_customers": stg_customers, "dim_customers": dim_customers,
    }


def _s1_glossary(db: Session, current_user: User) -> dict:
    data = _s1_dbt_marts(db, current_user)
    org_id = current_user.organization_id

    term = _ensure_glossary_term(
        db, org_id, "Customer",
        "A person or company that has purchased, or registered interest in purchasing, from us.",
        "Sales", "Data Governance",
    )
    _ensure_term_link(db, term, data["customers"])
    _ensure_term_link(db, term, data["dim_customers"])

    db.commit()
    return {**data, "customer_term": term}


def _s1_tag_system_of_record(db: Session, current_user: User) -> dict:
    data = _s1_glossary(db, current_user)
    data["customers"].system_role = "SYSTEM_OF_RECORD"
    db.commit()
    return data


def _s1_tag_system_of_reference(db: Session, current_user: User) -> dict:
    data = _s1_tag_system_of_record(db, current_user)
    data["dim_customers"].system_role = "SYSTEM_OF_REFERENCE"
    db.commit()
    return data


def _s1_process(db: Session, current_user: User) -> dict:
    data = _s1_tag_system_of_reference(db, current_user)
    org_id = current_user.organization_id

    tableau_source = _ensure_source(db, org_id, "Tableau Cloud - Analytics Site", "tableau", {
        "site_url": "https://prod-useast.online.tableau.com/#/site/acme-analytics",
    })
    ingest_tableau_workbooks(db, tableau_source, [{
        "luid": "wb-360", "name": "Customer 360", "project_name": "Customer Success",
        "upstream_tables": [{"schema": "analytics_marts", "name": "dim_customers"}],
    }], current_user)

    process = _ensure_business_process(
        db, org_id, "Customer Onboarding",
        "From a lead's first contact through to becoming a confirmed, recognized customer.",
        "Growth Team",
        "A Lead (salesforce.leads) is qualified and matched by email to a confirmed Customer "
        "(public.customers) - the reporting layer (analytics_marts.dim_customers) and the Customer "
        "360 dashboard both read from the confirmed record, never the raw lead.",
    )
    for key in ("leads", "customers", "stg_customers", "dim_customers"):
        _ensure_process_link(db, process, data[key])

    db.commit()
    return {**data, "tableau_source": tableau_source, "process": process}


_S1_STEP_CHECKPOINTS = [
    _s1_dbt_marts,               # 0 search - both raw systems + the dbt mart exist, so a search
                                   #            actually turns up "three different systems"; system_role
                                   #            stays unset, matching "the moment of confusion"
    _s1_glossary,                 # 1 glossary - the single owned definition appears, linked to both
    _s1_tag_system_of_record,     # 2 system-of-record - customers gets tagged authoritative, right here
    _s1_tag_system_of_reference,  # 3 system-of-reference - dim_customers' side of the same tagging
    _s1_tag_system_of_reference,  # 4 lineage - pure reveal, chain already built at checkpoint 0
    _s1_tag_system_of_reference,  # 5 ask - pure reveal, nothing new
    _s1_process,                  # 6 process - Tableau workbook + Customer Onboarding process appear
]


# --------------------------------------------------------------- #
# Scenario 2: vendor-data-quality
# --------------------------------------------------------------- #

def _s2_vendor_feed(db: Session, current_user: User) -> dict:
    org_id = current_user.organization_id

    vendor_source = _ensure_source(db, org_id, "Acme Vendor Product Feed (CSV)", "csv", {
        "filename": "acme_product_export.csv", "uploaded_by": current_user.email,
    })
    vendor_products = ingest_dataset_info(db, vendor_source, {
        "schema_name": "vendor_feeds", "table_name": "acme_product_feed",
        "columns": [
            ("vendor_sku", "varchar", "NO"), ("product_name", "varchar", "YES"),
            ("unit_price", "varchar", "YES"), ("in_stock_qty", "varchar", "YES"),
            ("category", "varchar", "YES"),
        ],
        "row_count": 2400,
        "column_stats": {
            "vendor_sku": {"non_null": 2400, "distinct": 2350}, "product_name": {"non_null": 2100, "distinct": 1900},
            "unit_price": {"non_null": 1900, "distinct": 800}, "in_stock_qty": {"non_null": 2000, "distinct": 300},
            "category": {"non_null": 1400, "distinct": 40},
        },
        "column_samples": {
            "vendor_sku": ["ACM-1001", "ACM-1002", "ACM-1003"],
            "product_name": ["Steel Widget", "Copper Bracket", ""],
            "unit_price": ["12.50", "$8.00", "n/a"],
            "in_stock_qty": ["120", "0", ""],
            "category": ["Hardware", "", "Hardware"],
        },
    }, current_user)
    vendor_products.owner = "Procurement"
    vendor_products.domain = "Product"
    vendor_products.steward = None
    vendor_products.tags = "vendor,product,inventory"
    vendor_products.purpose = "Vendor catalog sync into the internal product listing"
    vendor_products.consent_status = "CONSENT_NOT_REQUIRED"

    db.commit()
    return {"vendor_source": vendor_source, "vendor_products": vendor_products}


def _s2_contract(db: Session, current_user: User) -> dict:
    data = _s2_vendor_feed(db, current_user)

    contract = _ensure_contract(
        db, data["vendor_products"], owner="Procurement",
        schema_expectations={"columns": [
            {"name": "vendor_sku", "data_type": "varchar", "required": True},
            {"name": "unit_price", "data_type": "varchar", "required": True},
            {"name": "return_policy_url", "data_type": "varchar", "required": True},
        ]},
        quality_thresholds={"min_overall_score": 85},
        freshness_sla_hours=24,
    )
    evaluate_contract(db, data["vendor_products"], actor_user_id=current_user.id, actor_email=current_user.email)

    db.commit()
    return {**data, "vendor_contract": contract}


def _s2_discussion(db: Session, current_user: User) -> dict:
    data = _s2_contract(db, current_user)
    org_id = current_user.organization_id
    org_slug = org_id[:8]

    steward_member = _ensure_team_member(db, org_id, f"priya.sharma+{org_slug}@demo-datafe.example", "steward")
    data_owner_member = _ensure_team_member(db, org_id, f"marcus.webb+{org_slug}@demo-datafe.example", "data_owner")

    thread = _ensure_thread(
        db, org_id, data["vendor_products"], "ISSUE",
        "Acme's product feed keeps breaching contract - do we need a stricter vendor SLA?",
        "The last several exports have missing prices and blank categories. The contract's schema "
        "check and quality threshold are both currently breached. Flagging this before it shows up "
        "in the next Vendor Product Catalog Health report.",
        created_by=steward_member.id, raised_for_user_id=data_owner_member.id,
    )

    db.commit()
    return {**data, "steward_member": steward_member, "data_owner_member": data_owner_member, "issue_thread": thread}


def _s2_lineage(db: Session, current_user: User) -> dict:
    data = _s2_discussion(db, current_user)
    org_id = current_user.organization_id

    dbt_source = _ensure_source(db, org_id, "Analytics Warehouse (dbt)", "dbt", {
        "project_name": "analytics", "target": "prod",
    })
    manifest = {
        "nodes": {
            "model.analytics.stg_vendor_products": {
                "resource_type": "model", "alias": "stg_vendor_products", "schema": "staging",
                "description": "The vendor's raw CSV export, loaded unmodified into staging.",
                "depends_on": {"nodes": []},
                "columns": {"sku": {}, "unit_price": {}, "in_stock_qty": {}},
            },
            "model.analytics.dim_products": {
                "resource_type": "model", "alias": "dim_products", "schema": "analytics_marts",
                "description": "Reporting-layer product dimension, blending every vendor and internal feed.",
                "depends_on": {"nodes": ["model.analytics.stg_vendor_products"]},
                "columns": {"sku": {}, "unit_price": {}, "in_stock_qty": {}},
            },
        }
    }
    ingest_dbt_project(db, dbt_source, manifest, {}, current_user)

    stg_vendor_products = _get_or_raise(db, org_id, "staging", "stg_vendor_products")
    dim_products = _get_or_raise(db, org_id, "analytics_marts", "dim_products")

    _ensure_lineage(db, data["vendor_products"], stg_vendor_products, "ETL_INGESTION",
                     "Nightly EL job loads the vendor's CSV export into the staging schema, unmodified.")
    for upstream_col, downstream_col in (("vendor_sku", "sku"), ("unit_price", "unit_price"), ("in_stock_qty", "in_stock_qty")):
        _ensure_column_lineage(db, data["vendor_products"], upstream_col, stg_vendor_products, downstream_col, "PASSTHROUGH")
    for col in ("sku", "unit_price", "in_stock_qty"):
        _ensure_column_lineage(db, stg_vendor_products, col, dim_products, col, "PASSTHROUGH")

    tableau_source = _ensure_source(db, org_id, "Tableau Cloud - Analytics Site", "tableau", {
        "site_url": "https://prod-useast.online.tableau.com/#/site/acme-analytics",
    })
    ingest_tableau_workbooks(db, tableau_source, [{
        "luid": "wb-vendor-quality", "name": "Vendor Product Catalog Health", "project_name": "Procurement Analytics",
        "upstream_tables": [{"schema": "analytics_marts", "name": "dim_products"}],
    }], current_user)

    vendor_catalog_health = _get_or_raise(db, org_id, "Procurement Analytics", "Vendor Product Catalog Health")

    db.commit()
    return {
        **data, "dbt_source": dbt_source, "stg_vendor_products": stg_vendor_products,
        "dim_products": dim_products, "tableau_source": tableau_source,
        "vendor_catalog_health": vendor_catalog_health,
    }


def _s2_risk(db: Session, current_user: User) -> dict:
    data = _s2_lineage(db, current_user)
    org_id = current_user.organization_id

    process = _ensure_business_process(
        db, org_id, "Vendor Catalog Sync",
        "Nightly ingestion of a third-party vendor's product feed into the internal catalog.",
        "Procurement",
        "Acme's raw CSV export (vendor_feeds.acme_product_feed) is loaded into staging and blended "
        "into the shared product dimension (analytics_marts.dim_products), which the Vendor Product "
        "Catalog Health report reads from directly.",
    )
    for key in ("vendor_products", "stg_vendor_products", "dim_products", "vendor_catalog_health"):
        _ensure_process_link(db, process, data[key])

    risk = _ensure_risk(
        db, org_id, "Vendor product feed quality is unmanaged",
        "Acme's product feed has repeatedly breached its data contract on both schema and quality "
        "thresholds, and the breach reaches a downstream report before anyone notices manually.",
        category="DATA_QUALITY", likelihood="HIGH", impact="MEDIUM",
        created_by=current_user.id, owner_user_id=data["data_owner_member"].id,
    )
    control = _ensure_control(
        db, org_id, "Automated vendor feed validation on ingest",
        "Reject or quarantine a vendor export at load time if it fails schema or completeness checks, "
        "instead of letting a bad feed reach staging and propagate downstream.",
        control_type="PREVENTIVE", created_by=current_user.id, owner_user_id=data["data_owner_member"].id,
    )
    _ensure_risk_links(db, risk, dataset=data["vendor_products"], process=process, control=control)

    db.commit()
    return {**data, "vendor_catalog_sync_process": process, "vendor_quality_risk": risk, "vendor_validation_control": control}


_S2_STEP_CHECKPOINTS = [
    _s2_vendor_feed,   # 0 search
    _s2_vendor_feed,   # 1 quality (pure reveal - DQ already computed by ingestion)
    _s2_contract,      # 2 contract - contract created + evaluated as breached, right here
    _s2_discussion,    # 3 discussion - team roster + the open issue thread appear
    _s2_lineage,       # 4 lineage - full chain incl. the Tableau report node
    _s2_lineage,       # 5 propagation (pure reveal - breach banner computed live from what's already there)
    _s2_risk,          # 6 risk - process, risk, and control all appear
    _s2_risk,          # 7 ask (pure reveal)
]


_SCENARIO_CHECKPOINTS = {
    "discovery-bottleneck": _S1_STEP_CHECKPOINTS,
    "vendor-data-quality": _S2_STEP_CHECKPOINTS,
}


def ensure_tour_step(db: Session, current_user: User, scenario_id: str, step_index: int) -> dict:
    """
    Idempotently creates every piece of demo data needed for a guided
    tour scenario up through (and including) the given step index -
    safe to call repeatedly, since advancing, going back, or
    re-visiting a step all just re-run already-satisfied checkpoints,
    which no-op. Raises UnknownTourScenarioError for an unrecognized
    scenario id, and IndexError for a step index outside the
    scenario's step count - both are stale-frontend/config errors,
    not something a user did.
    """

    checkpoints = _SCENARIO_CHECKPOINTS.get(scenario_id)
    if checkpoints is None:
        raise UnknownTourScenarioError(f"Unknown tour scenario id: {scenario_id!r}")

    if step_index < 0 or step_index >= len(checkpoints):
        raise IndexError(
            f"Step index {step_index} is out of range for scenario {scenario_id!r} "
            f"({len(checkpoints)} steps)"
        )

    checkpoints[step_index](db, current_user)

    return {"scenario_id": scenario_id, "step_index": step_index}
