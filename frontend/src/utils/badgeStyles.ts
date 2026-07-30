// Shared status/severity -> Tailwind badge-class mappings. These used to
// be copy-pasted per file (contracts/page.tsx and DataContractPanel.tsx
// had byte-identical statusBadgeClasses/evaluationBadgeClasses functions,
// and BusinessViewPanel.tsx quietly duplicated risks/page.tsx's risk-level
// coloring under a different name) - centralized here so a status color
// only has to be decided once, and any new file needing the same concept
// imports it instead of reinventing it.

import type { ContractStatus, ControlStatus, RiskLevel, RiskStatus } from "../types/metadata";

// A data contract's lifecycle stage (draft -> active -> deprecated).
export function contractStatusBadgeClasses(status: ContractStatus | string): string {
  if (status === "ACTIVE") return "bg-blue-100 text-blue-700";
  if (status === "DEPRECATED") return "bg-gray-100 text-gray-500";
  return "bg-yellow-100 text-yellow-700"; // DRAFT
}

// Whether a contract's most recent scheduled evaluation found it
// compliant or breached - a separate axis from the lifecycle status
// above (last_status, not status).
export function contractEvaluationBadgeClasses(status: string | null | undefined): string {
  if (status === "COMPLIANT") return "bg-green-100 text-green-700";
  if (status === "BREACHED") return "bg-red-100 text-red-700";
  return "bg-gray-100 text-gray-500"; // PENDING_EVALUATION, NO_CONTRACT, or not yet evaluated
}

export function riskLevelBadgeClasses(level: RiskLevel | string): string {
  if (level === "HIGH") return "bg-red-100 text-red-700";
  if (level === "MEDIUM") return "bg-yellow-100 text-yellow-700";
  return "bg-green-100 text-green-700"; // LOW
}

export function riskStatusBadgeClasses(status: RiskStatus | string): string {
  if (status === "OPEN") return "bg-orange-100 text-orange-700";
  if (status === "MITIGATED") return "bg-blue-100 text-blue-700";
  if (status === "ACCEPTED") return "bg-purple-100 text-purple-700";
  return "bg-gray-100 text-gray-600"; // CLOSED
}

export function controlStatusBadgeClasses(status: ControlStatus | string): string {
  if (status === "EFFECTIVE") return "bg-green-100 text-green-700";
  if (status === "INEFFECTIVE") return "bg-red-100 text-red-700";
  return "bg-gray-100 text-gray-600"; // NOT_TESTED
}
