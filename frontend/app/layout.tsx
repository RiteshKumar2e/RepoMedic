import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/layout/Providers";

export const metadata: Metadata = {
  title: "RepoMedic — Diagnose Code. Repair Faster. Ship Confidently.",
  description:
    "Repository-aware AI code review that detects architectural, security, performance, and reliability issues—and validates every proposed fix before it reaches your branch.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 antialiased selection:bg-sky-500/30">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
