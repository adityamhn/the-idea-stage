"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { createRun, listRuns, type RunListItem } from "@/lib/api";
import { AppHeader } from "../components/header";
import { useSession } from "../components/session";
import { SignIn } from "../components/signin";

const MOCK = process.env.NEXT_PUBLIC_MOCK !== "false"; // default on until live billing lands

export default function IdeasPage() {
  const { session, authReady } = useSession();

  if (!authReady) {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-sm text-muted">Loading…</main>;
  }
  if (!session) return <SignIn />;
  return <Dashboard />;
}

function Dashboard() {
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunListItem[] | null>(null);

  const load = useCallback(async () => {
    try {
      setRuns((await listRuns()).runs);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function start() {
    setErr(null);
    setBusy(true);
    try {
      const snap = await createRun(idea.trim(), MOCK, "");
      router.push(`/idea/${snap.id}`);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <AppHeader />

      {err && (
        <div className="mb-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {err}
        </div>
      )}

      <section>
        <label className="block text-sm font-medium">Validate a new idea</label>
        <textarea
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          rows={3}
          placeholder="e.g. AI expense reconciliation for mid-market finance teams"
          className="mt-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink"
        />
        <button
          onClick={start}
          disabled={busy || !idea.trim()}
          className="mt-4 rounded-md bg-ink px-6 py-2.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Starting…" : "Start validation"}
        </button>
      </section>

      <section className="mt-14">
        <h2 className="font-serif text-xl">Your ideas</h2>
        {runs === null ? (
          <p className="mt-4 text-sm text-muted">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="mt-4 text-sm text-muted">
            No ideas yet — start your first validation above.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {runs.map((r) => (
              <Link
                key={r.id}
                href={`/idea/${r.id}`}
                className="block rounded-lg border border-line bg-white/70 p-5 transition hover:border-ink"
              >
                <div className="flex items-start justify-between gap-4">
                  <p className="min-w-0 font-medium">{r.idea}</p>
                  {r.published && (
                    <span className="shrink-0 rounded-full bg-green-100 px-2 py-0.5 text-[11px] text-green-800">
                      Public
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs text-muted">
                  <RunStatus run={r} />
                </p>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function RunStatus({ run }: { run: RunListItem }) {
  const n = run.completed_stages.length;
  const total = run.total_stages;
  if (run.status === "error") return <span className="text-red-700">Needs retry · {n}/{total} stages</span>;
  if (run.status === "running") return <span>Working… · {n}/{total} stages</span>;
  if (run.next_stage === null && run.status === "done")
    return <span>Complete ✓ · {total}/{total} stages</span>;
  return <span>In progress · {n}/{total} stages</span>;
}
