"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, LoaderCircle, Sparkles } from "lucide-react";
import {
  ApiError,
  cancelGenerationJob,
  createStoryGeneration,
  listProjectCharacters,
} from "@/lib/api";
import { useAuth } from "@/components/providers";
import type {
  StoryGenerationOutput,
  StoryGenerationRequest,
} from "@/lib/types";
import { genres } from "@/lib/utils";
import { jobStatusLabel } from "@/lib/job-status";
import {
  forgetGenerationJob,
  rememberGenerationJob,
  terminalGenerationStatuses,
  useGenerationJob,
  useRememberedGenerationJob,
} from "@/lib/generation-job";
import { SceneImageGenerator } from "@/components/scene-image-generator";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";

type RememberedJob = {
  scope: string;
  jobId: string;
};
type UnconfirmedRequest = {
  input: StoryGenerationRequest;
  key: string;
};
type StoryForm = Required<Omit<StoryGenerationRequest, "genre">> & {
  genre: string;
};

function safeRequestError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return "로그인이 필요합니다. 다시 로그인해 주세요.";
    if (error.status === 403 || error.status === 404)
      return "프로젝트를 찾을 수 없거나 접근할 수 없습니다.";
    if (error.status === 429)
      return "오늘 사용할 수 있는 AI Story 생성 횟수를 모두 사용했습니다.";
    if (error.status === 422) return "입력 내용을 확인해 주세요.";
    if (error.status === 0 || error.status >= 500)
      return "서버 응답이 지연되고 있습니다. 잠시 후 다시 확인해 주세요.";
  }
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

function safeJobFailure(code: string | null): string {
  if (code === "provider_error")
    return "AI Story 서비스를 현재 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  if (code === "provider_not_configured")
    return "AI Story 서비스를 현재 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  return "이야기를 완성하지 못했습니다. 다시 생성할 수 있습니다.";
}

function isStoryOutput(value: unknown): value is StoryGenerationOutput {
  if (!value || typeof value !== "object") return false;
  const result = value as Record<string, unknown>;
  return (
    typeof result.title === "string" &&
    typeof result.synopsis === "string" &&
    typeof result.episode_id === "string" &&
    Array.isArray(result.scene_ids) &&
    result.scene_ids.every((id) => typeof id === "string") &&
    Array.isArray(result.scenes) &&
    result.scenes.every(
      (scene) =>
        !!scene &&
        typeof scene === "object" &&
        typeof scene.order === "number" &&
        typeof scene.title === "string" &&
        typeof scene.narration === "string" &&
        Array.isArray(scene.dialogue),
    )
  );
}

type StoryStudioProps = {
  projectId: string;
  projectGenre: string;
  initialIdea: string;
};

export function StoryStudio(props: StoryStudioProps) {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <StoryStudioContent
      key={`${user.id}:${props.projectId}`}
      userId={user.id}
      {...props}
    />
  );
}

