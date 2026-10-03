"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, RefreshCw, Sparkles } from "lucide-react";
import {
  ApiError,
  cancelGenerationJob,
  createSceneVideoGeneration,
  getAsset,
  getScene,
  mediaUrl,
} from "@/lib/api";
import {
  forgetGenerationJob,
  rememberGenerationJob,
  terminalGenerationStatuses,
  useGenerationJob,
  useRememberedGenerationJob,
} from "@/lib/generation-job";
import { Button } from "@/components/ui/button";

type SceneMotionGeneratorProps = {
  userId: string;
  projectId: string;
  sceneId: string;
  posterUrl?: string;
};

function requestError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return "로그인이 필요합니다. 다시 로그인해 주세요.";
    if (error.status === 403 || error.status === 404)
      return "장면을 찾을 수 없거나 접근할 수 없습니다.";
    if (error.status === 409) return "이 장면의 Motion 생성이 이미 진행 중입니다.";
    if (error.status === 413) return "장면 이미지가 Motion 생성 한도를 초과합니다.";
    if (error.status === 429)
      return "오늘 사용할 수 있는 Motion 생성 횟수를 모두 사용했습니다.";
    if (error.status === 0 || error.status >= 500)
      return "Motion 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  }
  return "Motion 생성 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

function motionStatus(status: string) {
  return {
    queued: "모션 생성 준비 중",
    running: "영상 생성을 시작하고 있어요",
    provider_pending: "AI가 장면을 움직이는 중이에요",
    saving: "영상을 안전하게 저장하고 있어요",
    succeeded: "모션 생성 완료",
    failed: "모션 생성 실패",
    canceled: "모션 생성 취소",
  }[status];
}

