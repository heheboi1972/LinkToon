import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { PublicationManager } from "@/components/publication-manager";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  createPublication: vi.fn(),
  getEpisodePublication: vi.fn(),
  getEpisodeReader: vi.fn(),
  getProjectOverview: vi.fn(),
  republish: vi.fn(),
  unpublish: vi.fn(),
  updatePublication: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, ...mocks };
});

function renderManager() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PublicationManager projectId="project-1" episodeId="episode-1" />
    </QueryClientProvider>,
  );
}

describe("PublicationManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.api.mockResolvedValue({
      id: "episode-1",
      project_id: "project-1",
      number: 1,
      title: "달빛의 귀환",
      description: "첫 번째 이야기",
    });
    mocks.getEpisodeReader.mockResolvedValue({
      episode_id: "episode-1",
      project_id: "project-1",
      number: 1,
      title: "달빛의 귀환",
      summary: "첫 번째 이야기",
      scenes: [
        {
          id: "scene-1",
          order: 1,
          title: "옥상",
          narration: "달이 다시 떠올랐다.",
          dialogue: [],
          image_url: null,
          video_url: null,
        },
      ],
    });
    mocks.getProjectOverview.mockResolvedValue({
      project_id: "project-1",
      episode_count: 1,
      scene_count: 1,
      image_count: 0,
      motion_count: 0,
      character_count: 1,
      character_reference_count: 0,
      published_count: 0,
      latest_scene_image_url: null,
      latest_scene_title: null,
      updated_at: "2026-10-02T00:00:00Z",
    });
    mocks.getEpisodePublication.mockRejectedValue(
      new ApiError("Publication not found", 404, "not_found"),
    );
    mocks.createPublication.mockResolvedValue({
      id: "publication-1",
      project_id: "project-1",
      episode_id: "episode-1",
      slug: "moonlight-return-a81e9a22",
      title: "달빛의 귀환",
      description: "첫 번째 이야기",
      visibility: "public",
      status: "published",
      current_version: 1,
      published_at: "2026-10-02T00:00:00Z",
      scene_count: 1,
      image_count: 0,
      motion_count: 0,
    });
  });

  it("shows real readiness and creates a shareable publication", async () => {
    renderManager();
    expect(await screen.findByText("Reader 준비됨")).toBeTruthy();
    expect(screen.getByText("달빛의 귀환")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "게시하기" }));

    await waitFor(() =>
      expect(mocks.createPublication).toHaveBeenCalledWith("episode-1", {
        title: "달빛의 귀환",
        description: "첫 번째 이야기",
        visibility: "public",
      }),
    );
    expect(await screen.findByText("게시가 완료되었습니다.")).toBeTruthy();
    expect(screen.getByText(/\/read\/moonlight-return-a81e9a22/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /공개 페이지 열기/ })).toBeTruthy();
  });

  it("blocks publishing when there are no scenes", async () => {
    mocks.getEpisodeReader.mockResolvedValue({
      episode_id: "episode-1",
      project_id: "project-1",
      number: 1,
      title: "달빛의 귀환",
      summary: "",
      scenes: [],
    });
    renderManager();
    const publish = await screen.findByRole("button", { name: "게시하기" });
    expect(publish).toHaveProperty("disabled", true);
    expect(screen.getByText(/장면을 하나 이상/)).toBeTruthy();
    expect(mocks.createPublication).not.toHaveBeenCalled();
  });
});
