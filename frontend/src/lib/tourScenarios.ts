/**
 * Guided-tour scenario definitions for the demo data estate seeded by
 * demo_data_service.py. Each scenario tells one problem -> process ->
 * solution story using the *real* seeded data (resolved by schema_name
 * + table_name at tour-start time via GET /api/datasets, never
 * hardcoded IDs, since those are generated fresh per organization),
 * deep-linking across the actual product pages rather than a
 * standalone narrated slide - see docs/13_Roadmap.md and
 * TourContext.tsx for how steps get resolved and navigated.
 *
 * Keep this in sync with backend/app/services/demo_data_service.py -
 * every dataset referenced here by schemaName/tableName must exist in
 * the seeder, or TourContext's resolution will skip that step.
 */

export type TourStepTarget = {
  /** Base app route to navigate to. */
  path: string;
  /**
   * Resolve a real dataset ID at tour-start time from its schema_name
   * + name (as seeded), then either append it as the dataset detail
   * page's [id] segment or as a `?dataset=` query param on the
   * lineage page - TourContext infers which based on `path`.
   */
  dataset?: { schemaName: string; tableName: string };
  /** Dataset detail page tab to deep-link into (?tab=...). */
  tab?: string;
  /** Any other static query params, e.g. a prefilled search/ask query. */
  query?: Record<string, string>;
};

export type TourStep = {
  id: string;
  /** Short label shown in the stepper's step list. */
  title: string;
  /** The contextual callout shown for this step - the narrative glue. */
  narrative: string;
  target: TourStepTarget;
};

export type TourScenario = {
  id: string;
  title: string;
  /** The problem statement this scenario opens with. */
  problem: string;
  /** One-line summary of the resolution, shown on the picker card. */
  solutionSummary: string;
  steps: TourStep[];
};

