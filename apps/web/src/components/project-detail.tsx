"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Check,
  Eye,
  ImagePlus,
  Plus,
  Save,
  Send,
  Sparkles,
  Video,
  WandSparkles,
  X,
} from "lucide-react";
import {
  api,
  getProjectOverview,
  mediaUrl,
  patch,
  post,
  remove,
  uploadImage,
} from "@/lib/api";
import type { Episode, Project } from "@/lib/types";
import { genres, statuses } from "@/lib/utils";
import { PageHeading, ConfirmDelete } from "@/components/shell";
import { AssetImage } from "@/components/asset-image";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { EmptyState, ErrorState, Loading } from "@/components/states";

export function ProjectDetail({
  projectId,
  episodesOnly = false,
}: {
  projectId: string;
  episodesOnly?: boolean;
}) {
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api<Project>(`/projects/${projectId}`),
  });
  const episodes = useQuery({
    queryKey: ["episodes", projectId],
    queryFn: () => api<Episode[]>(`/projects/${projectId}/episodes?limit=200`),
  });
  const overview = useQuery({
    queryKey: ["project-overview", projectId],
    queryFn: () => getProjectOverview(projectId),
    enabled: !episodesOnly,
  });
  const client = useQueryClient();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["project", projectId] }),
      client.invalidateQueries({ queryKey: ["projects"] }),
    ]);
  }
  const update = useMutation({
    mutationFn: (data: unknown) =>
      patch<Project>(`/projects/${projectId}`, data),
    onSuccess: async () => {
      await refresh();
      setEditing(false);
    },
  });
  const cover = useMutation({
    mutationFn: async (file: File) => {
      const asset = await uploadImage(projectId, file, "thumbnail");
      return patch(`/projects/${projectId}`, { thumbnail_asset_id: asset.id });
    },
    onSuccess: refresh,
  });
  const deletion = useMutation({
    mutationFn: () => remove(`/projects/${projectId}`),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["projects"] });
      router.push("/dashboard");
    },
  });
  const createEpisode = useMutation({
    mutationFn: (data: unknown) =>
      post<Episode>(`/projects/${projectId}/episodes`, data),
    onSuccess: async (episode) => {
      await client.invalidateQueries({ queryKey: ["episodes", projectId] });
      await refresh();
      router.push(`/projects/${projectId}/episodes/${episode.id}`);
    },
  });
  if (project.isPending) return <Loading />;
  if (project.error || !project.data)
    return (
      <ErrorState error={project.error} retry={() => void project.refetch()} />
    );
  if (!episodesOnly && overview.isPending)
    return <Loading label="제작 현황을 불러오는 중" />;
  if (!episodesOnly && overview.error)
    return (
      <ErrorState
        error={overview.error}
        retry={() => void overview.refetch()}
      />
    );
  const p = project.data;
  const firstEpisode = episodes.data?.[0];
  const metrics = overview.data;
  const continueHref = !metrics?.episode_count
    ? `/projects/${projectId}/story`
    : metrics.scene_count > metrics.image_count
      ? `/projects/${projectId}/story#scenes`
      : firstEpisode && metrics.published_count === 0
        ? `/projects/${projectId}/episodes/${firstEpisode.id}/publish`
        : firstEpisode
          ? `/projects/${projectId}/episodes/${firstEpisode.id}/read`
          : `/projects/${projectId}/story`;
  const continueLabel = !metrics?.episode_count
    ? "이야기 시작하기"
    : metrics.scene_count > metrics.image_count
      ? "장면 이어 만들기"
      : metrics.published_count === 0
        ? "작품 게시하기"
        : "Reader로 감상하기";
  return (
    <>
      {episodesOnly ? (
        <PageHeading
          eyebrow="EPISODES"
          title={p.title}
          description="에피소드와 장면을 이어서 관리합니다."
        >
          <Button variant="outline" onClick={() => setEditing(!editing)}>
            {editing ? "닫기" : "프로젝트 설정"}
          </Button>
        </PageHeading>
      ) : (
        <>
          <section className="hero-grid relative isolate mb-6 grid overflow-hidden rounded-3xl border border-white/[.08] bg-[#111318] md:grid-cols-[1.05fr_.95fr]">
            <div className="relative z-10 flex flex-col items-start justify-center p-6 sm:p-9 lg:p-11">
              <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold tracking-[.16em] text-violet-300">
                <Sparkles className="size-3.5" />
                AI WEBTOON PROJECT
                <span className="rounded-full border border-white/10 px-2.5 py-1 tracking-normal text-zinc-400">
                  {genres[p.genre] || p.genre} · {statuses[p.status]}
                </span>
              </div>
              <h1 className="mt-5 max-w-2xl text-3xl font-semibold leading-tight tracking-tight text-zinc-100 sm:text-4xl lg:text-5xl">
                {p.title}
              </h1>
              <p className="mt-4 max-w-xl whitespace-pre-wrap text-sm leading-7 text-zinc-400 sm:text-base">
                {p.description || "아이디어를 이야기와 장면으로 확장해 보세요."}
              </p>
              <div className="mt-7 flex w-full flex-wrap gap-2">
                <Button asChild className="min-h-11">
                  <Link href={continueHref}>
                    <WandSparkles />
                    {continueLabel}
                    <ArrowRight />
                  </Link>
                </Button>
                <Button variant="outline" onClick={() => setEditing(!editing)}>
                  <Save />
                  {editing ? "설정 닫기" : "프로젝트 설정"}
                </Button>
                {firstEpisode && metrics?.scene_count ? (
                  <Button asChild variant="ghost">
                    <Link
                      href={`/projects/${projectId}/episodes/${firstEpisode.id}/read`}
                    >
                      <Eye />
                      미리 읽기
                    </Link>
                  </Button>
                ) : null}
              </div>
              <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-white/[.07] pt-4 text-[11px] text-zinc-500">
                <span>{metrics?.episode_count ?? 0} episodes</span>
                <span>{metrics?.scene_count ?? 0} scenes</span>
                <span>
                  수정{" "}
                  {new Intl.DateTimeFormat("ko-KR", {
                    dateStyle: "medium",
                  }).format(new Date(p.updated_at))}
                </span>
              </div>
            </div>
            <div className="relative min-h-64 overflow-hidden border-t border-white/[.06] bg-[#0b0c11] md:min-h-[350px] md:border-l md:border-t-0">
              {metrics?.latest_scene_image_url ? (
                <img
                  src={mediaUrl(metrics.latest_scene_image_url)}
                  alt={metrics.latest_scene_title || `${p.title} 최근 장면`}
                  className="absolute inset-0 size-full object-cover opacity-90"
                />
              ) : p.thumbnail_asset_id ? (
                <div className="absolute inset-0">
                  <AssetImage
                    id={p.thumbnail_asset_id}
                    alt={`${p.title} 표지`}
                    className="size-full"
                  />
                </div>
              ) : (
                <div aria-hidden="true" className="hero-grid absolute inset-0">
                  <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_65%_40%,rgba(139,92,246,.18),transparent_55%)]" />
                </div>
              )}
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#08090d]/90 via-[#08090d]/15 to-transparent" />
              <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between gap-4 sm:bottom-6 sm:left-6 sm:right-6">
                <div>
                  <p className="text-[10px] font-semibold tracking-[.16em] text-violet-200">
                    LATEST SCENE
                  </p>
                  <p className="mt-1 text-sm font-semibold text-white">
                    {metrics?.latest_scene_title ||
                      "작품의 첫 장면이 기다리고 있어요"}
                  </p>
                </div>
                <span className="rounded-full border border-white/15 bg-black/45 px-3 py-1.5 text-[10px] font-medium text-zinc-200">
                  {metrics?.published_count
                    ? `${metrics.published_count}개 게시됨`
                    : "Draft"}
                </span>
              </div>
            </div>
          </section>

          <section
            aria-label="작품 제작 지표"
            className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6"
          >
            <MetricCard
              label="EPISODES"
              value={metrics?.episode_count ?? 0}
              detail="에피소드"
              icon={BookOpen}
            />
            <MetricCard
              label="SCENES"
              value={metrics?.scene_count ?? 0}
              detail="이야기 장면"
              icon={WandSparkles}
            />
            <MetricCard
              label="IMAGES"
              value={`${metrics?.image_count ?? 0} / ${metrics?.scene_count ?? 0}`}
              detail={`${metrics?.scene_count ? Math.round(((metrics.image_count || 0) / metrics.scene_count) * 100) : 0}% 장면 이미지`}
              icon={ImagePlus}
            />
            <MetricCard
              label="MOTION"
              value={`${metrics?.motion_count ?? 0} / ${metrics?.scene_count ?? 0}`}
              detail={`${metrics?.scene_count ? Math.round(((metrics.motion_count || 0) / metrics.scene_count) * 100) : 0}% 장면 영상`}
              icon={Video}
            />
            <MetricCard
              label="CHARACTERS"
              value={metrics?.character_count ?? 0}
              detail={`${metrics?.character_reference_count ?? 0}개 기준 이미지`}
              icon={Sparkles}
            />
            <MetricCard
              label="PUBLISHED"
              value={metrics?.published_count ?? 0}
              detail="게시된 에피소드"
              icon={Send}
            />
          </section>

          <section
            aria-label="제작 단계"
            className="mb-8 overflow-hidden rounded-2xl border border-white/[.08] bg-[#111318] p-4 sm:p-5"
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">Production path</p>
                <p className="mt-1 text-xs text-zinc-500">
                  현재 작업 데이터로 계산한 제작 진행 상황
                </p>
              </div>
              <span className="text-[10px] font-medium text-zinc-500">
                {metrics?.scene_count ?? 0} scenes
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
              {[
                {
                  label: "Story",
                  value: (metrics?.episode_count ?? 0) > 0,
                  detail: `${metrics?.episode_count ?? 0}화`,
                },
                {
                  label: "Characters",
                  value: (metrics?.character_count ?? 0) > 0,
                  detail: `${metrics?.character_count ?? 0}명`,
                },
                {
                  label: "Images",
                  value:
                    (metrics?.scene_count ?? 0) > 0 &&
                    metrics?.image_count === metrics?.scene_count,
                  detail: `${metrics?.image_count ?? 0}/${metrics?.scene_count ?? 0}`,
                },
                {
                  label: "Motion",
                  value:
                    (metrics?.scene_count ?? 0) > 0 &&
                    metrics?.motion_count === metrics?.scene_count,
                  detail: `${metrics?.motion_count ?? 0}/${metrics?.scene_count ?? 0}`,
                },
                {
                  label: "Reader",
                  value: (metrics?.scene_count ?? 0) > 0,
                  detail:
                    (metrics?.scene_count ?? 0) > 0 ? "준비됨" : "장면 필요",
                },
                {
                  label: "Publish",
                  value: (metrics?.published_count ?? 0) > 0,
                  detail:
                    (metrics?.published_count ?? 0) > 0
                      ? `${metrics?.published_count}개 게시`
                      : "미게시",
                },
              ].map((step, index) => (
                <div
                  key={step.label}
                  className="flex min-h-16 items-center gap-2.5 rounded-xl border border-white/[.06] bg-white/[.02] px-3 py-2.5"
                >
                  <span
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold ${step.value ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-200" : "border-white/10 text-zinc-500"}`}
                  >
                    {step.value ? (
                      <Check className="size-3.5" />
                    ) : (
                      String(index + 1).padStart(2, "0")
                    )}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-semibold">
                      {step.label}
                    </span>
                    <span className="mt-0.5 block truncate text-[10px] text-zinc-500">
                      {step.detail}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
      {editing && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            update.mutate({
              title: d.get("title"),
              description: d.get("description"),
              genre: d.get("genre"),
              status: d.get("status"),
            });
          }}
          className="mb-7 space-y-4 rounded-2xl border border-zinc-200 bg-white p-6"
        >
          <label className="field-label">
            제목
            <Input
              name="title"
              defaultValue={p.title}
              required
              maxLength={120}
            />
          </label>
          <label className="field-label">
            소개
            <Textarea
              name="description"
              defaultValue={p.description}
              maxLength={5000}
            />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="field-label">
              장르
              <select name="genre" defaultValue={p.genre}>
                {Object.entries(genres).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label">
              상태
              <select name="status" defaultValue={p.status}>
                <option value="draft">초안</option>
                <option value="active">제작 중</option>
                <option value="archived">보관됨</option>
              </select>
            </label>
          </div>
          {update.error && <ErrorState error={update.error} />}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button disabled={update.isPending}>
              <Save />
              {update.isPending ? "저장 중" : "설정 저장"}
            </Button>
            <ConfirmDelete
              label="프로젝트와 모든 에피소드를"
              onDelete={() => deletion.mutate()}
              pending={deletion.isPending}
            />
          </div>
        </form>
      )}
      {(deletion.error || cover.error) && (
        <ErrorState error={deletion.error || cover.error} />
      )}
      {!episodesOnly && (
        <div className="mb-8 grid gap-5 md:grid-cols-[240px_1fr]">
          <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
            <AssetImage
              id={p.thumbnail_asset_id}
              alt={`${p.title} 표지`}
              className="aspect-[1.5]"
            />
            <label className="flex cursor-pointer items-center justify-center gap-2 p-3 text-xs font-semibold text-zinc-500">
              <ImagePlus className="size-4" />
              {cover.isPending ? "업로드 중" : "표지 이미지 업로드"}
              <input
                type="file"
                aria-label="표지 이미지 업로드"
                accept="image/png,image/jpeg,image/webp"
                className="sr-only"
                disabled={cover.isPending}
                onChange={(e) => {
                  if (e.target.files?.[0]) cover.mutate(e.target.files[0]);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              {
                href: "assets",
                title: "프로젝트 이미지",
                text: "직접 그린 장면과 영감을 한곳에",
                icon: ImagePlus,
              },
              {
                href: "story",
                title: "이야기 설정",
                text: "아이디어를 장면별 AI Story 초안으로 만들기",
                icon: BookOpen,
              },
            ].map(({ href, title, text, icon: Icon }) => (
              <Link
                key={href}
                href={`/projects/${projectId}/${href}`}
                className="flex flex-col justify-center rounded-2xl border border-zinc-200 bg-white p-6 hover:border-violet-300"
              >
                <Icon className="mb-4 size-6 text-violet-500" />
                <h2 className="text-sm font-semibold">{title}</h2>
                <p className="mt-2 text-xs leading-5 text-zinc-400">{text}</p>
                <ArrowRight className="mt-5 size-4 text-zinc-400" />
              </Link>
            ))}
          </div>
        </div>
      )}
      <section id="episodes" className="scroll-mt-6">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-bold">
            에피소드{" "}
            <span className="ml-1 text-sm font-normal text-zinc-400">
              {episodes.data?.length || 0}
            </span>
          </h2>
          <Button size="sm" onClick={() => setAdding(!adding)}>
            {adding ? <X /> : <Plus />}
            {adding ? "닫기" : "에피소드 만들기"}
          </Button>
        </div>
        {adding && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const d = new FormData(e.currentTarget);
              createEpisode.mutate({
                title: d.get("title"),
                description: d.get("description"),
              });
            }}
            className="mb-5 space-y-4 rounded-2xl border border-violet-200 bg-white p-5"
          >
            <label className="field-label">
              에피소드 제목
              <Input
                name="title"
                placeholder="예: 낯선 편지가 도착했다"
                required
                maxLength={120}
                autoFocus
              />
            </label>
            <label className="field-label">
              에피소드 소개
              <Textarea
                name="description"
                placeholder="이 에피소드에서 일어나는 일을 적어 주세요."
                maxLength={5000}
              />
            </label>
            {createEpisode.error && <ErrorState error={createEpisode.error} />}
            <Button type="submit" disabled={createEpisode.isPending}>
              {createEpisode.isPending ? "만드는 중" : "에피소드 생성"}
            </Button>
          </form>
        )}
        {episodes.isPending ? (
          <Loading />
        ) : episodes.error ? (
          <ErrorState
            error={episodes.error}
            retry={() => void episodes.refetch()}
          />
        ) : !episodes.data?.length ? (
          <EmptyState
            title="아직 첫 장면이 비어 있어요"
            description="에피소드를 만든 다음, 패널과 이미지를 하나씩 추가해 보세요."
          >
            <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
              <Plus />첫 에피소드 만들기
            </Button>
          </EmptyState>
        ) : (
          <div className="space-y-3">
            {episodes.data.map((episode) => (
              <Link
                href={`/projects/${projectId}/episodes/${episode.id}`}
                key={episode.id}
                className="flex items-center gap-5 rounded-xl border border-zinc-200 bg-white p-5 hover:border-violet-300"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-violet-50 text-sm font-bold text-violet-500">
                  {String(episode.number).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-sm font-semibold">
                    {episode.title}
                  </h3>
                  <p className="mt-1 truncate text-xs text-zinc-400">
                    {episode.description || "이야기를 채워 주세요."}
                  </p>
                </div>
                <span className="text-[10px] text-zinc-400">초안</span>
                <ArrowRight className="size-4 text-zinc-400" />
              </Link>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: number | string;
  detail: string;
  icon: typeof BookOpen;
}) {
  return (
    <article className="rounded-2xl border border-white/[.08] bg-[#111318] p-4 transition-colors hover:border-white/[.14] sm:p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold tracking-[.12em] text-zinc-500">
          {label}
        </p>
        <Icon className="size-4 text-violet-300" aria-hidden="true" />
      </div>
      <p className="mt-4 text-2xl font-semibold tabular-nums tracking-tight text-zinc-100 sm:text-3xl">
        {value}
      </p>
      <p className="mt-1 truncate text-[11px] text-zinc-500">{detail}</p>
    </article>
  );
}
