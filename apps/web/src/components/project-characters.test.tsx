import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectCharacters } from "@/components/project-characters";
import {
  clearCharacterReference,
  createCharacter,
  createCharacterReferenceGeneration,
  deleteCharacter,
  getGenerationJob,
  listProjectCharacters,
  selectCharacterReference,
  updateCharacter,
} from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: vi.fn(),
    listProjectCharacters: vi.fn(),
    createCharacter: vi.fn(),
    updateCharacter: vi.fn(),
    deleteCharacter: vi.fn(),
    selectCharacterReference: vi.fn(),
    clearCharacterReference: vi.fn(),
    createCharacterReferenceGeneration: vi.fn(),
    getGenerationJob: vi.fn(),
  };
});

const mockedList = vi.mocked(listProjectCharacters);
const mockedCreate = vi.mocked(createCharacter);
const mockedUpdate = vi.mocked(updateCharacter);
const mockedDelete = vi.mocked(deleteCharacter);
const mockedSelect = vi.mocked(selectCharacterReference);
const mockedClear = vi.mocked(clearCharacterReference);
const mockedGenerate = vi.mocked(createCharacterReferenceGeneration);
const mockedJob = vi.mocked(getGenerationJob);
const character = { id: "11111111-1111-4111-8111-111111111111", project_id: "p1", name: "Mina", description: "Courier", character_bible: { face_description: "round" }, reference_asset_id: null, reference_stale: false, character_revision: 1 };

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><ProjectCharacters projectId="p1" userId="u1" /></QueryClientProvider>);
}

beforeEach(() => {
  mockedList.mockResolvedValue([character]);
  mockedCreate.mockResolvedValue(character);
  mockedUpdate.mockResolvedValue(character);
  mockedDelete.mockResolvedValue(undefined);
  mockedSelect.mockResolvedValue(character);
  mockedClear.mockResolvedValue(character);
  mockedGenerate.mockResolvedValue({ job_id: "22222222-2222-4222-8222-222222222222", status: "queued" });
  mockedJob.mockResolvedValue({ id: "22222222-2222-4222-8222-222222222222", project_id: "p1", job_type: "character:reference", status: "queued", progress: 0, retry_count: 0, next_poll_at: null, error_code: null, error_message: null, started_at: null, completed_at: null, cancel_requested_at: null, created_at: "", updated_at: "", input: { character_id: character.id }, output: {}, cost_estimate: null, cost_actual: null });
});
afterEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

describe("ProjectCharacters", () => {
  it("loads the Character Bible section", async () => { mount(); expect(await screen.findByText("캐릭터 일관성 관리")).toBeInTheDocument(); });
  it("renders the character name", async () => { mount(); expect(await screen.findByDisplayValue("Mina")).toBeInTheDocument(); });
  it("renders face field", async () => { mount(); expect(await screen.findByDisplayValue("round")).toBeInTheDocument(); });
  it("renders create name input", () => { mount(); expect(screen.getByRole("textbox", { name: "새 캐릭터 이름" })).toBeInTheDocument(); });
  it("creates a character", async () => { mount(); await userEvent.type(screen.getByRole("textbox", { name: "새 캐릭터 이름" }), "Nova"); await userEvent.click(screen.getByRole("button", { name: "캐릭터 추가" })); await waitFor(() => expect(mockedCreate).toHaveBeenCalled()); });
  it("saves edits", async () => { mount(); await screen.findByDisplayValue("Mina"); await userEvent.click(screen.getByRole("button", { name: /저장/ })); await waitFor(() => expect(mockedUpdate).toHaveBeenCalled()); });
  it("requires a name before create", () => { mount(); expect(screen.getByRole("button", { name: "캐릭터 추가" })).toBeDisabled(); });
  it("shows reference empty state", async () => { mount(); expect(await screen.findByText("기준 이미지 없음")).toBeInTheDocument(); });
  it("offers existing image selection", async () => { mount(); expect(await screen.findByRole("combobox", { name: "기존 이미지 선택" })).toBeInTheDocument(); });
  it("starts reference generation", async () => { mount(); await screen.findByDisplayValue("Mina"); await userEvent.click(screen.getByRole("button", { name: "기준 이미지 생성" })); await waitFor(() => expect(mockedGenerate).toHaveBeenCalledWith(character.id, expect.any(String))); });
  it("deletes after confirmation", async () => { vi.spyOn(window, "confirm").mockReturnValue(true); mount(); await screen.findByDisplayValue("Mina"); await userEvent.click(screen.getByRole("button", { name: /삭제/ })); await waitFor(() => expect(mockedDelete).toHaveBeenCalledWith(character.id)); });
  it("cancels delete when not confirmed", async () => { vi.spyOn(window, "confirm").mockReturnValue(false); mount(); await screen.findByDisplayValue("Mina"); await userEvent.click(screen.getByRole("button", { name: /삭제/ })); expect(mockedDelete).not.toHaveBeenCalled(); });
  it("uses selected reference asset", async () => { mount(); await screen.findByDisplayValue("Mina"); expect(screen.getByRole("button", { name: "이 이미지 사용" })).toBeDisabled(); });
  it("shows revision label", async () => { mount(); expect(await screen.findByText("revision 1")).toBeInTheDocument(); });
  it("renders refreshable query state", async () => { mount(); await waitFor(() => expect(mockedList).toHaveBeenCalledWith("p1")); });
  it("shows character consistency copy", async () => { mount(); expect(await screen.findByText(/기준 이미지를 장면 생성에 자동/)).toBeInTheDocument(); });
});
