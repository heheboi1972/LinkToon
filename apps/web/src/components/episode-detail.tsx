"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  ImagePlus,
  Plus,
  Save,
  Send,
  X,
} from "lucide-react";
import { api, patch, post, remove, uploadImage } from "@/lib/api";
import type { Episode, Panel } from "@/lib/types";
import { PageHeading, ConfirmDelete } from "@/components/shell";
import { AssetImage } from "@/components/asset-image";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { EmptyState, ErrorState, Loading } from "@/components/states";

export function EpisodeDetail({
  projectId,
  episodeId,
}: {
  projectId: string;
  episodeId: string;
}) {
  const client = useQueryClient();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const episode = useQuery({
    queryKey: ["episode", episodeId],
    queryFn: () => api<Episode>(`/episodes/${episodeId}`),
  });
  const panels = useQuery({
    queryKey: ["panels", episodeId],
    queryFn: () => api<Panel[]>(`/episodes/${episodeId}/panels?limit=200`),
  });
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["panels", episodeId] }),
      client.invalidateQueries({ queryKey: ["projects"] }),
    ]);
  }
  const add = useMutation({
    mutationFn: () => post<Panel>(`/episodes/${episodeId}/panels`, {}),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: (data: unknown) => patch(`/episodes/${episodeId}`, data),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["episode", episodeId] });
      await client.invalidateQueries({ queryKey: ["episodes", projectId] });
      setEditing(false);
    },
  });
  const deletion = useMutation({
    mutationFn: () => remove(`/episodes/${episodeId}`),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["episodes", projectId] });
      router.push(`/projects/${projectId}`);
    },
  });
  if (episode.isPending) return <Loading />;
  if (episode.error || !episode.data)
    return (
      <ErrorState error={episode.error} retry={() => void episode.refetch()} />
    );
  if (episode.data.project_id !== projectId)
    return (
      <ErrorState error={new Error("이 프로젝트의 에피소드가 아닙니다.")} />
    );
  const ep = episode.data;
  return (
    <>
      <Link
        href={`/projects/${projectId}`}
        className="mb-5 inline-flex items-center gap-2 text-xs text-zinc-500"
      >
        <ArrowLeft className="size-3" />
        프로젝트로 돌아가기
      </Link>
      <PageHeading
        eyebrow={`EPISODE ${String(ep.number).padStart(2, "0")}`}
        title={ep.title}
        description={`${panels.data?.length || 0}개의 패널 · 한 장면씩 이야기를 채워 보세요.`}
      >
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/projects/${projectId}/episodes/${episodeId}/read`}>
              <BookOpen />
              읽기
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href={`/projects/${projectId}/episodes/${episodeId}/publish`}>
              <Send />
              게시
            </Link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing(!editing)}
          >
            에피소드 설정
          </Button>
          <Button
            size="sm"
            disabled={add.isPending}
            onClick={() => add.mutate()}
          >
            <Plus />
            {add.isPending ? "추가 중" : "패널 추가"}
          </Button>
        </div>
      </PageHeading>
      {editing && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            update.mutate({
              title: d.get("title"),
              description: d.get("description"),
            });
          }}
          className="mb-6 space-y-4 rounded-2xl border border-zinc-200 bg-white p-5"
        >
          <label className="field-label">
            제목
            <Input
              name="title"
              defaultValue={ep.title}
              required
              maxLength={120}
            />
          </label>
          <label className="field-label">
            소개
            <Textarea
              name="description"
              defaultValue={ep.description}
              maxLength={5000}
            />
          </label>
          <div className="flex flex-wrap justify-between gap-3">
            <Button disabled={update.isPending}>
              <Save />
              저장
            </Button>
            <ConfirmDelete
              label="에피소드와 모든 패널을"
              onDelete={() => deletion.mutate()}
              pending={deletion.isPending}
            />
          </div>
          {update.error && <ErrorState error={update.error} />}
        </form>
      )}
      {(add.error || deletion.error) && (
        <ErrorState error={add.error || deletion.error} />
      )}
      {panels.isPending ? (
        <Loading />
      ) : panels.error ? (
        <ErrorState error={panels.error} retry={() => void panels.refetch()} />
      ) : !panels.data?.length ? (
        <EmptyState
          title="첫 번째 패널을 추가해 보세요"
          description="이미지를 업로드하고 장면 설명과 대사를 저장할 수 있어요."
        >
          <Button onClick={() => add.mutate()} disabled={add.isPending}>
            <Plus />첫 패널 추가
          </Button>
        </EmptyState>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {panels.data.map((panel, index) => (
            <PanelCard
              key={panel.id}
              panel={panel}
              index={index}
              projectId={projectId}
              onChange={refresh}
            />
          ))}
          <button
            onClick={() => add.mutate()}
            disabled={add.isPending}
            className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-zinc-200 bg-white/40 text-sm text-zinc-400 hover:border-violet-300 hover:text-violet-600"
          >
            <Plus className="size-7" />
            {add.isPending ? "추가 중" : "다음 패널 추가"}
          </button>
        </div>
      )}
    </>
  );
}

export function PanelCard({
  panel,
  index,
  projectId,
  onChange,
}: {
  panel: Panel;
  index: number;
  projectId: string;
  onChange: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const save = useMutation({
    mutationFn: (data: unknown) => patch(`/panels/${panel.id}`, data),
    onSuccess: async () => {
      await onChange();
      setEditing(false);
    },
  });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const asset = await uploadImage(projectId, file);
      return patch(`/panels/${panel.id}`, { image_asset_id: asset.id });
    },
    onSuccess: onChange,
  });
  const deletion = useMutation({
    mutationFn: () => remove(`/panels/${panel.id}`),
    onSuccess: onChange,
  });
  return (
    <article className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
      <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3">
        <span className="text-[11px] font-bold text-zinc-500">
          PANEL {String(index + 1).padStart(2, "0")}
        </span>
        <span className="rounded bg-zinc-50 px-2 py-1 text-[9px] text-zinc-400">
          {panel.status === "static" ? "이미지" : "빈 패널"}
        </span>
      </div>
      <AssetImage
        id={panel.image_asset_id}
        alt={panel.title || `패널 ${index + 1}`}
        className="aspect-[4/3]"
      />
      <div className="p-4">
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-zinc-200 py-2 text-xs font-semibold text-zinc-600">
          <ImagePlus className="size-4" />
          {upload.isPending
            ? "업로드 중…"
            : panel.image_asset_id
              ? "이미지 교체"
              : "이미지 업로드"}
          <input
            aria-label={`패널 ${index + 1} 이미지 업로드`}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            disabled={upload.isPending}
            onChange={(e) => {
              if (e.target.files?.[0]) upload.mutate(e.target.files[0]);
              e.target.value = "";
            }}
          />
        </label>
        {panel.image_asset_id && (
          <button
            className="mt-2 text-[10px] text-zinc-400"
            disabled={save.isPending}
            onClick={() => save.mutate({ image_asset_id: null })}
          >
            이미지 연결 해제
          </button>
        )}
        {editing ? (
          <form
            className="mt-4 space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              const d = new FormData(e.currentTarget);
              save.mutate({
                title: d.get("title"),
                description: d.get("description"),
                dialogue: d.get("dialogue"),
              });
            }}
          >
            <label className="field-label">
              패널 제목
              <Input name="title" defaultValue={panel.title} maxLength={120} />
            </label>
            <label className="field-label">
              장면 설명
              <Textarea
                name="description"
                defaultValue={panel.description}
                maxLength={5000}
                className="min-h-20"
              />
            </label>
            <label className="field-label">
              대사
              <Textarea
                name="dialogue"
                defaultValue={panel.dialogue}
                maxLength={5000}
                className="min-h-20"
              />
            </label>
            <div className="flex gap-2">
              <Button size="sm" disabled={save.isPending}>
                <Save />
                저장
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setEditing(false)}
              >
                <X />
                취소
              </Button>
            </div>
          </form>
        ) : (
          <>
            <h3 className="mt-4 text-sm font-semibold">
              {panel.title || `장면 ${index + 1}`}
            </h3>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-zinc-400">
              {panel.description || "어떤 장면인지 적어 주세요."}
            </p>
            {panel.dialogue && (
              <p className="mt-3 whitespace-pre-wrap rounded-lg bg-violet-50 p-3 text-xs leading-5 text-violet-700">
                “{panel.dialogue}”
              </p>
            )}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEditing(true)}
              >
                장면 편집
              </Button>
              <ConfirmDelete
                label="이 패널을"
                onDelete={() => deletion.mutate()}
                pending={deletion.isPending}
              />
            </div>
          </>
        )}
        {(save.error || upload.error || deletion.error) && (
          <ErrorState error={save.error || upload.error || deletion.error} />
        )}
      </div>
    </article>
  );
}
