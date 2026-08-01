import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import StoryRecorderWidget from "./StoryRecorderWidget";
import TourPickerModal from "./TourPickerModal";
import { StoryRecorderProvider } from "../contexts/StoryRecorderContext";
import { TourProvider } from "../contexts/TourContext";
import api from "../services/api";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("../services/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;
const mockedPost = api.post as jest.Mock;

function Harness() {
  return (
    <TourProvider>
      <StoryRecorderProvider>
        <TourPickerModal open onClose={() => {}} />
        <StoryRecorderWidget />
      </StoryRecorderProvider>
    </TourProvider>
  );
}

describe("story recorder (record -> capture -> save)", () => {
  beforeEach(() => {
    mockedGet.mockReset();
    mockedPost.mockReset();
    window.history.pushState({}, "", "/");
    // Both TourContext and StoryRecorderContext persist their state to
    // localStorage so an in-progress tour/recording survives a reload -
    // without clearing it, a later test's fresh render would resume
    // whatever an earlier test left behind.
    window.localStorage.clear();

    // TourProvider fetches the org's custom stories on mount - start
    // from an empty list unless a test overrides it.
    mockedGet.mockImplementation((url: string) => {
      if (url === "/api/stories") return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
  });

  it('starting a recording from the picker shows the recorder widget, and captures a plain-path step', async () => {
    render(<Harness />);

    fireEvent.click(await screen.findByText("+ Record a new story"));

    expect(await screen.findByText("0 steps captured")).toBeInTheDocument();

    fireEvent.click(screen.getByText("+ Add this view"));
    fireEvent.change(screen.getByPlaceholderText(/Step title/), {
      target: { value: "Start where the analyst starts" },
    });
    fireEvent.change(screen.getByPlaceholderText(/What should the viewer notice/), {
      target: { value: "Search turns up three different systems." },
    });
    fireEvent.click(screen.getByText("Add this view"));

    expect(await screen.findByText("1 step captured")).toBeInTheDocument();
    // A plain path (no /datasets/ or /lineage in the URL) never needs
    // a dataset lookup - only the initial custom-stories fetch ran.
    expect(mockedGet).toHaveBeenCalledTimes(1);
  });

  it("resolves a dataset-detail-page capture to a portable schema/table reference, and saves the full story", async () => {
    window.history.pushState({}, "", "/datasets/d1?tab=business");

    mockedGet.mockImplementation((url: string) => {
      if (url === "/api/stories") return Promise.resolve({ data: [] });
      if (url === "/api/datasets/d1") {
        return Promise.resolve({ data: { id: "d1", schema_name: "public", name: "customers" } });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    mockedPost.mockResolvedValue({ data: { id: "new-story-id" } });

    render(<Harness />);

    fireEvent.click(await screen.findByText("+ Record a new story"));
    await screen.findByText("0 steps captured");

    fireEvent.click(screen.getByText("+ Add this view"));
    fireEvent.change(screen.getByPlaceholderText(/Step title/), {
      target: { value: "The authoritative table" },
    });
    fireEvent.change(screen.getByPlaceholderText(/What should the viewer notice/), {
      target: { value: "This is the one to trust." },
    });
    fireEvent.click(screen.getByText("Add this view"));

    await screen.findByText("1 step captured");

    fireEvent.click(screen.getByText("Review & save"));
    fireEvent.change(screen.getByPlaceholderText(/Onboarding a new analyst/), {
      target: { value: "My saved story" },
    });

    await act(async () => {
      fireEvent.click(screen.getByText("Save story"));
    });

    await waitFor(() => expect(mockedPost).toHaveBeenCalledWith("/api/stories", expect.objectContaining({
      title: "My saved story",
      steps: [
        expect.objectContaining({
          title: "The authoritative table",
          narrative: "This is the one to trust.",
          path: "/datasets/[id]",
          dataset: { schema_name: "public", table_name: "customers" },
          tab: "business",
        }),
      ],
    })));

    // Saving clears the recorder back to its idle (hidden) state.
    await waitFor(() => expect(screen.queryByText(/steps captured/)).not.toBeInTheDocument());
  });

  it("discarding a recording clears captured steps without saving anything", async () => {
    window.confirm = jest.fn(() => true);

    render(<Harness />);

    fireEvent.click(await screen.findByText("+ Record a new story"));
    await screen.findByText("0 steps captured");

    fireEvent.click(screen.getByText("+ Add this view"));
    fireEvent.change(screen.getByPlaceholderText(/Step title/), { target: { value: "A step" } });
    fireEvent.change(screen.getByPlaceholderText(/What should the viewer notice/), {
      target: { value: "Something." },
    });
    fireEvent.click(screen.getByText("Add this view"));
    await screen.findByText("1 step captured");

    fireEvent.click(screen.getByText("Discard"));

    expect(window.confirm).toHaveBeenCalled();
    expect(mockedPost).not.toHaveBeenCalled();
    expect(screen.queryByText(/steps captured/)).not.toBeInTheDocument();
  });
});
