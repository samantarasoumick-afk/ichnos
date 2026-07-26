import { render, screen } from "@testing-library/react";
import DataQualityBars from "./DataQualityBars";
import type { DataQuality, EffectiveQuality } from "../types/metadata";

describe("DataQualityBars", () => {
  it("shows the empty state when there is no quality profile and no effective quality", () => {
    render(<DataQualityBars dataQuality={null} />);

    expect(screen.getByText("No data quality profile yet.")).toBeInTheDocument();
  });

  it("renders all five dimension bars with correct percentage labels", () => {
    const dataQuality: DataQuality = {
      id: "dq1",
      dataset_id: "d1",
      completeness: 91.4,
      uniqueness: 80,
      validity: 55.2,
      consistency: 100,
      freshness: 0,
      overall_score: 65.3,
    };

    render(<DataQualityBars dataQuality={dataQuality} />);

    expect(screen.getByText("65")).toBeInTheDocument();
    expect(screen.getByText("/ 100 overall")).toBeInTheDocument();

    expect(screen.getByText("Completeness")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();

    expect(screen.getByText("Uniqueness")).toBeInTheDocument();
    expect(screen.getByText("Validity")).toBeInTheDocument();
    expect(screen.getByText("55%")).toBeInTheDocument();
    expect(screen.getByText("Consistency")).toBeInTheDocument();
    expect(screen.getByText("Freshness")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("renders the lineage-adjusted effective score section when contributing edges exist", () => {
    const dataQuality: DataQuality = {
      id: "dq1",
      dataset_id: "d1",
      completeness: 100,
      uniqueness: 100,
      validity: 100,
      consistency: 100,
      freshness: 100,
      overall_score: 100,
    };

    const effectiveQuality: EffectiveQuality = {
      dataset_id: "d1",
      own_score: 100,
      effective_score: 88,
      contributing_edges: [
        {
          edge_id: "e1",
          upstream_dataset_id: "up1",
          upstream_effective_score: 70,
          documentation_completeness: 50,
          adjustment: -12,
          contribution: -12,
        },
      ],
    };

    render(<DataQualityBars dataQuality={dataQuality} effectiveQuality={effectiveQuality} allDatasets={[]} />);

    expect(screen.getByText("88")).toBeInTheDocument();
    expect(screen.getByText("/ 100 lineage-adjusted")).toBeInTheDocument();
    expect(screen.getByText("-12 vs. own score")).toBeInTheDocument();
    expect(screen.getByText(/Own profile blended/)).toBeInTheDocument();
  });

  it("shows the 'no standalone profile' empty state when only effective quality is available", () => {
    const effectiveQuality: EffectiveQuality = {
      dataset_id: "d1",
      own_score: null,
      effective_score: 72,
      contributing_edges: [
        {
          edge_id: "e1",
          upstream_dataset_id: "up1",
          upstream_effective_score: 72,
          documentation_completeness: 80,
          adjustment: 0,
          contribution: 0,
        },
      ],
    };

    render(<DataQualityBars dataQuality={null} effectiveQuality={effectiveQuality} allDatasets={[]} />);

    expect(screen.getByText("No standalone data quality profile yet.")).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText(/inherited from upstream lineage/)).toBeInTheDocument();
  });
});
