"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  Copy,
  Eye,
  Globe2,
  ImageIcon,
  LockKeyhole,
  RefreshCw,
  Send,
  Sparkles,
  Video,
} from "lucide-react";
import {
  ApiError,
  createPublication,
  getEpisodePublication,
  getEpisodeReader,
  getProjectOverview,
  mediaUrl,
  republish,
  unpublish,
  updatePublication,
} from "@/lib/api";
import { api } from "@/lib/api";
import type {
  Episode,
  EpisodeReader,
  ProjectOverview,
  Publication,
  PublicationVisibility,
} from "@/lib/types";
import { PageHeading } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { ErrorState, Loading } from "@/components/states";

const visibilityOptions: {
  value: PublicationVisibility;
  label: string;
  description: string;
  icon: typeof Globe2;
}[] = [
  {
    value: "public",
    label: "공개",
    description: "누구나 링크에서 볼 수 있고 공개 작품으로 취급됩니다.",
    icon: Globe2,
  },
  {
    value: "unlisted",
    label: "링크 공개",
    description:
      "링크를 가진 사람만 감상할 수 있으며 검색에는 노출되지 않습니다.",
    icon: Eye,
  },
  {
    value: "private",
    label: "비공개",
    description: "작가 작업실에서만 확인할 수 있습니다.",
    icon: LockKeyhole,
  },
];

