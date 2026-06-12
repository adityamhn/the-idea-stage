"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

export type ToastKind = "info" | "success" | "error";
type ToastInput = { title: string; body?: string; kind?: ToastKind; notify?: boolean };
type Toast = { id: number; title: string; body?: string; kind: ToastKind };

const ToastContext = createContext<((t: ToastInput) => void) | null>(null);

/** Ask for OS-notification permission. Call from a user gesture (e.g. starting a stage)
 *  so the later "stage done" notification can fire when the tab is hidden. */
export function requestNotifyPermission() {
  if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().catch(() => {});
  }
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const toast = useCallback(
    ({ title, body, kind = "info", notify = false }: ToastInput) => {
      const id = ++idRef.current;
      setToasts((t) => [...t, { id, title, body, kind }]);
      window.setTimeout(() => dismiss(id), 6000);
      // When the user has switched away, surface an OS notification too.
      if (
        notify &&
        typeof document !== "undefined" &&
        document.hidden &&
        "Notification" in window &&
        Notification.permission === "granted"
      ) {
        try {
          new Notification(title, { body });
        } catch {
          /* notifications unsupported in this context */
        }
      }
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={
              "pointer-events-auto rounded-md border bg-white px-4 py-3 text-sm shadow-lg " +
              (t.kind === "error"
                ? "border-red-300"
                : t.kind === "success"
                  ? "border-green-300"
                  : "border-line")
            }
          >
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium text-ink">{t.title}</p>
              <button
                onClick={() => dismiss(t.id)}
                className="-mr-1 -mt-0.5 shrink-0 text-base leading-none text-muted hover:text-ink"
                aria-label="Dismiss"
              >
                ×
              </button>
            </div>
            {t.body && <p className="mt-1 text-muted">{t.body}</p>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): (t: ToastInput) => void {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
