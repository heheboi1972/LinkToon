import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EpisodeReader } from "@/components/episode-reader";
import { getEpisodeReader } from "@/lib/api";
import type { EpisodeReader as EpisodeReaderData } from "@/lib/types";

const pathnameState = vi.hoisted(() => ({ current: "" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathnameState.current }));
vi.mock("@/components/providers", () => ({
  useAuth: () => ({ user: { id: "reader-user", display_name: "Reader" } }),
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, getEpisodeReader: vi.fn() };
});

const episodeId = "episode-1";
const projectId = "project-1";
const progressKey = `linktoon:reader:reader-user:${episodeId}`;
const motionKey = "linktoon:reader-motion:reader-user";

function createReader(): EpisodeReaderData {
  return {
    episode_id: episodeId,
    project_id: projectId,
    number: 1,
    title: "달빛 아래",
    summary: "사라진 별을 찾아가는 이야기입니다.",
    scenes: [
      {
        id: "scene-1",
        order: 1,
        title: "옥상",
        narration: "미나는 고개를 들었다.",
        dialogue: [{ character: "미나", text: "저기 봐." }],
        image_url: "https://api.example/api/v1/assets/image-1/content?token=image-token",
        video_url: "https://api.example/api/v1/assets/video-1/content?token=video-token",
      },
      {
        id: "scene-2",
        order: 2,
        title: "골목",
        narration: "골목에 불이 켜졌다.",
        dialogue: [],
        image_url: "https://api.example/api/v1/assets/image-2/content?token=image-token",
        video_url: null,
      },
      {
        id: "scene-3",
        order: 3,
        title: "새벽",
        narration: "첫차가 지나갔다.",
        dialogue: [],
        image_url: null,
        video_url: null,
      },
    ],
  };
}

const mockedGetReader = vi.mocked(getEpisodeReader);
const scrollIntoView = vi.fn();

class TestIntersectionObserver {
  static instances: TestIntersectionObserver[] = [];
  callback: IntersectionObserverCallback;
  observed: Element[] = [];

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    TestIntersectionObserver.instances.push(this);
  }

  observe(element: Element) {
    this.observed.push(element);
  }

  unobserve() {}

  disconnect() {}

  intersect(id: string, ratio: number) {
    const target = document.querySelector(`[data-reader-scene="${id}"]`);
    if (!target) throw new Error(`Reader scene ${id} was not rendered`);
    this.callback(
      [
        {
          target,
          isIntersecting: ratio > 0,
          intersectionRatio: ratio,
        } as IntersectionObserverEntry,
      ],
      this as unknown as IntersectionObserver,
    );
  }
}

function renderReader() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const readerTree = () => (
    <QueryClientProvider client={queryClient}>
      <EpisodeReader projectId={projectId} episodeId={episodeId} />
    </QueryClientProvider>
  );
  const view = render(readerTree());
  return { ...view, rerenderReader: () => view.rerender(readerTree()) };
}

