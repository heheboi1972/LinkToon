import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SceneMotionGenerator } from "@/components/scene-motion-generator";
import {
  ApiError,
  cancelGenerationJob,
  createSceneVideoGeneration,
  getAsset,
  getGenerationJob,
  getScene,
} from "@/lib/api";
import type { Asset, GenerationJob, GenerationJobStatus, SceneRecord } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    createSceneVideoGeneration: vi.fn(),
    cancelGenerationJob: vi.fn(),
    getAsset: vi.fn(),
    getGenerationJob: vi.fn(),
    getScene: vi.fn(),
  };
});

const userId = "11111111-1111-4111-8111-111111111111";
const projectId = "22222222-2222-4222-8222-222222222222";
const sceneId = "33333333-3333-4333-8333-333333333333";
const imageId = "44444444-4444-4444-8444-444444444444";
const videoId = "55555555-5555-4555-8555-555555555555";
const jobId = "66666666-6666-4666-8666-666666666666";
const scope = `linktoon-scene-motion-job:${userId}:${sceneId}`;

const mockedCreate = vi.mocked(createSceneVideoGeneration);
const mockedCancel = vi.mocked(cancelGenerationJob);
const mockedGetAsset = vi.mocked(getAsset);
const mockedGetJob = vi.mocked(getGenerationJob);
const mockedGetScene = vi.mocked(getScene);

function scene(imageAssetId: string | null = imageId, videoAssetId: string | null = null): SceneRecord {
  return {
    id: sceneId,
    episode_id: "77777777-7777-4777-8777-777777777777",
    position: 0,
    title: "달빛 옥상",
    image_asset_id: imageAssetId,
    video_asset_id: videoAssetId,
    created_at: "2026-09-25T00:00:00Z",
    updated_at: "2026-09-25T00:00:00Z",
  };
}

function asset(id = videoId, metadata: Asset["metadata"] = {}): Asset {
  return {
    id,
    project_id: projectId,
    asset_type: id === videoId ? "video" : "image",
    mime_type: id === videoId ? "video/mp4" : "image/webp",
    public_url: `http://localhost:8000/api/v1/assets/${id}/content?token=signed-token`,
    width: null,
    height: null,
    file_size: 1234,
    metadata,
    upload_status: "ready",
  };
}

