"""
Generates a downloadable PDF compliance report: a snapshot of privacy
and governance posture across an organization's catalog, meant to be
handed to a compliance officer or kept as pilot evidence. Everything
in it is derived from data already computed elsewhere (Dataset's
privacy_score/governance_status properties, the privacy engine's DPDP
categories) - this module is purely presentation, no new scoring
logic.

reportlab is pure-Python-installable (no system libraries like
WeasyPrint's cairo/pango dependency chain), which matters here since
this needs to install cleanly on whatever machine runs the backend.
"""

from collections import defaultdict
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


def _summary_table(rows, col_widths=None):
    table = Table(rows, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def generate_compliance_report_pdf(
    organization_name: str,
    generated_by_email: str,
    datasets: list,
) -> bytes:

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        title=f"{organization_name} - Privacy & Governance Compliance Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], fontSize=20, spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#6b7280")
    )
    section_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], fontSize=13, spaceBefore=18, spaceAfter=8
    )

    story = [
        Paragraph("Privacy & Governance Compliance Report", title_style),
        Paragraph(organization_name, subtitle_style),
        Paragraph(
            f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} by {generated_by_email}",
            subtitle_style,
        ),
        Spacer(1, 0.25 * inch),
    ]

    total_datasets = len(datasets)

    if total_datasets == 0:
        story.append(Paragraph(
            "No datasets have been cataloged yet. Scan a source to populate this report.",
            styles["Normal"],
        ))
        doc.build(story)
        return buffer.getvalue()

    avg_privacy_score = round(sum(d.privacy_score for d in datasets) / total_datasets)
    avg_governance_score = round(sum(d.governance_score for d in datasets) / total_datasets)

    consent_review_needed = len([
        d for d in datasets
        if any(c.consent_required for c in d.columns) and d.consent_status == "NOT_ASSESSED"
    ])
    overdue_retention = len([d for d in datasets if d.retention_status == "OVERDUE"])
    missing_purpose = len([
        d for d in datasets
        if any(c.consent_required for c in d.columns) and not d.purpose
    ])
    uncertified = len([d for d in datasets if d.certification != "VERIFIED"])
    critical = len([d for d in datasets if d.governance_status == "CRITICAL"])

    # --- Executive summary ---
    story.append(Paragraph("Executive Summary", section_style))
    summary_rows = [
        ["Metric", "Value"],
        ["Total datasets cataloged", str(total_datasets)],
        ["Average privacy score", f"{avg_privacy_score}/100"],
        ["Average governance score", f"{avg_governance_score}/100"],
        ["Datasets needing consent review", str(consent_review_needed)],
        ["Datasets overdue on retention policy", str(overdue_retention)],
        ["Datasets missing a documented purpose", str(missing_purpose)],
        ["Uncertified datasets", str(uncertified)],
        ["Critical governance status", str(critical)],
    ]
    story.append(_summary_table(summary_rows, col_widths=[3.5 * inch, 2.5 * inch]))

    # --- DPDP category breakdown ---
    dpdp_counts = defaultdict(int)
    for dataset in datasets:
        for column in dataset.columns:
            if column.dpdp_category:
                dpdp_counts[column.dpdp_category] += 1

    story.append(Paragraph("Sensitive Columns by DPDP/GDPR Category", section_style))
    if dpdp_counts:
        category_rows = [["Category", "Column Count"]] + [
            [category.replace("_", " ").title(), str(count)]
            for category, count in sorted(dpdp_counts.items(), key=lambda item: -item[1])
        ]
        story.append(_summary_table(category_rows, col_widths=[3.5 * inch, 2.5 * inch]))
    else:
        story.append(Paragraph("No sensitive columns detected.", styles["Normal"]))

    # --- Per-dataset detail ---
    story.append(Paragraph("Dataset-Level Detail", section_style))
    detail_rows = [[
        "Dataset", "Domain", "Owner", "Certification",
        "Sensitivity", "Consent", "Retention", "Privacy Score",
    ]]
    for dataset in sorted(datasets, key=lambda d: d.privacy_score):
        detail_rows.append([
            f"{dataset.schema_name}.{dataset.name}",
            dataset.domain or "-",
            dataset.owner or "Unassigned",
            dataset.certification or "DRAFT",
            dataset.sensitivity_score,
            dataset.consent_status or "NOT_ASSESSED",
            dataset.retention_status,
            f"{dataset.privacy_score}/100",
        ])

    story.append(_summary_table(
        detail_rows,
        col_widths=[1.5 * inch, 0.85 * inch, 0.95 * inch, 0.85 * inch, 0.75 * inch, 1.0 * inch, 0.85 * inch, 0.75 * inch],
    ))

    doc.build(story)
    return buffer.getvalue()
