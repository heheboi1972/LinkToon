import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StoryStudio } from "@/components/story-studio";
import {
  ApiError,
  cancelGenerationJob,
  createStoryGeneration,
  getGenerationJob,
  listProjectCharacters,
} from "@/lib/api";
import type { GenerationJob, GenerationJobStatus } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    createStoryGeneration: vi.fn(),
    getGenerationJob: vi.fn(),
    cancelGenerationJob: vi.fn(),
    listProjectCharacters: vi.fn(),
  };
});
vi.mock("@/components/providers", () => ({
  useAuth: () => ({ user: { id: "user-1", display_name: "작가" } }),
}));
vi.mock("@/components/scene-image-generator", () => ({
  SceneImageGenerator: () => <div data-testid="scene-image-generator" />,
}));

const projectId = "11111111-1111-4111-8111-111111111111";
const firstJobId = "22222222-2222-4222-8222-222222222222";
const secondJobId = "33333333-3333-4333-8333-333333333333";
const episodeId = "44444444-4444-4444-8444-444444444444";
const storageKey = `linktoon-story-job:user-1:${projectId}`;
const mockedCreate = vi.mocked(createStoryGeneration);
const mockedGet = vi.mocked(getGenerationJob);
const mockedCancel = vi.mocked(cancelGenerationJob);
const mockedCharacters = vi.mocked(listProjectCharacters);

function makeJob(
  status: GenerationJobStatus,
  overrides: Partial<GenerationJob> = {},
): GenerationJob {
  return {
    id: firstJobId,
    project_id: projectId,
    job_type: "story:generate",
    status,
    progress: 0,
    retry_count: 0,
    next_poll_at: null,
    error_code: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    cancel_requested_at: null,
    created_at: "2026-09-21T00:00:00Z",
    updated_at: "2026-09-21T00:00:00Z",
    input: {},
    output: {},
    cost_estimate: null,
    cost_actual: null,
    ...overrides,
  };
}

function successfulJob(overrides: Partial<GenerationJob> = {}) {
  return makeJob("succeeded", {
    output: {
      title: "달빛 도시의 비밀",
      synopsis: "친구들이 도시의 비밀을 찾아간다.",
      episode_id: episodeId,
      scene_ids: ["55555555-5555-4555-8555-555555555555"],
      asset_ids: [],
      mock: true,
      scenes: [
        {
          order: 1,
          title: "첫 만남",
          narration: "달빛 아래 두 친구가 만났다.",
          dialogue: [
            { character_id: null, character: "민아", text: "함께 가자." },
          ],
          visual_prompt: "달빛 거리",
          character_ids: [],
        },
      ],
    },
    ...overrides,
  });
}

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <StoryStudio
        projectId={projectId}
        projectGenre="fantasy"
        initialIdea="밤의 도시에서 시작된 모험"
      />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

