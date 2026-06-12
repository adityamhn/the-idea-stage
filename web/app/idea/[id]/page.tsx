"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  continueRun,
  getGalleryDetail,
  getRun,
  INSUFFICIENT_CREDITS,
  publishRun,
  regenerateHypothesis,
  regenerateRun,
  saveHypothesis,
  subscribeEvents,
  unpublishRun,
  type GalleryDetail,
  type RunSnapshot,
  type StageOutput,
} from "@/lib/api";
import { BuyCredits } from "../../components/buy-credits";
import { AppHeader } from "../../components/header";
import {
  Journey,
  NAV_TITLES,
  type Pending,
  ReadOnlyStages,
  STAGE_ORDER,
  StageNav,
} from "../../components/journey";
import { useSession } from "../../components/session";
import { requestNotifyPermission, useToast } from "../../components/toast";

type Mode = "loading" | "owner" | "public" | "notfound";

export default function IdeaPage() {
  const { id } = useParams<{ id: string }>();
  const { session, authReady, refreshCredits } = useSession();
  const toast = useToast();

  const [mode, setMode] = useState<Mode>("loading");
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [pub, setPub] = useState<GalleryDetail | null>(null);
  const [pending, setPending] = useState<Pending>({});
  const [needCredits, setNeedCredits] = useState(false);

  const prevRef = useRef<RunSnapshot | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const kickedRef = useRef(false);

  // Apply a fresh snapshot and surface toasts on the state transitions that matter.
  const apply = useCallback(
    (next: RunSnapshot) => {
      const prev = prevRef.current;
      if (prev) {
        for (const s of next.completed_stages.filter((x) => !prev.completed_stages.includes(x))) {
          toast({ title: `${NAV_TITLES[s] ?? s} done ✓`, kind: "success", notify: true });
        }
        if (next.status === "done" && prev.status !== "done") {
          toast({ title: "Validation complete ✓", kind: "success", notify: true });
        }
        if (next.status === "error" && prev.status !== "error") {
          toast({
            title: `${next.next_stage ? NAV_TITLES[next.next_stage] : "A stage"} failed`,
            body: "Retry below.",
            kind: "error",
            notify: true,
          });
        }
      }
      prevRef.current = next;
      setRun(next);
    },
    [toast],
  );

  const refresh = useCallback(async () => {
    try {
      apply(await getRun(id));
      refreshCredits();
    } catch {
      /* transient — polling/SSE will retry */
    }
  }, [id, apply, refreshCredits]);

  // Initial load: owner snapshot if we can, else the public read-only view.
  useEffect(() => {
    if (!authReady) return;
    let cancelled = false;
    (async () => {
      if (session) {
        try {
          const snap = await getRun(id);
          if (cancelled) return;
          prevRef.current = snap;
          setRun(snap);
          setMode("owner");
          cleanupRef.current = await subscribeEvents(id, () => refresh());
          return;
        } catch {
          /* not the owner (or not found) — try the public view */
        }
      }
      try {
        const detail = await getGalleryDetail(id);
        if (cancelled) return;
        setPub(detail);
        setMode("public");
      } catch {
        if (!cancelled) setMode("notfound");
      }
    })();
    return () => {
      cancelled = true;
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, [id, session, authReady, refresh]);

  // Poll while a stage is running (covers the gap if the SSE drops).
  useEffect(() => {
    if (run?.status !== "running") return;
    const timer = window.setInterval(refresh, 2000);
    return () => window.clearInterval(timer);
  }, [run?.status, refresh]);

  // Auto-kick the first stage when the owner opens a brand-new run.
  useEffect(() => {
    if (mode !== "owner" || !run || kickedRef.current) return;
    if (run.results.length === 0 && run.status === "idle" && run.next_stage) {
      kickedRef.current = true;
      continueStage("next");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, run]);

  async function withPending(key: string, fn: () => Promise<void>) {
    setPending((p) => ({ ...p, [key]: true }));
    setNeedCredits(false);
    try {
      await fn();
    } catch (e) {
      const msg = (e as Error).message;
      if (msg === INSUFFICIENT_CREDITS) {
        setNeedCredits(true);
        toast({ title: "Out of credits", body: "Buy more to continue.", kind: "error" });
      } else {
        toast({ title: "Something went wrong", body: msg, kind: "error" });
      }
    } finally {
      setPending((p) => ({ ...p, [key]: false }));
    }
  }

  // Continue / retry both just (re)run the next stage; the backend recovers error
  // and stuck-running states. `key` only changes the button's pending label.
  function continueStage(key: "next" | "retry") {
    return withPending(key, async () => {
      requestNotifyPermission();
      const label = run?.next_stage ? NAV_TITLES[run.next_stage] : "the next stage";
      toast({
        title: `Working on ${label}…`,
        body: "We'll notify you when it's done. You can leave this page open.",
      });
      apply(await continueRun(id));
    });
  }

  if (mode === "loading") {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-sm text-muted">Loading…</main>;
  }

  if (mode === "notfound") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-24 text-center">
        <h1 className="font-serif text-3xl tracking-tight">This idea is private or doesn&apos;t exist</h1>
        <p className="mt-3 text-muted">
          Only the owner can see an unpublished validation.
        </p>
        <Link href="/" className="mt-6 inline-block text-sm underline">
          ← Back to gallery
        </Link>
      </main>
    );
  }

  if (mode === "public" && pub) {
    const pseudo = {
      stage_order: [...STAGE_ORDER],
      completed_stages: pub.results.map((r) => r.stage_key),
      running_stage: null,
    } as unknown as RunSnapshot;
    return (
      <main className="mx-auto max-w-5xl px-6 py-12">
        <AppHeader />
        <div className="lg:grid lg:grid-cols-[180px_1fr] lg:gap-10">
          <div className="mb-8 lg:mb-0">
            <StageNav run={pseudo} />
          </div>
          <div className="min-w-0">
            <h1 className="font-serif text-3xl tracking-tight">{pub.idea}</h1>
            <p className="mt-2 text-sm text-muted">{pub.verdict}</p>
            <div className="mt-8">
              <ReadOnlyStages results={pub.results} />
            </div>
          </div>
        </div>
      </main>
    );
  }

  // Owner, interactive.
  if (!run) return null;
  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <AppHeader />
      {needCredits && <BuyCredits onClose={() => setNeedCredits(false)} />}
      <Journey
        run={run}
        pending={pending}
        onNext={() => continueStage("next")}
        onRetry={() => continueStage("retry")}
        onRegen={() => withPending("regen", async () => apply(await regenerateRun(id)))}
        onSaveHypo={(output: StageOutput) =>
          withPending("saveHypo", async () => apply(await saveHypothesis(id, output)))
        }
        onRegenHypo={(edits: string) =>
          withPending("regenHypo", async () => apply(await regenerateHypothesis(id, edits)))
        }
        onTogglePublish={() =>
          withPending("publish", async () =>
            apply(run.published ? await unpublishRun(id) : await publishRun(id)),
          )
        }
        onPtDone={refresh}
      />
    </main>
  );
}
