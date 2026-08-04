"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./docs.module.css";
import { Logo } from "../Logo";

interface Entry {
  href: string;
  label: string;
}

interface Section {
  title: string;
  entries: Entry[];
}

export const NAV: Section[] = [
  {
    title: "Getting started",
    entries: [
      { href: "/docs", label: "What is Cascade" },
      { href: "/docs/quickstart", label: "Install and run" },
      { href: "/docs/first-incident", label: "Your first incident" },
      { href: "/docs/interface", label: "The interface" },
    ],
  },
  {
    title: "Using Cascade",
    entries: [
      { href: "/docs/incidents", label: "Running incidents" },
      { href: "/docs/runbooks", label: "Managing runbooks" },
      { href: "/docs/policy", label: "Changing policy" },
      { href: "/docs/approvals", label: "Approving actions" },
      { href: "/docs/intelligence", label: "Measuring value" },
      { href: "/docs/copilot", label: "Asking questions" },
    ],
  },
  {
    title: "Understanding it",
    entries: [
      { href: "/docs/concepts", label: "Key concepts" },
      { href: "/docs/architecture", label: "How it works" },
    ],
  },
  {
    title: "Reference",
    entries: [
      { href: "/docs/configuration", label: "Settings" },
      { href: "/docs/api", label: "HTTP API" },
      { href: "/docs/deployment", label: "Deploying" },
      { href: "/docs/troubleshooting", label: "Troubleshooting" },
    ],
  },
];

export function DocsNav() {
  const pathname = usePathname();

  return (
    <nav className={styles.sidebar} aria-label="Documentation">
      <Link href="/docs" className={styles.sidebarBrand}>
        <Logo size={22} wordmark />
      </Link>

      <div className={styles.sidebarScroll}>
        {NAV.map((section) => (
          <div key={section.title} className={styles.navSection}>
            <div className={styles.navTitle}>{section.title}</div>
            {section.entries.map((entry) => {
              const active = pathname === entry.href;
              return (
                <Link
                  key={entry.href}
                  href={entry.href}
                  className={`${styles.navLink} ${active ? styles.navLinkActive : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  {entry.label}
                </Link>
              );
            })}
          </div>
        ))}
      </div>

      <Link href="/" className={styles.sidebarFooter}>
        ← Back to the app
      </Link>
    </nav>
  );
}

/** Previous / next pagination, derived from NAV so it can never drift. */
export function DocsPager() {
  const pathname = usePathname();
  const flat = NAV.flatMap((s) => s.entries);
  const index = flat.findIndex((e) => e.href === pathname);
  if (index === -1) return null;

  const previous = flat[index - 1];
  const next = flat[index + 1];

  return (
    <div className={styles.pager}>
      {previous ? (
        <Link href={previous.href} className={styles.pagerLink}>
          <span className={styles.pagerLabel}>Previous</span>
          <span className={styles.pagerTitle}>{previous.label}</span>
        </Link>
      ) : (
        <span />
      )}
      {next && (
        <Link
          href={next.href}
          className={`${styles.pagerLink} ${styles.pagerNext}`}
        >
          <span className={styles.pagerLabel}>Next</span>
          <span className={styles.pagerTitle}>{next.label}</span>
        </Link>
      )}
    </div>
  );
}
