"use client";

import Link from "next/link";
import { useState } from "react";
import { supabase } from "@/lib/supabase";
import { BuyCredits } from "./buy-credits";
import { useSession } from "./session";

export function AppHeader() {
  const { session, credits } = useSession();
  const [showBuy, setShowBuy] = useState(false);
  const email = session?.user.email ?? "";

  return (
    <header className="mb-10 flex items-start justify-between gap-4">
      <div>
        <Link href="/">
          <h1 className="font-serif text-4xl tracking-tight">The Idea Stage</h1>
        </Link>
        <p className="mt-2 text-muted">Helping founders navigate through the idea stage.</p>
      </div>
      <div className="shrink-0 text-right text-xs text-muted">
        {session && (
          <div>
            {email}
            {credits !== null && (
              <>
                {" · "}
                <b className="text-ink">{credits} credits</b>
              </>
            )}
          </div>
        )}
        <div className="mt-1 flex justify-end gap-3">
          <Link href="/" className="underline">
            Home
          </Link>
          {session && (
            <Link href="/ideas" className="underline">
              My ideas
            </Link>
          )}
          {session && (
            <>
              <button onClick={() => setShowBuy(true)} className="underline">
                Buy credits
              </button>
              <button onClick={() => supabase.auth.signOut()} className="underline">
                Sign out
              </button>
            </>
          )}
        </div>
      </div>
      {showBuy && <BuyCredits onClose={() => setShowBuy(false)} />}
    </header>
  );
}
