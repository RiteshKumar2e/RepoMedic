import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/layout/Providers";

export const metadata: Metadata = {
  title: "RepoMedic — Diagnose code. Repair faster. Ship confidently.",
  description:
    "Repository-aware AI code review that detects architectural, security, performance and reliability issues — and validates every proposed fix before it reaches your branch.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-canvas text-ink antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
