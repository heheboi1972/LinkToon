"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, Play, VolumeX } from "lucide-react";
import { useAuth } from "@/components/providers";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { getEpisodeReader, mediaUrl } from "@/lib/api";
import type { ReaderScene } from "@/lib/types";

const PROGRESS_REFRESH_MS = 10 * 60 * 1000;
const EMPTY_SCENES: ReaderScene[] = [];

export function EpisodeReader({
  projectId,
  episodeId,
}: {
  projectId: string;
  episodeId: string;
}) {
  const { user } = useAuth();
  const pathname = usePathname();
  const storageKey = `linktoon:reader:${user?.id ?? ""}:${episodeId}`;
  const motionKey = `linktoon:reader-motion:${user?.id ?? ""}`;
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null);
  const [resumeSceneId, setResumeSceneId] = useState<string | null>(null);
  const [resumeChecked, setResumeChecked] = useState(false);
  const [resumeDismissed, setResumeDismissed] = useState(false);
  const [autoMotion, setAutoMotion] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [playingVideoId, setPlayingVideoId] = useState<string | null>(null);
  const sceneElements = useRef(new Map<string, HTMLElement>());
  const checkedProgressKey = useRef<string | null>(null);

  const reader = useQuery({
    queryKey: ["episode-reader", user?.id, episodeId],
    queryFn: () => getEpisodeReader(episodeId),
    enabled: Boolean(user?.id && episodeId),
    staleTime: 8 * 60 * 1000,
    refetchInterval: PROGRESS_REFRESH_MS,
  });
  const scenes = reader.data?.scenes ?? EMPTY_SCENES;

  useEffect(() => {
    if (!user?.id) return;
    const frame = window.requestAnimationFrame(() => {
      try {
        setAutoMotion(localStorage.getItem(motionKey) === "on");
      } catch {
        setAutoMotion(false);
      }
    });
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    const reducedMotionFrame = window.requestAnimationFrame(update);
    media.addEventListener("change", update);
    return () => {
      window.cancelAnimationFrame(frame);
      window.cancelAnimationFrame(reducedMotionFrame);
      media.removeEventListener("change", update);
    };
  }, [motionKey, user?.id]);

  useEffect(() => {
    const isReaderRoute = pathname?.endsWith(`/episodes/${episodeId}/read`) ?? false;
    if (!isReaderRoute) {
      checkedProgressKey.current = null;
      return;
    }
    if (!reader.data || !user?.id || checkedProgressKey.current === storageKey) return;
    setResumeChecked(false);
    setResumeSceneId(null);
    setResumeDismissed(false);
    const frame = window.requestAnimationFrame(() => {
      checkedProgressKey.current = storageKey;
      try {
        const saved = localStorage.getItem(storageKey);
        const isValid = saved && reader.data?.scenes.some((scene) => scene.id === saved);
        if (isValid && reader.data?.scenes[0]?.id !== saved) {
          setResumeSceneId(saved);
          setResumeDismissed(false);
        } else {
          if (saved && !isValid) localStorage.removeItem(storageKey);
          setResumeSceneId(null);
          setResumeDismissed(true);
        }
      } catch {
        setResumeSceneId(null);
        setResumeDismissed(true);
      }
      setResumeChecked(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [episodeId, pathname, reader.data, storageKey, user?.id]);

  useEffect(() => {
    if (!scenes.length || typeof IntersectionObserver === "undefined") return;
    const visible = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset.readerScene;
          if (!id) continue;
          if (entry.isIntersecting) visible.set(id, entry.intersectionRatio);
          else visible.delete(id);
        }
        let nextId: string | null = null;
        let nextRatio = 0;
        for (const [id, ratio] of visible) {
          if (ratio > nextRatio) {
            nextId = id;
            nextRatio = ratio;
          }
        }
        setActiveSceneId((current) => (current === nextId ? current : nextId));
      },
      { rootMargin: "-18% 0px -30% 0px", threshold: [0, 0.2, 0.45, 0.7, 1] },
    );
    for (const element of sceneElements.current.values()) observer.observe(element);
    return () => observer.disconnect();
  }, [scenes]);

  const activeIndex = Math.max(
    0,
    scenes.findIndex((scene) => scene.id === activeSceneId),
  );
  const motionCanPlay =
    autoMotion && !reducedMotion && resumeChecked && (!resumeSceneId || resumeDismissed);

  useEffect(() => {
    if (!activeSceneId || !resumeChecked || (resumeSceneId && !resumeDismissed)) return;
    const timer = window.setTimeout(() => {
      try {
        localStorage.setItem(storageKey, activeSceneId);
      } catch {
        // Reading remains available when browser storage is disabled.
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [activeSceneId, resumeChecked, resumeSceneId, resumeDismissed, storageKey]);

  const setSceneRef = useCallback(
    (id: string, element: HTMLElement | null) => {
      if (element) sceneElements.current.set(id, element);
      else sceneElements.current.delete(id);
    },
    [],
  );

  const resumeAt = useCallback(
    (id: string) => {
      setActiveSceneId(id);
      setResumeSceneId(null);
      setResumeDismissed(true);
      window.requestAnimationFrame(() => {
        sceneElements.current.get(id)?.scrollIntoView({
          behavior: reducedMotion ? "auto" : "smooth",
          block: "start",
        });
      });
    },
    [reducedMotion],
  );

  const startOver = useCallback(() => {
    const first = scenes[0];
    setResumeSceneId(null);
    setResumeDismissed(true);
    if (first) {
      setActiveSceneId(first.id);
      try {
        localStorage.setItem(storageKey, first.id);
      } catch {
        // Reading remains available when browser storage is disabled.
      }
      window.requestAnimationFrame(() =>
        sceneElements.current.get(first.id)?.scrollIntoView({
          behavior: reducedMotion ? "auto" : "smooth",
          block: "start",
        }),
      );
    }
  }, [reducedMotion, scenes, storageKey]);

  const toggleAutoMotion = useCallback(() => {
    const next = !autoMotion;
    setAutoMotion(next);
    try {
      localStorage.setItem(motionKey, next ? "on" : "off");
    } catch {
      // Preference is optional; the control still works for this visit.
    }
  }, [autoMotion, motionKey]);

  const refreshMedia = () => {
    void reader.refetch();
  };

  if (reader.isPending) return <Loading label="에피소드를 불러오는 중" />;
  if (reader.isError || !reader.data) {
    const notFound = (reader.error as { status?: number } | null)?.status === 404;
    return (
      <section className="mx-auto max-w-3xl py-8">
        <ReaderBack projectId={projectId} episodeId={episodeId} />
        {notFound ? (
          <div role="alert" className="my-6 rounded-2xl bg-white p-6 text-sm text-zinc-600">
            이 에피소드를 볼 수 없습니다. 주소와 계정을 확인해 주세요.
            <Button className="mt-4" variant="outline" onClick={refreshMedia}>
              다시 시도
            </Button>
          </div>
        ) : (
          <ErrorState error={reader.error} retry={refreshMedia} />
        )}
      </section>
    );
  }

  if (reader.data.project_id !== projectId) {
    return (
      <ErrorState
        error={new Error("이 프로젝트에서 해당 에피소드를 읽을 수 없습니다.")}
      />
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl pb-14">
      <nav
        aria-label="Reader navigation"
        className="sticky top-0 z-20 -mx-5 mb-6 flex min-h-14 items-center justify-between gap-3 border-b border-zinc-200/70 bg-[#f8f9fc]/95 px-4 py-2 backdrop-blur sm:-mx-9 sm:px-8 lg:-mx-11 lg:px-10"
      >
        <ReaderBack projectId={projectId} episodeId={episodeId} />
        {scenes.length > 0 && (
          <div className="flex items-center gap-3">
            <span className="whitespace-nowrap text-xs font-semibold tabular-nums text-zinc-500">
              {activeIndex + 1} / {scenes.length}
            </span>
            <div
              role="progressbar"
              aria-label="읽기 진행"
              aria-valuemin={1}
              aria-valuemax={scenes.length}
              aria-valuenow={activeIndex + 1}
              className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-200 sm:w-28"
            >
              <div
                className="h-full rounded-full bg-violet-600 transition-[width]"
                style={{ width: `${((activeIndex + 1) / scenes.length) * 100}%` }}
              />
            </div>
          </div>
        )}
      </nav>

      <header className="mb-8 px-1 sm:mb-10">
        <p className="mb-2 text-xs font-semibold tracking-wide text-violet-600">
          EPISODE {String(reader.data.number).padStart(2, "0")}
        </p>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-950 sm:text-3xl">
          {reader.data.title}
        </h1>
        {reader.data.summary && (
          <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-zinc-600 sm:text-base">
            {reader.data.summary}
          </p>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button
            variant={autoMotion && !reducedMotion ? "default" : "outline"}
            size="sm"
            aria-pressed={autoMotion && !reducedMotion}
            aria-label="Motion 자동 재생 설정"
            disabled={reducedMotion}
            onClick={toggleAutoMotion}
          >
            {reducedMotion ? <VolumeX /> : <Play />}
            Motion 자동 재생 {autoMotion && !reducedMotion ? "켜짐" : "꺼짐"}
          </Button>
          {reducedMotion && (
            <span className="text-xs text-zinc-500">
              기기의 움직임 줄이기 설정에 따라 자동 재생을 껐습니다.
            </span>
          )}
        </div>
      </header>

      {resumeSceneId && !resumeDismissed && (
        <aside
          aria-label="읽기 이어보기"
          className="mb-8 flex flex-col gap-3 rounded-2xl border border-violet-100 bg-violet-50 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5"
        >
          <div>
            <p className="font-semibold text-violet-950">읽던 곳부터 이어볼까요?</p>
            <p className="mt-1 text-sm text-violet-800">마지막으로 본 장면으로 이동합니다.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => resumeAt(resumeSceneId)}>
              이어서 보기
            </Button>
            <Button size="sm" variant="outline" onClick={startOver}>
              처음부터 보기
            </Button>
          </div>
        </aside>
      )}

      {scenes.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-16 text-center">
          <BookOpen className="mx-auto size-8 text-violet-400" aria-hidden="true" />
          <h2 className="mt-4 font-semibold text-zinc-900">아직 읽을 장면이 없습니다.</h2>
          <p className="mt-2 text-sm text-zinc-500">장면이 준비되면 여기에서 감상할 수 있어요.</p>
        </div>
      ) : (
        <div className="space-y-12 sm:space-y-16">
          {scenes.map((scene, index) => (
            <ReaderSceneCard
              key={scene.id}
              scene={scene}
              index={index}
              activeIndex={activeIndex}
              register={setSceneRef}
              activeSceneId={activeSceneId}
              playingVideoId={playingVideoId}
              autoPlay={motionCanPlay}
              reducedMotion={reducedMotion}
              onVideoPlay={setPlayingVideoId}
              onVideoError={refreshMedia}
            />
          ))}
        </div>
      )}
    </main>
  );
}

function ReaderBack({ projectId, episodeId }: { projectId: string; episodeId: string }) {
  return (
    <Link
      href={`/projects/${projectId}/episodes/${episodeId}`}
      className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-medium text-zinc-600 outline-none hover:bg-white hover:text-violet-700 focus-visible:ring-4 focus-visible:ring-violet-200"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      <span className="hidden sm:inline">에피소드로 돌아가기</span>
      <span className="sm:hidden">돌아가기</span>
    </Link>
  );
}

function ReaderSceneCard({
  scene,
  index,
  activeIndex,
  register,
  activeSceneId,
  playingVideoId,
  autoPlay,
  reducedMotion,
  onVideoPlay,
  onVideoError,
}: {
  scene: ReaderScene;
  index: number;
  activeIndex: number;
  register: (id: string, element: HTMLElement | null) => void;
  activeSceneId: string | null;
  playingVideoId: string | null;
  autoPlay: boolean;
  reducedMotion: boolean;
  onVideoPlay: (id: string | null) => void;
  onVideoError: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const autoStarted = useRef(false);
  const mediaRetryUsed = useRef(false);
  const [failedVideoSource, setFailedVideoSource] = useState<string | null>(null);
  const [failedImageSource, setFailedImageSource] = useState<string | null>(null);
  const imageSrc = mediaUrl(scene.image_url ?? null);
  const videoSrc = mediaUrl(scene.video_url ?? null);
  const videoFailed = Boolean(videoSrc && failedVideoSource === videoSrc);
  const imageFailed = Boolean(imageSrc && failedImageSource === imageSrc);
  const shouldAutoplay = autoPlay && !reducedMotion && activeSceneId === scene.id;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (playingVideoId && playingVideoId !== scene.id) {
      if (autoStarted.current) autoStarted.current = false;
      video.pause();
    } else if (shouldAutoplay) {
      autoStarted.current = true;
      video.muted = true;
      void video.play().catch(() => undefined);
    } else if (autoStarted.current) {
      autoStarted.current = false;
      video.pause();
    }
  }, [autoPlay, onVideoPlay, playingVideoId, scene.id, shouldAutoplay]);

  const onError = () => {
    if (videoSrc) setFailedVideoSource(videoSrc);
    onVideoPlay(playingVideoId === scene.id ? null : playingVideoId);
    if (!mediaRetryUsed.current) {
      mediaRetryUsed.current = true;
      onVideoError();
    }
  };

  return (
    <article
      ref={(element) => register(scene.id, element)}
      data-reader-scene={scene.id}
      className="scroll-mt-20 overflow-hidden rounded-[1.35rem] bg-white shadow-[0_12px_45px_rgba(24,24,27,0.07)] ring-1 ring-zinc-200/70"
      aria-labelledby={`reader-scene-title-${scene.id}`}
    >
      <div className="px-4 pb-3 pt-4 sm:px-7 sm:pt-6">
        <p className="text-[11px] font-semibold tracking-[.16em] text-violet-600">
          {String(index + 1).padStart(2, "0")}
        </p>
        {scene.title && (
          <h2
            id={`reader-scene-title-${scene.id}`}
            className="mt-1 text-lg font-semibold text-zinc-900 sm:text-xl"
          >
            {scene.title}
          </h2>
        )}
      </div>

      <figure className="overflow-hidden bg-zinc-100">
        {videoSrc && !videoFailed ? (
          <video
            ref={videoRef}
            src={videoSrc}
            poster={imageSrc}
            controls
            muted
            playsInline
            preload={index <= activeIndex + 2 ? "metadata" : "none"}
            aria-label={`${scene.title || `장면 ${index + 1}`} Motion 영상`}
            className="block h-auto max-h-[82svh] w-full bg-black object-contain"
            onPlay={() => onVideoPlay(scene.id)}
            onPause={() => {
              if (playingVideoId === scene.id) onVideoPlay(null);
            }}
            onError={onError}
          />
        ) : imageSrc && !imageFailed ? (
          // Capability URLs are private and refreshed with the Reader read model.
          <img
            src={imageSrc}
            alt={`장면 ${index + 1}${scene.title ? `: ${scene.title}` : " 일러스트"}`}
            loading={
              index < 2 || (index >= activeIndex && index <= activeIndex + 2)
                ? "eager"
                : "lazy"
            }
            decoding="async"
            fetchPriority={index === 0 ? "high" : "auto"}
            className="mx-auto block h-auto max-h-[82svh] w-full object-contain"
            onError={() => {
              if (imageSrc) setFailedImageSource(imageSrc);
              if (!mediaRetryUsed.current) {
                mediaRetryUsed.current = true;
                onVideoError();
              }
            }}
          />
        ) : imageFailed ? (
          <div role="status" className="flex min-h-36 items-center justify-center px-6 py-9 text-center text-sm text-zinc-500 sm:min-h-48">
            이미지를 불러오지 못했습니다.
          </div>
        ) : (
          <div className="flex min-h-36 items-center justify-center px-6 py-9 text-center text-sm text-zinc-500 sm:min-h-48">
            장면 이미지는 아직 준비되지 않았어요.
          </div>
        )}
        {videoFailed && imageSrc && !imageFailed && (
          <figcaption className="px-4 py-2 text-center text-xs text-zinc-500">
            Motion을 불러오지 못해 장면 이미지로 보여드려요.
          </figcaption>
        )}
        {videoFailed && !imageSrc && (
          <figcaption role="status" className="px-4 py-2 text-center text-xs text-zinc-500">
            Motion을 불러오지 못했습니다.
          </figcaption>
        )}
      </figure>

      <div className="space-y-4 px-4 py-5 sm:px-7 sm:py-7">
        {scene.narration && (
          <p className="whitespace-pre-wrap text-[15px] leading-8 text-zinc-700 sm:text-base sm:leading-9">
            {scene.narration}
          </p>
        )}
        {scene.dialogue.length > 0 && (
          <ul aria-label="대사" className="space-y-3">
            {scene.dialogue.map((line, lineIndex) => (
              <li
                key={`${scene.id}-${lineIndex}`}
                className="rounded-2xl border border-violet-100 bg-violet-50/70 px-4 py-3 sm:px-5"
              >
                <p className="text-xs font-semibold text-violet-700">{line.character}</p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-zinc-800 sm:text-base sm:leading-7">
                  {line.text}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