function job(status: GenerationJobStatus, overrides: Partial<GenerationJob> = {}): GenerationJob {
  return {
    id: jobId,
    project_id: projectId,
    job_type: "video:scene",
    status,
    progress: 0,
    retry_count: 0,
    next_poll_at: null,
    error_code: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    cancel_requested_at: null,
    created_at: "2026-09-25T00:00:00Z",
    updated_at: "2026-09-25T00:00:00Z",
    input: { scene_id: sceneId },
    output: {},
    cost_estimate: null,
    cost_actual: null,
    ...overrides,
  };
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <SceneMotionGenerator userId={userId} projectId={projectId} sceneId={sceneId} />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

beforeEach(() => {
  sessionStorage.clear();
  mockedGetScene.mockResolvedValue(scene());
  mockedGetAsset.mockResolvedValue(asset());
  mockedCreate.mockResolvedValue({ job_id: jobId, status: "queued" });
  mockedGetJob.mockResolvedValue(job("queued"));
  mockedCancel.mockResolvedValue(job("canceled"));
});

afterEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe("SceneMotionGenerator", () => {
  it("does not show Motion controls before the Scene has an image", async () => {
    mockedGetScene.mockResolvedValue(scene(null));
    mount();
    await waitFor(() => expect(mockedGetScene).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Motion 만들기" })).not.toBeInTheDocument();
  });

  it("shows a Motion button for an image-backed Scene", async () => {
    mount();
    expect(await screen.findByRole("button", { name: "Motion 만들기" })).toBeInTheDocument();
  });

  it("posts one accepted job with a fresh Idempotency-Key and blocks duplicate clicks", async () => {
    let resolve!: (result: { job_id: string; status: "queued" }) => void;
    mockedCreate.mockImplementation(() => new Promise((done) => { resolve = done; }));
    mount();
    const button = await screen.findByRole("button", { name: "Motion 만들기" });
    await userEvent.click(button);
    expect(screen.getByRole("button", { name: "요청하는 중" })).toBeDisabled();
    expect(mockedCreate).toHaveBeenCalledTimes(1);
    expect(mockedCreate).toHaveBeenCalledWith(sceneId, expect.stringMatching(/^[0-9a-f-]{36}$/i));
    resolve({ job_id: jobId, status: "queued" });
    expect(await screen.findByText("모션 생성 준비 중")).toBeInTheDocument();
  });

  it.each([
    ["running", "영상 생성을 시작하고 있어요"],
    ["provider_pending", "AI가 장면을 움직이는 중이에요"],
    ["saving", "영상을 안전하게 저장하고 있어요"],
  ] as const)("shows the %s state", async (status, label) => {
    sessionStorage.setItem(scope, JSON.stringify({ jobId }));
    mockedGetJob.mockResolvedValue(job(status));
    mount();
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it("restores a persisted private video after reload and keeps the source as a capability URL", async () => {
    mockedGetScene.mockResolvedValue(scene(imageId, videoId));
    mockedGetAsset.mockResolvedValue(asset(videoId, { mock_provider: true }));
    mount();
    const video = await screen.findByLabelText("장면 Motion 미리보기");
    expect(video).toHaveAttribute("src", expect.stringContaining(`/assets/${videoId}/content`));
    expect(await screen.findByText("개발용 Mock Motion 미리보기")).toBeInTheDocument();
    expect(video).toHaveAttribute("controls");
    expect(video).toHaveProperty("muted", true);
    expect(video).toHaveAttribute("playsinline");
  });

  it("shows a new video while preserving the old preview during regeneration", async () => {
    sessionStorage.setItem(scope, JSON.stringify({ jobId }));
    mockedGetScene.mockResolvedValue(scene(imageId, videoId));
    mockedGetAsset.mockResolvedValue(asset());
    mockedGetJob.mockResolvedValue(job("succeeded"));
    mount();
    expect(await screen.findByLabelText("장면 Motion 미리보기")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Motion 다시 생성" })).toBeEnabled();
  });

  it("maps failed jobs without showing provider diagnostics", async () => {
    sessionStorage.setItem(scope, JSON.stringify({ jobId }));
    mockedGetJob.mockResolvedValue(job("failed", { error_code: "provider_error", error_message: "The AI service could not complete this generation." }));
    mount();
    expect(await screen.findByText("Motion 미리보기를 만들지 못했습니다. 설정이나 서비스 상태를 확인한 뒤 다시 시도해 주세요.")).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("shows the Motion quota message for HTTP 429", async () => {
    mockedCreate.mockRejectedValue(new ApiError("internal quota record", 429, "generation_quota_exceeded"));
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Motion 만들기" }));
    expect(await screen.findByText("오늘 사용할 수 있는 Motion 생성 횟수를 모두 사용했습니다.")).toBeInTheDocument();
    expect(screen.queryByText("internal quota record")).not.toBeInTheDocument();
  });

  it("cancels the LinkToon Job without displaying provider task IDs", async () => {
    sessionStorage.setItem(scope, JSON.stringify({ jobId }));
    const internalJob = {
      ...job("provider_pending"),
      provider_task_id: "runway-secret-task",
    } as GenerationJob;
    mockedGetJob.mockResolvedValue(internalJob);
    mount();
    await userEvent.click(await screen.findByRole("button", { name: "Motion 취소" }));
    await waitFor(() => expect(mockedCancel).toHaveBeenCalledWith(jobId));
    expect(screen.queryByText("runway-secret-task")).not.toBeInTheDocument();
  });
});
