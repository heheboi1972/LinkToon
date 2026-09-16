import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setTokenGetter, uploadImage } from "@/lib/api";

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
});
