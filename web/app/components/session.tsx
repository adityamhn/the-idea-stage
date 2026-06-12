"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { getMe } from "@/lib/api";
import { supabase } from "@/lib/supabase";

type Ctx = {
  session: Session | null;
  authReady: boolean;
  credits: number | null;
  refreshCredits: () => void;
};

const SessionContext = createContext<Ctx | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [credits, setCredits] = useState<number | null>(null);

  const refreshCredits = useCallback(async () => {
    try {
      setCredits((await getMe()).credits);
    } catch {
      /* not signed in / transient — leave as-is */
    }
  }, []);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setAuthReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (session) refreshCredits();
    else setCredits(null);
  }, [session, refreshCredits]);

  return (
    <SessionContext.Provider value={{ session, authReady, credits, refreshCredits }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): Ctx {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
