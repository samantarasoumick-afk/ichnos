import { fireEvent, render, screen } from "@testing-library/react";
import SearchAnswerCard from "./SearchAnswerCard";

const pushMock = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const ANSWER = {
  answer: "public.customers is owned by Growth Team.",
  sources: [{ type: "dataset" as const, id: "d1", label: "public.customers", url: "/datasets/d1" }],
  follow_up_suggestions: [
    { label: "Data quality", query: "What's the data quality score for public.customers?" },
    { label: "PII", query: "Does public.customers contain PII?" },
  ],
};

describe("SearchAnswerCard", () => {
  beforeEach(() => {
    pushMock.mockClear();
  });

  it("renders nothing when there's no answer and nothing is in flight", () => {
    const { container } = render(
      <SearchAnswerCard query="customers" answer={null} asking={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a thinking state while asking", () => {
    render(<SearchAnswerCard query="who owns customers?" answer={null} asking={true} />);
    expect(screen.getByText("Thinking...")).toBeInTheDocument();
  });

  it("does not render follow-up chips when onSelectFollowUp isn't provided", () => {
    render(<SearchAnswerCard query="who owns customers?" answer={ANSWER} asking={false} />);
    expect(screen.queryByText("Keep going")).not.toBeInTheDocument();
    expect(screen.queryByText("Data quality")).not.toBeInTheDocument();
  });

  it("renders follow-up chips when onSelectFollowUp is provided, and clicking one calls it with the suggestion's query", () => {
    const onSelectFollowUp = jest.fn();
    render(
      <SearchAnswerCard
        query="who owns customers?"
        answer={ANSWER}
        asking={false}
        onSelectFollowUp={onSelectFollowUp}
      />
    );

    expect(screen.getByText("Keep going")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Data quality"));

    expect(onSelectFollowUp).toHaveBeenCalledWith("What's the data quality score for public.customers?");
    // Selecting a follow-up re-runs the inline flow in place - it should
    // never navigate away like a source chip or "Continue" does.
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("still renders source chips and the Continue in Ask'Fe' link alongside follow-up chips", () => {
    render(
      <SearchAnswerCard
        query="who owns customers?"
        answer={ANSWER}
        asking={false}
        onSelectFollowUp={jest.fn()}
      />
    );

    expect(screen.getByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText(/Continue in Ask'Fe'/)).toBeInTheDocument();
  });
});
