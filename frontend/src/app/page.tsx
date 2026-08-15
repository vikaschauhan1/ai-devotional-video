"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AspectRatio, HealthResponse, Project } from "@/lib/api-types";

const ASPECT_RATIOS: AspectRatio[] = ["9:16", "16:9", "1:1"];

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState("Shiva bhajan");
  const [deity, setDeity] = useState("Shiva");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("9:16");
  const [lyrics, setLyrics] = useState(
    "जय शिव शंभो, जय महेश्वर\nआदि अनंत, तू ही ईश्वर",
  );
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
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
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    // Initial-mount fetch. React 19's `react-hooks/set-state-in-effect`
    // fires because refresh() calls setLoading synchronously before its
    // first await. This is the canonical fetch-on-mount pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh(ctrl.signal);
    return () => ctrl.abort();
  }, [refresh]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      await api.createProject({
        name,
        deity: deity || null,
        aspect_ratio: aspectRatio,
        lyrics: lyrics || null,
        language: "auto",
      });
      await refresh();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Delete this project?")) return;
    try {
      await api.deleteProject(id);
      await refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10 space-y-10">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">
          AI Devotional Video Studio
        </h1>
        <p className="text-sm text-neutral-500">
          Local-first pipeline for Hindi / Sanskrit devotional videos.
          Backend: <code className="font-mono">{api.base}</code>
        </p>
      </header>

      <section className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Backend health</h2>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="text-sm px-3 py-1 rounded border border-neutral-300 dark:border-neutral-700 disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        {healthError ? (
          <p className="mt-3 text-sm text-red-600 dark:text-red-400">
            {healthError}
          </p>
        ) : health ? (
          <dl className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-y-2 gap-x-6 text-sm">
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

      <section className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
        <h2 className="text-lg font-medium">New project</h2>
        <form onSubmit={onCreate} className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="text-sm space-y-1">
            <span className="text-neutral-500">Name</span>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1"
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-neutral-500">Deity</span>
            <input
              type="text"
              value={deity}
              onChange={(e) => setDeity(e.target.value)}
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1"
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-neutral-500">Aspect ratio</span>
            <select
              value={aspectRatio}
              onChange={(e) => setAspectRatio(e.target.value as AspectRatio)}
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1"
            >
              {ASPECT_RATIOS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm space-y-1 sm:col-span-2">
            <span className="text-neutral-500">Lyrics (Hindi / Sanskrit)</span>
            <textarea
              rows={4}
              value={lyrics}
              onChange={(e) => setLyrics(e.target.value)}
              className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1 font-mono"
            />
          </label>
          <div className="sm:col-span-2 flex items-center gap-3">
            <button
              type="submit"
              disabled={creating}
              className="px-4 py-2 rounded bg-orange-600 text-white disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create project"}
            </button>
            {createError && (
              <span className="text-sm text-red-600 dark:text-red-400">
                {createError}
              </span>
            )}
          </div>
        </form>
      </section>

      <section className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-5">
        <h2 className="text-lg font-medium">
          Projects{" "}
          <span className="text-neutral-500 text-sm">({projects.length})</span>
        </h2>
        {projectsError ? (
          <p className="mt-3 text-sm text-red-600 dark:text-red-400">
            {projectsError}
          </p>
        ) : projects.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">
            No projects yet. Create one above.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-neutral-200 dark:divide-neutral-800">
            {projects.map((p) => (
              <li
                key={p.id}
                className="py-3 flex items-start justify-between gap-4"
              >
                <div className="min-w-0">
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-neutral-500 mt-0.5">
                    {[
                      p.deity,
                      p.aspect_ratio,
                      p.language,
                      p.lip_sync_enabled ? "lip-sync" : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                  <div className="text-xs text-neutral-400 font-mono mt-0.5">
                    {p.id}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void onDelete(p.id)}
                  className="text-xs px-2 py-1 rounded border border-neutral-300 dark:border-neutral-700 text-red-600 dark:text-red-400"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
