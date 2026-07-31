import type {
  Dataset,
  GovernanceOverview,
  MaturityOverview,
  PrivacyOverview,
} from "../types/metadata";

// The full universe of metrics a user can put on their home dashboard.
// Deliberately not just the original 5 KPI cards - this is meant to
// surface everything the platform already computes somewhere, so a
// person can pick what they personally care about rather than being
// stuck with one fixed set. Every metric here reads from data the
// dashboard already fetches (the org's datasets, plus the governance/
// maturity/privacy overview endpoints - all three are already
// accessible to every role, not just admins) - nothing here triggers
// a new fetch per metric.
export type DashboardMetricContext = {
  datasets: Dataset[];
  governance: GovernanceOverview | null;
  maturity: MaturityOverview | null;
  privacy: PrivacyOverview | null;
};

export type MetricTone = "neutral" | "danger" | "warning" | "success";

export type MetricValue = {
  display: string | number;
  tone: MetricTone;
};

export type MetricGroup = "Catalog" | "Governance" | "Quality" | "Privacy & Risk" | "Contracts" | "Maturity";

export type MetricDefinition = {
  id: string;
  label: string;
  description: string;
  group: MetricGroup;
  // Where "show me more" should take you when this metric doesn't
  // have its own inline drill-down list (the original 5 quick-filter
  // metrics manage their own drill-down and ignore this).
  href?: string;
  getValue: (ctx: DashboardMetricContext) => MetricValue;
};

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return Math.round(values.reduce((sum, v) => sum + v, 0) / values.length);
}

function isOperationalAlert(dataset: Dataset) {
  return (
    dataset.operational_status === "DEGRADED" ||
    dataset.operational_status === "AT_RISK" ||
    dataset.operational_status === "UNSTABLE"
  );
}

// The original 5 cards - kept first in the catalog since they're the
// default selection for anyone who's never customized this. These
// are the only metrics with real click-to-drill-down list behavior,
// wired up directly in app/page.tsx via the existing quickFilter
// mechanism rather than through getValue/href here.
export const DEFAULT_METRIC_IDS = [
  "total_datasets",
  "high_risk_datasets",
  "pii_columns",
  "governance_alerts",
  "operational_alerts",
];

