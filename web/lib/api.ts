import { accessToken } from "./supabase";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const token = await accessToken();
  return {
    "content-type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export type PlaybookFlag = { principle: string; note: string };

export type StageReview = {
  summary: string;
  what_this_means: string;
  strengths: string[];
  risks: string[];
  playbook_flags: PlaybookFlag[];
  suggested_next: string;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type StageOutput = Record<string, any>;

export type StageResultDTO = {
  stage_key: string;
  title: string;
  output: StageOutput;
  review: StageReview;
  usage: Record<string, number>;
};

export type RunSnapshot = {
  id: string;
  idea: string;
  mock: boolean;
  status: "idle" | "running" | "done" | "error";
  running_stage: string | null;
  error: string | null;
  published: boolean;
  stage_order: string[];
  completed_stages: string[];
  next_stage: string | null;
  results: StageResultDTO[];
};

export type Me = { email: string; credits: number };
export type RunListItem = {
  id: string;
  idea: string;
  status: "idle" | "running" | "done" | "error";
  completed_stages: string[];
  next_stage: string | null;
  total_stages: number;
  published: boolean;
  updated_at: string | null;
};
export type GalleryItem = {
  id: string;
  idea: string;
  verdict: string;
  stages_done: string[];
  published_at: string | null;
};
export type GalleryDetail = {
  id: string;
  idea: string;
  verdict: string;
  published_at: string | null;
  results: StageResultDTO[];
};
export type Pack = { credits: number; amount_cents: number; name: string };

export const INSUFFICIENT_CREDITS = "insufficient_credits";

async function jsonOrThrow(res: Response) {
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function createRun(
  idea: string,
  mock: boolean,
  scheduling_link: string,
): Promise<RunSnapshot> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({ idea, mock, scheduling_link }),
  });
  return jsonOrThrow(res);
}

export async function getRun(id: string): Promise<RunSnapshot> {
  return jsonOrThrow(await fetch(`${API_BASE}/runs/${id}`, { headers: await authHeaders() }));
}

export async function listRuns(): Promise<{ runs: RunListItem[] }> {
  return jsonOrThrow(await fetch(`${API_BASE}/runs`, { headers: await authHeaders() }));
}

export async function continueRun(id: string): Promise<RunSnapshot> {
  const res = await fetch(`${API_BASE}/runs/${id}/continue`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({}),
  });
  return jsonOrThrow(res);
}

export async function regenerateRun(id: string): Promise<RunSnapshot> {
  const res = await fetch(`${API_BASE}/runs/${id}/regenerate`, {
    method: "POST",
    headers: await authHeaders(),
  });
  return jsonOrThrow(res);
}

export async function saveHypothesis(id: string, output: StageOutput): Promise<RunSnapshot> {
  const res = await fetch(`${API_BASE}/runs/${id}/hypothesis`, {
    method: "PATCH",
    headers: await authHeaders(),
    body: JSON.stringify({ output }),
  });
  return jsonOrThrow(res);
}

export async function regenerateHypothesis(id: string, edits: string): Promise<RunSnapshot> {
  const res = await fetch(`${API_BASE}/runs/${id}/hypothesis/regenerate`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({ edits }),
  });
  return jsonOrThrow(res);
}

export type PtMessage = { role: "assistant" | "user"; text: string; sources?: Cite[] };
export type PtState = { messages: PtMessage[]; concluded: boolean };
export type Cite = { url: string; title?: string; quote?: string };

export async function ptState(id: string): Promise<PtState> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/runs/${id}/pressure-test`, { headers: await authHeaders() }),
  );
}

export async function ptStart(id: string): Promise<PtState> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/runs/${id}/pressure-test/start`, {
      method: "POST",
      headers: await authHeaders(),
    }),
  );
}

export async function ptMessage(id: string, text: string): Promise<PtState> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/runs/${id}/pressure-test/message`, {
      method: "POST",
      headers: await authHeaders(),
      body: JSON.stringify({ text }),
    }),
  );
}

export async function getMe(): Promise<Me> {
  return jsonOrThrow(await fetch(`${API_BASE}/me`, { headers: await authHeaders() }));
}

export async function getGallery(): Promise<{ ideas: GalleryItem[] }> {
  return jsonOrThrow(await fetch(`${API_BASE}/gallery`));
}

export async function getGalleryDetail(id: string): Promise<GalleryDetail> {
  return jsonOrThrow(await fetch(`${API_BASE}/gallery/${id}`));
}

export async function publishRun(id: string): Promise<RunSnapshot> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/runs/${id}/publish`, { method: "POST", headers: await authHeaders() }),
  );
}

export async function unpublishRun(id: string): Promise<RunSnapshot> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/runs/${id}/unpublish`, { method: "POST", headers: await authHeaders() }),
  );
}

export async function getPacks(): Promise<{ configured: boolean; packs: Record<string, Pack> }> {
  return jsonOrThrow(await fetch(`${API_BASE}/billing/packs`));
}

export async function checkout(pack: string): Promise<{ url: string }> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/billing/checkout`, {
      method: "POST",
      headers: await authHeaders(),
      body: JSON.stringify({ pack }),
    }),
  );
}

export async function ptConclude(id: string): Promise<RunSnapshot> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/runs/${id}/pressure-test/conclude`, {
      method: "POST",
      headers: await authHeaders(),
    }),
  );
}

/** Subscribe to the SSE stream; calls back on every event with the event type.
 *  EventSource can't set headers, so the token rides as a query param. */
export async function subscribeEvents(
  id: string,
  onEvent: (type: string) => void,
): Promise<() => void> {
  const token = await accessToken();
  const es = new EventSource(`${API_BASE}/runs/${id}/events?token=${encodeURIComponent(token)}`);
  const types = ["snapshot", "stage_start", "stage_complete", "error", "done"];
  for (const t of types) es.addEventListener(t, () => onEvent(t));
  es.onerror = () => es.close();
  return () => es.close();
}
