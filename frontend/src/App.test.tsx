import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { api } from "./api";
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