export const METRIC_CATALOG: MetricDefinition[] = [
  {
    id: "total_datasets",
    label: "Total Datasets",
    description: "Every dataset currently in the catalog.",
    group: "Catalog",
    getValue: ({ datasets }) => ({ display: datasets.length, tone: "neutral" }),
  },
  {
    id: "high_risk_datasets",
    label: "High Risk",
    description: "Datasets classified HIGH sensitivity.",
    group: "Privacy & Risk",
    getValue: ({ datasets }) => ({
      display: datasets.filter((d) => d.sensitivity_score === "HIGH").length,
      tone: "danger",
    }),
  },
  {
    id: "pii_columns",
    label: "PII Columns",
    description: "Total columns across the catalog containing personal data.",
    group: "Privacy & Risk",
    getValue: ({ datasets }) => ({
      display: datasets.reduce((total, d) => total + (d.pii_columns || 0), 0),
      tone: "warning",
    }),
  },
  {
    id: "governance_alerts",
    label: "Governance Alerts",
    description: "Datasets that aren't governance-healthy right now.",
    group: "Governance",
    getValue: ({ datasets }) => ({
      display: datasets.filter((d) => d.governance_status !== "HEALTHY").length,
      tone: "warning",
    }),
  },
  {
    id: "operational_alerts",
    label: "Operational Alerts",
    description: "Datasets flagged degraded, at-risk, or unstable.",
    group: "Catalog",
    getValue: ({ datasets }) => ({
      display: datasets.filter(isOperationalAlert).length,
      tone: "danger",
    }),
  },
  {
    id: "critical_datasets",
    label: "Critical Datasets",
    description: "Datasets whose governance status is CRITICAL.",
    group: "Governance",
    href: "/governance",
    getValue: ({ datasets }) => ({
      display: datasets.filter((d) => d.governance_status === "CRITICAL").length,
      tone: "danger",
    }),
  },
  {
    id: "stale_datasets",
    label: "Stale Datasets",
    description: "Datasets whose freshness status is STALE.",
    group: "Quality",
    href: "/data-quality",
    getValue: ({ datasets }) => ({
      display: datasets.filter((d) => d.freshness_status === "STALE").length,
      tone: "warning",
    }),
  },
  {
    id: "avg_quality_score",
    label: "Avg Quality Score",
    description: "Average profiled data quality score across the catalog.",
    group: "Quality",
    href: "/data-quality",
    getValue: ({ datasets }) => ({
      display: average(datasets.map((d) => d.quality_score || 0)),
      tone: "neutral",
    }),
  },
  {
    id: "avg_governance_score",
    label: "Avg Governance Score",
    description: "Average governance score across the catalog.",
    group: "Governance",
    href: "/governance",
    getValue: ({ governance, datasets }) => ({
      display:
        governance?.average_governance_score !== undefined
          ? Math.round(governance.average_governance_score)
          : average(datasets.map((d) => d.governance_score || 0)),
      tone: "neutral",
    }),
  },
  {
    id: "avg_trust_score",
    label: "Avg Trust Score",
    description: "Average trust score across the catalog.",
    group: "Catalog",
    getValue: ({ datasets }) => ({
      display: average(datasets.map((d) => d.trust_score || 0)),
      tone: "neutral",
    }),
  },
  {
    id: "avg_privacy_score",
    label: "Avg Privacy Score",
    description: "Average privacy score across the catalog.",
    group: "Privacy & Risk",
    href: "/privacy",
    getValue: ({ privacy, datasets }) => ({
      display:
        privacy?.average_privacy_score !== undefined
          ? Math.round(privacy.average_privacy_score)
          : average(datasets.map((d) => d.trust_score || 0)),
      tone: "neutral",
    }),
  },
  {
    id: "breached_contracts",
    label: "Breached Contracts",
    description: "Datasets whose data contract is currently breached.",
    group: "Contracts",
    href: "/contracts",
    getValue: ({ datasets }) => ({
      display: datasets.filter((d) => d.contract_status === "BREACHED").length,
      tone: "danger",
    }),
  },
  {
    id: "no_contract_datasets",
    label: "Without a Contract",
    description: "Datasets with no data contract in place at all.",
    group: "Contracts",
    href: "/contracts",
    getValue: ({ datasets }) => ({
      display: datasets.filter((d) => !d.contract_status || d.contract_status === "NO_CONTRACT").length,
      tone: "neutral",
    }),
  },
  {
    id: "retention_overdue",
    label: "Retention Overdue",
    description: "Datasets past their data retention window.",
    group: "Privacy & Risk",
    href: "/privacy",
    getValue: ({ privacy }) => ({
      display: privacy?.datasets_overdue_retention ?? 0,
      tone: "danger",
    }),
  },
  {
    id: "consent_review_needed",
    label: "Consent Review Needed",
    description: "Datasets containing personal data whose consent status hasn't been reviewed.",
    group: "Privacy & Risk",
    href: "/privacy",
    getValue: ({ privacy }) => ({
      display: privacy?.datasets_needing_consent_review ?? 0,
      tone: "warning",
    }),
  },
  {
    id: "missing_purpose",
    label: "Missing Purpose",
    description: "Datasets with personal data but no documented purpose for holding it.",
    group: "Privacy & Risk",
    href: "/privacy",
    getValue: ({ privacy }) => ({
      display: privacy?.datasets_missing_purpose ?? 0,
      tone: "warning",
    }),
  },
  {
    id: "uncertified_datasets",
    label: "Uncertified Datasets",
    description: "Datasets that have never been certified.",
    group: "Governance",
    href: "/governance",
    getValue: ({ governance }) => ({
      display: governance?.uncertified_datasets ?? 0,
      tone: "neutral",
    }),
  },
  {
    id: "missing_stewards",
    label: "Missing Stewards",
    description: "Datasets with no assigned steward.",
    group: "Governance",
    href: "/governance",
    getValue: ({ governance }) => ({
      display: governance?.missing_stewards ?? 0,
      tone: "warning",
    }),
  },
  {
    id: "glossary_terms",
    label: "Glossary Terms",
    description: "Business glossary terms defined so far.",
    group: "Governance",
    href: "/glossary",
    getValue: ({ governance }) => ({
      display: governance?.glossary_terms ?? 0,
      tone: "neutral",
    }),
  },
  {
    id: "maturity_score",
    label: "Maturity Score",
    description: "Overall governance maturity score for the organization.",
    group: "Maturity",
    href: "/governance",
    getValue: ({ maturity }) => ({
      display: maturity?.overall_score ?? 0,
      tone: "neutral",
    }),
  },
  {
    id: "maturity_level",
    label: "Maturity Level",
    description: "Governance maturity level (Not Started through Trusted).",
    group: "Maturity",
    href: "/governance",
    getValue: ({ maturity }) => ({
      display: maturity?.level ? maturity.level.replace("_", " ") : "–",
      tone: "neutral",
    }),
  },
];

export const METRIC_BY_ID: Record<string, MetricDefinition> = Object.fromEntries(
  METRIC_CATALOG.map((metric) => [metric.id, metric])
);

export function toneClasses(tone: MetricTone): string {
  if (tone === "danger") return "text-red-600";
  if (tone === "warning") return "text-yellow-600";
  if (tone === "success") return "text-green-600";
  return "text-gray-900";
}
