import type { Asset } from "@/lib/types";

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