function StoryStudioContent({
  userId,
  projectId,
  projectGenre,
  initialIdea,
}: StoryStudioProps & { userId: string }) {
  const queryClient = useQueryClient();
  const scope = `linktoon-story-job:${userId}:${projectId}`;
  const storedJobId = useRememberedGenerationJob(scope);
  const [volatileJob, setVolatileJob] = useState<RememberedJob | null>(null);
  const [form, setForm] = useState<StoryForm>({
    idea: initialIdea,
    genre: projectGenre,
    tone: "cinematic",
    theme: "",
    characters: [],
    scene_count: 6,
  });
  const [posting, setPosting] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [unconfirmed, setUnconfirmed] = useState<UnconfirmedRequest | null>(
    null,
  );
  const submissionLock = useRef(false);
  const ideaTouched = useRef(false);
  const invalidated = useRef(new Set<string>());
  const jobId = volatileJob?.scope === scope ? volatileJob.jobId : storedJobId;

  useEffect(() => {
    if (initialIdea && !ideaTouched.current)
      setForm((current) => ({ ...current, idea: initialIdea }));
  }, [initialIdea]);

  const characters = useQuery({
    queryKey: ["characters", projectId],
    queryFn: () => listProjectCharacters(projectId),
  });
  const job = useGenerationJob({
    queryKey: ["story-job", userId, projectId, jobId],
    jobId,
    onPollStart: (polledJobId) =>
      setVolatileJob((current) =>
        current ?? { scope, jobId: polledJobId },
      ),
    validate: (result) =>
      result.project_id === projectId && result.job_type === "story:generate",
  });

  useEffect(() => {
    if (!scope || !jobId) return;
    if (job.data?.status === "failed" || job.data?.status === "canceled")
      forgetGenerationJob(scope);
    if (
      job.error instanceof ApiError &&
      [401, 403, 404].includes(job.error.status)
    ) {
      forgetGenerationJob(scope);
    }
    if (job.data?.status === "succeeded" && !invalidated.current.has(jobId)) {
      invalidated.current.add(jobId);
      void queryClient.invalidateQueries({ queryKey: ["episodes", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    }
  }, [job.data?.status, job.error, jobId, projectId, queryClient, scope]);

  const jobUnavailable =
    job.error instanceof ApiError && [401, 403, 404].includes(job.error.status);
  const active =
    !!jobId &&
    !jobUnavailable &&
    (!job.data || !terminalGenerationStatuses.has(job.data.status));
  const genreOptions = Object.entries(genres);
  const hasCustomGenre = !Object.hasOwn(genres, projectGenre);

  function rememberJob(nextJobId: string, key: string) {
    if (!scope) return;
    rememberGenerationJob(scope, nextJobId, key);
    setVolatileJob({ scope, jobId: nextJobId });
  }

  async function submit(input: StoryGenerationRequest, key: string) {
    if (submissionLock.current || active || !scope) return;
    submissionLock.current = true;
    setPosting(true);
    setRequestError(null);
    try {
      const accepted = await createStoryGeneration(projectId, input, key);
      setUnconfirmed(null);
      rememberJob(accepted.job_id, key);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (error) {
      const uncertain =
        error instanceof ApiError &&
        (error.status === 0 || [502, 503, 504].includes(error.status));
      setUnconfirmed(uncertain ? { input, key } : null);
      setRequestError(safeRequestError(error));
    } finally {
      submissionLock.current = false;
      setPosting(false);
    }
  }

  function generate(event?: React.FormEvent) {
    event?.preventDefault();
    if (unconfirmed || posting || active) return;
    const idea = form.idea.trim();
    const genre = form.genre.trim() || projectGenre;
    const tone = form.tone.trim();
    if (
      !idea ||
      !tone ||
      !Number.isInteger(form.scene_count) ||
      form.scene_count < 1 ||
      form.scene_count > 20
    ) {
      setRequestError(
        "아이디어, 분위기와 1~20 사이의 장면 수를 확인해 주세요.",
      );
      return;
    }
    const input = { ...form, idea, genre, tone, theme: form.theme.trim() };
    void submit(input, crypto.randomUUID());
  }

  async function cancel() {
    if (!jobId || canceling || !active) return;
    setCanceling(true);
    setCancelError(null);
    try {
      const result = await cancelGenerationJob(jobId);
      queryClient.setQueryData(["story-job", userId, projectId, jobId], result);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await job.refetch();
      } else {
        setCancelError(safeRequestError(error));
      }
    } finally {
      setCanceling(false);
    }
  }

  const output =
    job.data?.status === "succeeded" && isStoryOutput(job.data.output)
      ? job.data.output
      : null;

  return (
    <section className="mt-8 space-y-6" aria-labelledby="story-studio-title">
      <div className="rounded-2xl border border-violet-100 bg-white p-6 sm:p-8">
        <div className="mb-6 flex items-start gap-3">
          <span className="rounded-xl bg-violet-50 p-2 text-violet-600">
            <Sparkles className="size-5" />
          </span>
          <div>
            <h2 id="story-studio-title" className="text-lg font-bold">
              AI와 이야기 만들기
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              아이디어를 장면별 이야기로 만들어요. 다시 생성하면 기존 에피소드는
              그대로 보존됩니다.
            </p>
          </div>
        </div>
        <form onSubmit={generate} className="space-y-5">
          <label className="field-label">
            이야기 아이디어
            <Textarea
              value={form.idea}
              onChange={(event) => {
                ideaTouched.current = true;
                setForm((current) => ({
                  ...current,
                  idea: event.target.value,
                }));
              }}
              placeholder="주인공과 사건, 시작 장면을 적어 주세요."
              maxLength={10_000}
              required
              disabled={posting || active || !!unconfirmed}
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="field-label">
              장르
              <select
                value={form.genre}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    genre: event.target.value,
                  }))
                }
                disabled={posting || active || !!unconfirmed}
              >
                {hasCustomGenre && (
                  <option value={projectGenre}>{projectGenre}</option>
                )}
                {genreOptions.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label">
              분위기/톤
              <select
                value={form.tone}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    tone: event.target.value,
                  }))
                }
                disabled={posting || active || !!unconfirmed}
              >
                <option value="cinematic">시네마틱</option>
                <option value="hopeful">희망적</option>
                <option value="warm">따뜻한</option>
                <option value="suspenseful">긴장감 있는</option>
                <option value="comedic">유쾌한</option>
              </select>
            </label>
            <label className="field-label">
              테마
              <Input
                value={form.theme}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    theme: event.target.value,
                  }))
                }
                placeholder="예: 우정, 용기"
                maxLength={500}
                disabled={posting || active || !!unconfirmed}
              />
            </label>
            <label className="field-label">
              장면 수
              <Input
                type="number"
                value={form.scene_count}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    scene_count: Number(event.target.value),
                  }))
                }
                min={1}
                max={20}
                step={1}
                required
                disabled={posting || active || !!unconfirmed}
              />
            </label>
          </div>
          <fieldset disabled={posting || active || !!unconfirmed}>
            <legend className="text-sm font-semibold">등장 캐릭터</legend>
            {characters.isPending ? (
              <p className="mt-2 text-xs text-zinc-500">
                캐릭터를 불러오는 중이에요.
              </p>
            ) : characters.error ? (
              <p role="alert" className="mt-2 text-xs text-red-600">
                캐릭터를 불러오지 못했습니다. 다시 조회해 주세요.
              </p>
            ) : characters.data?.length ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {characters.data.map((character) => (
                  <label
                    key={character.id}
                    className="flex cursor-pointer gap-3 rounded-xl border border-zinc-200 p-3 text-sm"
                  >
                    <input
                      type="checkbox"
                      className="mt-1 accent-violet-600"
                      checked={form.characters.includes(character.id)}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          characters: event.target.checked
                            ? current.characters.length < 20
                              ? [...current.characters, character.id]
                              : current.characters
                            : current.characters.filter(
                                (id) => id !== character.id,
                              ),
                        }))
                      }
                    />
                    <span>
                      <span className="block font-medium">
                        {character.name}
                      </span>
                      <span className="mt-1 block text-xs text-zinc-500">
                        {character.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-xs text-zinc-500">
                등록된 캐릭터가 없어도 이야기를 만들 수 있어요.
              </p>
            )}
            {characters.error && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void characters.refetch()}
              >
                캐릭터 다시 조회
              </Button>
            )}
          </fieldset>
          {requestError && (
            <p
              role="alert"
              className="rounded-xl bg-red-50 p-3 text-sm text-red-700"
            >
              {requestError}
            </p>
          )}
          {unconfirmed && (
            <p className="text-xs text-zinc-500">
              요청이 접수됐는지 확인되지 않았어요. 중복 생성을 피하려면 같은
              요청을 먼저 다시 확인해 주세요.
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <Button
              type="submit"
              disabled={posting || active || !!unconfirmed || !form.idea.trim()}
            >
              {posting ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <Sparkles />
              )}
              {posting
                ? "요청하는 중"
                : job.data
                  ? "다시 생성"
                  : "AI Story 생성"}
            </Button>
            {unconfirmed && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  disabled={posting}
                  onClick={() =>
                    void submit(unconfirmed.input, unconfirmed.key)
                  }
                >
                  같은 요청 다시 확인
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={posting}
                  onClick={() => {
                    setUnconfirmed(null);
                    setRequestError(null);
                  }}
                >
                  새 요청 시작
                </Button>
              </>
            )}
          </div>
        </form>
      </div>

      {jobId && (
        <div
          className="rounded-2xl border border-zinc-200 bg-white p-6"
          aria-live="polite"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-bold">생성 작업</h3>
              <p className="mt-1 text-sm text-zinc-500">
                {job.data
                  ? jobStatusLabel(job.data.status)
                  : "생성 상태를 확인하는 중이에요"}
              </p>
            </div>
            {active && job.data && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={canceling}
                onClick={() => void cancel()}
              >
                {canceling ? "취소하는 중" : "생성 취소"}
              </Button>
            )}
          </div>
          {active && (
            <ol className="mt-5 grid gap-2 text-xs sm:grid-cols-3">
              {["요청 접수", "이야기 생성", "저장"].map((label, index) => {
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
                        ? "rounded-lg bg-violet-50 p-3 font-semibold text-violet-700"
                        : "rounded-lg bg-zinc-50 p-3 text-zinc-400"
                    }
                  >
                    {index < step ? "✓" : index === step ? "●" : "○"} {label}
                  </li>
                );
              })}
            </ol>
          )}
          {job.error && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {safeRequestError(job.error)}
            </p>
          )}
          {cancelError && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {cancelError}
            </p>
          )}
          {job.data?.status === "failed" && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {safeJobFailure(job.data.error_code)}
            </p>
          )}
          {job.data?.status === "canceled" && (
            <p className="mt-4 text-sm text-zinc-500">
              새 요청으로 다시 시작할 수 있어요.
            </p>
          )}
        </div>
      )}

      {job.data?.status === "succeeded" &&
        (output ? (
          <div className="rounded-2xl border border-zinc-200 bg-white p-6 sm:p-8">
            <p className="text-xs font-bold tracking-wider text-violet-600">
              새 초안 에피소드
            </p>
            <h3 className="mt-2 text-2xl font-bold">{output.title}</h3>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-zinc-600">
              {output.synopsis}
            </p>
            <div className="mt-7 space-y-4">
              {[...output.scenes]
                .sort((a, b) => a.order - b.order)
                .map((scene) => {
                  const sceneId = output.scene_ids[scene.order - 1];
                  return (
                    <article
                      key={scene.order}
                      className="rounded-xl border border-zinc-200 p-5"
                    >
                      <p className="text-xs font-semibold text-violet-600">
                        장면 {scene.order}
                      </p>
                      <h4 className="mt-1 font-semibold">{scene.title}</h4>
                      {sceneId && (
                        <SceneImageGenerator
                          userId={userId}
                          projectId={projectId}
                          sceneId={sceneId}
                          sceneTitle={scene.title}
                          characterIds={scene.character_ids}
                          characterReferenceMap={Object.fromEntries(
                            (characters.data || []).map((character) => [
                              character.id,
                              {
                                hasReference: !!character.reference_asset_id,
                                stale: !!character.reference_stale,
                              },
                            ]),
                          )}
                        />
                      )}
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-zinc-600">
                        {scene.narration}
                      </p>
                      {scene.dialogue.length > 0 && (
                        <div className="mt-4 space-y-2 border-l-2 border-violet-200 pl-4">
                          {scene.dialogue.map((line, index) => (
                            <p
                              key={`${scene.order}-${index}`}
                              className="text-sm text-zinc-700"
                            >
                              <strong>{line.character}</strong> · {line.text}
                            </p>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
            </div>
            <Button asChild variant="outline" className="mt-6">
              <Link
                href={`/projects/${projectId}/episodes/${output.episode_id}`}
              >
                새 에피소드 보기 <ArrowRight />
              </Link>
            </Button>
            <p className="mt-3 text-xs text-zinc-400">
              기존 초안은 유지됩니다. 위 장면별 이야기를 확인한 뒤 에피소드에서
              패널을 구성할 수 있어요.
            </p>
          </div>
        ) : (
          <p
            role="alert"
            className="rounded-xl bg-red-50 p-4 text-sm text-red-700"
          >
            저장된 결과를 표시할 수 없습니다. 생성 작업 내역을 확인해 주세요.
          </p>
        ))}
    </section>
  );
}
