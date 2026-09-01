const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type ErrorEnvelope = { error?: { code?: string; message?: string; details?: unknown[] } };

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorEnvelope;
    throw new Error(`${body.error?.code ?? response.status}: ${body.error?.message ?? "Request failed"}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  list: <T>(resource: string) => request<T[]>(`/api/v1/${resource}`),
  create: <T>(resource: string, body: unknown) =>
    request<T>(`/api/v1/${resource}`, { method: "POST", body: JSON.stringify(body) }),
  task: <T>(id: string) => request<T>(`/api/v1/tasks/${id}`),
  readiness: <T>(id: string) => request<T>(`/api/v1/tasks/${id}/readiness`),
  start: <T>(id: string) => request<T>(`/api/v1/tasks/${id}/attempts`, { method: "POST" }),
};
