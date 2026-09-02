import { afterEach, describe, expect, it, vi } from "vitest";
import { api, request } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("API boundary", () => {
  it("sends commands as JSON and returns the server response", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"id":"work-id"}', { status: 201 }));
    vi.stubGlobal("fetch", fetch);
    expect(await api.create("tasks", { title: "Logical work" })).toEqual({ id: "work-id" });
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/v1/tasks"), {
      method: "POST",
      body: JSON.stringify({ title: "Logical work" }),
      headers: { "Content-Type": "application/json" },
    });
  });

  it("surfaces stable server rejection codes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: "task.not_ready", message: "Readiness is incomplete." },
    }), { status: 409 })));
    await expect(api.start("work-id")).rejects.toThrow("task.not_ready: Readiness is incomplete.");
  });

  it("does not expose a non-JSON error body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("sensitive-error-sentinel", { status: 502 })));
    await expect(request("/api/v1/tasks")).rejects.toThrow("502: Request failed");
  });
});
