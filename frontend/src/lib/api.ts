import type {
  HealthResponse,
  Project,
  ProjectCreate,
} from "./api-types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    signal,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      `API ${res.status} ${res.statusText}: ${detail || path}`,
    );
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  return (await res.json()) as T;
}

export const api = {
  base: API_BASE,
  health: (signal?: AbortSignal) =>
    request<HealthResponse>("/api/health", {}, signal),
  listProjects: (signal?: AbortSignal) =>
    request<Project[]>("/api/projects", {}, signal),
  createProject: (payload: ProjectCreate, signal?: AbortSignal) =>
    request<Project>(
      "/api/projects",
      { method: "POST", body: JSON.stringify(payload) },
      signal,
    ),
  deleteProject: (id: string, signal?: AbortSignal) =>
    request<void>(
      `/api/projects/${id}`,
      { method: "DELETE" },
      signal,
    ),
};