describe("EpisodeReader", () => {
  beforeEach(() => {
    localStorage.clear();
    pathnameState.current = `/projects/${projectId}/episodes/${episodeId}/read`;
    TestIntersectionObserver.instances = [];
    mockedGetReader.mockReset();
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    scrollIntoView.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  });

  it("shows ordered narration, dialogue, image, video, image-only and text-only scenes", async () => {
    mockedGetReader.mockResolvedValue(createReader());
    renderReader();

    expect(await screen.findByRole("heading", { name: "달빛 아래" })).toBeInTheDocument();
    expect(screen.getByText("미나는 고개를 들었다.")).toBeInTheDocument();
    expect(screen.getByText("미나")).toBeInTheDocument();
    expect(screen.getByText("저기 봐.")).toBeInTheDocument();
    const video = document.querySelector("video");
    expect(video).toHaveAttribute("poster", expect.stringContaining("image-1"));
    expect(video).toHaveAttribute("preload", "metadata");
    expect(video).toHaveAttribute("playsinline");
    expect(video).toHaveAttribute("controls");
    expect(document.querySelectorAll("img[loading='eager']").length).toBeGreaterThan(0);
    expect(screen.getByText("장면 이미지는 아직 준비되지 않았어요.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "읽기 진행" })).toHaveAttribute(
      "aria-valuemax",
      "3",
    );
  });

  it("renders a loading state while Reader data is pending", () => {
    mockedGetReader.mockReturnValue(new Promise(() => {}));
    renderReader();
    expect(screen.getByRole("status")).toHaveTextContent("에피소드를 불러오는 중");
  });

  it("renders an empty episode", async () => {
    mockedGetReader.mockResolvedValue({ ...createReader(), scenes: [] });
    renderReader();
    expect(await screen.findByText("아직 읽을 장면이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("keeps the image and story readable when media fails", async () => {
    mockedGetReader.mockResolvedValue(createReader());
    renderReader();
    const video = await screen.findByLabelText("옥상 Motion 영상");
    fireEvent.error(video);
    expect(await screen.findByText("Motion을 불러오지 못해 장면 이미지로 보여드려요.")).toBeInTheDocument();
    expect(screen.getByAltText("장면 1: 옥상")).toBeInTheDocument();
    expect(screen.getByText("미나는 고개를 들었다.")).toBeInTheDocument();
  });

  it("refreshes an expired image capability and shows a local image error", async () => {
    const reader = createReader();
    mockedGetReader.mockResolvedValue(reader);
    renderReader();
    const image = await screen.findByAltText("장면 2: 골목");
    fireEvent.error(image);
    expect(await screen.findByText("이미지를 불러오지 못했습니다.")).toBeInTheDocument();
    expect(mockedGetReader).toHaveBeenCalledTimes(2);
  });

  it("offers explicit resume and saves the chosen scene position", async () => {
    const user = userEvent.setup();
    localStorage.setItem(progressKey, "scene-2");
    mockedGetReader.mockResolvedValue(createReader());
    renderReader();

    const continueButton = await screen.findByRole("button", { name: "이어서 보기" });
    await user.click(continueButton);
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    await waitFor(() => expect(localStorage.getItem(progressKey)).toBe("scene-2"));
    expect(screen.queryByRole("complementary", { name: "읽기 이어보기" })).not.toBeInTheDocument();
  });

  it("stores the most visible scene by ID after scrolling", async () => {
    mockedGetReader.mockResolvedValue(createReader());
    renderReader();
    await screen.findByRole("heading", { name: "달빛 아래" });
    const observer = TestIntersectionObserver.instances.at(-1);
    expect(observer).toBeDefined();
    observer?.intersect("scene-2", 0.8);
    await waitFor(() => expect(localStorage.getItem(progressKey)).toBe("scene-2"));
    expect(screen.getByRole("progressbar", { name: "읽기 진행" })).toHaveAttribute(
      "aria-valuenow",
      "2",
    );
  });

  it("rechecks saved progress after returning through client navigation", async () => {
    mockedGetReader.mockResolvedValue(createReader());
    const view = renderReader();
    await screen.findByRole("heading", { name: "달빛 아래" });
    TestIntersectionObserver.instances.at(-1)?.intersect("scene-2", 0.8);
    await waitFor(() => expect(localStorage.getItem(progressKey)).toBe("scene-2"));

    pathnameState.current = `/projects/${projectId}/episodes/${episodeId}`;
    view.rerenderReader();
    pathnameState.current = `/projects/${projectId}/episodes/${episodeId}/read`;
    view.rerenderReader();

    expect(await screen.findByRole("button", { name: "이어서 보기" })).toBeInTheDocument();
  });

  it("prevents three videos from auto-playing together", async () => {
    const reader = createReader();
    reader.scenes[1] = { ...reader.scenes[1], video_url: "https://api.example/video-2?token=two" };
    reader.scenes[2] = { ...reader.scenes[2], video_url: "https://api.example/video-3?token=three" };
    mockedGetReader.mockResolvedValue(reader);
    localStorage.setItem(motionKey, "on");
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    renderReader();
    await screen.findByRole("heading", { name: "달빛 아래" });
    const first = document.querySelector("video[aria-label='옥상 Motion 영상']");
    const second = document.querySelector("video[aria-label='골목 Motion 영상']");
    const third = document.querySelector("video[aria-label='새벽 Motion 영상']");
    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(third).toBeTruthy();
    const observer = TestIntersectionObserver.instances.at(-1);
    observer?.intersect("scene-1", 0.95);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    observer?.intersect("scene-1", 0);
    observer?.intersect("scene-2", 0.95);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    expect(pause).toHaveBeenCalled();
    observer?.intersect("scene-2", 0);
    observer?.intersect("scene-3", 0.95);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(3));
    expect(pause).toHaveBeenCalledTimes(2);
  });

  it("disconnects the scene observer on unmount", async () => {
    mockedGetReader.mockResolvedValue(createReader());
    const view = renderReader();
    await screen.findByRole("heading", { name: "달빛 아래" });
    const observer = TestIntersectionObserver.instances.at(-1);
    expect(observer).toBeDefined();
    const disconnect = vi.spyOn(observer!, "disconnect");

    view.unmount();

    expect(disconnect).toHaveBeenCalledOnce();
  });

  it("disables automatic Motion playback when reduced motion is enabled", async () => {
    mockedGetReader.mockResolvedValue(createReader());
    localStorage.setItem(motionKey, "on");
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    renderReader();
    const toggle = await screen.findByRole("button", { name: "Motion 자동 재생 설정" });
    await waitFor(() => expect(toggle).toBeDisabled());
    TestIntersectionObserver.instances.at(-1)?.intersect("scene-1", 0.9);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(play).not.toHaveBeenCalled();
  });

  it("uses the backend ownership check for private Reader failures", async () => {
    mockedGetReader.mockRejectedValue(
      Object.assign(new Error("not found"), { status: 404 }),
    );
    renderReader();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "이 에피소드를 볼 수 없습니다.",
    );
  });
});
