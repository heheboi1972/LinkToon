import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PublicReader } from "@/components/public-reader";
import type { PublicationReader } from "@/lib/types";
import { getPublicPublication } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, getPublicPublication: vi.fn() };
});

const publication: PublicationReader = {
  slug: "moonlight-episode-a8c7012f",
  title: "달빛 아래의 귀환",
  description: "폐허가 된 서울에서 두 사람이 다시 만난다.",
  author_name: "Mina",
  visibility: "unlisted",
  published_at: "2026-10-01T12:00:00Z",
  scene_count: 1,
  scenes: [
    {
      order: 1,
      title: "옥상에서",
      narration: "도시의 불빛이 천천히 깨어났다.",
      dialogue: [{ character: "서윤", text: "여기가 정말 서울이라고?" }],
      image_url:
        "https://api.example/api/v1/publications/moonlight/assets/a1/content?token=t1",
      video_url: null,
    },
  ],
};

describe("PublicReader", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", () => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    vi.mocked(getPublicPublication).mockResolvedValue(publication);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders the shared work without studio navigation and supports reduced motion", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <PublicReader publication={publication} />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("heading", { name: "달빛 아래의 귀환" })).toBeTruthy();
    expect(screen.getByText("도시의 불빛이 천천히 깨어났다.")).toBeTruthy();
    expect(screen.getByText(/여기가 정말 서울이라고/)).toBeTruthy();
    expect(screen.getByRole("img", { name: /옥상에서/ })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "주 메뉴" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Motion 자동재생 꺼짐" }));
    expect(screen.getByRole("button", { name: "Motion 자동재생 켜짐" })).toBeTruthy();
  });
});