export function SceneMotionGenerator({
  userId,
  projectId,
  sceneId,
  posterUrl,
}: SceneMotionGeneratorProps) {
  const queryClient = useQueryClient();
  const scope = `linktoon-scene-motion-job:${userId}:${sceneId}`;
  const rememberedJob = useRememberedGenerationJob(scope);
  const [volatileJob, setVolatileJob] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = useRef(false);
  const invalidated = useRef(new Set<string>());
  const jobId = volatileJob ?? rememberedJob;

  const scene = useQuery({
    queryKey: ["scene", sceneId],
    queryFn: () => getScene(sceneId),
    retry: false,
  });
  const videoAssetId = scene.data?.video_asset_id ?? null;
  const videoAsset = useQuery({
    queryKey: ["asset", videoAssetId],
    queryFn: () => {
      if (!videoAssetId) throw new Error("Video Asset ID is missing");
      return getAsset(videoAssetId);
    },
    enabled: !!videoAssetId,
    retry: false,
    refetchInterval: videoAssetId ? 10 * 60 * 1_000 : false,
  });
  const job = useGenerationJob({
    queryKey: ["scene-motion-job", userId, sceneId, jobId],
    jobId,
    onPollStart: (next) => setVolatileJob((current) => current ?? next),
    validate: (result) =>
      result.project_id === projectId &&
      result.job_type === "video:scene" &&
      result.input.scene_id === sceneId,
  });

  useEffect(() => {
    if (!jobId) return;
    if (job.data?.status === "failed" || job.data?.status === "canceled")
      forgetGenerationJob(scope);
    if (
      job.error instanceof ApiError &&
      [401, 403, 404].includes(job.error.status)
    )
      forgetGenerationJob(scope);
    if (job.data?.status === "succeeded" && !invalidated.current.has(jobId)) {
      invalidated.current.add(jobId);
      void queryClient.invalidateQueries({ queryKey: ["scene", sceneId] });
      void queryClient.invalidateQueries({ queryKey: ["assets", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  }, [job.data?.status, job.error, jobId, projectId, queryClient, sceneId, scope]);

  const inaccessible =
    job.error instanceof ApiError && [401, 403, 404].includes(job.error.status);
  const active =
    !!jobId &&
    !inaccessible &&
    (!job.data || !terminalGenerationStatuses.has(job.data.status));
  const videoSrc = videoAsset.data?.public_url
    ? mediaUrl(videoAsset.data.public_url)
    : undefined;
  const hasImage = !!scene.data?.image_asset_id;

  async function generate() {
    if (locked.current || posting || active || !hasImage) return;
    locked.current = true;
    setPosting(true);
    setError(null);
    const key = crypto.randomUUID();
    try {
      const accepted = await createSceneVideoGeneration(sceneId, key);
      rememberGenerationJob(scope, accepted.job_id, key);
      setVolatileJob(accepted.job_id);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (cause) {
      setError(requestError(cause));
    } finally {
      locked.current = false;
      setPosting(false);
    }
  }

  async function cancel() {
    if (!jobId || !active || canceling) return;
    setCanceling(true);
    setError(null);
    try {
      const result = await cancelGenerationJob(jobId);
      queryClient.setQueryData(["scene-motion-job", userId, sceneId, jobId], result);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) await job.refetch();
      else setError(requestError(cause));
    } finally {
      setCanceling(false);
    }
  }

  if (!hasImage) return null;

  return (
    <section className="mt-4 rounded-xl border border-sky-100 bg-sky-50/40 p-3" aria-label="장면 Motion">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant={videoSrc ? "outline" : "default"}
          disabled={posting || active || scene.isPending || scene.isError}
          onClick={() => void generate()}
        >
          {posting || active ? <LoaderCircle className="animate-spin" /> : videoSrc ? <RefreshCw /> : <Sparkles />}
          {posting ? "요청하는 중" : videoSrc ? "Motion 다시 생성" : "Motion 만들기"}
        </Button>
        {active && job.data && (
          <Button type="button" size="sm" variant="ghost" disabled={canceling} onClick={() => void cancel()}>
            {canceling ? "취소하는 중" : "Motion 취소"}
          </Button>
        )}
        {job.data && <span className="text-xs font-medium text-sky-800" aria-live="polite">{motionStatus(job.data.status)}</span>}
      </div>
      {videoSrc && (
        <div className="mt-3">
          {videoAsset.data?.metadata.mock_provider === true && (
            <p className="mb-2 text-xs text-zinc-500">개발용 Mock Motion 미리보기</p>
          )}
          <video
            key={videoAssetId}
            src={videoSrc}
            poster={posterUrl}
            controls
            muted
            playsInline
            preload="metadata"
            className="max-h-[36rem] w-full rounded-lg bg-zinc-950 object-contain"
            aria-label="장면 Motion 미리보기"
          >
            브라우저가 동영상 재생을 지원하지 않습니다.
          </video>
        </div>
      )}
      {active && job.data && (
        <ol className="mt-3 grid gap-1 text-[11px] sm:grid-cols-3">
          {["요청 접수", "장면 움직이기", "안전하게 저장"].map((label, index) => {
            const step = job.data?.status === "saving" ? 2 : job.data?.status === "running" || job.data?.status === "provider_pending" ? 1 : 0;
            return <li key={label} className={index <= step ? "rounded-md bg-white p-2 font-semibold text-sky-800" : "rounded-md bg-white/60 p-2 text-zinc-400"}>{index < step ? "✓" : index === step ? "●" : "○"} {label}</li>;
          })}
        </ol>
      )}
      {(error || scene.error || videoAsset.error || job.error) && (
        <p role="alert" className="mt-3 text-xs text-red-700">{error || requestError(scene.error || videoAsset.error || job.error)}</p>
      )}
      {job.data?.status === "failed" && (
        <p role="alert" className="mt-3 text-xs text-red-700">Motion 미리보기를 만들지 못했습니다. 설정이나 서비스 상태를 확인한 뒤 다시 시도해 주세요.</p>
      )}
      {job.data?.status === "canceled" && <p className="mt-3 text-xs text-zinc-500">Motion 생성이 취소되었습니다. 다시 생성할 수 있어요.</p>}
    </section>
  );
}
