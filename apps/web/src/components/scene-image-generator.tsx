"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageIcon, LoaderCircle, RefreshCw, Sparkles } from "lucide-react";
import {
  ApiError,
  cancelGenerationJob,
  createSceneImageGeneration,
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
import { SceneMotionGenerator } from "@/components/scene-motion-generator";

type SceneImageGeneratorProps = {
  userId: string;
  projectId: string;
  sceneId: string;
  sceneTitle: string;
  characterIds?: string[];
  characterReferenceMap?: Record<string, { hasReference: boolean; stale: boolean }>;
};

type VolatileJob = { scope: string; jobId: string };

function imageRequestError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return "로그인이 필요합니다. 다시 로그인해 주세요.";
    if (error.status === 403 || error.status === 404)
      return "장면을 찾을 수 없거나 접근할 수 없습니다.";
    if (error.status === 409)
      return "이 장면의 이미지 생성이 이미 진행 중입니다.";
    if (error.status === 429)
      return "오늘 사용할 수 있는 AI 이미지 생성 횟수를 모두 사용했습니다.";
    if (error.status === 422)
      return "이 장면에는 이미지 생성에 필요한 시각 설명이 없습니다.";
    if (error.status === 0 || error.status >= 500)
      return "이미지 서비스 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.";
  }
  return "이미지 생성 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

function imageFailure(code: string | null): string {
  if (code === "provider_error")
    return "AI 이미지 서비스를 현재 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  if (
    code === "storage_error" ||
    code === "database_save_error"
  )
    return "이미지 생성 또는 저장이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.";
  if (code === "provider_not_configured")
    return "AI 이미지 서비스를 현재 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  return "장면 이미지를 완성하지 못했습니다. 다시 생성할 수 있습니다.";
}

function imageStatus(status: string) {
  return {
    queued: "이미지 생성 준비 중",
    running: "AI가 장면을 그리고 있어요",
    provider_pending: "AI 이미지 응답을 기다리고 있어요",
    saving: "이미지를 저장하고 있어요",
    succeeded: "이미지 생성 완료",
    failed: "이미지 생성 실패",
    canceled: "이미지 생성 취소",
  }[status];
}

