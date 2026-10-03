import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SceneImageGenerator } from "@/components/scene-image-generator";
import {
  ApiError,
  cancelGenerationJob,
  createSceneImageGeneration,
  getAsset,
  getGenerationJob,
  getScene,
} from "@/lib/api";
import type {
  Asset,
  GenerationJob,
  GenerationJobStatus,
  SceneRecord,
} from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    createSceneImageGeneration: vi.fn(),
    getGenerationJob: vi.fn(),
    cancelGenerationJob: vi.fn(),
    getScene: vi.fn(),
    getAsset: vi.fn(),
  };
});

const userId = "11111111-1111-4111-8111-111111111111";
const projectId = "22222222-2222-4222-8222-222222222222";
const sceneId = "33333333-3333-4333-8333-333333333333";
const assetId = "44444444-4444-4444-8444-444444444444";
const firstJobId = "55555555-5555-4555-8555-555555555555";
const secondJobId = "66666666-6666-4666-8666-666666666666";
const storageKey = `linktoon-scene-image-job:${userId}:${sceneId}`;

const mockedCreate = vi.mocked(createSceneImageGeneration);
const mockedGetJob = vi.mocked(getGenerationJob);
const mockedCancel = vi.mocked(cancelGenerationJob);
const mockedGetScene = vi.mocked(getScene);
const mockedGetAsset = vi.mocked(getAsset);

function scene(imageAssetId: string | null = null): SceneRecord {
  return {
    id: sceneId,
    episode_id: "77777777-7777-4777-8777-777777777777",
    position: 0,
    title: "달빛 옥상",
    image_asset_id: imageAssetId,
    video_asset_id: null,
    created_at: "2026-09-25T00:00:00Z",
    updated_at: "2026-09-25T00:00:00Z",
  };
}

function asset(): Asset {
  return {
    id: assetId,
    project_id: projectId,
    asset_type: "image",
    mime_type: "image/webp",
    public_url: `http://localhost:8000/api/v1/assets/${assetId}/content?token=signed-token`,
    width: 1024,
    height: 1536,
    file_size: 1234,
    metadata: {},
    upload_status: "ready",
  };
}

