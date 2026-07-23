import type { Dataset } from "../types/metadata";

export type HealthLevel = "HEALTHY" | "NEEDS_ATTENTION" | "CRITICAL";

export type HealthAssessment = {
  level: HealthLevel;
  reasons: string[];
};

// Shared by the catalog card and the dataset detail page so "is this
// dataset okay?" always means the same thing in both places, instead
// of each view inventing its own reading of the same six underlying
// status fields.
export function getOverallHealth(dataset: Dataset): HealthAssessment {
  const reasons: string[] = [];
  let level: HealthLevel = "HEALTHY";

  function escalate(next: HealthLevel) {
    if (next === "CRITICAL") level = "CRITICAL";
    else if (next === "NEEDS_ATTENTION" && level !== "CRITICAL") level = "NEEDS_ATTENTION";
  }

  if (dataset.governance_status === "CRITICAL") {
    escalate("CRITICAL");
    reasons.push("governance status is critical");
  } else if (dataset.governance_status && dataset.governance_status !== "HEALTHY") {
    escalate("NEEDS_ATTENTION");
    reasons.push(`governance status is ${dataset.governance_status.toLowerCase()}`);
  }

  if (dataset.operational_status === "UNSTABLE") {
    escalate("CRITICAL");
    reasons.push("operationally unstable");
  } else if (dataset.operational_status === "AT_RISK" || dataset.operational_status === "DEGRADED") {
    escalate("NEEDS_ATTENTION");
    reasons.push(`operational status is ${dataset.operational_status.toLowerCase()}`);
  }

  if (dataset.contract_status === "BREACHED") {
    escalate("CRITICAL");
    reasons.push("data contract is breached");
  } else if (dataset.contract_status === "PENDING_EVALUATION") {
    escalate("NEEDS_ATTENTION");
    reasons.push("contract pending evaluation");
  }

  if (dataset.freshness_status === "STALE") {
    escalate("NEEDS_ATTENTION");
    reasons.push("data is stale");
  } else if (dataset.freshness_status === "AGING") {
    escalate("NEEDS_ATTENTION");
    reasons.push("data is aging");
  }

  return { level, reasons };
}

export const HEALTH_STYLES: Record<HealthLevel, { bg: string; text: string; label: string }> = {
  HEALTHY: { bg: "bg-green-100", text: "text-green-700", label: "Healthy" },
  NEEDS_ATTENTION: { bg: "bg-yellow-100", text: "text-yellow-700", label: "Needs Attention" },
  CRITICAL: { bg: "bg-red-100", text: "text-red-700", label: "Critical" },
};