export function PublicationManager({
  projectId,
  episodeId,
}: {
  projectId: string;
  episodeId: string;
}) {
  const client = useQueryClient();
  const [title, setTitle] = useState<string | null>(null);
  const [description, setDescription] = useState<string | null>(null);
  const [visibility, setVisibility] = useState<PublicationVisibility | null>(
    null,
  );
  const [copied, setCopied] = useState(false);
  const episode = useQuery({
    queryKey: ["episode", episodeId],
    queryFn: () => api<Episode>(`/episodes/${episodeId}`),
  });
  const reader = useQuery({
    queryKey: ["episode-reader", episodeId],
    queryFn: () => getEpisodeReader(episodeId),
  });
  const overview = useQuery({
    queryKey: ["project-overview", projectId],
    queryFn: () => getProjectOverview(projectId),
  });
  const publicationQuery = useQuery({
    queryKey: ["episode-publication", episodeId],
    queryFn: () => getEpisodePublication(episodeId),
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  const publication = publicationQuery.data;

  const formTitle = title ?? publication?.title ?? episode.data?.title ?? "";
  const formDescription =
    description ?? publication?.description ?? episode.data?.description ?? "";
  const formVisibility = visibility ?? publication?.visibility ?? "public";
  const metadataDirty = Boolean(
    publication &&
    (formTitle !== publication.title ||
      formDescription !== publication.description ||
      formVisibility !== publication.visibility),
  );

  const refresh = async (value: Publication) => {
    client.setQueryData(["episode-publication", episodeId], value);
    await Promise.all([
      client.invalidateQueries({ queryKey: ["project-overview", projectId] }),
      client.invalidateQueries({ queryKey: ["projects"] }),
    ]);
  };
  const create = useMutation({
    mutationFn: () =>
      createPublication(episodeId, {
        title: formTitle,
        description: formDescription,
        visibility: formVisibility,
      }),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: () =>
      updatePublication(publication!.id, {
        title: formTitle,
        description: formDescription,
        visibility: formVisibility,
      }),
    onSuccess: refresh,
  });
  const publishAgain = useMutation({
    mutationFn: () => republish(publication!.id),
    onSuccess: refresh,
  });
  const unpublishNow = useMutation({
    mutationFn: () => unpublish(publication!.id),
    onSuccess: refresh,
  });
  const mutationError =
    create.error || update.error || publishAgain.error || unpublishNow.error;
  const pending =
    create.isPending ||
    update.isPending ||
    publishAgain.isPending ||
    unpublishNow.isPending;
  const readyReader = Boolean(reader.data?.scenes.length);
  const isPublished = publication?.status === "published";
  const shareUrl =
    typeof window !== "undefined" && publication
      ? `${window.location.origin}/read/${publication.slug}`
      : "";
  const missingImages = reader.data
    ? reader.data.scenes.filter((scene) => !scene.image_url).length
    : 0;
  const missingMotion = reader.data
    ? reader.data.scenes.filter((scene) => !scene.video_url).length
    : 0;
  const previewScene = reader.data?.scenes.find(
    (scene) => scene.image_url || scene.video_url,
  );

  async function copyLink() {
    if (!shareUrl) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else {
        const field = document.createElement("textarea");
        field.value = shareUrl;
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.append(field);
        field.select();
        const copiedByFallback = document.execCommand("copy");
        field.remove();
        if (!copiedByFallback) throw new Error("copy failed");
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    } catch {
      setCopied(false);
    }
  }

  if (
    episode.isPending ||
    reader.isPending ||
    overview.isPending ||
    publicationQuery.isPending
  ) {
    return <Loading label="게시 상태와 미리보기를 준비하는 중" />;
  }
  if (episode.error || !episode.data || episode.data.project_id !== projectId) {
    return (
      <ErrorState
        error={episode.error || new Error("이 프로젝트의 에피소드가 아닙니다.")}
        retry={() => void episode.refetch()}
      />
    );
  }
  const missingPublication =
    publicationQuery.error instanceof ApiError &&
    publicationQuery.error.status === 404;
  if (
    reader.error ||
    overview.error ||
    (publicationQuery.error && !missingPublication)
  ) {
    return (
      <ErrorState
        error={reader.error || overview.error || publicationQuery.error}
        retry={() =>
          void Promise.all([
            reader.refetch(),
            overview.refetch(),
            publicationQuery.refetch(),
          ])
        }
      />
    );
  }
  const overviewData = overview.data as ProjectOverview;
  const readerData = reader.data as EpisodeReader;

  return (
    <>
      <PageHeading
        eyebrow="PUBLICATION · EPISODE "
        title="작품을 세상에 공개하기"
        description={`${episode.data.title}의 공개 정보를 정하고, 게시 당시의 장면을 고정합니다.`}
      />
      {isPublished && (
        <section
          className="mb-6 flex flex-col gap-4 rounded-2xl border border-emerald-300/20 bg-emerald-400/[0.06] p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6"
          aria-label="게시 완료"
        >
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300">
              <Check className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="font-semibold">
                {formVisibility === "private"
                  ? "게시본이 비공개 상태입니다."
                  : "게시가 완료되었습니다."}
              </p>
              <p className="mt-1 text-sm text-zinc-500">
                v{publication?.current_version} · {publication?.scene_count}개
                장면 ·{" "}
                {formVisibility === "unlisted"
                  ? "링크 공개"
                  : formVisibility === "private"
                    ? "작업실 전용"
                    : "전체 공개"}
              </p>
              {formVisibility !== "private" && (
                <p className="mt-3 truncate rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-zinc-300">
                  {shareUrl}
                </p>
              )}
            </div>
          </div>
          {formVisibility !== "private" && (
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void copyLink()}
              >
                {copied ? <Check /> : <Copy />}
                {copied ? "링크 복사됨" : "링크 복사"}
              </Button>
              <Button asChild type="button" size="sm" variant="outline">
                <Link
                  href={`/read/${publication?.slug}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ArrowUpRight />
                  공개 페이지 열기
                </Link>
              </Button>
            </div>
          )}
        </section>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.82fr)] xl:gap-7">
        <section className="space-y-5">
          <div className="rounded-2xl border border-zinc-200 bg-white p-5 sm:p-7">
            <div className="mb-6 flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-xl bg-violet-50 text-violet-500">
                <Send className="size-5" />
              </span>
              <div>
                <h2 className="font-semibold">게시 정보</h2>
                <p className="mt-1 text-xs text-zinc-500">
                  공유 URL은 제목을 바꾸거나 새 버전을 게시해도 유지됩니다.
                </p>
              </div>
            </div>
            <div className="space-y-5">
              <label className="field-label">
                작품 제목
                <Input
                  value={formTitle}
                  maxLength={120}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label className="field-label">
                소개
                <Textarea
                  value={formDescription}
                  maxLength={5000}
                  rows={4}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>
              <fieldset>
                <legend className="mb-3 text-sm font-semibold text-zinc-300">
                  공개 범위
                </legend>
                <div className="grid gap-2">
                  {visibilityOptions.map(
                    ({ value, label, description: detail, icon: Icon }) => (
                      <label
                        key={value}
                        className={`flex min-h-16 cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors ${formVisibility === value ? "border-violet-300/40 bg-violet-500/[0.08]" : "border-zinc-200 bg-white hover:border-white/15"}`}
                      >
                        <input
                          className="mt-1 accent-violet-400"
                          type="radio"
                          name="visibility"
                          value={value}
                          checked={formVisibility === value}
                          onChange={() => setVisibility(value)}
                        />
                        <Icon
                          className={`mt-0.5 size-4 shrink-0 ${formVisibility === value ? "text-violet-300" : "text-zinc-500"}`}
                        />
                        <span>
                          <span className="block text-sm font-semibold">
                            {label}
                          </span>
                          <span className="mt-1 block text-xs leading-5 text-zinc-500">
                            {detail}
                          </span>
                        </span>
                      </label>
                    ),
                  )}
                </div>
              </fieldset>
            </div>
          </div>

          <div className="rounded-2xl border border-zinc-200 bg-white p-5 sm:p-7">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">게시 준비 상태</h2>
                <p className="mt-1 text-xs text-zinc-500">
                  장면이 있으면 이미지나 Motion 없이도 게시할 수 있습니다.
                </p>
              </div>
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${readyReader ? "bg-emerald-400/10 text-emerald-300" : "bg-amber-400/10 text-amber-200"}`}
              >
                {readyReader ? "Reader 준비됨" : "장면 필요"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Readiness
                label="장면"
                value={`${readerData.scenes.length}`}
                detail="이 에피소드"
                icon={BookOpen}
              />
              <Readiness
                label="이미지"
                value={`${readerData.scenes.length - missingImages}/${readerData.scenes.length}`}
                detail={
                  missingImages ? `${missingImages}개 미완성` : "모두 준비됨"
                }
                icon={ImageIcon}
              />
              <Readiness
                label="Motion"
                value={`${readerData.scenes.length - missingMotion}/${readerData.scenes.length}`}
                detail={
                  missingMotion ? `${missingMotion}개 미생성` : "모두 준비됨"
                }
                icon={Video}
              />
              <Readiness
                label="캐릭터"
                value={`${overviewData.character_count}`}
                detail={`${overviewData.character_reference_count}개 기준 이미지`}
                icon={Sparkles}
              />
            </div>
            {readerData.scenes.length === 0 ? (
              <p
                role="alert"
                className="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-3 text-sm text-amber-100"
              >
                게시하기 전에 Story Studio에서 장면을 하나 이상 만들어 주세요.
              </p>
            ) : missingImages > 0 || missingMotion > 0 ? (
              <p className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-xs leading-5 text-zinc-400">
                이미지 {missingImages}개, Motion {missingMotion}개가 비어
                있습니다. 텍스트 장면도 Reader에서 그대로 감상할 수 있습니다.
              </p>
            ) : null}
          </div>

          {mutationError && <ErrorState error={mutationError} />}
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-zinc-200 bg-white p-4 sm:p-5">
            {publication ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  disabled={pending || !formTitle.trim()}
                  onClick={() => update.mutate()}
                >
                  <Check />
                  {update.isPending ? "저장 중" : "정보 저장"}
                </Button>
                <Button
                  type="button"
                  disabled={pending || !readyReader || metadataDirty}
                  onClick={() => publishAgain.mutate()}
                >
                  <RefreshCw />
                  {publishAgain.isPending
                    ? "새 버전 게시 중"
                    : isPublished
                      ? "변경 내용 다시 게시"
                      : "게시 다시 시작"}
                </Button>
                {isPublished && (
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={pending}
                    onClick={() => unpublishNow.mutate()}
                    className="ml-auto text-zinc-400"
                  >
                    공개 중단
                  </Button>
                )}
              </>
            ) : (
              <Button
                type="button"
                disabled={pending || !readyReader || !formTitle.trim()}
                onClick={() => create.mutate()}
              >
                <Send />
                {create.isPending ? "게시 중" : "게시하기"}
              </Button>
            )}
          </div>
        </section>

        <aside className="h-fit overflow-hidden rounded-2xl border border-zinc-200 bg-white xl:sticky xl:top-6">
          <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4">
            <div>
              <p className="text-[10px] font-bold tracking-[.15em] text-violet-300">
                READER PREVIEW
              </p>
              <p className="mt-1 text-xs text-zinc-500">게시본 미리보기</p>
            </div>
            <span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] text-zinc-400">
              {readerData.scenes.length} SCENES
            </span>
          </div>
          <div className="relative flex aspect-[4/3] items-center justify-center overflow-hidden bg-[#0c0d12]">
            {previewScene?.video_url ? (
              <video
                src={mediaUrl(previewScene.video_url)}
                poster={mediaUrl(previewScene.image_url)}
                controls
                playsInline
                preload="metadata"
                className="size-full object-contain"
              />
            ) : previewScene?.image_url ? (
              <img
                src={mediaUrl(previewScene.image_url)}
                alt={previewScene.title || "첫 장면 미리보기"}
                className="size-full object-contain"
              />
            ) : (
              <div className="flex flex-col items-center gap-3 px-6 text-center">
                <span className="flex size-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] text-violet-300">
                  <ImageIcon className="size-6" />
                </span>
                <p className="text-sm text-zinc-400">
                  장면을 만들면 대표 이미지가 여기에 표시됩니다.
                </p>
              </div>
            )}
            {previewScene?.video_url && (
              <span className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-black/70 px-2.5 py-1 text-[10px] font-medium text-white">
                <Video className="size-3" />
                MOTION
              </span>
            )}
          </div>
          <div className="p-5 sm:p-6">
            <div className="flex items-center gap-2 text-[10px] font-semibold tracking-[.15em] text-violet-300">
              <Sparkles className="size-3.5" />
              LINKTOON ORIGINAL
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">
              {formTitle || episode.data.title}
            </h2>
            <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm leading-6 text-zinc-400">
              {formDescription || "작품의 분위기를 짧게 소개해 보세요."}
            </p>
            <div className="mt-5 flex items-center justify-between border-t border-white/10 pt-4 text-xs text-zinc-500">
              <span>
                {episode.data.number}화 · {readerData.scenes.length}개 장면
              </span>
              <span>
                {readerData.scenes.filter((scene) => scene.video_url).length}{" "}
                Motion
              </span>
            </div>
            {isPublished && formVisibility !== "private" && (
              <Link
                href={`/read/${publication?.slug}`}
                target="_blank"
                className="mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-white/10 text-sm font-semibold text-zinc-200 hover:bg-white/[.04]"
              >
                <Eye className="size-4" />
                공개 Reader 보기
                <ArrowUpRight className="size-4" />
              </Link>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}

function Readiness({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof BookOpen;
}) {
  return (
    <div className="rounded-xl border border-white/[.07] bg-white/[.025] p-3">
      <Icon className="size-4 text-violet-300" />
      <p className="mt-3 text-[10px] font-medium text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 truncate text-[10px] text-zinc-500">{detail}</p>
    </div>
  );
}
