/**
 * API types mirroring the FastAPI Pydantic models.
 * Keep in sync with backend/app/schemas/**.
 */

export type AspectRatio = "9:16" | "16:9" | "1:1";

export type JobStatus =
  | "QUEUED"
  | "ANALYZING"
  | "PLANNING"
  | "GENERATING_IMAGES"
  | "GENERATING_VIDEO"
  | "LIP_SYNC"
  | "COMPOSITING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface HealthResponse {
  status: string;
  version: string;
  engines: Record<string, string>;
}

export interface Project {
  id: string;
  name: string;
  deity: string | null;
  style: string | null;
  language: string;
  aspect_ratio: AspectRatio;
  resolution: string;
  lip_sync_enabled: boolean;
  lyrics: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  deity?: string | null;
  style?: string | null;
  language?: string;
  aspect_ratio?: AspectRatio;
  resolution?: string;
  lip_sync_enabled?: boolean;
  lyrics?: string | null;
}

export interface Job {
  id: string;
  project_id: string;
  kind: string;
  status: JobStatus;
  progress: number;
  message: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}
