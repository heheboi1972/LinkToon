"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  Clapperboard,
  Play,
  Sparkles,
  VolumeX,
} from "lucide-react";
import { ApiError, getPublicPublication, mediaUrl } from "@/lib/api";
import type { PublicationReader, PublicationScene } from "@/lib/types";

export function PublicReader({
  publication,
}: {
  publication: PublicationReader;
}) {
  const liveReader = useQuery({
    queryKey: ["public-publication", publication.slug],
    queryFn: () => getPublicPublication(publication.slug),
    initialData: publication,
    staleTime: 10 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });
  const current = liveReader.data ?? publication;
  const [activeScene, setActiveScene] = useState(0);
  const [motionAuto, setMotionAuto] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const sceneRefs = useRef(new Map<number, HTMLElement>());
  const count = current.scenes.length;
  const progress = count ? Math.min(count, activeScene + 1) : 0;
  const publishedDate = useMemo(
    () =>
      new Intl.DateTimeFormat("ko-KR", { dateStyle: "long" }).format(
        new Date(current.published_at),
      ),
    [current.published_at],
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!count || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        const order = Number(
          (visible.target as HTMLElement).dataset.sceneOrder,
        );
        if (Number.isInteger(order)) setActiveScene(order);
      },
      { rootMargin: "-20% 0px -35% 0px", threshold: [0.2, 0.45, 0.7] },
    );
    for (const node of sceneRefs.current.values()) observer.observe(node);
    return () => observer.disconnect();
  }, [count]);

  function register(order: number, node: HTMLElement | null) {
    if (node) sceneRefs.current.set(order, node);
    else sceneRefs.current.delete(order);
  }

  if (liveReader.error instanceof ApiError && liveReader.error.status === 404) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#08090d] px-5 text-center text-zinc-100">
        <section className="max-w-md rounded-2xl border border-white/10 bg-[#111318] p-7">
          <BookOpen className="mx-auto size-8 text-violet-300" />
          <h1 className="mt-4 text-xl font-semibold">
            이 작품은 더 이상 공개되지 않습니다.
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            작가가 공개 상태를 변경했거나 공유 링크가 만료되었습니다.
          </p>
          <Link
            href="/"
            className="mt-5 inline-flex min-h-11 items-center justify-center rounded-xl border border-white/10 px-4 text-sm"
          >
            LinkToon으로 돌아가기
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#08090d] text-zinc-100">
      <nav
        aria-label="Reader navigation"
        className="sticky top-0 z-20 border-b border-white/[.07] bg-[#08090d]/90 px-4 backdrop-blur-xl sm:px-8"
      >
        <div className="mx-auto flex min-h-14 max-w-4xl items-center justify-between gap-3">
          <Link
            href="/"
            className="inline-flex min-h-11 items-center gap-2 rounded-lg px-2 text-sm text-zinc-400 hover:bg-white/[.04] hover:text-white"
          >
            <ArrowLeft className="size-4" />
            <span className="hidden sm:inline">LinkToon</span>
          </Link>
          <div className="min-w-0 flex-1 truncate text-center text-xs font-medium text-zinc-300">
            {current.title}
          </div>
          <div className="flex items-center gap-2">
            {count > 0 && (
              <span className="whitespace-nowrap text-xs tabular-nums text-zinc-500">
                {progress} / {count}
              </span>
            )}
            <div
              role="progressbar"
              aria-label="읽기 진행"
              aria-valuemin={0}
              aria-valuemax={count}
              aria-valuenow={progress}
              className="h-1.5 w-12 overflow-hidden rounded-full bg-white/10 sm:w-20"
            >
              <div
                className="h-full rounded-full bg-violet-400 transition-[width]"
                style={{ width: `${count ? (progress / count) * 100 : 0}%` }}
              />
            </div>
          </div>
        </div>
      </nav>

      <div className="mx-auto w-full max-w-4xl px-4 pb-24 sm:px-8">
        <header className="relative mb-8 overflow-hidden rounded-b-3xl border-x border-b border-white/[.07] bg-[#111318] px-5 py-8 sm:px-9 sm:py-10">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-violet-500/[.07] blur-3xl"
          />
          <div className="relative">
            <div className="flex items-center gap-2 text-[10px] font-semibold tracking-[.16em] text-violet-300">
              <Clapperboard className="size-4" />
              LINKTOON ·{" "}
              {current.visibility === "public"
                ? "PUBLIC EDITION"
                : "SHARED EDITION"}
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-100 sm:text-5xl">
            {current.title}
            </h1>
            {current.description && (
              <p className="mt-4 max-w-2xl whitespace-pre-wrap text-sm leading-7 text-zinc-400 sm:text-base">
                {current.description}
              </p>
            )}
            <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-zinc-500">
            <span>by {current.author_name}</span>
              <span aria-hidden="true" className="text-white/20">
                ·
              </span>
              <span>{count} scenes</span>
              <span aria-hidden="true" className="text-white/20">
                ·
              </span>
            <time dateTime={current.published_at}>{publishedDate}</time>
            </div>
            <button
              type="button"
              aria-pressed={motionAuto && !reducedMotion}
              disabled={reducedMotion}
              onClick={() => setMotionAuto((value) => !value)}
              className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 bg-white/[.035] px-4 text-xs font-semibold text-zinc-300 transition-colors hover:bg-white/[.07] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {reducedMotion ? (
                <VolumeX className="size-4" />
              ) : (
                <Play className="size-4" />
              )}
              {reducedMotion
                ? "기기 설정으로 Motion 자동재생 꺼짐"
                : `Motion 자동재생 ${motionAuto ? "켜짐" : "꺼짐"}`}
            </button>
          </div>
        </header>

        {count === 0 ? (
          <section className="rounded-2xl border border-dashed border-white/10 px-6 py-16 text-center">
            <BookOpen className="mx-auto size-8 text-violet-300" />
            <h2 className="mt-4 font-semibold">아직 공개된 장면이 없습니다.</h2>
          </section>
        ) : (
          <div className="space-y-10 sm:space-y-14">
          {current.scenes.map((scene, index) => (
              <PublicSceneCard
              key={`${current.slug}-${scene.order}`}
                scene={scene}
                index={index}
                autoPlay={motionAuto && !reducedMotion && activeScene === index}
                register={register}
              refresh={() => void liveReader.refetch()}
              />
            ))}
          </div>
        )}
        <footer className="mt-16 flex items-center justify-center gap-2 border-t border-white/[.07] pt-6 text-xs text-zinc-600">
          <Sparkles className="size-3.5 text-violet-400" />
          Made with LinkToon
        </footer>
      </div>
    </main>
  );
}

