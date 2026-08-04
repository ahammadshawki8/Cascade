import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const ibmPlexSans = IBM_Plex_Sans({
  variable: "--font-ibm-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: {
    default: "Cascade",
    template: "%s · Cascade",
  },
  description:
    "A procedural memory layer for AI agents that learns skills — and knows when to unlearn them.",
  applicationName: "Cascade",
  authors: [{ name: "Ashfaq" }, { name: "Shawki" }],
  keywords: [
    "agentic memory",
    "incident response",
    "CockroachDB",
    "vector search",
    "provenance",
    "SRE",
  ],
  // app/icon.svg is picked up automatically; declaring it here keeps the
  // wiring visible rather than implicit in a filename.
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${ibmPlexSans.variable} ${ibmPlexMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