async function createStory() {
  await userEvent.click(screen.getByRole("button", { name: "AI Story 생성" }));
}

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  mockedCharacters.mockResolvedValue([]);
  mockedCreate.mockResolvedValue({ job_id: firstJobId, status: "queued" });
  mockedGet.mockResolvedValue(makeJob("queued"));
  mockedCancel.mockResolvedValue(makeJob("canceled"));
});
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe("StoryStudio", () => {
  it("submits the form, selected project Character IDs and a UUID key, then shows queued state", async () => {
    const characterId = "66666666-6666-4666-8666-666666666666";
    mockedCharacters.mockResolvedValue([
      {
        id: characterId,
        project_id: projectId,
        name: "민아",
        description: "탐험가",
      },
    ]);
    mount();
    await userEvent.clear(
      screen.getByRole("textbox", { name: "이야기 아이디어" }),
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "이야기 아이디어" }),
      "달빛 도시의 비밀",
    );
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "분위기/톤" }),
      "hopeful",
    );
    await userEvent.type(screen.getByRole("textbox", { name: "테마" }), "우정");
    await userEvent.clear(screen.getByRole("spinbutton", { name: "장면 수" }));
    await userEvent.type(
      screen.getByRole("spinbutton", { name: "장면 수" }),
      "1",
    );
    await userEvent.click(
      await screen.findByRole("checkbox", { name: /민아/ }),
    );
    await createStory();
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    expect(mockedCreate).toHaveBeenCalledWith(
      projectId,
      {
        idea: "달빛 도시의 비밀",
        genre: "fantasy",
        tone: "hopeful",
        theme: "우정",
        characters: [characterId],
        scene_count: 1,
      },
      expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      ),
    );
    expect(await screen.findByText("생성 준비 중")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 생성" })).toBeDisabled();
    expect(
      JSON.parse(sessionStorage.getItem(storageKey) || "{}"),
    ).toMatchObject({ jobId: firstJobId });
  });

  it("keeps the same request and key after uncertain network failure", async () => {
    mockedCreate
      .mockRejectedValueOnce(
        new ApiError("secret server detail", 0, "network_error"),
      )
      .mockResolvedValueOnce({ job_id: firstJobId, status: "queued" });
    mount();
    await createStory();
    expect(
      await screen.findByRole("button", { name: "같은 요청 다시 확인" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("secret server detail")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "같은 요청 다시 확인" }),
    );
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));
    expect(mockedCreate.mock.calls[1][1]).toEqual(
      mockedCreate.mock.calls[0][1],
    );
    expect(mockedCreate.mock.calls[1][2]).toBe(mockedCreate.mock.calls[0][2]);
  });

  it("shows running and saving, then renders the persisted Story with a real Episode link", async () => {
    mockedGet
      .mockResolvedValueOnce(makeJob("queued"))
      .mockResolvedValueOnce(makeJob("running"))
      .mockResolvedValueOnce(makeJob("saving"))
      .mockResolvedValueOnce(successfulJob());
    const { client } = mount();
    await createStory();
    expect(await screen.findByText("생성 준비 중")).toBeInTheDocument();
    await act(() => client.invalidateQueries({ queryKey: ["story-job"] }));
    expect(
      await screen.findByText("AI가 이야기를 만들고 있어요"),
    ).toBeInTheDocument();
    await act(() => client.invalidateQueries({ queryKey: ["story-job"] }));
    expect(
      await screen.findByText("이야기를 저장하고 있어요"),
    ).toBeInTheDocument();
    await act(() => client.invalidateQueries({ queryKey: ["story-job"] }));
    expect(await screen.findByText("달빛 도시의 비밀")).toBeInTheDocument();
    expect(
      screen.getByText("친구들이 도시의 비밀을 찾아간다."),
    ).toBeInTheDocument();
    expect(screen.getByText("달빛 아래 두 친구가 만났다.")).toBeInTheDocument();
    expect(screen.getByText(/함께 가자/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /새 에피소드 보기/ }),
    ).toHaveAttribute("href", `/projects/${projectId}/episodes/${episodeId}`);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("maps provider failure safely and makes explicit regeneration use a fresh key", async () => {
    mockedCreate
      .mockResolvedValueOnce({ job_id: firstJobId, status: "queued" })
      .mockResolvedValueOnce({ job_id: secondJobId, status: "queued" });
    mockedGet.mockImplementation(async (id) =>
      id === firstJobId
        ? makeJob("failed", {
            error_code: "provider_error",
            error_message: "The AI service could not complete this generation.",
          })
        : successfulJob({ id: secondJobId }),
    );
    mount();
    await createStory();
    expect(
      await screen.findByText(
        "AI Story 서비스를 현재 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/internal-secret/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "다시 생성" }));
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));
    expect(mockedCreate.mock.calls[1][2]).not.toBe(
      mockedCreate.mock.calls[0][2],
    );
    expect(await screen.findByText("달빛 도시의 비밀")).toBeInTheDocument();
  });

  it("shows a safe daily quota message for HTTP 429", async () => {
    mockedCreate.mockRejectedValue(
      new ApiError(
        "Daily story generation limit reached",
        429,
        "generation_quota_exceeded",
      ),
    );
    mount();
    await createStory();
    expect(
      await screen.findByText(
        "오늘 사용할 수 있는 AI Story 생성 횟수를 모두 사용했습니다.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Daily story generation limit reached"),
    ).not.toBeInTheDocument();
  });

  it("cancels through the backend and trusts its returned status", async () => {
    mount();
    await createStory();
    await screen.findByText("생성 준비 중");
    await userEvent.click(screen.getByRole("button", { name: "생성 취소" }));
    expect(mockedCancel).toHaveBeenCalledWith(firstJobId);
    expect(
      await screen.findByText("생성이 취소되었습니다"),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });

  it("blocks duplicate submissions while POST is unresolved", async () => {
    let resolveRequest!: (value: { job_id: string; status: "queued" }) => void;
    mockedCreate.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }),
    );
    mount();
    await createStory();
    expect(screen.getByRole("button", { name: "요청하는 중" })).toBeDisabled();
    expect(mockedCreate).toHaveBeenCalledTimes(1);
    await act(async () =>
      resolveRequest({ job_id: firstJobId, status: "queued" }),
    );
    expect(await screen.findByText("생성 준비 중")).toBeInTheDocument();
  });

  it("recovers its project-scoped job after remount and clears inaccessible jobs safely", async () => {
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({ jobId: firstJobId, key: "request-key" }),
    );
    mockedGet.mockRejectedValueOnce(
      new ApiError("another user's resource exists", 404, "not_found"),
    );
    mount();
    await waitFor(() => expect(mockedGet).toHaveBeenCalledWith(firstJobId));
    expect(
      await screen.findByText("프로젝트를 찾을 수 없거나 접근할 수 없습니다."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("another user's resource exists"),
    ).not.toBeInTheDocument();
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });

  it("restores a succeeded result after refresh without another POST", async () => {
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({ jobId: firstJobId, key: "request-key" }),
    );
    mockedGet.mockResolvedValue(successfulJob());
    mount();
    expect(await screen.findByText("달빛 도시의 비밀")).toBeInTheDocument();
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  it("stops polling terminal jobs and cleans up polling after unmount", async () => {
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({ jobId: firstJobId, key: "request-key" }),
    );
    mockedGet.mockResolvedValue(makeJob("running"));
    const view = mount();
    expect(
      await screen.findByText("AI가 이야기를 만들고 있어요"),
    ).toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_100);
    });
    const callsBeforeUnmount = mockedGet.mock.calls.length;
    view.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_100);
    });
    expect(mockedGet).toHaveBeenCalledTimes(callsBeforeUnmount);
  });

  it("shows provider_pending as a waiting step", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGet.mockResolvedValue(makeJob("provider_pending"));
    mount();
    expect(
      await screen.findByText("AI 응답을 기다리고 있어요"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 생성" })).toBeDisabled();
  });

  it("maps unauthorized requests without revealing server details", async () => {
    mockedCreate.mockRejectedValue(
      new ApiError("token internals", 401, "unauthorized"),
    );
    mount();
    await createStory();
    expect(
      await screen.findByText("로그인이 필요합니다. 다시 로그인해 주세요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("token internals")).not.toBeInTheDocument();
  });

  it("rejects a job from another project even if the endpoint returns it", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGet.mockResolvedValue(
      makeJob("succeeded", {
        project_id: "77777777-7777-4777-8777-777777777777",
        output: successfulJob().output,
      }),
    );
    mount();
    expect(
      await screen.findByText("프로젝트를 찾을 수 없거나 접근할 수 없습니다."),
    ).toBeInTheDocument();
    expect(screen.queryByText("달빛 도시의 비밀")).not.toBeInTheDocument();
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });

  it("refetches the real Job when cancellation races with completion", async () => {
    mockedCancel.mockRejectedValue(
      new ApiError(
        "Completed jobs cannot be canceled",
        409,
        "job_not_cancelable",
      ),
    );
    mockedGet
      .mockResolvedValueOnce(makeJob("running"))
      .mockResolvedValueOnce(successfulJob());
    mount();
    await createStory();
    expect(
      await screen.findByText("AI가 이야기를 만들고 있어요"),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "생성 취소" }));
    expect(await screen.findByText("달빛 도시의 비밀")).toBeInTheDocument();
    expect(screen.queryByText("생성이 취소되었습니다")).not.toBeInTheDocument();
  });

  it("does not poll a completed Job again", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGet.mockResolvedValue(successfulJob());
    mount();
    expect(await screen.findByText("달빛 도시의 비밀")).toBeInTheDocument();
    const callsAtCompletion = mockedGet.mock.calls.length;
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_100);
    });
    expect(mockedGet).toHaveBeenCalledTimes(callsAtCompletion);
  });
});