export const TOUR_SCENARIOS: TourScenario[] = [
  {
    id: "discovery-bottleneck",
    title: "My analysts spend half their time in discovery",
    problem:
      "A new analyst needs a number for the exec team. There are three tables that could " +
      "plausibly be “the” customer table, nobody documented which one is authoritative, " +
      "and the only way to find out is to ask around.",
    solutionSummary:
      "One glossary definition, tagged System of Record vs. Reference, full lineage, and an " +
      "assistant that already knows the answer.",
    steps: [
      {
        id: "search",
        title: "Start where the analyst starts",
        narrative:
          "Searching the catalog for “customer” turns up results from three different " +
          "systems - a storefront database, an analytics warehouse, and a CRM. This is the " +
          "moment of confusion the whole story starts from.",
        target: { path: "/", query: { q: "customer" } },
      },
      {
        id: "glossary",
        title: "One definition, not three guesses",
        narrative:
          "The Business Glossary has a single, owned definition of “Customer” - and it's " +
          "linked to every technical table that actually implements it, not just described in " +
          "prose someone has to go find.",
        target: { path: "/glossary" },
      },
      {
        id: "system-of-record",
        title: "Which one is authoritative?",
        narrative:
          "customers is tagged System of Record - this is where a customer is actually created " +
          "and corrected. The Business View tab also shows its data quality and lineage in one " +
          "place, not three separate pages.",
        target: {
          path: "/datasets/[id]",
          dataset: { schemaName: "public", tableName: "customers" },
          tab: "business",
        },
      },
      {
        id: "system-of-reference",
        title: "The reporting copy, clearly labeled",
        narrative:
          "dim_customers is tagged System of Reference - a derived copy built for reporting, not " +
          "the place to go correct a customer's email. Same entity, explicit relationship, no " +
          "guessing which one to trust.",
        target: {
          path: "/datasets/[id]",
          dataset: { schemaName: "analytics_marts", tableName: "dim_customers" },
          tab: "business",
        },
      },
      {
        id: "lineage",
        title: "The full path, end to end",
        narrative:
          "The Lineage page shows exactly how a raw customer record flows through staging into " +
          "this reporting table - the path a new analyst would otherwise have to reconstruct " +
          "from memory or a Slack thread.",
        target: {
          path: "/lineage",
          dataset: { schemaName: "analytics_marts", tableName: "dim_customers" },
        },
      },
      {
        id: "ask",
        title: "Or just ask, in plain English",
        narrative:
          "Instead of posting in Slack and waiting forty minutes for an answer, Ask'Fe' " +
          "already knows who owns customers - grounded in the real catalog and " +
          "lineage graph, not a canned FAQ.",
        target: { path: "/ask", query: { q: "Who owns customers?", autosubmit: "1" } },
      },
      {
        id: "process",
        title: "Tied to the business process, not just a table",
        narrative:
          "Customer Onboarding ties the lead, the confirmed customer record, and the reporting " +
          "views together as one process - so a new analyst sees not just what the data is, but " +
          "what it's for.",
        target: { path: "/processes" },
      },
    ],
  },
  {
    id: "vendor-data-quality",
    title: "My vendors are inconsistent in data quality",
    problem:
      "A third-party vendor's product feed lands in the warehouse every night. It looks fine in " +
      "a spreadsheet preview - until it quietly breaks a report three tables downstream, and " +
      "nobody notices until a category manager asks why the numbers look wrong.",
    solutionSummary:
      "Real profiled quality scores, a breached data contract, and a breach that's visible on " +
      "the downstream report - not just the raw feed.",
    steps: [
      {
        id: "search",
        title: "A new vendor source lands in the catalog",
        narrative:
          "Acme's product feed shows up in the catalog like any other source - no steward " +
          "assigned yet, and no obvious sign of trouble until you look closer.",
        target: { path: "/", query: { q: "acme" } },
      },
      {
        id: "quality",
        title: "Profiled from the real data, not guessed",
        narrative:
          "The Business View tab shows this dataset's actual profiled quality score - " +
          "completeness, uniqueness, validity, and consistency computed from the real sampled " +
          "values, not a placeholder number. It's meaningfully worse than the platform's other " +
          "sources.",
        target: {
          path: "/datasets/[id]",
          dataset: { schemaName: "vendor_feeds", tableName: "acme_product_feed" },
          tab: "business",
        },
      },
      {
        id: "contract",
        title: "A contract, and a breach",
        narrative:
          "This dataset has an active data contract - and it's BREACHED, on both a missing-" +
          "column schema check and the quality-threshold check. This is the enforcement " +
          "mechanism catching the problem automatically, not a person noticing by chance.",
        target: {
          path: "/datasets/[id]",
          dataset: { schemaName: "vendor_feeds", tableName: "acme_product_feed" },
          tab: "governance",
        },
      },
      {
        id: "discussion",
        title: "Flagged, but not yet owned",
        narrative:
          "Someone already raised it as an open issue - but with no steward assigned, it's " +
          "sitting there unresolved. Visibility isn't the same as accountability.",
        target: {
          path: "/datasets/[id]",
          dataset: { schemaName: "vendor_feeds", tableName: "acme_product_feed" },
          tab: "discussion",
        },
      },
      {
        id: "lineage",
        title: "The mess doesn't stay contained",
        narrative:
          "Follow the lineage forward: this raw feed feeds a staging model, which feeds a " +
          "product dimension, which feeds a Tableau report. Every hop inherits whatever showed " +
          "up in last night's export.",
        target: {
          path: "/lineage",
          dataset: { schemaName: "vendor_feeds", tableName: "acme_product_feed" },
        },
      },
      {
        id: "propagation",
        title: "The breach, visible three hops downstream",
        narrative:
          "Open the actual report a category manager would look at - Vendor Product Catalog " +
          "Health - and the breach banner is right there, computed live from lineage. Nobody " +
          "has to already know to go check the raw feed.",
        target: {
          path: "/datasets/[id]",
          dataset: { schemaName: "Procurement Analytics", tableName: "Vendor Product Catalog Health" },
          tab: "governance",
        },
      },
      {
        id: "risk",
        title: "Turned into a tracked risk, with a proposed fix",
        narrative:
          "The risk register captures this as “Vendor product feed quality is unmanaged,” " +
          "with a proposed control - automated validation on ingest - so the next vendor feed " +
          "doesn't repeat the same story.",
        target: { path: "/risks" },
      },
      {
        id: "ask",
        title: "Or just ask which contracts are breached",
        narrative:
          "Ask'Fe' surfaces every current contract breach on demand - this is the " +
          "kind of question a data quality process should be able to answer in seconds, not " +
          "during a quarterly review.",
        target: { path: "/ask", query: { q: "Do we have any contract breaches?", autosubmit: "1" } },
      },
    ],
  },
];

export function findScenario(id: string | null): TourScenario | undefined {
  if (!id) return undefined;
  return TOUR_SCENARIOS.find((scenario) => scenario.id === id);
}
