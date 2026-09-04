import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { api, request } from "./api";
import type { Readiness, TaskDetail } from "./types";

vi.mock("./api", () => ({
  api: { list: vi.fn(), task: vi.fn(), readiness: vi.fn(), start: vi.fn() },
  request: vi.fn(),
}));

const detail: TaskDetail = {
  task: { id: "work-id", project_id: "project-id", title: "Example work", status: "draft", ownership_epoch: 0, current_specification_id: null },
  current_specification: null,
  specification_history: [],
  attempts: [],
};
const gate: Readiness = {
  work_id: "work-id", ready: false, satisfied: 0, total: 1,
  requirements: [{ code: "repository.validated", satisfied: false, remediation: "Validate the repository." }],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.list).mockImplementation(async (resource) => resource === "tasks" ? [detail.task] : []);
  vi.mocked(api.task).mockResolvedValue(detail);
  vi.mocked(api.readiness).mockResolvedValue(gate);
});
afterEach(cleanup);

it("fails closed in the UI when the server readiness gate is incomplete", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Example work/ }));
  const start = await screen.findByRole<HTMLButtonElement>("button", { name: "Start manual attempt" });
  expect(start.disabled).toBe(true);
  fireEvent.click(start);
  expect(api.start).not.toHaveBeenCalled();
  expect(screen.getByText("Validate the repository.")).toBeTruthy();
});

it("shows an authoritative API rejection without claiming an attempt started", async () => {
  vi.mocked(api.readiness).mockResolvedValue({ ...gate, ready: true, satisfied: 1 });
  vi.mocked(api.start).mockRejectedValue(new Error("agent.concurrency_exhausted: No slot available."));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Example work/ }));
  const start = await screen.findByRole<HTMLButtonElement>("button", { name: "Start manual attempt" });
  await waitFor(() => expect(start.disabled).toBe(false));
  fireEvent.click(start);
  await screen.findByText(/agent.concurrency_exhausted/);
  expect(api.start).toHaveBeenCalledWith("work-id");
  expect(screen.queryByText("Attempt started manually.")).toBeNull();
});

it("sends only editable specification fields when creating a new version", async () => {
  const current = {
    id: "specification-id",
    task_id: "work-id",
    version: 1,
    repository_id: "repository-id",
    goal: "Original goal",
    base_revision: "abc123",
    acceptance_criteria: ["It works"],
    verification_commands: ["pytest"],
    constraints: ["Stay bounded"],
    actor_configuration_id: "actor-id",
    reviewer_configuration_id: "reviewer-id",
    limits: { timeout_seconds: 60, max_tokens: 100, max_cost_usd: 1 },
    required_secret_refs: [],
    sandbox_policy: {
      network: "none" as const,
      writable_paths: ["/workspace"],
      allow_external_mutation: false as const,
    },
    dependency_ids: [],
    authored_by: "first-author",
    authored_at: "2026-09-04T00:00:00Z",
    content_hash: "original-content-hash",
  };
  const versionedDetail: TaskDetail = {
    ...detail,
    task: { ...detail.task, current_specification_id: current.id },
    current_specification: current,
    specification_history: [current],
  };
  vi.mocked(api.task).mockResolvedValue(versionedDetail);
  vi.mocked(request).mockResolvedValue({ ...current, version: 2 });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Example work/ }));
  await screen.findByText("Create next specification version");
  fireEvent.change(screen.getAllByLabelText("Goal")[0], {
    target: { value: "Updated goal" },
  });

  fireEvent.click(screen.getByRole("button", { name: "Save immutable version" }));

  await waitFor(() => expect(request).toHaveBeenCalled());
  const [, init] = vi.mocked(request).mock.calls[0];
  const payload = JSON.parse(String(init?.body)) as Record<string, unknown>;
  expect(payload.goal).toBe("Updated goal");
  expect(payload).not.toHaveProperty("id");
  expect(payload).not.toHaveProperty("task_id");
  expect(payload).not.toHaveProperty("version");
  expect(payload).not.toHaveProperty("authored_at");
  expect(payload).not.toHaveProperty("content_hash");
});