function PublicSceneCard({
  scene,
  index,
  autoPlay,
  register,
  refresh,
}: {
  scene: PublicationScene;
  index: number;
  autoPlay: boolean;
  register: (order: number, node: HTMLElement | null) => void;
  refresh: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const refreshUsed = useRef(false);
  const videoSrc = mediaUrl(scene.video_url);
  const imageSrc = mediaUrl(scene.image_url);
  useEffect(() => {
    if (!video.current) return;
    if (autoPlay) {
      video.current.muted = true;
      void video.current.play().catch(() => undefined);
    } else {
      video.current.pause();
    }
  }, [autoPlay]);
  return (
    <article
      ref={(node) => register(index, node)}
      data-scene-order={index}
      className="scroll-mt-20 overflow-hidden rounded-2xl border border-white/[.08] bg-[#111318] shadow-[0_18px_60px_rgba(0,0,0,.2)]"
    >
      <header className="flex items-start justify-between gap-4 px-4 pb-4 pt-5 sm:px-7 sm:pt-7">
        <div>
          <p className="text-[10px] font-semibold tracking-[.16em] text-violet-300">
            SCENE {String(scene.order).padStart(2, "0")}
          </p>
          {scene.title && (
            <h2 className="mt-2 text-lg font-semibold text-zinc-100 sm:text-xl">
              {scene.title}
            </h2>
          )}
        </div>
        {scene.video_url && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-medium text-zinc-400">
            <Clapperboard className="size-3" />
            MOTION
          </span>
        )}
      </header>
      <figure className="overflow-hidden bg-black/50">
        {videoSrc ? (
          <video
            ref={video}
            src={videoSrc}
            poster={imageSrc}
            controls
            playsInline
            muted
            preload={index <= 1 ? "metadata" : "none"}
            aria-label={`${scene.title || `장면 ${scene.order}`} Motion 영상`}
            className="block max-h-[82svh] w-full bg-black object-contain"
            onError={() => {
              if (!refreshUsed.current) {
                refreshUsed.current = true;
                refresh();
              }
            }}
          />
        ) : imageSrc ? (
          <img
            src={imageSrc}
            alt={`${scene.order}번째 장면${scene.title ? `: ${scene.title}` : " 일러스트"}`}
            loading={index < 2 ? "eager" : "lazy"}
            decoding="async"
            className="mx-auto block max-h-[82svh] w-full object-contain"
            onError={() => {
              if (!refreshUsed.current) {
                refreshUsed.current = true;
                refresh();
              }
            }}
          />
        ) : (
          <div className="flex min-h-40 items-center justify-center px-6 text-sm text-zinc-500">
            이 장면에는 아직 이미지가 없습니다.
          </div>
        )}
      </figure>
      <div className="space-y-5 px-4 py-5 sm:px-7 sm:py-7">
        {scene.narration && (
          <p className="whitespace-pre-wrap text-[15px] leading-8 text-zinc-300 sm:text-base sm:leading-9">
            {scene.narration}
          </p>
        )}
        {scene.dialogue.length > 0 && (
          <ul aria-label="대사" className="space-y-3">
            {scene.dialogue.map((line, lineIndex) => (
              <li
                key={`${scene.order}-${lineIndex}`}
                className="rounded-xl border border-violet-300/10 bg-violet-400/[.045] px-4 py-3 sm:px-5"
              >
                <p className="text-xs font-semibold text-violet-300">
                  {line.character}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-7 text-zinc-200 sm:text-base">
                  “{line.text}”
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
