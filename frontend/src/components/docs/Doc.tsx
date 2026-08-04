import { ReactNode } from "react";
import styles from "./docs.module.css";

/** Page header: title, one-line summary, optional eyebrow. */
export function PageHeader({
  eyebrow,
  title,
  lede,
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
}) {
  return (
    <header className={styles.pageHeader}>
      {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
      <h1 className={styles.h1}>{title}</h1>
      {lede && <p className={styles.lede}>{lede}</p>}
    </header>
  );
}

/**
 * Section with an anchor. The id is derived from the title, so links in prose
 * (`#the-freshness-gate`) stay correct if a heading is reworded: they break
 * loudly rather than silently pointing at nothing.
 */
export function Section({
  title,
  id,
  children,
}: {
  title: string;
  id?: string;
  children: ReactNode;
}) {
  const anchor = id ?? slug(title);
  return (
    <section className={styles.section}>
      <h2 id={anchor} className={styles.h2}>
        <a href={`#${anchor}`} className={styles.anchor} aria-hidden="true">
          #
        </a>
        {title}
      </h2>
      {children}
    </section>
  );
}

export function SubSection({
  title,
  id,
  children,
}: {
  title: string;
  id?: string;
  children: ReactNode;
}) {
  const anchor = id ?? slug(title);
  return (
    <div className={styles.subsection}>
      <h3 id={anchor} className={styles.h3}>
        {title}
      </h3>
      {children}
    </div>
  );
}

type CalloutKind = "note" | "warn" | "danger" | "good";

const CALLOUT_LABEL: Record<CalloutKind, string> = {
  note: "Note",
  warn: "Caution",
  danger: "Important",
  good: "Why this matters",
};

export function Callout({
  kind = "note",
  title,
  children,
}: {
  kind?: CalloutKind;
  title?: string;
  children: ReactNode;
}) {
  return (
    <aside className={`${styles.callout} ${styles[`callout_${kind}`]}`}>
      <div className={styles.calloutTitle}>{title ?? CALLOUT_LABEL[kind]}</div>
      <div className={styles.calloutBody}>{children}</div>
    </aside>
  );
}

export { CodeBlock as Code } from "./CodeBlock";
export { Mermaid } from "./Mermaid";

/** Names an on-screen control the reader has to find. */
export function UI({ children }: { children: ReactNode }) {
  return <span className={styles.ui}>{children}</span>;
}

/** A keyboard shortcut. */
export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className={styles.kbd}>{children}</kbd>;
}

/** Where in the interface a task begins. */
export function Where({ children }: { children: ReactNode }) {
  return (
    <div className={styles.location}>
      <span className={styles.locationLabel}>Where</span>
      <span>{children}</span>
    </div>
  );
}

export function Table({
  head,
  rows,
  widths,
}: {
  head: string[];
  rows: ReactNode[][];
  widths?: string[];
}) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i} style={widths ? { width: widths[i] } : undefined}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Numbered procedure. Each step is a discrete action with a result. */
export function Steps({ children }: { children: ReactNode }) {
  return <ol className={styles.steps}>{children}</ol>;
}

export function Step({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <li className={styles.step}>
      <div className={styles.stepTitle}>{title}</div>
      {children && <div className={styles.stepBody}>{children}</div>}
    </li>
  );
}

/** Inline code. */
export function C({ children }: { children: ReactNode }) {
  return <code className={styles.inlineCode}>{children}</code>;
}

/** Key/value definition rows, for config and field references. */
export function Defs({ items }: { items: { term: string; def: ReactNode }[] }) {
  return (
    <dl className={styles.defs}>
      {items.map((item) => (
        <div key={item.term} className={styles.defRow}>
          <dt className={styles.defTerm}>{item.term}</dt>
          <dd className={styles.defBody}>{item.def}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Card grid for landing pages. */
export function CardGrid({ children }: { children: ReactNode }) {
  return <div className={styles.cardGrid}>{children}</div>;
}

export function Card({
  href,
  title,
  children,
}: {
  href: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <a href={href} className={styles.card}>
      <span className={styles.cardTitle}>{title}</span>
      <span className={styles.cardBody}>{children}</span>
    </a>
  );
}

function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
