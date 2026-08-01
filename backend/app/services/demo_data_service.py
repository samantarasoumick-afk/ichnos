"""
Builds (and tears back down) one coherent demo estate so a new org can
see the whole platform "in motion" without bringing their own data
first - structured as two problem -> process -> solution stories
rather than a pile of unrelated sample rows, so the guided tour
(frontend TourProvider/tourScenarios) has real data to walk through
for each:

1. "My analysts spend half their time in discovery" - three different
   front-office applications (an OLTP e-commerce database, a
   Salesforce-style CRM, a Zendesk-style support desk) feed a
   dbt-modeled analytics warehouse, reported on through Tableau
   workbooks - the same shape almost every real customer's environment
   takes, with an ambiguous "which customer table is real" problem
   solved by the glossary, system-of-record/reference tagging,
   lineage, and the Ask assistant.
2. "My vendors are inconsistent in data quality" - a fourth source, a
   third-party CSV product feed, deliberately messy in a different way
   than the first story's tables (inconsistent price formats, sparse
   categorization, no steward), carrying a stacked schema + DQ-
   threshold contract breach that propagates - live, via
   get_upstream_contract_breaches() - all the way to a downstream
   Tableau report, demonstrating the data contract + lineage-breach-
   propagation features end to end.

Together these touch every major feature rather than scattering
unrelated sample rows: PII/financial classification, data quality
scoring (deliberately varied across multiple tables), dataset- *and*
column-level lineage spanning all layers (including a PCI-style
masking transformation actually enforced via DatasetColumn.masked, not
just documented in lineage), contracts both compliant and breached
(breached on both a schema check and a DQ-threshold check, in two
different places), all three governance-status outcomes
(HEALTHY/CRITICAL/REVIEW_REQUIRED), the certification approval queue,
all three governance discussion types (QUESTION/PROPOSAL/ISSUE), a
risk register with linked controls, a few retention/consent/purpose-
filled datasets alongside deliberately unassessed ones, a small
mixed-role team roster, a handful of logged Ask/search queries
(including a repeated one that never lands), and usage/view tracking.

Deliberately reuses the platform's *real* ingestion pipelines rather
than hand-crafting rows that merely look right:
  - ingest_dataset_info() for the three front-office sources - same
    path a live Postgres/S3/etc. scan uses, so PII classification and
    data quality scoring run for real against the sample data below.
  - ingest_dbt_project() for the staging/mart layer, fed a
    synthetically-built manifest.json/catalog.json - the exact same
    function the real dbt upload endpoint calls.
  - ingest_tableau_workbooks() for the reporting layer, fed
    synthetic workbook/upstream-table data - the exact same function
    the real Tableau connect endpoint calls.
Only the ETL "raw -> staging" lineage edges, the column-level lineage,
the contracts, the certification request, the discussion thread, and
the view rows are constructed directly, since nothing else in the app
produces those from a scan.

Every DataSource this creates has is_seed_data=True - the one marker
clear_demo_data() needs to find and remove everything that hangs off
it without touching anything a user connected or uploaded themselves.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.business_process import BusinessProcess, BusinessProcessLink
from app.models.column import DatasetColumn
from app.models.column_lineage import ColumnLineage
from app.models.control import Control
from app.models.data_contract import DataContract
from app.models.data_quality import DataQuality
from app.models.dataset import Dataset
from app.models.dataset_view import DatasetView
from app.models.certification_request import CertificationRequest
from app.models.governance import BusinessGlossaryTerm
from app.models.glossary_link import GlossaryTermLink
from app.models.governance_thread import GovernanceThread, GovernanceThreadReply
from app.models.lineage import DatasetLineage
from app.models.query_log import QueryLog
from app.models.risk import Risk, RiskControlLink, RiskDatasetLink, RiskProcessLink
from app.models.source import DataSource
from app.models.user import User

from app.auth.security import hash_password
from app.services.audit_service import log_audit_event
from app.services.data_contract_service import evaluate_contract
from app.services.dataset_ingestion_service import ingest_dataset_info
from app.services.dbt_ingestion_service import ingest_dbt_project
from app.services.tableau_ingestion_service import ingest_tableau_workbooks


class DemoDataAlreadyLoadedError(Exception):
    pass


def _create_source(db: Session, name: str, source_type: str, organization_id: str, connection_config: dict) -> DataSource:

    source = DataSource(
        name=name,
        type=source_type,
        connection_config=connection_config,
        organization_id=organization_id,
        is_seed_data=True,
    )
    db.add(source)
    db.flush()
    return source


def _get_dataset(db: Session, organization_id: str, schema_name: str, table_name: str) -> Dataset:

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
            f"Demo seeding expected a dataset at {schema_name}.{table_name} "
            "but it wasn't created - this is a bug in the seed data, not "
            "something a user did."
        )

    return dataset


def _get_column(db: Session, dataset: Dataset, column_name: str) -> DatasetColumn:

    column = (
        db.query(DatasetColumn)
        .filter(
            DatasetColumn.dataset_id == dataset.id,
            DatasetColumn.name == column_name,
        )
        .first()
    )

    if column is None:
        raise RuntimeError(
            f"Demo seeding expected column '{column_name}' on "
            f"{dataset.schema_name}.{dataset.name} but it wasn't found."
        )

    return column


def _glossary_term(db: Session, organization_id: str, term: str, definition: str, domain: str, owner: str) -> BusinessGlossaryTerm:

    glossary_term = BusinessGlossaryTerm(
        term=term,
        definition=definition,
        domain=domain,
        owner=owner,
        organization_id=organization_id,
        status="APPROVED",
        is_seed_data=True,
    )
    db.add(glossary_term)
    db.flush()
    return glossary_term


def _link_term(db: Session, term: BusinessGlossaryTerm, dataset: Dataset, column: DatasetColumn | None = None):

    db.add(
        GlossaryTermLink(
            term_id=term.id,
            dataset_id=dataset.id,
            column_id=column.id if column else None,
        )
    )


def _business_process(
    db: Session,
    organization_id: str,
    name: str,
    description: str,
    owner: str,
    narrative: str | None = None,
) -> BusinessProcess:

    process = BusinessProcess(
        name=name,
        description=description,
        narrative=narrative,
        owner=owner,
        organization_id=organization_id,
        is_seed_data=True,
    )
    db.add(process)
    db.flush()
    return process


def _link_process(db: Session, process: BusinessProcess, dataset: Dataset):

    db.add(
        BusinessProcessLink(
            process_id=process.id,
            dataset_id=dataset.id,
        )
    )


def _team_member(db: Session, organization_id: str, email: str, role: str) -> User:
    """
    A real, working account (login-capable, same as one created via
    the actual team-invite endpoint) rather than a decorative row -
    so the Team page shows what a mixed-role roster actually looks
    like, and so risks/controls/discussions below can be owned by
    someone other than whoever clicked "Load Demo Data." Password is
    the same fixed demo password across every seeded account, since
    nobody is meant to keep using it - see the docstring on
    clear_demo_data for why these are deactivated, not deleted, on
    clear.

    Re-seeding the same organization after a clear reuses that
    deactivated row by email instead of inserting a duplicate - each
    email is org_slug-suffixed (see call sites below) so it's stable
    across seed/clear/re-seed cycles for one org, and without this a
    second seed would hit a UNIQUE constraint on users.email rather
    than standing the same demo team back up.
    """

    existing = (
        db.query(User)
        .filter(User.email == email, User.organization_id == organization_id)
        .first()
    )

    if existing is not None:
        existing.role = role
        existing.is_active = True
        existing.is_seed_data = True
        existing.password_hash = hash_password("password123")
        db.flush()
        return existing

    member = User(
        email=email,
        password_hash=hash_password("password123"),
        role=role,
        organization_id=organization_id,
        is_active=True,
        is_seed_data=True,
    )
    db.add(member)
    db.flush()
    return member


def _risk(
    db: Session,
    organization_id: str,
    title: str,
    description: str,
    category: str,
    likelihood: str,
    impact: str,
    status: str,
    created_by: str,
    owner_user_id: str | None = None,
) -> Risk:

    risk = Risk(
        organization_id=organization_id,
        title=title,
        description=description,
        category=category,
        likelihood=likelihood,
        impact=impact,
        status=status,
        owner_user_id=owner_user_id,
        created_by=created_by,
        is_seed_data=True,
    )
    db.add(risk)
    db.flush()
    return risk


def _control(
    db: Session,
    organization_id: str,
    name: str,
    description: str,
    control_type: str,
    status: str,
    created_by: str,
    owner_user_id: str | None = None,
    last_tested_at: datetime | None = None,
) -> Control:

    control = Control(
        organization_id=organization_id,
        name=name,
        description=description,
        control_type=control_type,
        status=status,
        owner_user_id=owner_user_id,
        last_tested_at=last_tested_at,
        created_by=created_by,
        is_seed_data=True,
    )
    db.add(control)
    db.flush()
    return control


def _link(db: Session, upstream: Dataset, downstream: Dataset, transformation_type: str, description: str | None = None):

    db.add(
        DatasetLineage(
            upstream_dataset_id=upstream.id,
            downstream_dataset_id=downstream.id,
            transformation_type=transformation_type,
            transformation_description=description,
            documentation_source="AUTO",
        )
    )


def _link_columns(
    db: Session,
    upstream: Dataset,
    upstream_column: str,
    downstream: Dataset,
    downstream_column: str,
    transformation_type: str,
    description: str | None = None,
):

    db.add(
        ColumnLineage(
            upstream_dataset_id=upstream.id,
            upstream_column_name=upstream_column,
            downstream_dataset_id=downstream.id,
            downstream_column_name=downstream_column,
            transformation_type=transformation_type,
            transformation_description=description,
            documentation_source="AUTO",
        )
    )


def seed_demo_data(db: Session, current_user: User) -> dict:

    organization_id = current_user.organization_id

    already_loaded = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == organization_id,
            DataSource.is_seed_data.is_(True),
        )
        .first()
    )

    if already_loaded:
        raise DemoDataAlreadyLoadedError(
            "Demo data is already loaded for this organization - clear it first."
        )

    # ---------------------------------------------------------------
    # Layer 1: Front office - three different applications.
    # ---------------------------------------------------------------

    storefront = _create_source(
        db, "Storefront Postgres", "postgres", organization_id,
        {"host": "storefront-db.internal", "port": 5432, "database": "storefront", "user": "readonly_demo"},
    )

    customer_emails = [
        "ava.patel@example.com", "liam.chen@example.com", "noor.khan@example.com",
        "diego.ramirez@example.com", "mei.tanaka@example.com", "sara.okafor@example.com",
        "ivan.petrov@example.com", "priya.nair@example.com", "tomas.novak@example.com",
        "yui.sato@example.com",
    ]
    customer_phones = [
        "9876543210", "9123456780", "9988776655", "9871122334", "9345678901",
        "9012345678", "9556677889", "9223344556", "9667788990", "9098765432",
    ]

    ingest_dataset_info(db, storefront, {
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("customer_id", "integer", "NO"),
            ("full_name", "varchar", "NO"),
            ("email", "varchar", "NO"),
            ("phone_number", "varchar", "YES"),
            ("signup_date", "date", "YES"),
        ],
        "row_count": 500,
        "column_stats": {
            "customer_id": {"non_null": 500, "distinct": 500},
            "full_name": {"non_null": 500, "distinct": 495},
            "email": {"non_null": 500, "distinct": 500},
            "phone_number": {"non_null": 480, "distinct": 480},
            "signup_date": {"non_null": 500, "distinct": 365},
        },
        "column_samples": {
            "customer_id": [str(i) for i in range(1, 11)],
            "full_name": ["Ava Patel", "Liam Chen", "Noor Khan", "Diego Ramirez", "Mei Tanaka"],
            "email": customer_emails,
            "phone_number": customer_phones,
            "signup_date": ["2024-01-15", "2024-02-20", "2024-03-05", "2024-04-11", "2024-05-02"],
        },
    }, current_user)

    ingest_dataset_info(db, storefront, {
        "schema_name": "public",
        "table_name": "orders",
        "columns": [
            ("order_id", "integer", "NO"),
            ("customer_id", "integer", "NO"),
            ("order_date", "timestamp", "NO"),
            ("total_amount", "numeric", "NO"),
            ("status", "varchar", "YES"),
        ],
        "row_count": 1200,
        "column_stats": {
            "order_id": {"non_null": 1200, "distinct": 1200},
            "customer_id": {"non_null": 1200, "distinct": 480},
            "order_date": {"non_null": 1200, "distinct": 1100},
            "total_amount": {"non_null": 1200, "distinct": 900},
            "status": {"non_null": 1190, "distinct": 4},
        },
        "column_samples": {
            "order_id": [str(i) for i in range(1001, 1011)],
            "customer_id": [str(i) for i in range(1, 11)],
            "order_date": ["2025-01-05T10:00:00", "2025-02-14T15:30:00", "2025-03-01T09:15:00"],
            "total_amount": ["149.99", "89.50", "210.00", "45.25", "999.00", "12.99"],
            "status": ["completed", "pending", "completed", "cancelled", "completed"],
        },
    }, current_user)

    ingest_dataset_info(db, storefront, {
        "schema_name": "public",
        "table_name": "payments",
        "columns": [
            ("payment_id", "integer", "NO"),
            ("order_id", "integer", "NO"),
            ("card_number", "varchar", "NO"),
            ("billing_email", "varchar", "YES"),
            ("billing_address", "varchar", "YES"),
            ("amount", "numeric", "NO"),
            ("payment_method", "varchar", "YES"),
        ],
        "row_count": 1200,
        # Deliberately messy - this is the "poor data quality" table in
        # the demo. card_number is mostly unparseable placeholders
        # (tokenized/blank/garbage rather than real card numbers), and
        # payment_method/billing fields are only populated part of the
        # time. Also deliberately the "high sensitivity" table: a
        # financial identifier (card_number) plus two PII columns
        # (billing_email, billing_address) puts this at HIGH
        # sensitivity, which combined with having no assigned steward
        # (see below) is what drives CRITICAL governance status.
        "column_stats": {
            "payment_id": {"non_null": 1200, "distinct": 1200},
            "order_id": {"non_null": 1200, "distinct": 1200},
            "card_number": {"non_null": 1200, "distinct": 1150},
            "billing_email": {"non_null": 700, "distinct": 690},
            "billing_address": {"non_null": 650, "distinct": 640},
            "amount": {"non_null": 1200, "distinct": 950},
            "payment_method": {"non_null": 600, "distinct": 4},
        },
        "column_samples": {
            "payment_id": [str(i) for i in range(1, 11)],
            "order_id": [str(i) for i in range(1001, 1011)],
            "card_number": [
                "4111 1111 1111 1111", "5500005555555559", "4012888888881881",
                "tok_1a2b3c", "on file", "****", "N/A", "unknown", "REDACTED",
            ],
            "billing_email": customer_emails[:5],
            "billing_address": ["221B Baker Street", "42 Wallaby Way", None, None],
            "amount": ["149.99", "89.50", "210.00", "45.25", "999.00"],
            "payment_method": ["card", "upi", None, "netbanking", None, "card", "wallet", None],
        },
    }, current_user)

    customers = _get_dataset(db, organization_id, "public", "customers")
    orders = _get_dataset(db, organization_id, "public", "orders")
    payments = _get_dataset(db, organization_id, "public", "payments")

    customers.owner = "Growth Team"
    customers.domain = "E-Commerce"
    customers.steward = "Priya Sharma"
    customers.certification = "VERIFIED"
    customers.tags = "crm,customers,pii"
    # The storefront OLTP table is where a customer record is first
    # created and is treated as authoritative for identity - the
    # analytics warehouse's dim_customers below is a derived copy of
    # this same entity, tagged SYSTEM_OF_REFERENCE further down.
    customers.system_role = "SYSTEM_OF_RECORD"

    orders.owner = "Growth Team"
    orders.domain = "E-Commerce"
    orders.tags = "orders,transactions"
    orders.system_role = "SYSTEM_OF_RECORD"

    payments.owner = "Growth Team"
    payments.domain = "Payments"
    # No steward, and this dataset's sensitivity will come out HIGH
    # (a FINANCIAL card_number column plus other PII downstream) - the
    # combination is what drives Dataset.governance_status to CRITICAL,
    # deliberately, as one of the three governance outcomes this demo
    # shows side by side.
    payments.steward = None
    payments.tags = "payments,pci,financial"

    # A small, static lookup table - the demo's one deliberate example
    # of REFERENCE data (as opposed to the MASTER/TRANSACTIONAL/
    # ANALYTICAL tables everywhere else in this narrative), so the
    # auto-classification heuristic and the Reference Data Repository
    # view both have something real to show. Narrow (three columns),
    # a controlled vocabulary orders.status values are drawn from -
    # exactly the shape REFERENCE data usually takes.
    ingest_dataset_info(db, storefront, {
        "schema_name": "public",
        "table_name": "order_status_codes",
        "columns": [
            ("status_code", "varchar", "NO"),
            ("label", "varchar", "NO"),
            ("description", "varchar", "YES"),
        ],
        "row_count": 4,
        "column_stats": {
            "status_code": {"non_null": 4, "distinct": 4},
            "label": {"non_null": 4, "distinct": 4},
            "description": {"non_null": 4, "distinct": 4},
        },
        "column_samples": {
            "status_code": ["pending", "completed", "cancelled", "refunded"],
            "label": ["Pending", "Completed", "Cancelled", "Refunded"],
            "description": [
                "Order placed, payment not yet captured.",
                "Order fulfilled and payment captured.",
                "Order cancelled before fulfillment.",
                "Payment returned to the customer.",
            ],
        },
    }, current_user)

    order_status_codes = _get_dataset(db, organization_id, "public", "order_status_codes")
    order_status_codes.owner = "Growth Team"
    order_status_codes.domain = "E-Commerce"
    order_status_codes.steward = "Priya Sharma"
    order_status_codes.certification = "VERIFIED"
    order_status_codes.tags = "reference,lookup,codes"

    salesforce = _create_source(
        db, "Salesforce CRM", "salesforce", organization_id,
        {"instance_url": "https://demo-org.my.salesforce.com", "api_version": "v60.0"},
    )

    ingest_dataset_info(db, salesforce, {
        "schema_name": "salesforce",
        "table_name": "leads",
        "columns": [
            ("lead_id", "integer", "NO"),
            ("company_name", "varchar", "YES"),
            ("contact_email", "varchar", "YES"),
            ("lead_source", "varchar", "YES"),
            ("lead_status", "varchar", "YES"),
        ],
        "row_count": 300,
        "column_stats": {
            "lead_id": {"non_null": 300, "distinct": 300},
            "company_name": {"non_null": 290, "distinct": 270},
            "contact_email": {"non_null": 300, "distinct": 300},
            "lead_source": {"non_null": 300, "distinct": 5},
            "lead_status": {"non_null": 300, "distinct": 4},
        },
        "column_samples": {
            "lead_id": [str(i) for i in range(1, 9)],
            "company_name": ["Acme Corp", "Globex", "Initech", "Umbrella Inc"],
            "contact_email": customer_emails[:6],
            "lead_source": ["webinar", "referral", "ads", "outbound"],
            "lead_status": ["qualified", "new", "contacted", "converted"],
        },
    }, current_user)

    ingest_dataset_info(db, salesforce, {
        "schema_name": "salesforce",
        "table_name": "opportunities",
        "columns": [
            ("opportunity_id", "integer", "NO"),
            ("account_name", "varchar", "YES"),
            ("amount", "numeric", "YES"),
            ("stage", "varchar", "YES"),
            ("close_date", "date", "YES"),
        ],
        "row_count": 150,
        "column_stats": {
            "opportunity_id": {"non_null": 150, "distinct": 150},
            "account_name": {"non_null": 150, "distinct": 140},
            "amount": {"non_null": 150, "distinct": 130},
            "stage": {"non_null": 150, "distinct": 5},
            "close_date": {"non_null": 120, "distinct": 90},
        },
        "column_samples": {
            "opportunity_id": [str(i) for i in range(1, 9)],
            "account_name": ["Acme Corp", "Globex", "Initech"],
            "amount": ["12000.00", "45000.00", "8000.00"],
            "stage": ["negotiation", "closed_won", "closed_lost", "proposal"],
            "close_date": ["2025-06-01", "2025-07-15"],
        },
    }, current_user)

    leads = _get_dataset(db, organization_id, "salesforce", "leads")
    opportunities = _get_dataset(db, organization_id, "salesforce", "opportunities")
    leads.owner = "Sales Ops"
    leads.domain = "Sales"
    leads.tags = "crm,leads"
    # A source nobody has rescanned in over a month - one of the two
    # non-FRESH freshness outcomes this demo shows.
    leads.last_scanned_at = datetime.utcnow() - timedelta(days=35)
    opportunities.owner = "Sales Ops"
    opportunities.domain = "Sales"
    opportunities.tags = "crm,opportunities"

    zendesk = _create_source(
        db, "Zendesk Support", "zendesk", organization_id,
        {"subdomain": "demo-org", "api_token_name": "metadata-platform-readonly"},
    )

    ingest_dataset_info(db, zendesk, {
        "schema_name": "support",
        "table_name": "tickets",
        "columns": [
            ("ticket_id", "integer", "NO"),
            ("customer_email", "varchar", "YES"),
            ("subject", "varchar", "YES"),
            ("priority", "varchar", "YES"),
            ("status", "varchar", "YES"),
            ("created_at", "timestamp", "YES"),
        ],
        "row_count": 800,
        "column_stats": {
            "ticket_id": {"non_null": 800, "distinct": 800},
            "customer_email": {"non_null": 760, "distinct": 500},
            "subject": {"non_null": 800, "distinct": 700},
            "priority": {"non_null": 800, "distinct": 4},
            "status": {"non_null": 800, "distinct": 3},
            "created_at": {"non_null": 800, "distinct": 780},
        },
        "column_samples": {
            "ticket_id": [str(i) for i in range(1, 9)],
            "customer_email": customer_emails[:6],
            "subject": ["Refund request", "Login issue", "Late delivery", "Billing question"],
            "priority": ["low", "medium", "high", "urgent"],
            "status": ["open", "pending", "closed"],
            "created_at": ["2025-05-01T08:00:00", "2025-05-14T12:00:00"],
        },
    }, current_user)

    tickets = _get_dataset(db, organization_id, "support", "tickets")
    tickets.owner = "Customer Success"
    tickets.domain = "Support"
    tickets.tags = "support,tickets"
    # No description and one PII column (customer_email) puts this at
    # exactly MEDIUM sensitivity - the third governance outcome this
    # demo shows (REVIEW_REQUIRED), distinct from payments' CRITICAL
    # and customers' HEALTHY.
    tickets.description = None
    tickets.last_scanned_at = datetime.utcnow() - timedelta(days=10)

    # ---------------------------------------------------------------
    # Privacy: retention, consent, and purpose - filled out on some
    # datasets and deliberately left at their defaults on others (like
    # tickets, above), so the Privacy Dashboard and Reference Data
    # Repository have a real coverage gap to surface rather than
    # either a uniformly complete or uniformly empty picture.
    # ---------------------------------------------------------------

    customers.purpose = "Customer relationship management and order fulfillment."
    customers.consent_status = "CONSENT_OBTAINED"
    customers.retention_period_days = 1825
    customers.retention_notes = "Retained for the life of the account plus 3 years for finance record-keeping."

    payments.purpose = "Payment processing and fraud prevention."
    # Contractual necessity, not marketing consent - reflected here as
    # "not required" rather than leaving it unassessed, since someone
    # has actually made that determination for this table.
    payments.consent_status = "CONSENT_NOT_REQUIRED"
    payments.retention_period_days = 2555
    payments.retention_notes = "Retained 7 years to satisfy financial audit and tax requirements."

    leads.purpose = "Sales pipeline development and outreach."
    leads.consent_status = "CONSENT_OBTAINED"
    leads.retention_period_days = 730
    leads.retention_notes = "Reassessed at 2 years - stale leads beyond this point are purged."

    db.flush()

    # ---------------------------------------------------------------
    # Layer 1b: A vendor-supplied feed - not one of our own front-office
    # apps, but a third party's CSV export ingested as-is. This is the
    # seed for the "our vendors are inconsistent" story: nobody at our
    # company caused this mess, it arrived this way, and it's what the
    # data contract + lineage-breach-propagation machinery exists to
    # catch before it reaches a report - see the contract and the
    # downstream dbt/Tableau nodes built from this dataset below.
    # ---------------------------------------------------------------

    vendor_feed = _create_source(
        db, "Acme Vendor Product Feed (CSV)", "csv", organization_id,
        {"filename": "acme_product_export.csv", "uploaded_by": current_user.email},
    )

    ingest_dataset_info(db, vendor_feed, {
        "schema_name": "vendor_feeds",
        "table_name": "acme_product_feed",
        "columns": [
            ("vendor_sku", "varchar", "NO"),
            ("product_name", "varchar", "YES"),
            ("category", "varchar", "YES"),
            ("unit_price", "numeric", "YES"),
            ("in_stock_qty", "integer", "YES"),
            ("vendor_contact_email", "varchar", "YES"),
            ("last_updated", "varchar", "YES"),
        ],
        "row_count": 800,
        # Messy in a different way than payments: this isn't our own
        # system under-populating a field, it's a vendor exporting a
        # CSV with no schema enforced on their end - mixed price
        # formats ("TBD", "call for price"), a stock count that's
        # sometimes text instead of a number, sparse categorization,
        # and a contact field that's supposed to be an email but often
        # isn't. Looks fine in a spreadsheet preview; only shows up as
        # a real problem once profiled.
        "column_stats": {
            "vendor_sku": {"non_null": 800, "distinct": 650},
            "product_name": {"non_null": 700, "distinct": 680},
            "category": {"non_null": 500, "distinct": 12},
            "unit_price": {"non_null": 750, "distinct": 300},
            "in_stock_qty": {"non_null": 600, "distinct": 80},
            "vendor_contact_email": {"non_null": 400, "distinct": 390},
            "last_updated": {"non_null": 550, "distinct": 500},
        },
        "column_samples": {
            "vendor_sku": ["ACM-1001", "acm-1002", "ACM-1003", "ACM-1001", "ACM-1004"],
            "product_name": ["Steel Bracket 4in", "Steel Bracket 4in ", "Widget Mount", None],
            "category": ["Hardware", "Hardware", None, None, "Fasteners", None],
            "unit_price": ["12.99", "8.50", "TBD", "call for price", "45.00", "N/A", "22.10", "6.75"],
            "in_stock_qty": ["120", "45", "out of stock", "N/A", "0", "88", "discontinued", "15"],
            "vendor_contact_email": [
                "orders@acmesupply.example", "N/A", "unknown", "sales@acmesupply.example",
                "no email provided", "billing", "support@acmesupply.example", "n/a",
            ],
            "last_updated": ["2025-06-01", "06/02/2025", "2 weeks ago", "2025-06-15T10:00:00"],
        },
    }, current_user)

    vendor_products = _get_dataset(db, organization_id, "vendor_feeds", "acme_product_feed")
    vendor_products.owner = "Procurement"
    vendor_products.domain = "Product"
    # No steward, same shape as payments above - nobody is actually
    # accountable for a vendor's own export, which is exactly the
    # governance gap this scenario exists to surface.
    vendor_products.steward = None
    vendor_products.tags = "vendor,product,inventory"
    vendor_products.purpose = "Third-party product catalog and inventory sync."
    vendor_products.consent_status = "CONSENT_NOT_REQUIRED"

    db.flush()

    # ---------------------------------------------------------------
    # Layer 2: Data processing - a dbt-modeled analytics warehouse,
    # ingested through the real dbt artifact pipeline.
    # ---------------------------------------------------------------

    dbt_source = _create_source(
        db, "Analytics Warehouse (dbt)", "dbt", organization_id,
        {"manifest_filename": "manifest.json", "catalog_filename": "catalog.json", "uploaded_by": current_user.email},
    )

    def _node(schema, name, description, columns, depends_on, compiled_sql):
        return {
            "resource_type": "model",
            "name": name,
            "alias": name,
            "schema": schema,
            "description": description,
            "columns": {c: {"name": c} for c in columns},
            "depends_on": {"nodes": [f"model.analytics.{d}" for d in depends_on]},
            "compiled_code": compiled_sql,
        }

    def _catalog_node(columns_with_types, row_count):
        return {
            "columns": {
                name: {"name": name, "type": dtype, "index": i}
                for i, (name, dtype) in enumerate(columns_with_types, start=1)
            },
            "stats": {"row_count": {"value": row_count}},
        }

    manifest = {
        "nodes": {
            "model.analytics.stg_customers": _node(
                "analytics_staging", "stg_customers", "Cleaned, deduplicated customer records.",
                ["customer_id", "full_name", "email", "phone_number"], [],
                "select customer_id, full_name, lower(email) as email, phone_number from raw.customers",
            ),
            "model.analytics.stg_orders": _node(
                "analytics_staging", "stg_orders", "Cleaned order records.",
                ["order_id", "customer_id", "order_date", "total_amount"], [],
                "select order_id, customer_id, order_date, total_amount from raw.orders where status != 'cancelled'",
            ),
            "model.analytics.stg_payments": _node(
                "analytics_staging", "stg_payments", "Cleaned payment records.",
                ["payment_id", "order_id", "card_number", "amount"], [],
                "select payment_id, order_id, card_number, amount from raw.payments",
            ),
            "model.analytics.dim_customers": _node(
                "analytics_marts", "dim_customers", "Customer dimension for reporting, one row per customer.",
                ["customer_id", "full_name", "email", "lifetime_value"], ["stg_customers"],
                "select c.customer_id, c.full_name, c.email, sum(o.total_amount) as lifetime_value "
                "from stg_customers c left join stg_orders o using (customer_id) group by 1, 2, 3",
            ),
            "model.analytics.fct_customer_orders": _node(
                "analytics_marts", "fct_customer_orders", "One row per order, joined with customer and masked payment info.",
                ["order_id", "customer_id", "customer_email", "order_total", "masked_card_last4"],
                ["stg_customers", "stg_orders", "stg_payments"],
                "select o.order_id, o.customer_id, c.email as customer_email, "
                "cast(o.total_amount as decimal(10,2)) as order_total, "
                "right(p.card_number, 4) as masked_card_last4 "
                "from stg_orders o join stg_customers c using (customer_id) "
                "join stg_payments p using (order_id)",
            ),
            "model.analytics.stg_vendor_products": _node(
                "analytics_staging", "stg_vendor_products", "Vendor product feed, passed through as-is - cleaning happens downstream, not here.",
                ["sku", "product_name", "category", "unit_price", "in_stock_qty"], [],
                "select vendor_sku as sku, product_name, category, unit_price, in_stock_qty "
                "from raw.acme_product_feed",
            ),
            "model.analytics.dim_products": _node(
                "analytics_marts", "dim_products", "Product dimension for reporting, one row per vendor SKU.",
                ["sku", "product_name", "category", "unit_price", "in_stock_qty"],
                ["stg_vendor_products"],
                "select sku, product_name, category, unit_price, in_stock_qty from stg_vendor_products",
            ),
        }
    }

    catalog = {
        "nodes": {
            "model.analytics.stg_customers": _catalog_node(
                [("customer_id", "INTEGER"), ("full_name", "VARCHAR"), ("email", "VARCHAR"), ("phone_number", "VARCHAR")], 500,
            ),
            "model.analytics.stg_orders": _catalog_node(
                [("order_id", "INTEGER"), ("customer_id", "INTEGER"), ("order_date", "TIMESTAMP"), ("total_amount", "NUMERIC")], 1150,
            ),
            "model.analytics.stg_payments": _catalog_node(
                [("payment_id", "INTEGER"), ("order_id", "INTEGER"), ("card_number", "VARCHAR"), ("amount", "NUMERIC")], 1200,
            ),
            "model.analytics.dim_customers": _catalog_node(
                [("customer_id", "INTEGER"), ("full_name", "VARCHAR"), ("email", "VARCHAR"), ("lifetime_value", "NUMERIC")], 500,
            ),
            "model.analytics.fct_customer_orders": _catalog_node(
                [
                    ("order_id", "INTEGER"), ("customer_id", "INTEGER"), ("customer_email", "VARCHAR"),
                    ("order_total", "NUMERIC"), ("masked_card_last4", "VARCHAR"),
                ], 1150,
            ),
            "model.analytics.stg_vendor_products": _catalog_node(
                [
                    ("sku", "VARCHAR"), ("product_name", "VARCHAR"), ("category", "VARCHAR"),
                    ("unit_price", "NUMERIC"), ("in_stock_qty", "INTEGER"),
                ], 800,
            ),
            "model.analytics.dim_products": _catalog_node(
                [
                    ("sku", "VARCHAR"), ("product_name", "VARCHAR"), ("category", "VARCHAR"),
                    ("unit_price", "NUMERIC"), ("in_stock_qty", "INTEGER"),
                ], 650,
            ),
        }
    }

    ingest_dbt_project(db, dbt_source, manifest, catalog, current_user)

    stg_customers = _get_dataset(db, organization_id, "analytics_staging", "stg_customers")
    stg_orders = _get_dataset(db, organization_id, "analytics_staging", "stg_orders")
    stg_payments = _get_dataset(db, organization_id, "analytics_staging", "stg_payments")
    dim_customers = _get_dataset(db, organization_id, "analytics_marts", "dim_customers")
    fct_customer_orders = _get_dataset(db, organization_id, "analytics_marts", "fct_customer_orders")
    stg_vendor_products = _get_dataset(db, organization_id, "analytics_staging", "stg_vendor_products")
    dim_products = _get_dataset(db, organization_id, "analytics_marts", "dim_products")

    for ds in (stg_customers, stg_orders, stg_payments, dim_customers, fct_customer_orders, stg_vendor_products, dim_products):
        ds.owner = "Analytics Engineering"
        ds.domain = "Analytics"

    # dim_customers and fct_customer_orders are derived, downstream
    # copies of the customers/orders systems of record above - not
    # where those entities are created or corrected, so they're
    # tagged as the reference (not record) copy for their entity.
    dim_customers.system_role = "SYSTEM_OF_REFERENCE"
    fct_customer_orders.system_role = "SYSTEM_OF_REFERENCE"

    # The dbt lineage above only connects dbt models to each other -
    # it has no way to know about the raw front-office tables that
    # feed the staging layer, since those aren't dbt models. That's
    # exactly what a real "EL" (extract-load) pipeline covers, so
    # those edges are documented here instead.
    _link(db, customers, stg_customers, "ETL_INGESTION", "Nightly EL job copies raw customer records into the staging schema.")
    _link(db, orders, stg_orders, "ETL_INGESTION", "Nightly EL job copies raw order records into the staging schema.")
    _link(db, payments, stg_payments, "ETL_INGESTION", "Nightly EL job copies raw payment records into the staging schema.")
    _link(db, leads, stg_customers, "ETL_INGESTION", "CRM leads are matched against confirmed customers by email during the nightly merge.")
    _link(db, vendor_products, stg_vendor_products, "ETL_INGESTION", "Nightly EL job loads the vendor's CSV export into the staging schema, unmodified.")

    _link_columns(db, customers, "email", stg_customers, "email", "PASSTHROUGH")
    _link_columns(db, leads, "contact_email", stg_customers, "email", "MERGE", "CRM lead matched to an existing customer by email.")
    _link_columns(db, stg_customers, "email", dim_customers, "email", "PASSTHROUGH")
    _link_columns(db, stg_customers, "email", fct_customer_orders, "customer_email", "PASSTHROUGH")
    _link_columns(db, orders, "total_amount", stg_orders, "total_amount", "PASSTHROUGH")
    _link_columns(db, stg_orders, "total_amount", fct_customer_orders, "order_total", "CAST", "CAST(total_amount AS DECIMAL(10,2)) AS order_total")
    _link_columns(db, payments, "card_number", stg_payments, "card_number", "PASSTHROUGH")
    _link_columns(
        db, stg_payments, "card_number", fct_customer_orders, "masked_card_last4", "MASK",
        "RIGHT(card_number, 4) AS masked_card_last4 - PCI-DSS masking applied at the mart layer, "
        "so the raw card number never reaches a report.",
    )

    # The lineage edge above *documents* the masking transformation -
    # this is what actually turns column masking on for the column,
    # so the Data Owner masking capability has a real example to show
    # rather than only a paper trail of it having happened upstream.
    masked_card_last4 = _get_column(db, fct_customer_orders, "masked_card_last4")
    masked_card_last4.masked = True

    _link_columns(db, vendor_products, "vendor_sku", stg_vendor_products, "sku", "PASSTHROUGH")
    _link_columns(db, vendor_products, "unit_price", stg_vendor_products, "unit_price", "PASSTHROUGH")
    _link_columns(db, vendor_products, "in_stock_qty", stg_vendor_products, "in_stock_qty", "PASSTHROUGH")
    _link_columns(db, stg_vendor_products, "sku", dim_products, "sku", "PASSTHROUGH")
    _link_columns(db, stg_vendor_products, "unit_price", dim_products, "unit_price", "PASSTHROUGH")
    _link_columns(db, stg_vendor_products, "in_stock_qty", dim_products, "in_stock_qty", "PASSTHROUGH")

    db.flush()

    # ---------------------------------------------------------------
    # Layer 3: Reporting - Tableau workbooks, ingested through the
    # real Tableau Metadata API pipeline.
    # ---------------------------------------------------------------

    tableau_source = _create_source(
        db, "Tableau Cloud - Analytics Site", "tableau", organization_id,
        {"server_url": "https://10ax.online.tableau.com", "site_content_url": "demo-org", "token_name": "metadata-platform"},
    )

    ingest_tableau_workbooks(db, tableau_source, [
        {
            "luid": "wb-revenue", "name": "Revenue Dashboard", "project_name": "Executive Reporting",
            "upstream_tables": [{"schema": "analytics_marts", "name": "fct_customer_orders"}],
        },
        {
            "luid": "wb-360", "name": "Customer 360", "project_name": "Customer Success",
            "upstream_tables": [
                {"schema": "analytics_marts", "name": "dim_customers"},
                {"schema": "support", "name": "tickets"},
            ],
        },
        {
            "luid": "wb-sla", "name": "Support SLA Report", "project_name": "Customer Success",
            "upstream_tables": [{"schema": "support", "name": "tickets"}],
        },
        {
            "luid": "wb-vendor-quality", "name": "Vendor Product Catalog Health", "project_name": "Procurement Analytics",
            "upstream_tables": [{"schema": "analytics_marts", "name": "dim_products"}],
        },
    ], current_user)

    revenue_dashboard = _get_dataset(db, organization_id, "Executive Reporting", "Revenue Dashboard")
    customer_360 = _get_dataset(db, organization_id, "Customer Success", "Customer 360")
    support_sla_report = _get_dataset(db, organization_id, "Customer Success", "Support SLA Report")
    vendor_catalog_health = _get_dataset(db, organization_id, "Procurement Analytics", "Vendor Product Catalog Health")

    for ds in (revenue_dashboard, customer_360, support_sla_report, vendor_catalog_health):
        ds.owner = "BI Team"
        ds.domain = "Reporting"

    _link_columns(
        db, fct_customer_orders, "order_total", revenue_dashboard, "total_revenue", "AGGREGATION",
        "SUM(order_total) grouped by month, shown on the dashboard's headline revenue chart.",
    )
    _link_columns(
        db, dim_products, "unit_price", vendor_catalog_health, "avg_unit_price", "AGGREGATION",
        "AVG(unit_price) grouped by category, shown on the catalog health scorecard - inherits "
        "every quality problem already present in the raw vendor feed three hops upstream.",
    )

    db.flush()

    # ---------------------------------------------------------------
    # Audit log variety - the real ingestion pipelines above don't log
    # source.create themselves (that's done at the API-route layer for
    # a live scan/upload, which this seeder bypasses), so without this
    # the Audit Log page would only ever show two rows: demo.seed and
    # the payments contract breach. Logged here, once per source, so
    # the trail has the same shape a series of real connections would.
    # ---------------------------------------------------------------

    for source in (storefront, salesforce, zendesk, vendor_feed, dbt_source, tableau_source):
        log_audit_event(
            db,
            organization_id=organization_id,
            action="source.create",
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            resource_type="data_source",
            resource_id=source.id,
            details=f"Connected source '{source.name}' ({source.type}).",
        )

    # ---------------------------------------------------------------
    # Data contracts - one compliant, one breached.
    # ---------------------------------------------------------------

    compliant_contract = DataContract(
        dataset_id=fct_customer_orders.id,
        version=1,
        status="ACTIVE",
        owner="Analytics Engineering",
        schema_expectations={"columns": [
            {"name": "order_id", "data_type": "integer", "required": True},
            {"name": "customer_id", "data_type": "integer", "required": True},
            {"name": "order_total", "data_type": "numeric", "required": True},
        ]},
        freshness_sla_hours=24,
    )
    db.add(compliant_contract)

    breached_contract = DataContract(
        dataset_id=payments.id,
        version=1,
        status="ACTIVE",
        owner="Payments Platform",
        schema_expectations={"columns": [
            {"name": "payment_id", "data_type": "integer", "required": True},
            {"name": "amount", "data_type": "numeric", "required": True},
            {"name": "payment_method", "data_type": "varchar", "required": True, "nullable": False},
            {"name": "refund_status", "data_type": "varchar", "required": True},
        ]},
        # Stacked with the missing-column violation on purpose - this
        # contract breaches on both a schema check *and* the DQ
        # threshold enforcement, so evaluate_contract's quality_thresholds
        # path (not just schema_expectations) has a real breach to show,
        # given payments' deliberately messy profiled score below 85.
        quality_thresholds={"min_overall_score": 85},
        freshness_sla_hours=12,
    )
    db.add(breached_contract)

    # A third contract, on the vendor feed - also stacked (missing
    # required column + DQ threshold), so the breach this scenario is
    # built around exists at the very top of the chain, before
    # get_upstream_contract_breaches() ever needs to look downstream.
    vendor_contract = DataContract(
        dataset_id=vendor_products.id,
        version=1,
        status="ACTIVE",
        owner="Procurement",
        schema_expectations={"columns": [
            {"name": "vendor_sku", "data_type": "varchar", "required": True},
            {"name": "unit_price", "data_type": "numeric", "required": True},
            {"name": "return_policy_url", "data_type": "varchar", "required": True},
        ]},
        quality_thresholds={"min_overall_score": 85},
        freshness_sla_hours=24,
    )
    db.add(vendor_contract)

    db.flush()

    log_audit_event(
        db,
        organization_id=organization_id,
        action="contract.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=fct_customer_orders.id,
        details=f"Created data contract v1 for '{fct_customer_orders.schema_name}.{fct_customer_orders.name}'.",
    )
    log_audit_event(
        db,
        organization_id=organization_id,
        action="contract.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=payments.id,
        details=f"Created data contract v1 for '{payments.schema_name}.{payments.name}'.",
    )
    log_audit_event(
        db,
        organization_id=organization_id,
        action="contract.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=vendor_products.id,
        details=f"Created data contract v1 for '{vendor_products.schema_name}.{vendor_products.name}'.",
    )

    # evaluate_contract() itself logs contract.breach when a contract
    # comes out BREACHED (see data_contract_service.py) - only the
    # creation above needs logging explicitly here.
    evaluate_contract(db, fct_customer_orders, actor_user_id=current_user.id, actor_email=current_user.email)
    evaluate_contract(db, payments, actor_user_id=current_user.id, actor_email=current_user.email)
    evaluate_contract(db, vendor_products, actor_user_id=current_user.id, actor_email=current_user.email)

    # ---------------------------------------------------------------
    # Team roster - a few more accounts with different roles, so the
    # Team page has a real mixed-role list to show and so the risks,
    # controls, and discussion threads below can be owned/raised by
    # someone other than whoever clicked "Load Demo Data." All share
    # the same fixed demo password; see clear_demo_data for why these
    # are deactivated, not deleted, when the demo is cleared.
    # ---------------------------------------------------------------

    # User.email is globally unique (not scoped per organization), so
    # each org's demo accounts need their own addresses - a short slug
    # of this org's id keeps them readable while guaranteeing no
    # collision between two orgs that both load the demo.
    org_slug = organization_id.replace("-", "")[:8]
    steward_member = _team_member(
        db, organization_id, f"priya.sharma+{org_slug}@demo-datafe.example", "steward"
    )
    data_owner_member = _team_member(
        db, organization_id, f"marcus.webb+{org_slug}@demo-datafe.example", "data_owner"
    )
    viewer_member = _team_member(
        db, organization_id, f"jamie.lin+{org_slug}@demo-datafe.example", "viewer"
    )

    for member, role in (
        (steward_member, "steward"), (data_owner_member, "data_owner"), (viewer_member, "viewer"),
    ):
        log_audit_event(
            db,
            organization_id=organization_id,
            action="user.invite",
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            resource_type="user",
            resource_id=member.id,
            details=f"Invited {member.email} as {role}.",
        )

    # ---------------------------------------------------------------
    # Certification queue + a governance discussion tied to the
    # contract breach above, so the story is connected end to end.
    # ---------------------------------------------------------------

    certification_request = CertificationRequest(
        dataset_id=dim_customers.id,
        requested_by=current_user.id,
        request_note="Lineage and data quality both look solid - ready to certify for exec dashboard use.",
        status="PENDING",
        created_at=datetime.utcnow(),
    )
    db.add(certification_request)

    log_audit_event(
        db,
        organization_id=organization_id,
        action="certification.request",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dim_customers.id,
        details=f"Requested certification for '{dim_customers.schema_name}.{dim_customers.name}'.",
    )

    for certified in (customers, order_status_codes):
        log_audit_event(
            db,
            organization_id=organization_id,
            action="governance.certify",
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            resource_type="dataset",
            resource_id=certified.id,
            details=f"Certified '{certified.schema_name}.{certified.name}' as VERIFIED.",
        )

    thread = GovernanceThread(
        organization_id=organization_id,
        dataset_id=payments.id,
        thread_type="QUESTION",
        title="Why is payments missing a refund_status column?",
        body=(
            "The new data contract on this table just flagged a breach - "
            "should refund_status be added upstream, or should refunds "
            "live in a separate table entirely?"
        ),
        status="OPEN",
        created_by=current_user.id,
        created_at=datetime.utcnow() - timedelta(hours=3),
    )
    db.add(thread)
    db.flush()

    db.add(GovernanceThreadReply(
        thread_id=thread.id,
        body="Good catch - opening a ticket with the storefront team to add this column next sprint.",
        created_by=current_user.id,
        created_at=datetime.utcnow() - timedelta(hours=1),
    ))

    # A PROPOSAL thread - the second of the three discussion types,
    # not tied to a breach, just someone suggesting a change.
    proposal_thread = GovernanceThread(
        organization_id=organization_id,
        dataset_id=dim_customers.id,
        thread_type="PROPOSAL",
        title="Proposal: certify dim_customers once the pending request clears",
        body=(
            "Now that customers and order_status_codes are both VERIFIED, dim_customers "
            "is the natural next certification - it's the dimension every exec dashboard "
            "joins against."
        ),
        status="OPEN",
        created_by=steward_member.id,
        created_at=datetime.utcnow() - timedelta(days=1, hours=2),
    )
    db.add(proposal_thread)

    # An ISSUE thread with a stakeholder explicitly raised_for - the
    # third discussion type, and the one where that field actually
    # gets used (see governance_thread.py's docstring on the field).
    issue_thread = GovernanceThread(
        organization_id=organization_id,
        dataset_id=tickets.id,
        thread_type="ISSUE",
        title="tickets has no steward and no description",
        body=(
            "This dataset carries customer PII (customer_email) but nobody's assigned to "
            "own it, which is why it's sitting at REVIEW_REQUIRED. Flagging for Customer "
            "Success to pick up."
        ),
        status="OPEN",
        created_by=data_owner_member.id,
        raised_for_user_id=steward_member.id,
        created_at=datetime.utcnow() - timedelta(hours=6),
    )
    db.add(issue_thread)

    # A second ISSUE thread, on the vendor feed - the breach traced
    # all the way to a downstream report is the punchline, so the
    # thread body says so explicitly rather than leaving it implicit.
    vendor_issue_thread = GovernanceThread(
        organization_id=organization_id,
        dataset_id=vendor_products.id,
        thread_type="ISSUE",
        title="Acme's product feed keeps breaching contract - do we need a stricter vendor SLA?",
        body=(
            "Price and stock fields are inconsistently formatted in almost every export, and "
            "nobody's assigned as steward to chase Acme about it. The breach is now visible on "
            "Vendor Product Catalog Health too, not just the raw feed - it's reaching the report "
            "our category managers actually look at. Procurement should own getting this fixed "
            "at the source, not us re-cleaning it every load."
        ),
        status="OPEN",
        created_by=steward_member.id,
        raised_for_user_id=data_owner_member.id,
        created_at=datetime.utcnow() - timedelta(hours=4),
    )
    db.add(vendor_issue_thread)

    # ---------------------------------------------------------------
    # Usage signal, so the popularity story shows something too.
    # ---------------------------------------------------------------

    now = datetime.utcnow()
    for ds, offsets in (
        (customers, [0, 1, 3]),
        (fct_customer_orders, [0, 2]),
        (revenue_dashboard, [0, 1, 4, 6]),
    ):
        for hours_ago in offsets:
            db.add(DatasetView(
                dataset_id=ds.id,
                user_id=current_user.id,
                viewed_at=now - timedelta(hours=hours_ago),
            ))

    # ---------------------------------------------------------------
    # Business Glossary <-> technical catalog links, and the "process
    # dimension" - business processes datasets get tagged with. This
    # is the part of the demo that shows the catalog, glossary, and
    # ownership actually connected for a business reader, not three
    # separate silos: open any of these datasets' Business View tab
    # and the term definitions, owning process, quality, lineage, and
    # contract status are all in one place.
    # ---------------------------------------------------------------

    customer_term = _glossary_term(
        db, organization_id, "Customer",
        "A person or company that has purchased, or registered interest in purchasing, from us.",
        "Sales", "Data Governance",
    )
    _link_term(db, customer_term, customers)
    _link_term(db, customer_term, dim_customers)

    clv_term = _glossary_term(
        db, organization_id, "Customer Lifetime Value",
        "The total revenue attributed to a customer across all of their orders to date.",
        "Finance", "FP&A",
    )
    _link_term(db, clv_term, dim_customers, _get_column(db, dim_customers, "lifetime_value"))

    order_total_term = _glossary_term(
        db, organization_id, "Order Total",
        "The final charged amount for a single order, in the customer's billing currency.",
        "Finance", "FP&A",
    )
    _link_term(db, order_total_term, fct_customer_orders, _get_column(db, fct_customer_orders, "order_total"))

    masked_card_term = _glossary_term(
        db, organization_id, "Masked Card Number",
        "The last four digits only of the card used for payment - PCI-DSS masking is applied "
        "before this reaches the analytics mart, so the full card number never appears here.",
        "Payments", "Payments Platform",
    )
    _link_term(
        db, masked_card_term, fct_customer_orders,
        _get_column(db, fct_customer_orders, "masked_card_last4"),
    )

    support_term = _glossary_term(
        db, organization_id, "Support Ticket",
        "A single customer-reported issue or question tracked from open to resolution.",
        "Support", "Customer Success",
    )
    _link_term(db, support_term, tickets)

    sku_term = _glossary_term(
        db, organization_id, "SKU",
        "The vendor's own stock-keeping unit identifier for a product - not normalized "
        "against any internal product ID, so casing/format drift (e.g. 'ACM-1001' vs "
        "'acm-1002') is expected here rather than treated as an upstream bug.",
        "Product", "Procurement",
    )
    _link_term(db, sku_term, vendor_products, _get_column(db, vendor_products, "vendor_sku"))
    _link_term(db, sku_term, dim_products)

    order_to_cash = _business_process(
        db, organization_id, "Order-to-Cash",
        "Everything from a customer placing an order through to payment being collected and reconciled.",
        "Revenue Ops",
        narrative=(
            "A Customer (Master data) places an Order (Transactional data), which is "
            "settled through a Payment (Transactional data). Those transactions roll up "
            "into fct_customer_orders and the Revenue Dashboard (Analytical data)."
        ),
    )
    for ds in (orders, payments, stg_orders, stg_payments, fct_customer_orders, revenue_dashboard):
        _link_process(db, order_to_cash, ds)

    customer_onboarding = _business_process(
        db, organization_id, "Customer Onboarding",
        "From a lead's first contact through to becoming a confirmed, recognized customer.",
        "Growth Team",
    )
    for ds in (leads, customers, stg_customers, dim_customers, customer_360):
        _link_process(db, customer_onboarding, ds)

    customer_support = _business_process(
        db, organization_id, "Customer Support",
        "Handling customer-reported issues from intake through resolution and SLA reporting.",
        "Customer Success",
    )
    for ds in (tickets, customer_360, support_sla_report):
        _link_process(db, customer_support, ds)

    vendor_catalog_sync = _business_process(
        db, organization_id, "Vendor Catalog Sync",
        "Ingesting and reconciling a third-party vendor's product feed into our own product "
        "catalog and reporting.",
        "Procurement",
        narrative=(
            "Acme (an external vendor we don't control) exports a product feed we treat as "
            "Reference-like input data. It's loaded as-is into stg_vendor_products, rolled up "
            "into the dim_products (Analytical) mart, and reported on in Vendor Product "
            "Catalog Health - any quality problem in Acme's export is visible at every stop "
            "along this chain, not just at the source."
        ),
    )
    for ds in (vendor_products, stg_vendor_products, dim_products, vendor_catalog_health):
        _link_process(db, vendor_catalog_sync, ds)

    # ---------------------------------------------------------------
    # Risk register + control library.
    # ---------------------------------------------------------------

    card_data_risk = _risk(
        db, organization_id,
        "Card data exposure via the payments table",
        "payments carries a raw card_number column with no assigned steward and a "
        "breached data contract - exactly the shape of dataset most likely to leak "
        "sensitive data into a report or export by accident.",
        category="PRIVACY", likelihood="HIGH", impact="HIGH", status="OPEN",
        created_by=current_user.id, owner_user_id=steward_member.id,
    )
    db.add(RiskDatasetLink(risk_id=card_data_risk.id, dataset_id=payments.id))
    db.add(RiskProcessLink(risk_id=card_data_risk.id, process_id=order_to_cash.id))

    masking_control = _control(
        db, organization_id,
        "PCI masking at the analytics layer",
        "fct_customer_orders.masked_card_last4 exposes only the last four digits - the "
        "full card number never reaches the mart or any downstream report.",
        control_type="PREVENTIVE", status="EFFECTIVE",
        created_by=current_user.id, owner_user_id=steward_member.id,
        last_tested_at=datetime.utcnow() - timedelta(days=14),
    )
    access_review_control = _control(
        db, organization_id,
        "Quarterly access review for the payments schema",
        "Who has read access to public.payments is reviewed every quarter; overdue for "
        "this cycle.",
        control_type="DETECTIVE", status="NOT_TESTED",
        created_by=current_user.id, owner_user_id=data_owner_member.id,
    )
    db.add(RiskControlLink(risk_id=card_data_risk.id, control_id=masking_control.id))
    db.add(RiskControlLink(risk_id=card_data_risk.id, control_id=access_review_control.id))

    support_pii_risk = _risk(
        db, organization_id,
        "Free-text PII in support tickets",
        "Ticket subjects and bodies sometimes contain customer PII typed in by agents, "
        "outside of any structured, classified column.",
        category="PRIVACY", likelihood="MEDIUM", impact="MEDIUM", status="MITIGATED",
        created_by=current_user.id, owner_user_id=data_owner_member.id,
    )
    db.add(RiskDatasetLink(risk_id=support_pii_risk.id, dataset_id=tickets.id))
    db.add(RiskProcessLink(risk_id=support_pii_risk.id, process_id=customer_support.id))

    redaction_control = _control(
        db, organization_id,
        "Support ticket redaction review",
        "Sampled review of closed tickets for accidentally-included card numbers or SSNs; "
        "last cycle found gaps in agent training.",
        control_type="CORRECTIVE", status="INEFFECTIVE",
        created_by=current_user.id, owner_user_id=data_owner_member.id,
        last_tested_at=datetime.utcnow() - timedelta(days=45),
    )
    db.add(RiskControlLink(risk_id=support_pii_risk.id, control_id=redaction_control.id))

    lead_quality_risk = _risk(
        db, organization_id,
        "CRM lead records drifting stale",
        "leads hasn't been rescanned in over a month and email/company fields are only "
        "partially populated - low-severity, but worth tracking before it compounds.",
        category="DATA_QUALITY", likelihood="MEDIUM", impact="LOW", status="ACCEPTED",
        created_by=current_user.id, owner_user_id=steward_member.id,
    )
    db.add(RiskDatasetLink(risk_id=lead_quality_risk.id, dataset_id=leads.id))
    db.add(RiskProcessLink(risk_id=lead_quality_risk.id, process_id=customer_onboarding.id))

    vendor_quality_risk = _risk(
        db, organization_id,
        "Vendor product feed quality is unmanaged",
        "acme_product_feed carries inconsistent price formats, partial categorization, and no "
        "assigned steward - its contract is breached on both a schema check and the quality "
        "threshold, and that breach now reaches every downstream product report through "
        "lineage rather than staying contained at the source.",
        category="DATA_QUALITY", likelihood="HIGH", impact="MEDIUM", status="OPEN",
        created_by=current_user.id, owner_user_id=data_owner_member.id,
    )
    db.add(RiskDatasetLink(risk_id=vendor_quality_risk.id, dataset_id=vendor_products.id))
    db.add(RiskProcessLink(risk_id=vendor_quality_risk.id, process_id=vendor_catalog_sync.id))

    vendor_validation_control = _control(
        db, organization_id,
        "Automated vendor feed validation on ingest",
        "Proposed: reject or quarantine a vendor file at upload time if it fails schema/quality "
        "checks, instead of letting a breach reach the report layer first - not yet built, "
        "which is why this control is still NOT_TESTED.",
        control_type="PREVENTIVE", status="NOT_TESTED",
        created_by=current_user.id, owner_user_id=data_owner_member.id,
    )
    db.add(RiskControlLink(risk_id=vendor_quality_risk.id, control_id=vendor_validation_control.id))

    for risk in (card_data_risk, support_pii_risk, lead_quality_risk, vendor_quality_risk):
        log_audit_event(
            db,
            organization_id=organization_id,
            action="risk.create",
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            resource_type="risk",
            resource_id=risk.id,
            details=f"Logged risk '{risk.title}'.",
        )

    for control in (masking_control, access_review_control, redaction_control, vendor_validation_control):
        log_audit_event(
            db,
            organization_id=organization_id,
            action="control.create",
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            resource_type="control",
            resource_id=control.id,
            details=f"Logged control '{control.name}'.",
        )

    # ---------------------------------------------------------------
    # Query log - a handful of realistic Ask/search queries, including
    # one asked three times that never lands, so the admin "Search
    # Insights" report has something concrete to surface: a real
    # candidate for a new intent or glossary entry, not an empty page.
    # ---------------------------------------------------------------

    now_for_queries = datetime.utcnow()
    demo_queries = [
        ("ask", "who owns customers?", True, 1, timedelta(hours=26)),
        ("ask", "what's downstream of payments?", True, 2, timedelta(hours=20)),
        ("ask", "which datasets have PII?", True, 4, timedelta(hours=15)),
        ("ask", "does the shipments dataset have an owner?", False, 0, timedelta(hours=10)),
        ("ask", "does the shipments dataset have an owner?", False, 0, timedelta(hours=5)),
        ("ask", "does the shipments dataset have an owner?", False, 0, timedelta(hours=1)),
        ("search", "payments", True, 3, timedelta(hours=22)),
        ("search", "customer lifetime value", True, 1, timedelta(hours=18)),
        ("search", "refund policy", False, 0, timedelta(hours=8)),
        ("ask", "do we have any contract breaches?", True, 3, timedelta(hours=7)),
        ("ask", "what's downstream of the vendor product feed?", True, 2, timedelta(hours=2)),
    ]
    for source, query_text, matched, result_count, ago in demo_queries:
        db.add(QueryLog(
            organization_id=organization_id,
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            source=source,
            query_text=query_text,
            matched=matched,
            result_count=result_count,
            created_at=now_for_queries - ago,
        ))

    db.flush()

    log_audit_event(
        db,
        organization_id=organization_id,
        action="demo.seed",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="organization",
        resource_id=organization_id,
        details="Loaded demo data: 6 sources, front office -> processing -> reporting.",
    )

    db.commit()

    sources_created = 6
    datasets_created = (
        db.query(Dataset)
        .join(DataSource, Dataset.source_id == DataSource.id)
        .filter(DataSource.organization_id == organization_id, DataSource.is_seed_data.is_(True))
        .count()
    )
    glossary_terms_created = (
        db.query(BusinessGlossaryTerm)
        .filter(
            BusinessGlossaryTerm.organization_id == organization_id,
            BusinessGlossaryTerm.is_seed_data.is_(True),
        )
        .count()
    )
    business_processes_created = (
        db.query(BusinessProcess)
        .filter(
            BusinessProcess.organization_id == organization_id,
            BusinessProcess.is_seed_data.is_(True),
        )
        .count()
    )
    risks_created = (
        db.query(Risk)
        .filter(Risk.organization_id == organization_id, Risk.is_seed_data.is_(True))
        .count()
    )
    controls_created = (
        db.query(Control)
        .filter(Control.organization_id == organization_id, Control.is_seed_data.is_(True))
        .count()
    )
    team_members_created = (
        db.query(User)
        .filter(User.organization_id == organization_id, User.is_seed_data.is_(True))
        .count()
    )

    return {
        "sources_created": sources_created,
        "datasets_created": datasets_created,
        "glossary_terms_created": glossary_terms_created,
        "business_processes_created": business_processes_created,
        "risks_created": risks_created,
        "controls_created": controls_created,
        "team_members_created": team_members_created,
    }


def clear_demo_data(
    db: Session,
    organization_id: str,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
) -> dict:
    """
    Deletes (or, for team members, deactivates - see below) everything
    created by seed_demo_data() for one organization - and nothing
    else, even if a real source happens to share a name with a demo
    one, since matching is entirely by the is_seed_data flag rather
    than by name. Deletes in FK-safe order: everything that references
    a demo Dataset first, then the datasets themselves, then the
    sources; risks/controls/team members are handled in their own
    pass afterward since they're org-scoped rather than
    dataset-scoped, same as glossary terms and business processes.
    AuditLog and QueryLog rows are left in place deliberately - they're
    an append-only historical record, and "loaded/cleared the demo" is
    itself worth keeping a trace of.
    """

    seed_sources = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == organization_id,
            DataSource.is_seed_data.is_(True),
        )
        .all()
    )

    if not seed_sources:
        return {
            "sources_removed": 0,
            "datasets_removed": 0,
            "glossary_terms_removed": 0,
            "business_processes_removed": 0,
            "risks_removed": 0,
            "controls_removed": 0,
            "team_members_deactivated": 0,
        }

    source_ids = [s.id for s in seed_sources]

    dataset_ids = [
        row[0] for row in (
            db.query(Dataset.id)
            .filter(Dataset.source_id.in_(source_ids))
            .all()
        )
    ]

    datasets_removed = len(dataset_ids)

    if dataset_ids:

        thread_ids = [
            row[0] for row in (
                db.query(GovernanceThread.id)
                .filter(GovernanceThread.dataset_id.in_(dataset_ids))
                .all()
            )
        ]

        if thread_ids:
            db.query(GovernanceThreadReply).filter(
                GovernanceThreadReply.thread_id.in_(thread_ids)
            ).delete(synchronize_session=False)

            db.query(GovernanceThread).filter(
                GovernanceThread.id.in_(thread_ids)
            ).delete(synchronize_session=False)

        db.query(CertificationRequest).filter(
            CertificationRequest.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(DatasetView).filter(
            DatasetView.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(DataContract).filter(
            DataContract.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(DataQuality).filter(
            DataQuality.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(ColumnLineage).filter(
            ColumnLineage.upstream_dataset_id.in_(dataset_ids)
            | ColumnLineage.downstream_dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(DatasetLineage).filter(
            DatasetLineage.upstream_dataset_id.in_(dataset_ids)
            | DatasetLineage.downstream_dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        # Both link tables reference dataset_id (and glossary links can
        # also reference column_id) - must go before DatasetColumn/
        # Dataset are deleted below, or those foreign keys would point
        # at rows that no longer exist.
        db.query(GlossaryTermLink).filter(
            GlossaryTermLink.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(BusinessProcessLink).filter(
            BusinessProcessLink.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(RiskDatasetLink).filter(
            RiskDatasetLink.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(DatasetColumn).filter(
            DatasetColumn.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)

        db.query(Dataset).filter(
            Dataset.id.in_(dataset_ids)
        ).delete(synchronize_session=False)

    db.query(DataSource).filter(
        DataSource.id.in_(source_ids)
    ).delete(synchronize_session=False)

    # Glossary terms and business processes belong to the org, not to
    # any one dataset/source, so they're identified and removed by
    # is_seed_data directly rather than through dataset_ids. Their
    # links (to any dataset, demo or otherwise) are already gone from
    # the block above and the equivalent one for business processes,
    # but a term or process could in principle have been linked to a
    # dataset from a *different* demo batch's naming collision - this
    # catches any link row that survived for another reason too.
    seed_term_ids = [
        row[0] for row in (
            db.query(BusinessGlossaryTerm.id)
            .filter(
                BusinessGlossaryTerm.organization_id == organization_id,
                BusinessGlossaryTerm.is_seed_data.is_(True),
            )
            .all()
        )
    ]
    glossary_terms_removed = len(seed_term_ids)

    if seed_term_ids:
        db.query(GlossaryTermLink).filter(
            GlossaryTermLink.term_id.in_(seed_term_ids)
        ).delete(synchronize_session=False)

        db.query(BusinessGlossaryTerm).filter(
            BusinessGlossaryTerm.id.in_(seed_term_ids)
        ).delete(synchronize_session=False)

    seed_process_ids = [
        row[0] for row in (
            db.query(BusinessProcess.id)
            .filter(
                BusinessProcess.organization_id == organization_id,
                BusinessProcess.is_seed_data.is_(True),
            )
            .all()
        )
    ]
    business_processes_removed = len(seed_process_ids)

    if seed_process_ids:
        db.query(BusinessProcessLink).filter(
            BusinessProcessLink.process_id.in_(seed_process_ids)
        ).delete(synchronize_session=False)

        db.query(RiskProcessLink).filter(
            RiskProcessLink.process_id.in_(seed_process_ids)
        ).delete(synchronize_session=False)

        db.query(BusinessProcess).filter(
            BusinessProcess.id.in_(seed_process_ids)
        ).delete(synchronize_session=False)

    # Risks and controls belong to the org, same as glossary terms and
    # business processes - identified by is_seed_data directly. Their
    # link tables (to datasets/processes/each other) are removed first
    # regardless of which side is the demo one, since either a demo
    # risk could reference a real control (unlikely, but not
    # impossible) or vice versa.
    seed_risk_ids = [
        row[0] for row in (
            db.query(Risk.id)
            .filter(Risk.organization_id == organization_id, Risk.is_seed_data.is_(True))
            .all()
        )
    ]
    seed_control_ids = [
        row[0] for row in (
            db.query(Control.id)
            .filter(Control.organization_id == organization_id, Control.is_seed_data.is_(True))
            .all()
        )
    ]
    risks_removed = len(seed_risk_ids)
    controls_removed = len(seed_control_ids)

    if seed_risk_ids or seed_control_ids:
        db.query(RiskControlLink).filter(
            RiskControlLink.risk_id.in_(seed_risk_ids)
            | RiskControlLink.control_id.in_(seed_control_ids)
        ).delete(synchronize_session=False)

    if seed_risk_ids:
        db.query(RiskDatasetLink).filter(
            RiskDatasetLink.risk_id.in_(seed_risk_ids)
        ).delete(synchronize_session=False)

        db.query(RiskProcessLink).filter(
            RiskProcessLink.risk_id.in_(seed_risk_ids)
        ).delete(synchronize_session=False)

        db.query(Risk).filter(Risk.id.in_(seed_risk_ids)).delete(synchronize_session=False)

    if seed_control_ids:
        db.query(Control).filter(Control.id.in_(seed_control_ids)).delete(synchronize_session=False)

    # Team members the demo created are deactivated, not deleted - the
    # same "preferred over hard-deleting" reasoning as the User model's
    # own is_active field: these are real accounts that other rows
    # (owner_user_id on risks/controls above, raised_for_user_id on the
    # ISSUE thread, actor_user_id on audit/query log rows) may still
    # reference, and a real Postgres deployment enforces those foreign
    # keys - deleting the row out from under them would fail. QueryLog
    # and AuditLog rows are left in place for the same "append-only
    # historical record" reason noted below.
    team_members_deactivated = (
        db.query(User)
        .filter(User.organization_id == organization_id, User.is_seed_data.is_(True))
        .update({User.is_active: False}, synchronize_session=False)
    )

    log_audit_event(
        db,
        organization_id=organization_id,
        action="demo.clear",
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        resource_type="organization",
        resource_id=organization_id,
        details=f"Cleared demo data: {len(source_ids)} source(s), {datasets_removed} dataset(s).",
    )

    db.commit()

    return {
        "sources_removed": len(source_ids),
        "datasets_removed": datasets_removed,
        "glossary_terms_removed": glossary_terms_removed,
        "business_processes_removed": business_processes_removed,
        "risks_removed": risks_removed,
        "controls_removed": controls_removed,
        "team_members_deactivated": team_members_deactivated,
    }