function job(
  status: GenerationJobStatus,
  overrides: Partial<GenerationJob> = {},
): GenerationJob {
  return {
    id: firstJobId,
    project_id: projectId,
    job_type: "image:scene",
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
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <SceneImageGenerator
        userId={userId}
        projectId={projectId}
        sceneId={sceneId}
        sceneTitle="달빛 옥상"
      />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

beforeEach(() => {
  sessionStorage.clear();
  mockedGetScene.mockResolvedValue(scene());
  mockedGetAsset.mockResolvedValue(asset());
  mockedCreate.mockResolvedValue({ job_id: firstJobId, status: "queued" });
  mockedGetJob.mockResolvedValue(job("queued"));
  mockedCancel.mockResolvedValue(job("canceled"));
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe("SceneImageGenerator", () => {
  it("shows an image generation button for a Scene without an image", async () => {
    mount();
    expect(
      await screen.findByRole("button", { name: "이미지 생성" }),
    ).toBeInTheDocument();
    expect(screen.getByText("이미지 없음")).toBeInTheDocument();
  });

  it("clicking the button accepts an Image Job with HTTP 202 semantics", async () => {
    mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "이미지 생성" }),
    );
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("이미지 생성 준비 중")).toBeInTheDocument();
  });

  it("sends a UUID Idempotency-Key for an image generation intent", async () => {
    mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "이미지 생성" }),
    );
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    expect(mockedCreate).toHaveBeenCalledWith(
      sceneId,
      expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      ),
    );
  });

  it("blocks duplicate clicks while the POST is unresolved", async () => {
    let resolveRequest!: (value: { job_id: string; status: "queued" }) => void;
    mockedCreate.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }),
    );
    mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "이미지 생성" }),
    );
    expect(screen.getByRole("button", { name: "요청하는 중" })).toBeDisabled();
    expect(mockedCreate).toHaveBeenCalledTimes(1);
    await act(async () =>
      resolveRequest({ job_id: firstJobId, status: "queued" }),
    );
    expect(await screen.findByText("이미지 생성 준비 중")).toBeInTheDocument();
  });

  it("shows the queued state without a fake percentage", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mount();
    expect(await screen.findByText("이미지 생성 준비 중")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("shows the running state", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGetJob.mockResolvedValue(job("running"));
    mount();
    expect(
      await screen.findByText("AI가 장면을 그리고 있어요"),
    ).toBeInTheDocument();
  });

  it("shows the saving state", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGetJob.mockResolvedValue(job("saving"));
    mount();
    expect(
      await screen.findByText("이미지를 저장하고 있어요"),
    ).toBeInTheDocument();
  });

  it("refetches the persisted Scene and renders the signed Asset after success", async () => {
    mockedGetScene
      .mockResolvedValueOnce(scene())
      .mockResolvedValue(scene(assetId));
    mockedGetJob.mockResolvedValue(
      job("succeeded", {
        output: { scene_id: sceneId, asset_id: assetId, asset_ids: [assetId] },
      }),
    );
    mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "이미지 생성" }),
    );
    expect(await screen.findByText("이미지 생성 완료")).toBeInTheDocument();
    expect(
      await screen.findByRole("img", { name: "달빛 옥상 생성 이미지" }),
    ).toHaveAttribute(
      "src",
      expect.stringContaining(`/assets/${assetId}/content`),
    );
  });

  it("maps a failed Job without exposing provider internals", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGetJob.mockResolvedValue(
      job("failed", {
        error_code: "provider_error",
        error_message: "The AI service could not complete this generation.",
      }),
    );
    mount();
    expect(
      await screen.findByText(
        "AI 이미지 서비스를 현재 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/secret-value/)).not.toBeInTheDocument();
  });

  it("shows the image daily limit message for HTTP 429", async () => {
    mockedCreate.mockRejectedValue(
      new ApiError("internal quota record", 429, "generation_quota_exceeded"),
    );
    mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "이미지 생성" }),
    );
    expect(
      await screen.findByText(
        "오늘 사용할 수 있는 AI 이미지 생성 횟수를 모두 사용했습니다.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("internal quota record")).not.toBeInTheDocument();
  });

  it("uses a new key for explicit regeneration", async () => {
    mockedGetScene.mockResolvedValue(scene(assetId));
    mockedCreate
      .mockResolvedValueOnce({ job_id: firstJobId, status: "queued" })
      .mockResolvedValueOnce({ job_id: secondJobId, status: "queued" });
    mockedGetJob.mockImplementation(async (id) =>
      job("succeeded", {
        id,
        output: { scene_id: sceneId, asset_id: assetId },
      }),
    );
    mount();
    const button = await screen.findByRole("button", {
      name: "이미지 다시 생성",
    });
    await userEvent.click(button);
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    await screen.findByText("이미지 생성 완료");
    await userEvent.click(
      screen.getByRole("button", { name: "이미지 다시 생성" }),
    );
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));
    expect(mockedCreate.mock.calls[1][1]).not.toBe(
      mockedCreate.mock.calls[0][1],
    );
  });

  it("keeps the existing image visible while regeneration is running", async () => {
    mockedGetScene.mockResolvedValue(scene(assetId));
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGetJob.mockResolvedValue(job("running"));
    mount();
    expect(
      await screen.findByRole("img", { name: "달빛 옥상 생성 이미지" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("AI가 장면을 그리고 있어요"),
    ).toBeInTheDocument();
  });

  it("restores the persisted Scene image and Job after refresh", async () => {
    mockedGetScene.mockResolvedValue(scene(assetId));
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGetJob.mockResolvedValue(job("succeeded"));
    mount();
    expect(
      await screen.findByRole("img", { name: "달빛 옥상 생성 이미지" }),
    ).toBeInTheDocument();
    expect(mockedGetJob).toHaveBeenCalledWith(firstJobId);
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  it("stops polling after unmount", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGetJob.mockResolvedValue(job("running"));
    const view = mount();
    await screen.findByText("AI가 장면을 그리고 있어요");
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_100);
    });
    const callsBeforeUnmount = mockedGetJob.mock.calls.length;
    view.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_100);
    });
    expect(mockedGetJob).toHaveBeenCalledTimes(callsBeforeUnmount);
  });

  it("cancels through the backend and displays the returned status", async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ jobId: firstJobId }));
    mockedGetJob.mockResolvedValue(job("running"));
    mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "이미지 생성 취소" }),
    );
    expect(mockedCancel).toHaveBeenCalledWith(firstJobId);
    expect(
      await screen.findByText(
        "이미지 생성이 취소되었습니다. 다시 생성할 수 있어요.",
      ),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });
});