export function SceneImageGenerator({
  userId,
  projectId,
  sceneId,
  sceneTitle,
  characterIds = [],
  characterReferenceMap = {},
}: SceneImageGeneratorProps) {
  const queryClient = useQueryClient();
  const scope = `linktoon-scene-image-job:${userId}:${sceneId}`;
  const storedJobId = useRememberedGenerationJob(scope);
  const [volatileJob, setVolatileJob] = useState<VolatileJob | null>(null);
  const [posting, setPosting] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const submissionLock = useRef(false);
  const invalidated = useRef(new Set<string>());
  const jobId = volatileJob?.scope === scope ? volatileJob.jobId : storedJobId;

  const scene = useQuery({
    queryKey: ["scene", sceneId],
    queryFn: () => getScene(sceneId),
    retry: false,
  });
  const assetId = scene.data?.image_asset_id ?? null;
  const asset = useQuery({
    queryKey: ["asset", assetId],
    queryFn: () => {
      if (!assetId) throw new Error("Asset ID is missing");
      return getAsset(assetId);
    },
    enabled: !!assetId,
    retry: false,
    refetchInterval: assetId ? 10 * 60 * 1_000 : false,
  });
  const job = useGenerationJob({
    queryKey: ["scene-image-job", userId, sceneId, jobId],
    jobId,
    onPollStart: (polledJobId) =>
      setVolatileJob((current) =>
        current ?? { scope, jobId: polledJobId },
      ),
    validate: (result) =>
      result.project_id === projectId &&
      result.job_type === "image:scene" &&
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
  }, [
    job.data?.status,
    job.error,
    jobId,
    projectId,
    queryClient,
    sceneId,
    scope,
  ]);

  const inaccessible =
    job.error instanceof ApiError && [401, 403, 404].includes(job.error.status);
  const active =
    !!jobId &&
    !inaccessible &&
    (!job.data || !terminalGenerationStatuses.has(job.data.status));
  const imageSrc = asset.data?.public_url
    ? mediaUrl(asset.data.public_url)
    : undefined;

  async function generate() {
    if (submissionLock.current || posting || active) return;
    submissionLock.current = true;
    setPosting(true);
    setRequestError(null);
    const key = crypto.randomUUID();
    try {
      const accepted = await createSceneImageGeneration(sceneId, key);
      rememberGenerationJob(scope, accepted.job_id, key);
      setVolatileJob({ scope, jobId: accepted.job_id });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (error) {
      setRequestError(imageRequestError(error));
    } finally {
      submissionLock.current = false;
      setPosting(false);
    }
  }

  async function cancel() {
    if (!jobId || !active || canceling) return;
    setCanceling(true);
    setRequestError(null);
    try {
      const result = await cancelGenerationJob(jobId);
      queryClient.setQueryData(
        ["scene-image-job", userId, sceneId, jobId],
        result,
      );
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409)
        await job.refetch();
      else setRequestError(imageRequestError(error));
    } finally {
      setCanceling(false);
    }
  }

  return (
    <div className="mt-4 rounded-xl border border-violet-100 bg-violet-50/40 p-3">
      {imageSrc ? (
        <Image
          unoptimized
          src={imageSrc}
          alt={`${sceneTitle} 생성 이미지`}
          width={asset.data?.width || 1024}
          height={asset.data?.height || 1536}
          className="max-h-[36rem] w-full rounded-lg bg-zinc-100 object-contain"
        />
      ) : (
        <div className="flex aspect-[2/3] max-h-72 items-center justify-center rounded-lg bg-zinc-100 text-zinc-400">
          <span className="flex flex-col items-center gap-2 text-xs">
            <ImageIcon className="size-7" /> 이미지 없음
          </span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {characterIds.length > 0 && (
          <span className="w-full text-xs text-zinc-500">
            {characterIds.every((id) => characterReferenceMap[id]?.hasReference && !characterReferenceMap[id]?.stale)
              ? "캐릭터 기준 이미지가 장면 생성에 적용됩니다."
              : characterIds.some((id) => characterReferenceMap[id]?.hasReference)
                ? "일부 캐릭터 기준 이미지만 적용됩니다."
                : "캐릭터 기준 이미지가 없어 설명만 사용합니다."}
          </span>
        )}
        <Button
          type="button"
          size="sm"
          variant={imageSrc ? "outline" : "default"}
          disabled={posting || active || scene.isPending || scene.isError}
          onClick={() => void generate()}
        >
          {posting || active ? (
            <LoaderCircle className="animate-spin" />
          ) : imageSrc ? (
            <RefreshCw />
          ) : (
            <Sparkles />
          )}
          {posting
            ? "요청하는 중"
            : imageSrc
              ? "이미지 다시 생성"
              : "이미지 생성"}
        </Button>
        {active && job.data && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={canceling}
            onClick={() => void cancel()}
          >
            {canceling ? "취소하는 중" : "이미지 생성 취소"}
          </Button>
        )}
        {job.data && (
          <span
            className="text-xs font-medium text-violet-700"
            aria-live="polite"
          >
            {imageStatus(job.data.status)}
          </span>
        )}
      </div>

      {active && job.data && (
        <ol className="mt-3 grid gap-1 text-[11px] sm:grid-cols-3">
          {["요청 접수", "장면 그리기", "안전하게 저장"].map((label, index) => {
            const step =
              job.data?.status === "saving"
                ? 2
                : job.data?.status === "running" ||
                    job.data?.status === "provider_pending"
                  ? 1
                  : 0;
            return (
              <li
                key={label}
                className={
                  index <= step
                    ? "rounded-md bg-white p-2 font-semibold text-violet-700"
                    : "rounded-md bg-white/60 p-2 text-zinc-400"
                }
              >
                {index < step ? "✓" : index === step ? "●" : "○"} {label}
              </li>
            );
          })}
        </ol>
      )}
      {(scene.error || asset.error || job.error) && (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {imageRequestError(scene.error || asset.error || job.error)}
        </p>
      )}
      {requestError && (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {requestError}
        </p>
      )}
      {job.data?.status === "failed" && (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {imageFailure(job.data.error_code)}
        </p>
      )}
      {job.data?.status === "canceled" && (
        <p className="mt-3 text-xs text-zinc-500">
          이미지 생성이 취소되었습니다. 다시 생성할 수 있어요.
        </p>
      )}
      <SceneMotionGenerator
        userId={userId}
        projectId={projectId}
        sceneId={sceneId}
        posterUrl={imageSrc}
      />
    </div>
  );
}
