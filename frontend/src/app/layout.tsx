import type { Metadata } from "next";
import { Inter, Geist_Mono } from "next/font/google";

import { SiteFooter } from "@/components/layout/SiteFooter";
import "./globals.css";

// Matches the marketing site's font exactly (see
// anuragyadav9786/new-design's redesign-styles.tsx) — Geist Mono stays for
// this platform's own tabular figures (NAV/CAGR/drawdown columns), which
// the marketing site has no equivalent of.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ThinkFin — Mutual Fund Decision Intelligence",
  description: "ThinkFin research platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${geistMono.variable} antialiased`}>
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
