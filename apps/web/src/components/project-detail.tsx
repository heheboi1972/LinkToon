"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpen, ImagePlus, Plus, Save, X } from "lucide-react";
import { api, patch, post, remove, uploadImage } from "@/lib/api";
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
  const p = project.data;
  return (
    <>
      <PageHeading
        eyebrow={`${genres[p.genre] || p.genre} / ${statuses[p.status]}`}
        title={p.title}
        description={
          p.description || "첫 에피소드를 만들고 이야기를 시작해 보세요."
        }
      >
        <Button variant="outline" onClick={() => setEditing(!editing)}>
          {editing ? "닫기" : "프로젝트 설정"}
        </Button>
      </PageHeading>
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
                text: "아이디어와 비주얼 스타일 확인",
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
      <section>
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
