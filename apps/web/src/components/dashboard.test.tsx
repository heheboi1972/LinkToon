import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { Dashboard } from "@/components/dashboard";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));
vi.mock("@/components/providers", () => ({
  useAuth: () => ({ user: { display_name: "작가" } }),
}));
vi.mock("@/components/shell", () => ({
  PageHeading: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock("@/components/asset-image", () => ({
  AssetImage: () => <div>Cover</div>,
}));
const mockedApi = vi.mocked(api);
afterEach(() => vi.resetAllMocks());
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Dashboard />
    </QueryClientProvider>,
  );
}
it("shows the genuine empty state without fabricated projects", async () => {
  mockedApi.mockResolvedValue([]);
  mount();
  expect(
    await screen.findByText("첫 번째 이야기를 기다리고 있어요"),
  ).toBeInTheDocument();
  expect(screen.getByText("진행 중인 생성 작업이 없어요")).toBeInTheDocument();
});
it("filters persisted projects by title and status", async () => {
  mockedApi.mockImplementation(async (path) =>
    path.startsWith("/projects")
      ? [
          {
            id: "1",
            title: "달빛 도시",
            description: "도시의 비밀",
            genre: "fantasy",
            status: "draft",
            updated_at: "2026-09-14T00:00:00Z",
          },
          {
            id: "2",
            title: "여름 편지",
            description: "여름",
            genre: "romance",
            status: "active",
            updated_at: "2026-09-14T00:00:00Z",
          },
        ]
      : [],
  );
  mount();
  await screen.findByText("달빛 도시");
  await userEvent.type(screen.getByLabelText("프로젝트 검색"), "여름");
  expect(screen.queryByText("달빛 도시")).not.toBeInTheDocument();
  expect(screen.getByText("여름 편지")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "초안" }));
  expect(screen.getByText("조건에 맞는 프로젝트가 없어요")).toBeInTheDocument();
});
it("shows an API failure with a retry action", async () => {
  mockedApi.mockImplementation(async (path) => {
    if (path.startsWith("/projects")) throw new Error("API unavailable");
    return [];
  });
  mount();
  expect(await screen.findByText("API unavailable")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
});
