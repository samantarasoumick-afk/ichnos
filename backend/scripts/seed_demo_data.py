"""
One-time script to populate an existing organization with realistic
demo data: sources, datasets, columns (classified through the real
privacy engine, not hand-typed labels), lineage, a business glossary,
data quality profiles, audit log history, and a second team member -
so every page in the app (dashboard, governance, privacy, lineage,
audit log, team) has something real to show.

This is a local dev/demo convenience, not an API endpoint - it's not
something that should ever be exposed over HTTP, so it stays a script
you run once from a terminal.

Usage (from the backend/ directory, with the venv active):
    python3 scripts/seed_demo_data.py --email you@example.com

It seeds data into the *existing* organization that email already
belongs to (it does not create a new org). Refuses to run if that
organization already has any datasets, so it's safe to re-run without
risk of double-seeding - just pass --force to wipe and reseed anyway.
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.main  # noqa: E402  (loads .env, registers every model on Base.metadata)

from app.db.database import SessionLocal  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.source import DataSource  # noqa: E402
from app.models.dataset import Dataset  # noqa: E402
from app.models.column import DatasetColumn  # noqa: E402
from app.models.lineage import DatasetLineage  # noqa: E402
from app.models.governance import BusinessGlossaryTerm  # noqa: E402
from app.models.data_quality import DataQuality  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.utils.privacy_engine import analyze_column  # noqa: E402


def days_ago(n, hour=10):
    return datetime.utcnow() - timedelta(days=n, hours=-hour)


# (dataset_key, schema, name, domain, owner, steward, certification,
#  purpose, consent_status, retention_period_days, description)
DATASETS = [
    ("customers", "public", "customers", "CRM", "Data Platform", "Priya Sharma",
     "VERIFIED", "Customer relationship management and support", "CONSENT_OBTAINED", 730,
     "Core customer records used across sales and support."),
    ("orders", "public", "orders", "Sales", "Data Platform", "Priya Sharma",
     "VERIFIED", "Order fulfillment and revenue reporting", "CONSENT_NOT_REQUIRED", 1095,
     "Order transactions linked to customers and payments."),
    ("payments", "public", "payments", "Finance", "Finance Ops", None,
     "IN_REVIEW", None, "NOT_ASSESSED", None,
     "Payment records including card and bank account references."),
    ("employees", "hr", "employees", "HR", "People Ops", None,
     "DRAFT", None, "NOT_ASSESSED", None,
     "Employee master data including compensation."),
    ("performance_reviews", "hr", "performance_reviews", "HR", "People Ops", "Arjun Mehta",
     "DRAFT", "Annual performance evaluation", "CONSENT_OBTAINED", 1825,
     "Manager-submitted performance review records."),
    ("marketing_campaigns", "analytics", "marketing_campaigns", "Marketing", "Growth Team", "Arjun Mehta",
     "VERIFIED", None, "CONSENT_NOT_REQUIRED", None,
     "Campaign spend and engagement metrics, no personal data."),
    ("support_tickets", "analytics", "support_tickets", "Support", "Support Team", "Priya Sharma",
     "IN_REVIEW", "Customer support case handling", "NOT_ASSESSED", 365,
     "Support tickets including customer contact references."),
    ("product_catalog", "analytics", "product_catalog", "Product", "Product Team", None,
     "VERIFIED", None, "CONSENT_NOT_REQUIRED", None,
     "Product listing data, no personal data."),
    ("audit_trail", "public", "audit_trail", "Platform", "Data Platform", "Priya Sharma",
     "DRAFT", None, "CONSENT_NOT_REQUIRED", None,
     "Internal application event log."),
]

# dataset_key -> [(column_name, data_type, nullable, sample_values), ...]
COLUMNS = {
    "customers": [
        ("customer_id", "integer", False, ["1001", "1002", "1003"]),
        ("full_name", "varchar", False, ["Anita Rao", "Vikram Singh", "Meera Nair"]),
        ("email", "varchar", False, ["anita.rao@example.com", "vikram.singh@example.com"]),
        ("phone", "varchar", True, ["9876543210", "9123456780"]),
        ("date_of_birth", "date", True, ["1988-04-12", "1992-11-03"]),
        ("address", "varchar", True, ["221B MG Road, Bengaluru"]),
        ("created_at", "timestamp", False, []),
    ],
    "orders": [
        ("order_id", "integer", False, ["5001", "5002"]),
        ("customer_id", "integer", False, ["1001", "1002"]),
        ("order_date", "date", False, []),
        ("total_amount", "numeric", False, ["1499.00", "899.50"]),
        ("status", "varchar", False, ["SHIPPED", "PENDING", "DELIVERED"]),
    ],
    "payments": [
        ("payment_id", "integer", False, ["9001", "9002"]),
        ("order_id", "integer", False, ["5001", "5002"]),
        ("card_number", "varchar", True, ["4111 1111 1111 1111", "5500 0000 0000 0004"]),
        ("account_number", "varchar", True, ["000123456789"]),
        ("ifsc", "varchar", True, ["HDFC0001234", "ICIC0000456"]),
        ("amount", "numeric", False, ["1499.00"]),
    ],
    "employees": [
        ("employee_id", "integer", False, ["101", "102"]),
        ("full_name", "varchar", False, ["Karan Patel", "Sneha Iyer"]),
        ("email", "varchar", False, ["karan.patel@company.com"]),
        ("salary", "numeric", False, ["950000", "1200000"]),
        ("date_of_birth", "date", True, ["1990-06-21"]),
        ("aadhaar_number", "varchar", True, ["1234 5678 9012"]),
    ],
    "performance_reviews": [
        ("review_id", "integer", False, ["1", "2"]),
        ("employee_id", "integer", False, ["101", "102"]),
        ("rating", "integer", False, ["4", "5"]),
        ("comments", "text", True, ["Strong quarter, exceeded targets."]),
    ],
    "marketing_campaigns": [
        ("campaign_id", "integer", False, ["1", "2"]),
        ("name", "varchar", False, ["Diwali Sale", "New Year Promo"]),
        ("channel", "varchar", False, ["email", "social"]),
        ("spend", "numeric", False, ["25000.00"]),
        ("clicks", "integer", False, ["4200"]),
    ],
    "support_tickets": [
        ("ticket_id", "integer", False, ["7001", "7002"]),
        ("customer_email", "varchar", False, ["anita.rao@example.com"]),
        ("subject", "varchar", False, ["Refund request"]),
        ("description", "text", True, ["Item arrived damaged."]),
        ("status", "varchar", False, ["OPEN", "CLOSED"]),
    ],
    "product_catalog": [
        ("product_id", "integer", False, ["301", "302"]),
        ("name", "varchar", False, ["Wireless Mouse", "USB-C Cable"]),
        ("category", "varchar", False, ["Electronics"]),
        ("price", "numeric", False, ["799.00"]),
        ("stock", "integer", False, ["120"]),
    ],
    "audit_trail": [
        ("event_id", "integer", False, ["1", "2"]),
        ("user_id", "integer", True, ["1001"]),
        ("action", "varchar", False, ["LOGIN", "UPDATE"]),
        ("ip_address", "varchar", True, ["10.0.0.1"]),
        ("occurred_at", "timestamp", False, []),
    ],
}

# dataset_key -> (completeness, uniqueness, validity, consistency, freshness)
DATA_QUALITY = {
    "customers": (98.0, 95.0, 92.0, 97.0, 100.0),
    "orders": (99.0, 90.0, 100.0, 99.0, 100.0),
    "payments": (85.0, 88.0, 70.0, 90.0, 100.0),
    "employees": (92.0, 97.0, 80.0, 95.0, 100.0),
    "performance_reviews": (75.0, 60.0, 100.0, 88.0, 100.0),
    "marketing_campaigns": (100.0, 98.0, 100.0, 100.0, 100.0),
    "support_tickets": (80.0, 85.0, 90.0, 82.0, 100.0),
    "product_catalog": (100.0, 100.0, 100.0, 100.0, 100.0),
    "audit_trail": (65.0, 55.0, 100.0, 70.0, 100.0),
}

GLOSSARY_TERMS = [
    ("Customer", "An individual or organization that has purchased or registered for our product.", "CRM", "Priya Sharma", "APPROVED"),
    ("ARR", "Annual Recurring Revenue - the yearly value of active subscriptions.", "Finance", "Finance Ops", "APPROVED"),
    ("Churn Rate", "The percentage of customers who cancel within a given period.", "Sales", None, "DRAFT"),
    ("PII", "Personally Identifiable Information - any data that can identify a specific individual.", None, "Data Platform", "APPROVED"),
    ("Data Steward", "The individual accountable for the quality and governance of a dataset.", None, None, "APPROVED"),
    ("Retention Period", "The length of time a dataset is retained before review or deletion, per policy.", None, "Data Platform", "DRAFT"),
]

LINEAGE_EDGES = [
    ("customers", "orders", "foreign_key"),
    ("orders", "payments", "foreign_key"),
    ("customers", "support_tickets", "reference"),
    ("orders", "marketing_campaigns", "attribution"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Email of an existing user - demo data seeds into their organization")
    parser.add_argument("--force", action="store_true", help="Seed even if this organization already has datasets")
    args = parser.parse_args()

    db = SessionLocal()

    try:
        user = db.query(User).filter(User.email == args.email).first()
        if not user:
            print(f"No user found with email {args.email!r}. Register that account first.")
            sys.exit(1)

        organization = db.query(Organization).filter(Organization.id == user.organization_id).first()
        org_id = organization.id

        existing_count = db.query(Dataset).filter(Dataset.organization_id == org_id).count()
        if existing_count > 0 and not args.force:
            print(f"Organization {organization.name!r} already has {existing_count} dataset(s). Pass --force to seed anyway.")
            sys.exit(1)

        print(f"Seeding demo data into organization {organization.name!r} ({org_id})...")

        sources = {
            "postgres": DataSource(
                name="Production Postgres",
                type="postgresql",
                connection_config={"host": "prod-db.internal", "port": 5432, "database": "app"},
                organization_id=org_id,
            ),
            "warehouse": DataSource(
                name="Analytics Warehouse",
                type="snowflake",
                connection_config={"account": "acme-analytics", "database": "ANALYTICS"},
                organization_id=org_id,
            ),
        }
        db.add_all(sources.values())
        db.flush()

        source_for_schema = {
            "public": sources["postgres"],
            "hr": sources["postgres"],
            "analytics": sources["warehouse"],
        }

        dataset_objs = {}

        for i, (key, schema, name, domain, owner, steward, certification,
                purpose, consent_status, retention_days, description) in enumerate(DATASETS):

            dataset = Dataset(
                name=name,
                schema_name=schema,
                description=description,
                ai_summary=f"Auto-generated summary: {description}",
                domain=domain,
                steward=steward,
                tags=f"{domain.lower()},demo" if domain else "demo",
                certification=certification,
                owner=owner,
                purpose=purpose,
                consent_status=consent_status,
                retention_period_days=retention_days,
                retention_notes="Reviewed during quarterly compliance check." if retention_days else None,
                source_id=source_for_schema[schema].id,
                organization_id=org_id,
                last_scanned_at=days_ago(i % 5),
                created_at=days_ago(30 - i),
            )
            db.add(dataset)
            db.flush()
            dataset_objs[key] = dataset

            for column_name, data_type, nullable, samples in COLUMNS[key]:
                analysis = analyze_column(column_name, samples)
                db.add(DatasetColumn(
                    dataset_id=dataset.id,
                    name=column_name,
                    data_type=data_type,
                    nullable=nullable,
                    classification=analysis["classification"],
                    sensitivity_score=str(analysis["sensitivity_score"]),
                    confidence=analysis["confidence"],
                    detection_reason=analysis["detection_reason"],
                    recommendation=analysis["recommendation"],
                    dpdp_category=analysis["dpdp_category"],
                    consent_required=analysis["consent_required"],
                    classification_source="AUTO",
                ))

            completeness, uniqueness, validity, consistency, freshness = DATA_QUALITY[key]
            overall = round((completeness + uniqueness + validity + consistency + freshness) / 5, 2)
            db.add(DataQuality(
                dataset_id=dataset.id,
                completeness=completeness,
                uniqueness=uniqueness,
                validity=validity,
                consistency=consistency,
                freshness=freshness,
                overall_score=overall,
            ))

        db.flush()

        for upstream_key, downstream_key, transformation in LINEAGE_EDGES:
            db.add(DatasetLineage(
                upstream_dataset_id=dataset_objs[upstream_key].id,
                downstream_dataset_id=dataset_objs[downstream_key].id,
                transformation_type=transformation,
            ))

        for term, definition, domain, owner, status in GLOSSARY_TERMS:
            existing_term = (
                db.query(BusinessGlossaryTerm)
                .filter(
                    BusinessGlossaryTerm.organization_id == org_id,
                    BusinessGlossaryTerm.term == term,
                )
                .first()
            )
            if existing_term:
                continue
            db.add(BusinessGlossaryTerm(
                term=term,
                definition=definition,
                domain=domain,
                owner=owner,
                status=status,
                organization_id=org_id,
            ))

        demo_steward_email = "steward.demo@metadataintel.local"
        demo_steward = db.query(User).filter(User.email == demo_steward_email).first()
        if not demo_steward:
            demo_steward = User(
                email=demo_steward_email,
                password_hash=hash_password("DemoSteward123!"),
                role="steward",
                organization_id=org_id,
                is_active=True,
                created_at=days_ago(20),
            )
            db.add(demo_steward)
            db.flush()

        audit_events = [
            (days_ago(28), "source.create", sources["postgres"].id, "data_source", "Created source 'Production Postgres'"),
            (days_ago(28), "source.create", sources["warehouse"].id, "data_source", "Created source 'Analytics Warehouse'"),
            (days_ago(25), "scanner.scan", sources["postgres"].id, "data_source", "Scanned source, discovered 6 datasets"),
            (days_ago(20), "user.invite", demo_steward.id, "user", f"Invited {demo_steward_email} as steward"),
            (days_ago(14), "governance.certify", dataset_objs["customers"].id, "dataset", "Certification set to VERIFIED"),
            (days_ago(10), "governance.update", dataset_objs["payments"].id, "dataset", "Updated fields: certification"),
            (days_ago(7), "scanner.scan", sources["warehouse"].id, "data_source", "Scanned source, discovered 3 datasets"),
            (days_ago(2), "governance.update", dataset_objs["employees"].id, "dataset", "Updated fields: steward"),
        ]
        for created_at, action, resource_id, resource_type, details in audit_events:
            db.add(AuditLog(
                organization_id=org_id,
                actor_user_id=user.id,
                actor_email=user.email,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                created_at=created_at,
            ))

        db.commit()

        print(f"Done. Seeded {len(DATASETS)} datasets across {len(sources)} sources for {organization.name!r}.")
        print(f"Also added a demo steward account: {demo_steward_email} / DemoSteward123!")

    finally:
        db.close()


if __name__ == "__main__":
    main()
