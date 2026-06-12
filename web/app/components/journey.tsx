"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ptConclude,
  ptMessage,
  ptStart,
  ptState,
  type PtState,
  type RunSnapshot,
  type StageOutput,
  type StageResultDTO,
} from "@/lib/api";

// The fixed journey order — used to synthesize a nav for the read-only public view.
export const STAGE_ORDER = [
  "hypothesis",
  "pressure_test",
  "market",
  "discovery",
  "outreach",
  "solution",
] as const;

// Short labels for the left-nav table of contents (stage cards keep their full titles).
export const NAV_TITLES: Record<string, string> = {
  hypothesis: "Hypothesis",
  pressure_test: "Pressure test",
  market: "Market",
  discovery: "Discovery",
  outreach: "Outreach",
  solution: "Solution",
};

export type Pending = Record<string, boolean>;

// --------------------------------------------------------------------------- //
// Left table of contents — sticky on desktop, replaces the old top stepper.
// --------------------------------------------------------------------------- //
export function StageNav({ run }: { run: RunSnapshot }) {
  const jump = (key: string) =>
    document.getElementById(`stage-${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <nav className="lg:sticky lg:top-12">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Stages</p>
      <ol className="flex flex-wrap gap-2 lg:flex-col lg:gap-1">
        {run.stage_order.map((s, i) => {
          const completed = run.completed_stages.includes(s);
          const active = run.running_stage === s;
          const clickable = completed || active;
          return (
            <li key={s}>
              <button
                onClick={() => clickable && jump(s)}
                disabled={!clickable}
                className={
                  "flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm transition " +
                  (active
                    ? "bg-ink/5 font-medium text-ink"
                    : completed
                      ? "text-ink hover:bg-ink/5"
                      : "cursor-default text-muted")
                }
              >
                <span
                  className={
                    "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] " +
                    (completed
                      ? "bg-ink text-white"
                      : active
                        ? "border border-ink"
                        : "border border-line")
                  }
                >
                  {completed ? "✓" : active ? "●" : i + 1}
                </span>
                {NAV_TITLES[s]}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// --------------------------------------------------------------------------- //
// Interactive journey for the run's owner.
// --------------------------------------------------------------------------- //
export function Journey(props: {
  run: RunSnapshot;
  pending: Pending;
  onNext: () => void;
  onRegen: () => void;
  onRetry: () => void;
  onSaveHypo: (output: StageOutput) => void;
  onRegenHypo: (edits: string) => void;
  onPtDone: () => void;
  onTogglePublish: () => void;
}) {
  const { run, pending } = props;
  const done = run.next_stage === null && run.status === "done";
  const lastKey = run.completed_stages[run.completed_stages.length - 1];
  const failed = run.status === "error";
  const running = run.status === "running";
  const ready = run.status === "idle" || run.status === "done";
  const inPressureTest = run.next_stage === "pressure_test" && ready;
  const nextLabel = run.next_stage ? NAV_TITLES[run.next_stage] : "next stage";

  return (
    <div className="lg:grid lg:grid-cols-[180px_1fr] lg:gap-10">
      <div className="mb-8 lg:mb-0">
        <StageNav run={run} />
      </div>

      <div className="min-w-0 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <p className="font-serif text-lg italic text-muted">“{run.idea}”</p>
          <Link href="/ideas" className="shrink-0 text-sm text-muted underline">
            New idea
          </Link>
        </div>

        {run.results.map((r) => {
          const editableHypo = r.stage_key === "hypothesis" && lastKey === "hypothesis" && ready;
          return (
            <div key={r.stage_key} id={`stage-${r.stage_key}`} className="scroll-mt-6">
              {editableHypo ? (
                <HypothesisEditor
                  result={r}
                  pending={pending}
                  onSave={props.onSaveHypo}
                  onRegen={props.onRegenHypo}
                />
              ) : (
                <StageCard result={r} />
              )}
            </div>
          );
        })}

        {inPressureTest && (
          <div id="stage-pressure_test" className="scroll-mt-6">
            <PressureTestPanel runId={run.id} onConcluded={props.onPtDone} />
          </div>
        )}

        {running && run.running_stage && (
          <div
            id={`stage-${run.running_stage}`}
            className="scroll-mt-6 rounded-md border border-line bg-white/60 px-4 py-3 text-sm text-muted"
          >
            Working on <b>{NAV_TITLES[run.running_stage]}</b>… we&apos;ll notify you when it&apos;s done.
            You can leave this page open.
            <button
              onClick={props.onRetry}
              disabled={pending.retry}
              className="ml-2 underline disabled:opacity-40"
            >
              {pending.retry ? "Retrying…" : "Stuck? Retry"}
            </button>
          </div>
        )}

        {failed && run.next_stage && (
          <div
            id={`stage-${run.next_stage}`}
            className="scroll-mt-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            <p className="font-medium">Couldn&apos;t generate {nextLabel}.</p>
            {run.error && <p className="mt-1 break-words">{run.error}</p>}
            <button
              onClick={props.onRetry}
              disabled={pending.retry}
              className="mt-2 rounded-md bg-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {pending.retry ? "Retrying…" : "Retry stage"}
            </button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-6">
          {!done && ready && !inPressureTest && run.results.length > 0 && (
            <button
              onClick={props.onNext}
              disabled={pending.next}
              className="rounded-md bg-ink px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
            >
              {pending.next ? "Continuing…" : "Continue to next stage →"}
            </button>
          )}
          {/* Hypothesis has its own regenerate (with edits) inside its editor; the
              pressure test is interactive and can't be re-run by the generic path. */}
          {run.results.length > 0 && ready && lastKey !== "hypothesis" && lastKey !== "pressure_test" && (
            <button
              onClick={props.onRegen}
              disabled={pending.regen}
              className="rounded-md border border-line px-4 py-2.5 text-sm disabled:opacity-40"
            >
              {pending.regen ? "Regenerating…" : "Regenerate last stage"}
            </button>
          )}
          {done && <span className="text-sm text-muted">✓ You reached a solution concept.</span>}
          {run.results.length > 0 && ready && (
            <button
              onClick={props.onTogglePublish}
              disabled={pending.publish}
              className={
                "ml-auto rounded-md px-4 py-2.5 text-sm disabled:opacity-40 " +
                (run.published ? "border border-line" : "border border-ink font-medium")
              }
            >
              {pending.publish
                ? "Saving…"
                : run.published
                  ? "Published ✓ — unpublish"
                  : "Publish to gallery"}
            </button>
          )}
        </div>
        {run.published && (
          <p className="text-xs text-muted">
            This validation is public on the homepage gallery (no personal info shown).
          </p>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Read-only view for a published idea seen by someone other than the owner.
// --------------------------------------------------------------------------- //
export function ReadOnlyStages({ results }: { results: StageResultDTO[] }) {
  return (
    <div className="space-y-6">
      {results.map((r) => (
        <div key={r.stage_key} id={`stage-${r.stage_key}`} className="scroll-mt-6">
          <StageCard result={r} />
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Stage card + outputs (ported verbatim from the original monolith).
// --------------------------------------------------------------------------- //
export function StageCard({ result }: { result: StageResultDTO }) {
  return (
    <section className="rounded-lg border border-line bg-white/70 p-6">
      <h3 className="font-serif text-xl">{result.title}</h3>
      <div className="mt-4">
        <OutputView stageKey={result.stage_key} output={result.output} />
      </div>
      <CoachCard review={result.review} />
    </section>
  );
}

const HYPO_FIELDS: [string, string][] = [
  ["statement", "Hypothesis"],
  ["who", "Who"],
  ["how_often", "How often"],
  ["how_severe", "How severe"],
  ["current_workaround", "Current workaround"],
  ["why_now", "Why now"],
];

function HypothesisEditor({
  result,
  pending,
  onSave,
  onRegen,
}: {
  result: StageResultDTO;
  pending: Pending;
  onSave: (output: StageOutput) => void;
  onRegen: (edits: string) => void;
}) {
  const o = result.output;
  const initial = () => Object.fromEntries(HYPO_FIELDS.map(([k]) => [k, o[k] ?? ""]));
  const [f, setF] = useState<Record<string, string>>(initial);
  const [edits, setEdits] = useState("");
  // Reset the form when a fresh hypothesis arrives (e.g. after regenerate).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setF(initial()), [JSON.stringify(o)]);

  return (
    <section className="rounded-lg border border-line bg-white/70 p-6">
      <h3 className="font-serif text-xl">{result.title}</h3>
      <p className="mt-1 text-xs text-muted">
        Edit any field and save, or regenerate with instructions. Sources are below.
      </p>
      <div className="mt-3">
        <Pill ok={!!o.is_specific} label={o.is_specific ? "Specific" : "Still too generic"} />
      </div>

      <div className="mt-4 space-y-3">
        {HYPO_FIELDS.map(([k, label]) => (
          <div key={k}>
            <label className="text-xs font-semibold uppercase tracking-wide text-muted">
              {label}
            </label>
            <textarea
              value={f[k]}
              onChange={(e) => setF({ ...f, [k]: e.target.value })}
              rows={k === "statement" ? 2 : 1}
              className="mt-1 w-full resize-y rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink"
            />
          </div>
        ))}
        <button
          onClick={() => onSave({ ...o, ...f })}
          disabled={pending.saveHypo}
          className="rounded-md border border-ink px-4 py-2 text-sm font-medium disabled:opacity-40"
        >
          {pending.saveHypo ? "Saving…" : "Save edits"}
        </button>
      </div>

      {(o.key_assumptions ?? []).length > 0 && (
        <div className="mt-5 space-y-2">
          {(o.key_assumptions ?? []).map((a: StageOutput, i: number) => (
            <Field key={i} label={`Assumption — ${(a.kind ?? "").replace(/_/g, " ")}`}>
              <div className="mb-1 flex items-center gap-2">
                <ConfidenceChip level={a.confidence} />
                <Provenance n={(a.sources ?? []).length} />
              </div>
              <div>{a.claim}</div>
              <div className="text-muted">Signal: {a.signal}</div>
              <Sources sources={a.sources} />
            </Field>
          ))}
        </div>
      )}
      {o.sources?.length > 0 && (
        <div className="mt-4">
          <Field label="Sources">
            <Sources sources={o.sources} />
          </Field>
        </div>
      )}

      <CoachCard review={result.review} />

      <div className="mt-5 border-t border-line pt-4">
        <label className="text-xs font-semibold uppercase tracking-wide text-muted">
          Regenerate with edits
        </label>
        <textarea
          value={edits}
          onChange={(e) => setEdits(e.target.value)}
          rows={2}
          placeholder="e.g. focus on seed-stage startups, not enterprise; the buyer is the founder"
          className="mt-1 w-full resize-y rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink"
        />
        <button
          onClick={() => onRegen(edits)}
          disabled={pending.regenHypo}
          className="mt-2 rounded-md bg-ink px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {pending.regenHypo ? "Regenerating…" : "Regenerate hypothesis"}
        </button>
      </div>
    </section>
  );
}

const MIN_ANSWERS = 2; // mirror the API gate: a verdict shouldn't rest on one answer

// Pull a leading "[Targeting: ...]"-style tag off an interviewer message. The prompt
// asks for "[Targeting: <assumption>]" but the model sometimes labels differently
// (e.g. "[Differentiation: ...]"), so accept any leading "[Label: value]".
function splitTargeting(text: string): { tag: string | null; body: string } {
  const m = text.match(/^\s*\[([^\]:]{1,40}):\s*([^\]]+)\]\s*/);
  if (!m) return { tag: null, body: text };
  const label = m[1].trim();
  const tag = /^targeting$/i.test(label) ? m[2].trim() : `${label}: ${m[2].trim()}`;
  return { tag, body: text.slice(m[0].length).trimStart() };
}

function PressureTestPanel({ runId, onConcluded }: { runId: string; onConcluded: () => void }) {
  const [state, setState] = useState<PtState | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    ptState(runId)
      .then(setState)
      .catch((e) => setErr((e as Error).message));
  }, [runId]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const messages = state?.messages ?? [];
  const answers = messages.filter((m) => m.role === "user").length;

  return (
    <section className="rounded-lg border border-line bg-white/70 p-6">
      <h3 className="font-serif text-xl">Pressure test</h3>
      <p className="mt-1 text-xs text-muted">
        A VC interviews you to stress-test the hypothesis. Answer honestly — drilling into the
        weak spots is the whole point.
      </p>
      {err && <p className="mt-2 text-sm text-red-700">{err}</p>}

      {messages.length === 0 ? (
        <button
          onClick={() => run(async () => setState(await ptStart(runId)))}
          disabled={busy}
          className="mt-4 rounded-md bg-ink px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Starting…" : "Begin pressure test"}
        </button>
      ) : (
        <>
          <div className="mt-4 space-y-3">
            {messages.map((m, i) => {
              const { tag, body } = splitTargeting(m.text);
              return (
                <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
                  <div
                    className={
                      "max-w-[85%] rounded-lg px-3 py-2 text-sm " +
                      (m.role === "assistant" ? "bg-bg" : "bg-ink text-white")
                    }
                  >
                    {m.role === "assistant" && tag && (
                      <span className="mb-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[11px] uppercase tracking-wide text-amber-800">
                        Targeting: {tag}
                      </span>
                    )}
                    <div className="whitespace-pre-wrap">{body}</div>
                    {m.role === "assistant" && <Sources sources={m.sources} />}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3 flex gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" &&
                !busy &&
                text.trim() &&
                run(async () => {
                  const t = text.trim();
                  setText("");
                  setState(await ptMessage(runId, t));
                })
              }
              placeholder="Your answer…"
              disabled={busy}
              className="flex-1 rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink"
            />
            <button
              onClick={() =>
                run(async () => {
                  const t = text.trim();
                  setText("");
                  setState(await ptMessage(runId, t));
                })
              }
              disabled={busy || !text.trim()}
              className="rounded-md border border-line px-4 py-2 text-sm disabled:opacity-40"
            >
              Send
            </button>
          </div>
          {answers < MIN_ANSWERS && (
            <p className="mt-3 text-xs text-muted">
              Answer at least {MIN_ANSWERS} questions to get an honest verdict ({answers}/
              {MIN_ANSWERS}).
            </p>
          )}
          <button
            onClick={() =>
              run(async () => {
                await ptConclude(runId);
                onConcluded();
              })
            }
            disabled={busy || answers < MIN_ANSWERS}
            className="mt-2 rounded-md bg-ink px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
          >
            {busy ? "Working…" : "Conclude pressure test →"}
          </button>
        </>
      )}
    </section>
  );
}

function Pill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={
        "rounded-full px-2.5 py-0.5 text-xs " +
        (ok ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800")
      }
    >
      {ok ? "✓ " : "⚠ "}
      {label}
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

function List({ items }: { items?: string[] }) {
  if (!items?.length) return <span className="text-muted">—</span>;
  return (
    <ul className="list-disc space-y-0.5 pl-5">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
}

type Cite = { url: string; title?: string; quote?: string; published?: string };

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// Evidence-strength chip for an assumption (strong = green, mixed = amber, weak = red).
function ConfidenceChip({ level }: { level?: string }) {
  const l = (level || "mixed").toLowerCase();
  const cls =
    l === "strong"
      ? "bg-green-100 text-green-800"
      : l === "weak"
        ? "bg-red-100 text-red-700"
        : "bg-amber-100 text-amber-800";
  return (
    <span className={"rounded-full px-2 py-0.5 text-[11px] uppercase tracking-wide " + cls}>
      {l} evidence
    </span>
  );
}

// Whether a claim is backed by sources or is the analyst's own reasoning.
function Provenance({ n }: { n: number }) {
  return (
    <span className="text-[11px] text-muted">
      {n > 0 ? `· ${n} source${n > 1 ? "s" : ""}` : "· reasoning, not sourced"}
    </span>
  );
}

function Sources({ sources }: { sources?: Cite[] }) {
  if (!sources?.length) return null;
  return (
    <ul className="mt-1.5 space-y-1">
      {sources.map((s, i) => (
        <li key={i} className="text-xs leading-snug">
          <a
            href={s.url}
            target="_blank"
            rel="noreferrer"
            className="text-blue-700 underline underline-offset-2"
          >
            {s.title || hostOf(s.url)}
          </a>
          <span className="text-muted"> · {hostOf(s.url)}</span>
          {s.published && <span className="text-muted"> · {s.published}</span>}
          {s.quote && <div className="text-muted">“{s.quote}”</div>}
        </li>
      ))}
    </ul>
  );
}

function HypothesisBody({ output }: { output: StageOutput }) {
  return (
    <div className="space-y-3">
      <p className="font-medium">{output.statement}</p>
      <Pill ok={output.is_specific} label="Specific" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Who">{output.who}</Field>
        <Field label="How often">{output.how_often}</Field>
        <Field label="How severe">{output.how_severe}</Field>
        <Field label="Current workaround">{output.current_workaround}</Field>
      </div>
      <Field label="Why now">{output.why_now}</Field>
      {(output.key_assumptions ?? []).map((a: StageOutput, i: number) => (
        <Field key={i} label={`Assumption — ${(a.kind ?? "").replace(/_/g, " ")}`}>
          <div className="mb-1 flex items-center gap-2">
            <ConfidenceChip level={a.confidence} />
            <Provenance n={(a.sources ?? []).length} />
          </div>
          <div>{a.claim}</div>
          <div className="text-muted">Signal: {a.signal}</div>
          <Sources sources={a.sources} />
        </Field>
      ))}
      {output.sources?.length > 0 && (
        <Field label="Sources">
          <Sources sources={output.sources} />
        </Field>
      )}
    </div>
  );
}

function OutputView({ stageKey, output }: { stageKey: string; output: StageOutput }) {
  if (stageKey === "hypothesis") {
    return <HypothesisBody output={output} />;
  }
  if (stageKey === "pressure_test") {
    return (
      <div className="space-y-3">
        <Pill
          ok={output.survived}
          label={output.survived ? "Survived pressure test" : "Did not survive"}
        />
        <Field label="Strongest case against">{output.attack_summary}</Field>
        <Field label="Disconfirming evidence">
          <ul className="space-y-2">
            {(output.disconfirming_evidence ?? []).map((d: StageOutput, i: number) => (
              <li key={i}>
                <div>{d.point}</div>
                <Sources sources={d.sources} />
              </li>
            ))}
          </ul>
        </Field>
        {output.unresolved_questions?.length > 0 && (
          <Field label="Questions you didn't answer convincingly">
            <List items={output.unresolved_questions} />
          </Field>
        )}
        {output.suggested_sharpening && (
          <Field label="Suggested sharpening">{output.suggested_sharpening}</Field>
        )}
        {output.sources?.length > 0 && (
          <Field label="Sources">
            <Sources sources={output.sources} />
          </Field>
        )}
      </div>
    );
  }
  if (stageKey === "market") {
    const s = output.sizing ?? {};
    const c = output.competitors ?? {};
    const t = output.trends ?? {};
    const usd = (n: number) =>
      n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(0)}M` : `$${n}`;
    return (
      <div className="space-y-3">
        <Pill ok={output.real_signal} label="Real market signal" />
        <Field label="Defensible angle">{output.defensible_angle}</Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="TAM">{usd(s.tam_usd)}</Field>
          <Field label="SAM">{usd(s.sam_usd)}</Field>
          <Field label="SOM">{usd(s.som_usd)}</Field>
        </div>
        <Field label="Sizing method">{s.method}</Field>
        {s.key_assumptions?.length > 0 && (
          <Field label="Sizing assumptions">
            <List items={s.key_assumptions} />
          </Field>
        )}
        {s.sources?.length > 0 && <Sources sources={s.sources} />}
        <Field label="Competitors">
          <ul className="space-y-1.5">
            {(c.competitors ?? []).map((x: StageOutput, i: number) => (
              <li key={i}>
                <span className="font-medium">{x.name}</span>{" "}
                <span className="text-muted">({(x.tier ?? "").replace(/_/g, " ")})</span> —{" "}
                {x.why_threat}
                <Sources sources={x.sources} />
              </li>
            ))}
          </ul>
        </Field>
        <Field label="Strongest threat">
          {c.strongest_threat}
          <Sources sources={c.sources} />
        </Field>
        <Field label="Market state">{t.expanding_consolidating_or_mature}</Field>
        <Field label="Trends">
          <ul className="space-y-1.5">
            {(t.trends ?? []).map((x: StageOutput, i: number) => (
              <li key={i}>
                {x.trend} <span className="text-muted">({x.tailwind_or_headwind})</span>
                <Sources sources={x.sources} />
              </li>
            ))}
          </ul>
        </Field>
        {output.sources?.length > 0 && (
          <Field label="Sources">
            <Sources sources={output.sources} />
          </Field>
        )}
      </div>
    );
  }
  if (stageKey === "discovery") {
    return (
      <div className="space-y-3">
        <Pill ok={output.non_leading} label="Non-leading questions" />
        {(output.target_profiles ?? []).map((p: StageOutput, i: number) => (
          <Field key={i} label="Target profile">
            <div>{(p.job_titles ?? []).join(", ")}</div>
            <div className="text-muted">
              {(p.company_types ?? []).join(", ")} · {p.seniority}
            </div>
            <div className="mt-1">{p.why_acute}</div>
          </Field>
        ))}
        <Field label="Reachable channels">
          <List items={output.reachable_channels} />
        </Field>
        {(output.frameworks ?? []).map((f: StageOutput, i: number) => (
          <Field key={i} label={`Interview guide — ${f.persona}`}>
            <List items={f.questions} />
            {f.follow_up_probes?.length > 0 && (
              <p className="mt-1 text-muted">Probes: {f.follow_up_probes.join(" · ")}</p>
            )}
          </Field>
        ))}
      </div>
    );
  }
  if (stageKey === "outreach") {
    return (
      <div className="space-y-3">
        {(output.prospects ?? []).map((p: StageOutput, i: number) => (
          <Field key={i} label={`${p.name} — ${p.role} @ ${p.company}`}>
            {p.contact && <div className="text-muted">{p.contact}</div>}
            <pre className="mt-1 whitespace-pre-wrap rounded bg-bg p-3 text-sm">
              {p.draft_email}
            </pre>
          </Field>
        ))}
        <Field label="Interview guide">
          <List items={output.interview_guide} />
        </Field>
        <Field label="Findings (provisional until interviews happen)">
          <List items={output.discovery_findings} />
        </Field>
      </div>
    );
  }
  if (stageKey === "solution") {
    return (
      <div className="space-y-3">
        <Field label="Concept">{output.concept}</Field>
        <Field label="Addresses the revealed problem">{output.addresses_revealed_problem}</Field>
        {(output.assumptions ?? []).map((a: StageOutput, i: number) => (
          <Field key={i} label={`Load-bearing assumption ${i + 1}`}>
            <div className="font-medium">{a.assumption}</div>
            <div className="text-muted">Must be true: {a.what_must_be_true}</div>
            <div className="text-muted">If it fails: {a.failure_mode}</div>
          </Field>
        ))}
      </div>
    );
  }
  return <pre className="text-xs">{JSON.stringify(output, null, 2)}</pre>;
}

function CoachCard({ review }: { review: StageResultDTO["review"] }) {
  return (
    <div className="mt-5 rounded-md border border-line bg-bg p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">Coach</p>
      <p className="mt-1 font-medium">{review.summary}</p>
      <p className="mt-1 text-sm text-muted">{review.what_this_means}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {review.strengths.length > 0 && (
          <Field label="Strengths">
            <List items={review.strengths} />
          </Field>
        )}
        {review.risks.length > 0 && (
          <Field label="Risks to weigh">
            <List items={review.risks} />
          </Field>
        )}
      </div>
      {review.playbook_flags.map((f, i) => (
        <div key={i} className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
          <b>⚑ {f.principle}</b> — {f.note}
        </div>
      ))}
      <p className="mt-3 text-sm">
        <span className="font-medium">Suggested next: </span>
        {review.suggested_next}
      </p>
    </div>
  );
}
