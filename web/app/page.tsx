"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getGallery, type GalleryItem } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useSession } from "./components/session";

export default function Home() {
  const { session, authReady } = useSession();
  const [items, setItems] = useState<GalleryItem[] | null>(null);

  useEffect(() => {
    getGallery()
      .then((r) => setItems(r.ideas))
      .catch(() => setItems([]));
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-4xl tracking-tight">The Idea Stage</h1>
          <p className="mt-2 max-w-xl text-muted">
            Validate your startup idea the way a sharp VC would — real evidence, citations, and
            an honest pressure test before you build.
          </p>
          <div className="mt-6 flex items-center gap-4">
            <Link
              href="/ideas"
              className="rounded-md bg-ink px-6 py-3 text-sm font-medium text-white"
            >
              {session ? "My ideas" : "Validate your idea"}
            </Link>
          </div>
        </div>
        {authReady && session && (
          <button
            onClick={() => supabase.auth.signOut()}
            className="shrink-0 text-xs text-muted underline"
          >
            Sign out
          </button>
        )}
      </header>

      <section className="mt-14">
        <h2 className="font-serif text-xl">What founders are validating</h2>
        <p className="mt-1 text-sm text-muted">
          Real validations founders chose to publish. Open one to see the full, cited analysis.
        </p>
        {items === null ? (
          <p className="mt-6 text-sm text-muted">Loading…</p>
        ) : items.length === 0 ? (
          <p className="mt-6 text-sm text-muted">No published ideas yet — be the first.</p>
        ) : (
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {items.map((it) => (
              <Link
                key={it.id}
                href={`/idea/${it.id}`}
                className="rounded-lg border border-line bg-white/70 p-5 text-left transition hover:border-ink"
              >
                <p className="font-medium">{it.idea}</p>
                <p className="mt-2 text-xs text-muted">{it.verdict}</p>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
