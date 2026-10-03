import type {
  Asset,
  CharacterSummary,
  CharacterCreateInput,
  CharacterPatchInput,
  EpisodeReader,
  GenerationJob,
  ImageGenerationResponse,
  ProjectOverview,
  Publication,
  PublicationReader,
  SceneRecord,
  StoryGenerationRequest,
  StoryGenerationResponse,
} from "@/lib/types";

const apiOrigin = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "");

function apiRequestUrl(path: string) {
  const apiPath = `/api/v1${path}`;
  return apiOrigin ? `${apiOrigin}${apiPath}` : apiPath;
}

function capabilityUrl(value: string) {
  const parsed = new URL(value);
  const path = `${parsed.pathname}${parsed.search}`;
  return apiOrigin ? `${apiOrigin}${path}` : path;
}

let tokenGetter: () => Promise<string | null> = async () => null;
export function setTokenGetter(getter: () => Promise<string | null>) {
  tokenGetter = getter;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = await tokenGetter();
  let response: Response;
  try {
    response = await fetch(apiRequestUrl(path), {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      "서버에 연결할 수 없습니다. API가 실행 중인지 확인해 주세요.",
      0,
      "network_error",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message =
      body.error?.message ||
      (Array.isArray(body.detail)
        ? body.detail.map((d: { msg: string }) => d.msg).join(", ")
        : body.detail) ||
      "요청을 처리하지 못했습니다.";
    throw new ApiError(
      message,
      response.status,
      body.error?.code || "request_error",
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const post = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });
export const patch = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
export const remove = (path: string) => api<void>(path, { method: "DELETE" });

export async function createStoryGeneration(
  projectId: string,
  body: StoryGenerationRequest,
  idempotencyKey: string,
): Promise<StoryGenerationResponse> {
  // Serialize once so an ambiguous network failure cannot change the retried request.
  return createIdempotentGeneration<StoryGenerationResponse>(
    `/projects/${encodeURIComponent(projectId)}/stories/generate`,
    idempotencyKey,
    JSON.stringify(body),
  );
}

async function createIdempotentGeneration<T>(
  path: string,
  idempotencyKey: string,
  serializedBody?: string,
): Promise<T> {
  const options: RequestInit = {
    method: "POST",
    ...(serializedBody === undefined ? {} : { body: serializedBody }),
    headers: { "Idempotency-Key": idempotencyKey },
  };
  try {
    return await api<T>(path, options);
  } catch (error) {
    if (
      !(error instanceof ApiError) ||
      ![0, 502, 503, 504].includes(error.status)
    ) {
      throw error;
    }
    return api<T>(path, options);
  }
}

export function createSceneImageGeneration(
  sceneId: string,
  idempotencyKey: string,
) {
  return createIdempotentGeneration<ImageGenerationResponse>(
    `/scenes/${encodeURIComponent(sceneId)}/image/generate`,
    idempotencyKey,
  );
}

export function createSceneVideoGeneration(
  sceneId: string,
  idempotencyKey: string,
) {
  return createIdempotentGeneration<StoryGenerationResponse>(
    `/scenes/${encodeURIComponent(sceneId)}/video/generate`,
    idempotencyKey,
  );
}

export const getScene = (sceneId: string) =>
  api<SceneRecord>(`/scenes/${encodeURIComponent(sceneId)}`);

export const getEpisodeReader = (episodeId: string) =>
  api<EpisodeReader>(`/episodes/${encodeURIComponent(episodeId)}/reader`);

export const getProjectOverview = (projectId: string) =>
  api<ProjectOverview>(`/projects/${encodeURIComponent(projectId)}/overview`);

export const getEpisodePublication = (episodeId: string) =>
  api<Publication>(`/episodes/${encodeURIComponent(episodeId)}/publication`);

export const createPublication = (
  episodeId: string,
  data: {
    title: string;
    description: string;
    visibility: Publication["visibility"];
  },
) =>
  post<Publication>(`/episodes/${encodeURIComponent(episodeId)}/publish`, data);

export const updatePublication = (
  publicationId: string,
  data: Partial<Pick<Publication, "title" | "description" | "visibility">>,
) =>
  patch<Publication>(
    `/publications/${encodeURIComponent(publicationId)}`,
    data,
  );

export const republish = (publicationId: string) =>
  post<Publication>(
    `/publications/${encodeURIComponent(publicationId)}/republish`,
    {},
  );

export const unpublish = (publicationId: string) =>
  post<Publication>(
    `/publications/${encodeURIComponent(publicationId)}/unpublish`,
    {},
  );

export const getPublicPublication = (slug: string) =>
  api<PublicationReader>(`/publications/${encodeURIComponent(slug)}`);

export const getAsset = (assetId: string) =>
  api<Asset>(`/assets/${encodeURIComponent(assetId)}`);

export const getGenerationJob = (jobId: string) =>
  api<GenerationJob>(`/jobs/${encodeURIComponent(jobId)}`);

export const cancelGenerationJob = (jobId: string) =>
  api<GenerationJob>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });

export const listProjectCharacters = (projectId: string) =>
  api<CharacterSummary[]>(
    `/projects/${encodeURIComponent(projectId)}/characters`,
  );

export const getCharacter = (characterId: string) =>
  api<CharacterSummary>(`/characters/${encodeURIComponent(characterId)}`);

export const createCharacter = (
  projectId: string,
  data: CharacterCreateInput,
) =>
  post<CharacterSummary>(
    `/projects/${encodeURIComponent(projectId)}/characters`,
    data,
  );

export const updateCharacter = (
  characterId: string,
  data: CharacterPatchInput,
) =>
  patch<CharacterSummary>(
    `/characters/${encodeURIComponent(characterId)}`,
    data,
  );

export const deleteCharacter = (characterId: string) =>
  remove(`/characters/${encodeURIComponent(characterId)}`);

export const selectCharacterReference = (
  characterId: string,
  assetId: string,
) =>
  api<CharacterSummary>(
    `/characters/${encodeURIComponent(characterId)}/reference`,
    {
      method: "PUT",
      body: JSON.stringify({ asset_id: assetId }),
    },
  );

export const clearCharacterReference = (characterId: string) =>
  api<CharacterSummary>(
    `/characters/${encodeURIComponent(characterId)}/reference`,
    {
      method: "DELETE",
    },
  );

export function createCharacterReferenceGeneration(
  characterId: string,
  idempotencyKey: string,
) {
  return createIdempotentGeneration<StoryGenerationResponse>(
    `/characters/${encodeURIComponent(characterId)}/reference/generate`,
    idempotencyKey,
  );
}

export async function uploadImage(
  projectId: string,
  file: File,
  assetType = "image",
): Promise<Asset> {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
    throw new Error("PNG, JPG, WebP 이미지를 선택해 주세요.");
  if (file.size > 10 * 1024 * 1024)
    throw new Error("10 MB 이하 이미지를 선택해 주세요.");
  const ticket = await post<{ asset_id: string; upload_url: string }>(
    "/assets/upload-url",
    {
      project_id: projectId,
      filename: file.name,
      mime_type: file.type,
      file_size: file.size,
      asset_type: assetType,
    },
  );
  try {
    const response = await fetch(capabilityUrl(ticket.upload_url), {
      method: "PUT",
      body: file,
      headers: { "Content-Type": file.type },
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.error?.message || "이미지 업로드에 실패했습니다.");
    }
    return await post<Asset>("/assets/complete", { asset_id: ticket.asset_id });
  } catch (error) {
    await remove(`/assets/${ticket.asset_id}`).catch(() => undefined);
    throw error;
  }
}

export function mediaUrl(url: string | null) {
  if (!url) return undefined;
  return capabilityUrl(url);
}
