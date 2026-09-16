import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { SiteFooter } from "@/components/layout/SiteFooter";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
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
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
