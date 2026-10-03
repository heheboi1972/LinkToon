import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  ApiError,
  cancelGenerationJob,
  createSceneImageGeneration,
  createStoryGeneration,
  getAsset,
  getGenerationJob,
  getScene,
  listProjectCharacters,
  setTokenGetter,
  uploadImage,
} from "@/lib/api";

const configuredOrigin = (process.env.NEXT_PUBLIC_API_URL || "").replace(
  /\/+$/,
  "",
);
const expectedUrl = (path: string) =>
  configuredOrigin ? `${configuredOrigin}${path}` : path;

afterEach(() => {
  vi.unstubAllGlobals();
  setTokenGetter(async () => null);
});
describe("application API client", () => {
  it("attaches the current session and reads JSON", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ title: "Moonlight" })));
    vi.stubGlobal("fetch", fetch);
    setTokenGetter(async () => "session-token");
    expect(await api("/projects/123")).toEqual({ title: "Moonlight" });
    expect(fetch).toHaveBeenCalledWith(
      expectedUrl("/api/v1/projects/123"),
      expect.objectContaining({
        headers: { Authorization: "Bearer session-token" },
      }),
    );
  });
  it("preserves server status and application error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "unauthorized", message: "Sign in" },
          }),
          { status: 401 },
        ),
      ),
    );
    await expect(api("/projects")).rejects.toMatchObject({
      status: 401,
      message: "Sign in",
      code: "unauthorized",
    });
  });
  it("handles no-content deletes and network errors", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockRejectedValueOnce(new TypeError("offline"));
    vi.stubGlobal("fetch", fetch);
    expect(await api("/projects/1", { method: "DELETE" })).toBeUndefined();
    await expect(api("/projects")).rejects.toBeInstanceOf(ApiError);
  });
  it("validates images before requesting an upload ticket", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
      uploadImage(
        "project",
        new File(["<svg/>"], "unsafe.svg", { type: "image/svg+xml" }),
      ),
    ).rejects.toThrow("PNG");
    expect(fetch).not.toHaveBeenCalled();
  });
  it("uses a ticket, sends bytes through the configured API path, and completes the asset", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            asset_id: "a1",
            upload_url: "http://localhost:8000/api/v1/assets/a1/upload?token=t",
          }),
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "a1", upload_status: "ready" })),
      );
    vi.stubGlobal("fetch", fetch);
    const file = new File(["png-bytes"], "panel.png", { type: "image/png" });
    expect(await uploadImage("p1", file)).toMatchObject({
      id: "a1",
      upload_status: "ready",
    });
    expect(fetch.mock.calls[1][0]).toBe(
      expectedUrl("/api/v1/assets/a1/upload?token=t"),
    );
    expect(fetch.mock.calls[1][1].body).toBe(file);
  });

  it("accepts a Story job with the existing bearer token and idempotency key", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ job_id: "job-1", status: "queued" }), {
        status: 202,
      }),
    );
    vi.stubGlobal("fetch", fetch);
    setTokenGetter(async () => "session-token");

    const request = {
      idea: "달에 가는 고양이",
      genre: "fantasy",
      tone: "warm",
      theme: "friendship",
      characters: ["character-1"],
      scene_count: 3,
    };
    await expect(
      createStoryGeneration("project-1", request, "intent-1"),
    ).resolves.toEqual({ job_id: "job-1", status: "queued" });
    expect(fetch).toHaveBeenCalledWith(
      expectedUrl("/api/v1/projects/project-1/stories/generate"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer session-token",
          "Idempotency-Key": "intent-1",
        },
      }),
    );
  });

  it.each(["network", "503"])(
    "retries a transient %s Story submission once with the identical key and body",
    async (failure) => {
      const fetch = vi.fn();
      if (failure === "network") {
        fetch.mockRejectedValueOnce(new TypeError("offline"));
      } else {
        fetch.mockResolvedValueOnce(new Response(null, { status: 503 }));
      }
      fetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: "job-1", status: "queued" }), {
          status: 202,
        }),
      );
      vi.stubGlobal("fetch", fetch);

      const request = { idea: "숲의 비밀", scene_count: 1 };
      await expect(
        createStoryGeneration("project-1", request, "stable-key"),
      ).resolves.toMatchObject({ job_id: "job-1" });
      expect(fetch).toHaveBeenCalledTimes(2);
      const [, firstOptions] = fetch.mock.calls[0];
      const [, retryOptions] = fetch.mock.calls[1];
      expect(retryOptions.body).toBe(firstOptions.body);
      expect(retryOptions.body).toBe(JSON.stringify(request));
      expect(retryOptions.headers["Idempotency-Key"]).toBe("stable-key");
      expect(retryOptions.headers["Idempotency-Key"]).toBe(
        firstOptions.headers["Idempotency-Key"],
      );
    },
  );

  it("does not retry quota errors or retry a transient error more than once", async () => {
    const quotaFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "quota_exceeded" } }), {
        status: 429,
      }),
    );
    vi.stubGlobal("fetch", quotaFetch);
    await expect(
      createStoryGeneration("project-1", { idea: "A" }, "intent-1"),
    ).rejects.toMatchObject({ status: 429, code: "quota_exceeded" });
    expect(quotaFetch).toHaveBeenCalledTimes(1);

    const outageFetch = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 503 }));
    vi.stubGlobal("fetch", outageFetch);
    await expect(
      createStoryGeneration("project-1", { idea: "A" }, "intent-1"),
    ).rejects.toMatchObject({ status: 503 });
    expect(outageFetch).toHaveBeenCalledTimes(2);
  });

  it("uses the Job and project Character endpoints through the shared API client", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: "job-1", status: "running", output: {} }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "job-1", status: "canceled" })),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ id: "character-1", name: "민지" }])),
      );
    vi.stubGlobal("fetch", fetch);

    await expect(getGenerationJob("job-1")).resolves.toMatchObject({
      status: "running",
    });
    await expect(cancelGenerationJob("job-1")).resolves.toMatchObject({
      status: "canceled",
    });
    await expect(listProjectCharacters("project-1")).resolves.toMatchObject([
      { id: "character-1" },
    ]);
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      expectedUrl("/api/v1/jobs/job-1"),
      expectedUrl("/api/v1/jobs/job-1/cancel"),
      expectedUrl("/api/v1/projects/project-1/characters"),
    ]);
    expect(fetch.mock.calls[1][1].method).toBe("POST");
  });

  it("retries one Scene image intent with the same Idempotency-Key", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("network unavailable"))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: "job-2", status: "queued" }), {
          status: 202,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: "scene-1", image_asset_id: "asset-1" }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "asset-1",
            public_url: "https://api.test/media",
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);

    await expect(
      createSceneImageGeneration("scene-1", "image-intent-1"),
    ).resolves.toEqual({ job_id: "job-2", status: "queued" });
    await getScene("scene-1");
    await getAsset("asset-1");
    expect(fetch.mock.calls.slice(0, 2).map(([, options]) => options)).toEqual([
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": "image-intent-1" },
      }),
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": "image-intent-1" },
      }),
    ]);
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      expectedUrl("/api/v1/scenes/scene-1/image/generate"),
      expectedUrl("/api/v1/scenes/scene-1/image/generate"),
      expectedUrl("/api/v1/scenes/scene-1"),
      expectedUrl("/api/v1/assets/asset-1"),
    ]);
  });
});
