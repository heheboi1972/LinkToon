"use client";

import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, getGenerationJob } from "@/lib/api";
import type { GenerationJob, GenerationJobStatus } from "@/lib/types";

export const GENERATION_POLL_INTERVAL_MS = 2_000;
export const terminalGenerationStatuses: ReadonlySet<GenerationJobStatus> =
  new Set(["succeeded", "failed", "canceled"]);

const STORAGE_EVENT = "linktoon-generation-job-change";

function subscribeRememberedJobs(listener: () => void) {
  window.addEventListener(STORAGE_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(STORAGE_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}

function readRememberedJob(scope: string): string | null {
  try {
    const raw = sessionStorage.getItem(scope);
    if (!raw) return null;
    const saved: unknown = JSON.parse(raw);
    if (
      saved &&
      typeof saved === "object" &&
      "jobId" in saved &&
      typeof saved.jobId === "string" &&
      /^[0-9a-f-]{36}$/i.test(saved.jobId)
    )
      return saved.jobId;
  } catch {
    // Storage can be disabled; mounted component state still tracks the Job.
  }
  return null;
}

export function useRememberedGenerationJob(scope: string) {
  return useSyncExternalStore(
    subscribeRememberedJobs,
    () => readRememberedJob(scope),
    () => null,
  );
}

export function rememberGenerationJob(
  scope: string,
  jobId: string,
  idempotencyKey: string,
) {
  try {
    sessionStorage.setItem(
      scope,
      JSON.stringify({ jobId, key: idempotencyKey }),
    );
    window.dispatchEvent(new Event(STORAGE_EVENT));
  } catch {
    // The active component state continues polling when storage is unavailable.
  }
}

export function forgetGenerationJob(scope: string) {
  try {
    sessionStorage.removeItem(scope);
  } catch {
    // Nothing else is required when storage is unavailable.
  }
}

type UseGenerationJobOptions = {
  queryKey: readonly unknown[];
  jobId: string | null;
  validate: (job: GenerationJob) => boolean;
  onPollStart?: (jobId: string) => void;
};

export function useGenerationJob({
  queryKey,
  jobId,
  validate,
  onPollStart,
}: UseGenerationJobOptions) {
  return useQuery({
    queryKey,
    queryFn: async () => {
      if (!jobId) throw new Error("Job ID is missing");
      onPollStart?.(jobId);
      const result = await getGenerationJob(jobId);
      if (!validate(result))
        throw new ApiError(
          "Job does not belong to this resource",
          404,
          "not_found",
        );
      return result;
    },
    enabled: !!jobId,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && terminalGenerationStatuses.has(status)) return false;
      const error = query.state.error;
      if (error instanceof ApiError && [401, 403, 404].includes(error.status))
        return false;
      return GENERATION_POLL_INTERVAL_MS;
    },
  });
}
