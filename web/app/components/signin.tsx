"use client";

import Link from "next/link";
import { useState } from "react";
import { supabase } from "@/lib/supabase";

export function SignIn() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send() {
    setErr(null);
    setBusy(true);
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.href },
    });
    setBusy(false);
    if (error) setErr(error.message);
    else setSent(true);
  }

  return (
    <main className="mx-auto max-w-md px-6 py-24">
      <Link href="/" className="mb-4 inline-block text-sm text-muted underline">
        ← Back to gallery
      </Link>
      <h1 className="font-serif text-4xl tracking-tight">The Idea Stage</h1>
      <p className="mt-2 text-muted">Helping founders navigate through the idea stage.</p>

      {sent ? (
        <div className="mt-10 rounded-md border border-line bg-white/60 p-5 text-sm">
          Check <b>{email}</b> for a magic link to sign in.
        </div>
      ) : (
        <div className="mt-10">
          <label className="block text-sm font-medium">Sign in with email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && email.trim() && send()}
            placeholder="you@company.com"
            className="mt-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink"
          />
          {err && <p className="mt-2 text-sm text-red-700">{err}</p>}
          <button
            onClick={send}
            disabled={busy || !email.trim()}
            className="mt-4 rounded-md bg-ink px-6 py-2.5 text-sm font-medium text-white disabled:opacity-40"
          >
            {busy ? "Sending…" : "Send magic link"}
          </button>
        </div>
      )}
    </main>
  );
}
