"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, absolutize, api } from "@/lib/api";
import {
  ALL_PIPELINE_STAGES,
  STYLE_PRESETS,
  type AspectRatio,
  type FinalVideo,
  type GenerationStep,
  type HealthResponse,
  type Job,
  type PipelineStage,
  type Project,
} from "@/lib/api-types";

const ASPECT_RATIOS: AspectRatio[] = ["9:16", "16:9", "1:1"];

const STAGE_LABEL: Record<PipelineStage, string> = {
  transcribe: "Transcribe audio",
  analyze: "Analyse lyrics",
  "plan-scenes": "Plan scenes",
  "generate-images": "Generate images",
  "generate-videos": "Generate video clips",
  render: "Render final video",
};

interface ActiveGeneration {
  status: "idle" | "running" | "done" | "failed";
  progress: GenerationStep[];
  jobStatus: string | null;
  message: string | null;
  error: string | null;
  result: FinalVideo | null;
}

const IDLE_GEN: ActiveGeneration = {
  status: "idle",
  progress: [],
  jobStatus: null,
  message: null,
  error: null,
  result: null,
};

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);

  // ── Project form (new + selected project settings) ────
  const [name, setName] = useState("Shiva bhajan");
  const [deity, setDeity] = useState("Shiva");
  const [style, setStyle] = useState<string>("shiva-himalayan");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("9:16");
  const [lyrics, setLyrics] = useState(
    "जय शिव शंभो, जय महेश्वर\nआदि अनंत, तू ही ईश्वर\nतेरी कृपा से राह मिले\nहो जाए भव से पार",
  );
  const [creating, setCreating] = useState(false);
  const [savingLyrics, setSavingLyrics] = useState(false);

  // ── Audio upload state ────────────────────────────────
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioMeta, setAudioMeta] = useState<{
    duration: number;
    codec: string;
    filename: string;
  } | null>(null);
  const [uploading, setUploading] = useState(false);

  // ── Generation state ──────────────────────────────────
  const [runTranscription, setRunTranscription] = useState(false);
  const pollingRef = useRef<{ abort: () => void } | null>(null);
  const [burnSubs, setBurnSubs] = useState(true);
  const [targetScenes, setTargetScenes] = useState(6);
  const [gen, setGen] = useState<ActiveGeneration>(IDLE_GEN);
  const [existingFinal, setExistingFinal] = useState<FinalVideo | null>(null);

  const selectedProject = projects.find((p) => p.id === selectedId) ?? null;

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoadingList(true);
    setHealthError(null);
    setProjectsError(null);
    try {
      const [h, p] = await Promise.all([
        api.health(signal).catch((e: Error) => {
          setHealthError(e.message);
          return null;
        }),
        api.listProjects(signal).catch((e: Error) => {
          setProjectsError(e.message);
          return [] as Project[];
        }),
      ]);
      if (h) setHealth(h);
      setProjects(p ?? []);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh(ctrl.signal);
    return () => ctrl.abort();
  }, [refresh]);

  // Sync form fields when the selected project changes.
  useEffect(() => {
    if (!selectedProject) return;
    // Hydrating form fields from the newly-selected project is a
    // legitimate "sync external prop → internal state" pattern; the
    // React-19 rule can't tell the difference from cascading renders.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setName(selectedProject.name);
    setDeity(selectedProject.deity ?? "");
    setStyle(selectedProject.style ?? "shiva-himalayan");
    setAspectRatio(selectedProject.aspect_ratio);
    setLyrics(selectedProject.lyrics ?? "");
    setGen(IDLE_GEN);
    setExistingFinal(null);
    // Try to pull the latest render if any.
    api
      .getRender(selectedProject.id)
      .then(setExistingFinal)
      .catch(() => setExistingFinal(null));
  }, [selectedProject]);

  // ── Handlers ──────────────────────────────────────────
  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const p = await api.createProject({
        name,
        deity: deity || null,
        style: style || null,
        aspect_ratio: aspectRatio,
        language: "auto",
        lyrics: lyrics || null,
      });
      await refresh();
      setSelectedId(p.id);
      setAudioFile(null);
      setAudioMeta(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  async function onSaveLyrics() {
    if (!selectedProject) return;
    setSavingLyrics(true);
    try {
      await api.uploadLyrics(selectedProject.id, lyrics);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingLyrics(false);
    }
  }

  async function onUploadAudio() {
    if (!selectedProject || !audioFile) return;
    setUploading(true);
    try {
      const res = await api.uploadAudio(selectedProject.id, audioFile);
      setAudioMeta({
        duration: res.metadata.duration,
        codec: res.metadata.codec,
        filename: res.original_filename,
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function onGenerate() {
    if (!selectedProject) return;
    // Capture the id so TS narrowing survives the async loop closures.
    const projectId = selectedProject.id;
    // Stop any prior polling loop.
    pollingRef.current?.abort();
    setGen({
      status: "running",
      progress: [],
      jobStatus: "QUEUED",
      message: "queueing…",
      error: null,
      result: null,
    });
    let cancelled = false;
    const ctrl = new AbortController();
    pollingRef.current = {
      abort: () => {
        cancelled = true;
        ctrl.abort();
      },
    };
    try {
      const queued = await api.generateAsync(
        projectId,
        {
          run_transcription: runTranscription,
          target_scene_count: targetScenes,
          style_preset: style || null,
          burn_subtitles: burnSubs,
          fps: 24,
        },
        ctrl.signal,
      );
      // Poll the job until terminal state.
      while (!cancelled) {
        await new Promise((r) => setTimeout(r, 800));
        if (cancelled) return;
        let job: Job;
        try {
          job = await api.getJob(queued.job_id, ctrl.signal);
        } catch (err) {
          if (
            err instanceof DOMException &&
            err.name === "AbortError"
          ) {
            return;
          }
          throw err;
        }
        setGen((prev) => ({
          ...prev,
          progress: job.result?.stages ?? prev.progress,
          jobStatus: job.status,
          message: job.message,
        }));
        if (job.status === "COMPLETED") {
          const final = job.result?.final ?? null;
          setGen({
            status: "done",
            progress: job.result?.stages ?? [],
            jobStatus: job.status,
            message: job.message,
            error: null,
            result: final,
          });
          if (final) setExistingFinal(final);
          return;
        }
        if (job.status === "FAILED") {
          const failedStage = job.result?.failed_stage ?? "unknown";
          setGen({
            status: "failed",
            progress: job.result?.stages ?? [],
            jobStatus: job.status,
            message: job.message,
            error: `${failedStage}: ${job.result?.failure_reason ?? job.error ?? "unknown error"}`,
            result: null,
          });
          return;
        }
        if (job.status === "CANCELLED") {
          setGen({
            status: "failed",
            progress: job.result?.stages ?? [],
            jobStatus: job.status,
            message: job.message,
            error: "cancelled",
            result: null,
          });
          return;
        }
      }
    } catch (err) {
      let stageInfo = "";
      if (err instanceof ApiError) {
        try {
          const parsed = JSON.parse(err.rawDetail);
          if (parsed?.stage) {
            stageInfo = ` (stage: ${parsed.stage})`;
          }
        } catch {
          /* rawDetail wasn't JSON */
        }
      }
      setGen({
        status: "failed",
        progress: [],
        jobStatus: null,
        message: null,
        error:
          (err instanceof Error ? err.message : String(err)) + stageInfo,
        result: null,
      });
    }
  }

  // Abort any active polling when the component unmounts or the
  // selected project changes.
  useEffect(() => {
    return () => {
      pollingRef.current?.abort();
    };
  }, []);

  async function onDelete(id: string) {
    if (!confirm("Delete this project?")) return;
    try {
      await api.deleteProject(id);
      if (selectedId === id) setSelectedId(null);
      await refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }

  // ── Render ────────────────────────────────────────────
  return (
    <main className="mx-auto max-w-6xl px-6 py-10 space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">
          AI Devotional Video Studio
        </h1>
        <p className="text-sm text-neutral-500">
          Local-first pipeline for Hindi / Sanskrit devotional videos.
          Backend: <code className="font-mono">{api.base}</code>
        </p>
      </header>

      <BackendHealth
        health={health}
        error={healthError}
        loading={loadingList}
        onRefresh={() => void refresh()}
      />

      <div className="grid gap-6 md:grid-cols-[300px_1fr]">
        {/* ─── Project list ────────────────────────────── */}
        <aside className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium">Projects</h2>
            <button
              type="button"
              onClick={() => setSelectedId(null)}
              className="text-xs px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700"
            >
              + New
            </button>
          </div>
          {projectsError && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {projectsError}
            </p>
          )}
          <ul className="space-y-1">
            {projects.length === 0 && (
              <li className="text-sm text-neutral-500">
                No projects yet — create one on the right.
              </li>
            )}
            {projects.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(p.id)}
                  className={`w-full text-left px-3 py-2 rounded border ${
                    p.id === selectedId
                      ? "border-orange-500 bg-orange-500/10"
                      : "border-neutral-200 dark:border-neutral-800 hover:bg-neutral-100/40 dark:hover:bg-neutral-900/40"
                  }`}
                >
                  <div className="text-sm font-medium">{p.name}</div>
                  <div className="text-xs text-neutral-500 mt-0.5">
                    {[p.deity, p.aspect_ratio, p.style]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {/* ─── Workspace ──────────────────────────────── */}
        <section className="space-y-6">
          {selectedProject ? (
            <ProjectWorkspace
              key={selectedProject.id}
              project={selectedProject}
              // form state
              deity={deity}
              setDeity={setDeity}
              style={style}
              setStyle={setStyle}
              lyrics={lyrics}
              setLyrics={setLyrics}
              savingLyrics={savingLyrics}
              onSaveLyrics={onSaveLyrics}
              // audio
              audioFile={audioFile}
              setAudioFile={setAudioFile}
              audioMeta={audioMeta}
              uploading={uploading}
              onUploadAudio={onUploadAudio}
              // generate
              runTranscription={runTranscription}
              setRunTranscription={setRunTranscription}
              burnSubs={burnSubs}
              setBurnSubs={setBurnSubs}
              targetScenes={targetScenes}
              setTargetScenes={setTargetScenes}
              gen={gen}
              onGenerate={onGenerate}
              existingFinal={existingFinal}
              onDelete={() => void onDelete(selectedProject.id)}
            />
          ) : (
            <NewProjectForm
              name={name}
              setName={setName}
              deity={deity}
              setDeity={setDeity}
              style={style}
              setStyle={setStyle}
              aspectRatio={aspectRatio}
              setAspectRatio={setAspectRatio}
              lyrics={lyrics}
              setLyrics={setLyrics}
              creating={creating}
              onCreate={onCreate}
            />
          )}
        </section>
      </div>
    </main>
  );
}

// ─── Sub-components ────────────────────────────────────

function BackendHealth({
  health,
  error,
  loading,
  onRefresh,
}: {
  health: HealthResponse | null;
  error: string | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <section className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Backend health</h2>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="text-sm px-3 py-1 rounded border border-neutral-300 dark:border-neutral-700 disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {error ? (
        <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : health ? (
        <dl className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-y-2 gap-x-6 text-sm">
          <div>
            <dt className="text-neutral-500">Status</dt>
            <dd className="font-mono">{health.status}</dd>
          </div>
          <div>
            <dt className="text-neutral-500">Version</dt>
            <dd className="font-mono">{health.version}</dd>
          </div>
          {Object.entries(health.engines).map(([k, v]) => (
            <div key={k}>
              <dt className="text-neutral-500 capitalize">{k}</dt>
              <dd className="font-mono">{v}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-3 text-sm text-neutral-500">Loading…</p>
      )}
    </section>
  );
}

function NewProjectForm(props: {
  name: string;
  setName: (v: string) => void;
  deity: string;
  setDeity: (v: string) => void;
  style: string;
  setStyle: (v: string) => void;
  aspectRatio: AspectRatio;
  setAspectRatio: (v: AspectRatio) => void;
  lyrics: string;
  setLyrics: (v: string) => void;
  creating: boolean;
  onCreate: (e: React.FormEvent) => void;
}) {
  const {
    name, setName, deity, setDeity, style, setStyle,
    aspectRatio, setAspectRatio, lyrics, setLyrics, creating, onCreate,
  } = props;
  return (
    <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
      <h2 className="text-lg font-medium">New project</h2>
      <form onSubmit={onCreate} className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name">
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="input"
          />
        </Field>
        <Field label="Deity (optional)">
          <input
            type="text"
            value={deity}
            onChange={(e) => setDeity(e.target.value)}
            className="input"
          />
        </Field>
        <Field label="Visual style">
          <select
            value={style}
            onChange={(e) => setStyle(e.target.value)}
            className="input"
          >
            {STYLE_PRESETS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Aspect ratio">
          <select
            value={aspectRatio}
            onChange={(e) => setAspectRatio(e.target.value as AspectRatio)}
            className="input"
          >
            {ASPECT_RATIOS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Lyrics (Hindi / Sanskrit)" full>
          <textarea
            rows={6}
            value={lyrics}
            onChange={(e) => setLyrics(e.target.value)}
            className="input font-mono"
          />
        </Field>
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-2 rounded bg-orange-600 text-white disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create project"}
          </button>
        </div>
      </form>
      <style jsx>{`
        .input {
          width: 100%;
          border: 1px solid rgba(163, 163, 163, 0.4);
          border-radius: 4px;
          padding: 4px 8px;
          background: transparent;
        }
      `}</style>
    </div>
  );
}

function ProjectWorkspace(props: {
  project: Project;
  deity: string;
  setDeity: (v: string) => void;
  style: string;
  setStyle: (v: string) => void;
  lyrics: string;
  setLyrics: (v: string) => void;
  savingLyrics: boolean;
  onSaveLyrics: () => void;
  audioFile: File | null;
  setAudioFile: (f: File | null) => void;
  audioMeta: { duration: number; codec: string; filename: string } | null;
  uploading: boolean;
  onUploadAudio: () => void;
  runTranscription: boolean;
  setRunTranscription: (v: boolean) => void;
  burnSubs: boolean;
  setBurnSubs: (v: boolean) => void;
  targetScenes: number;
  setTargetScenes: (v: number) => void;
  gen: ActiveGeneration;
  onGenerate: () => void;
  existingFinal: FinalVideo | null;
  onDelete: () => void;
}) {
  const {
    project, deity, setDeity, style, setStyle, lyrics, setLyrics,
    savingLyrics, onSaveLyrics, audioFile, setAudioFile, audioMeta,
    uploading, onUploadAudio, runTranscription, setRunTranscription,
    burnSubs, setBurnSubs, targetScenes, setTargetScenes, gen, onGenerate,
    existingFinal, onDelete,
  } = props;

  const busy = gen.status === "running";
  const finalToShow: FinalVideo | null = gen.result ?? existingFinal;

  return (
    <>
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{project.name}</h2>
          <p className="text-xs text-neutral-500 font-mono mt-0.5">
            {project.id}
          </p>
        </div>
        <button
          type="button"
          onClick={onDelete}
          className="text-xs px-3 py-1 rounded border border-red-600/40 text-red-500 hover:bg-red-500/10"
        >
          Delete project
        </button>
      </header>

      {/* Audio */}
      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
        <h3 className="text-md font-medium">1 · Audio</h3>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/flac"
            onChange={(e) => setAudioFile(e.target.files?.[0] ?? null)}
            className="text-sm"
          />
          <button
            type="button"
            disabled={!audioFile || uploading}
            onClick={onUploadAudio}
            className="px-3 py-1.5 text-sm rounded bg-neutral-200 dark:bg-neutral-800 disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
        {audioMeta && (
          <p className="mt-3 text-xs text-neutral-500">
            uploaded <span className="font-mono">{audioMeta.filename}</span>{" "}
            · {audioMeta.duration.toFixed(1)}s · {audioMeta.codec}
          </p>
        )}
      </div>

      {/* Lyrics + settings */}
      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
        <h3 className="text-md font-medium">2 · Lyrics &amp; style</h3>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Field label="Deity">
            <input
              type="text"
              value={deity}
              onChange={(e) => setDeity(e.target.value)}
              className="input"
            />
          </Field>
          <Field label="Visual style">
            <select
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              className="input"
            >
              {STYLE_PRESETS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Lyrics (Hindi / Sanskrit)" full>
            <textarea
              rows={6}
              value={lyrics}
              onChange={(e) => setLyrics(e.target.value)}
              className="input font-mono"
            />
          </Field>
          <div className="sm:col-span-2 flex items-center gap-3">
            <button
              type="button"
              disabled={savingLyrics}
              onClick={onSaveLyrics}
              className="px-3 py-1.5 text-sm rounded bg-neutral-200 dark:bg-neutral-800 disabled:opacity-50"
            >
              {savingLyrics ? "Saving…" : "Save lyrics"}
            </button>
          </div>
        </div>
      </div>

      {/* Generate */}
      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
        <h3 className="text-md font-medium">3 · Generate video</h3>
        <div className="mt-3 grid gap-4 sm:grid-cols-3 items-end">
          <Field label="Target scene count">
            <input
              type="number"
              min={2}
              max={20}
              value={targetScenes}
              onChange={(e) =>
                setTargetScenes(Math.max(2, Math.min(20, Number(e.target.value) || 6)))
              }
              className="input"
            />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={runTranscription}
              onChange={(e) => setRunTranscription(e.target.checked)}
            />
            Run Whisper transcription
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={burnSubs}
              onChange={(e) => setBurnSubs(e.target.checked)}
            />
            Burn Devanagari subtitles
          </label>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            type="button"
            onClick={onGenerate}
            disabled={busy}
            className="px-4 py-2 rounded bg-orange-600 text-white disabled:opacity-50"
          >
            {busy
              ? gen.message
                ? `Generating (${gen.jobStatus?.toLowerCase() ?? "…"})`
                : "Generating…"
              : "GENERATE VIDEO"}
          </button>
          {gen.status === "failed" && (
            <span className="text-sm text-red-500">{gen.error}</span>
          )}
        </div>

        <ProgressTimeline gen={gen} />
      </div>

      {finalToShow && (
        <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
          <h3 className="text-md font-medium">Preview</h3>
          <div className="mt-3">
            {finalToShow.url ? (
              <video
                key={finalToShow.final_asset_id}
                controls
                className="max-h-[80vh] mx-auto rounded"
                src={absolutize(finalToShow.url)}
              />
            ) : (
              <p className="text-sm text-neutral-500">
                Video generated at <code>{finalToShow.path}</code> — but the
                backend didn&rsquo;t return a servable URL for it. Open the
                file with your OS media player.
              </p>
            )}
          </div>
          <p className="mt-3 text-xs text-neutral-500">
            {finalToShow.duration.toFixed(1)}s · {finalToShow.width}×
            {finalToShow.height} · {finalToShow.fps} fps ·{" "}
            {(finalToShow.size_bytes / 1024 / 1024).toFixed(2)} MB ·{" "}
            {finalToShow.scene_count} scenes
            {finalToShow.subtitles_burned && " · burned subtitles"}
          </p>
        </div>
      )}

      <style jsx>{`
        .input {
          width: 100%;
          border: 1px solid rgba(163, 163, 163, 0.4);
          border-radius: 4px;
          padding: 4px 8px;
          background: transparent;
        }
      `}</style>
    </>
  );
}

function ProgressTimeline({ gen }: { gen: ActiveGeneration }) {
  if (gen.status === "idle") return null;

  const byStage: Record<string, GenerationStep> = {};
  for (const p of gen.progress) byStage[p.stage] = p;

  return (
    <ol className="mt-4 space-y-1">
      {ALL_PIPELINE_STAGES.map((stage) => {
        const step = byStage[stage];
        let icon = "○";
        let color = "text-neutral-500";
        let detail = "";
        if (step) {
          if (step.status === "ok") {
            icon = "✓";
            color = "text-emerald-500";
          } else if (step.status === "skipped") {
            icon = "—";
            color = "text-neutral-500";
          } else if (step.status === "failed") {
            icon = "✗";
            color = "text-red-500";
          }
          detail = step.detail;
        } else if (gen.status === "running") {
          icon = "⏳";
          color = "text-neutral-400";
        }
        return (
          <li key={stage} className={`text-sm flex gap-3 ${color}`}>
            <span className="w-4 text-center">{icon}</span>
            <span className="min-w-40">{STAGE_LABEL[stage]}</span>
            <span className="text-xs text-neutral-500">{detail}</span>
          </li>
        );
      })}
    </ol>
  );
}

function Field({
  label,
  children,
  full = false,
}: {
  label: string;
  children: React.ReactNode;
  full?: boolean;
}) {
  return (
    <label
      className={`text-sm space-y-1 ${full ? "sm:col-span-2" : ""}`}
    >
      <span className="block text-neutral-500">{label}</span>
      {children}
    </label>
  );
}
