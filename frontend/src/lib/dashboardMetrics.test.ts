import {
  DEFAULT_METRIC_IDS,
  INITIAL_SELECTED_METRIC_IDS,
  METRIC_BY_ID,
} from "./dashboardMetrics";
import type { Dataset, Source } from "../types/metadata";

const SOURCES: Source[] = [
  { id: "s1", name: "Salesforce", type: "postgresql" } as Source,
  { id: "s2", name: "Warehouse", type: "snowflake" } as Source,
];

const EMPTY_CONTEXT = {
  datasets: [] as Dataset[],
  sources: [] as Source[],
  governance: null,
  maturity: null,
  privacy: null,
};

describe("total_sources metric", () => {
  it("counts the sources passed in context", () => {
    const metric = METRIC_BY_ID["total_sources"];
    expect(metric).toBeDefined();

    const { display, tone } = metric.getValue({ ...EMPTY_CONTEXT, sources: SOURCES });
    expect(display).toBe(2);
    expect(tone).toBe("neutral");
  });

  it("is zero when there are no sources yet", () => {
    const metric = METRIC_BY_ID["total_sources"];
    const { display } = metric.getValue(EMPTY_CONTEXT);
    expect(display).toBe(0);
  });

  it("links to the ecosystem view", () => {
    expect(METRIC_BY_ID["total_sources"].href).toBe("/ecosystem");
  });
});

describe("INITIAL_SELECTED_METRIC_IDS", () => {
  it("includes every DEFAULT_METRIC_IDS entry plus total_sources", () => {
    for (const id of DEFAULT_METRIC_IDS) {
      expect(INITIAL_SELECTED_METRIC_IDS).toContain(id);
    }
    expect(INITIAL_SELECTED_METRIC_IDS).toContain("total_sources");
    expect(INITIAL_SELECTED_METRIC_IDS.length).toBe(DEFAULT_METRIC_IDS.length + 1);
  });

  it("does not itself add total_sources to DEFAULT_METRIC_IDS", () => {
    // Guards against a regression where someone "fixes" this by folding
    // total_sources into DEFAULT_METRIC_IDS directly - that array is
    // also used to *exclude* ids from the generic-card render loop in
    // app/page.tsx, so doing that would make the metric vanish instead
    // of rendering generically (see the comment in dashboardMetrics.ts).
    expect(DEFAULT_METRIC_IDS).not.toContain("total_sources");
  });
});
