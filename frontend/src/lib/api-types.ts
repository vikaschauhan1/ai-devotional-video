/**
 * TypeScript types mirroring the FastAPI Pydantic models.
 * Keep in sync with backend/app/schemas/**.
 */

export type AspectRatio = "9:16" | "16:9" | "1:1";

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

export interface AudioMetadataOut {
  duration: number;
  sample_rate: number;
  channels: number;
  codec: string;
  bitrate: number | null;
  format_name: string;
  size_bytes: number;
}

export interface AudioUploadResponse {
  asset_id: string;
  project_id: string;
  path: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  metadata: AudioMetadataOut;
}

export interface LyricsUploadResponse {
  project_id: string;
  lyrics_length: number;
}

export interface GenerationStep {
  stage: string;
  status: "ok" | "skipped" | "failed";
  detail: string;
}

export interface FinalVideo {
  project_id: string;
  final_asset_id: string;
  path: string;
  url: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  size_bytes: number;
  subtitles_burned: boolean;
  scene_count: number;
}

export interface GenerateResponse extends FinalVideo {
  progress: GenerationStep[];
}

export interface GenerateRequest {
  run_transcription?: boolean;
  target_scene_count?: number;
  style_preset?: string | null;
  burn_subtitles?: boolean;
  fps?: number;
  xfade_seconds?: number;
}

/** Names of the 14 style presets recognised by agent/prompts.py. */
export const STYLE_PRESETS = [
  "shiva-himalayan",
  "shiva-temple",
  "kailash",
  "ganga",
  "jyotirlinga",
  "cosmic-shiva",
  "meditating-shiva",
  "krishna-vrindavan",
  "ram-darbar",
  "hanuman",
  "temple-aarti",
  "indian-classical",
  "traditional-indian-painting",
  "cinematic-devotional",
] as const;

export type StylePreset = (typeof STYLE_PRESETS)[number];

export const ALL_PIPELINE_STAGES = [
  "transcribe",
  "analyze",
  "plan-scenes",
  "generate-images",
  "generate-videos",
  "render",
] as const;

export type PipelineStage = (typeof ALL_PIPELINE_STAGES)[number];
