import type {
  AsyncGenerateResponse,
  AudioUploadResponse,
  FinalVideo,
  GenerateRequest,
  GenerateResponse,
  HealthResponse,
  Job,
  LyricsUploadResponse,
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
      Accept: "application/json",
      ...(init.body instanceof FormData
        ? {} // let the browser set multipart boundary
        : { "Content-Type": "application/json" }),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new ApiError(res.status, `API ${res.status} ${res.statusText}: ${detail || path}`, detail);
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly rawDetail: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Prepend the API base so an "/storage/..." path becomes a full URL. */
export function absolutize(url: string): string {
  if (!url) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${API_BASE}${url}`;
}

export const api = {
  base: API_BASE,
  health: (signal?: AbortSignal) =>
    request<HealthResponse>("/api/health", {}, signal),
  listProjects: (signal?: AbortSignal) =>
    request<Project[]>("/api/projects", {}, signal),
  getProject: (id: string, signal?: AbortSignal) =>
    request<Project>(`/api/projects/${id}`, {}, signal),
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
  uploadAudio: (id: string, file: File, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file);
    return request<AudioUploadResponse>(
      `/api/projects/${id}/audio`,
      { method: "POST", body: form },
      signal,
    );
  },
  uploadLyrics: (id: string, text: string, signal?: AbortSignal) =>
    request<LyricsUploadResponse>(
      `/api/projects/${id}/lyrics`,
      { method: "POST", body: JSON.stringify({ text }) },
      signal,
    ),
  generate: (id: string, payload: GenerateRequest, signal?: AbortSignal) =>
    request<GenerateResponse>(
      `/api/projects/${id}/generate`,
      { method: "POST", body: JSON.stringify(payload) },
      signal,
    ),
  generateAsync: (
    id: string,
    payload: GenerateRequest,
    signal?: AbortSignal,
  ) =>
    request<AsyncGenerateResponse>(
      `/api/projects/${id}/generate-async`,
      { method: "POST", body: JSON.stringify(payload) },
      signal,
    ),
  getJob: (jobId: string, signal?: AbortSignal) =>
    request<Job>(`/api/jobs/${jobId}`, {}, signal),
  cancelJob: (jobId: string, signal?: AbortSignal) =>
    request<{ message: string }>(
      `/api/jobs/${jobId}/cancel`,
      { method: "POST" },
      signal,
    ),
  getRender: (id: string, signal?: AbortSignal) =>
    request<FinalVideo>(`/api/projects/${id}/render`, {}, signal),
};
