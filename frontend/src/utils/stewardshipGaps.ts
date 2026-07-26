import type { Dataset } from "../types/metadata";

// Powers the home page's Steward queue: anything a steward should
// actually go fix - missing ownership/stewardship/domain/description,
// or a governance score low enough to flag. Extracted out of
// page.tsx so this logic (which decides what gets shown in a queue
// stewards act on) is unit-testable on its own, not only indirectly
// through a full page render.
export function stewardshipGaps(dataset: Dataset): string[] {
  const gaps: string[] = [];

  if (!dataset.owner || dataset.owner.trim() === "") gaps.push("no owner");
  if (!dataset.steward || dataset.steward.trim() === "") gaps.push("no steward");
  if (!dataset.domain || dataset.domain.trim() === "") gaps.push("no domain");
  if (!dataset.description || dataset.description.trim() === "") gaps.push("no description");
  if ((dataset.governance_score ?? 100) < 60) gaps.push(`score ${dataset.governance_score}`);

  return gaps;
}
