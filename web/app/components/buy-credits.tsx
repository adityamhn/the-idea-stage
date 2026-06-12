"use client";

import { useEffect, useState } from "react";
import { checkout, getPacks, type Pack } from "@/lib/api";

export function BuyCredits({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<{ configured: boolean; packs: Record<string, Pack> } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getPacks()
      .then(setData)
      .catch((e) => setErr((e as Error).message));
  }, []);

  async function buy(id: string) {
    setBusy(true);
    setErr(null);
    try {
      const { url } = await checkout(id);
      window.location.href = url;
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-line bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-serif text-lg">Buy credits</h3>
          <button onClick={onClose} className="text-sm text-muted underline">
            Close
          </button>
        </div>
        {err && <p className="mt-2 text-sm text-red-700">{err}</p>}
        {!data ? (
          <p className="mt-3 text-sm text-muted">Loading…</p>
        ) : !data.configured ? (
          <p className="mt-3 text-sm text-muted">
            Payments aren&apos;t enabled yet (Razorpay keys not configured).
          </p>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {Object.entries(data.packs).map(([id, p]) => (
              <button
                key={id}
                disabled={busy}
                onClick={() => buy(id)}
                className="rounded-md border border-line p-4 text-left transition hover:border-ink disabled:opacity-40"
              >
                <div className="font-medium">{p.credits} credits</div>
                <div className="text-sm text-muted">${(p.amount_cents / 100).toFixed(0)}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
