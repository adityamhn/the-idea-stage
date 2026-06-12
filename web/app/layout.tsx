import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "./components/session";
import { ToastProvider } from "./components/toast";

export const metadata: Metadata = {
  title: "The Idea Stage",
  description: "Validate your startup idea the disciplined way — one stage at a time.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>
          <ToastProvider>{children}</ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
