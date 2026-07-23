import type { ThreadType } from "../types/metadata";

export function threadTypeBadgeClasses(threadType: ThreadType | string) {
  if (threadType === "PROPOSAL") return "bg-purple-100 text-purple-700";
  if (threadType === "ISSUE") return "bg-orange-100 text-orange-700";
  return "bg-blue-100 text-blue-700";
}

export function threadTypeLabel(threadType: ThreadType | string) {
  if (threadType === "PROPOSAL") return "Proposal";
  if (threadType === "ISSUE") return "Issue";
  return "Question";
}
