"use client";

import { useState } from "react";
import styles from "./ActivityBar.module.css";
import { Logo } from "./Logo";
import {
  Terminal,
  BookOpen,
  Shield,
  Sparkles,
  Brain,
  ShieldCheck,
  RotateCcw,
  Command,
  BookMarked,
  MoreHorizontal,
  History,
  Network,
} from "lucide-react";

export type ViewId =
  | "incidents"
  | "history"
  | "runbooks"
  | "policy"
  | "architecture"
  | "copilot"
  | "intelligence"
  | "approvals";

interface Item {
  id: ViewId;
  label: string;
  hint: string;
  icon: typeof Terminal;
}

export const VIEWS: Item[] = [
  { id: "incidents", label: "Incidents", hint: "Run and watch tasks", icon: Terminal },
  { id: "history", label: "History", hint: "Past runs and why", icon: History },
  { id: "runbooks", label: "Runbooks", hint: "Learned procedures", icon: BookOpen },
  { id: "policy", label: "Policy", hint: "Rules and impact", icon: Shield },
  {
    id: "architecture",
    label: "Architecture",
    hint: "How it holds together",
    icon: Network,
  },
  { id: "copilot", label: "Copilot", hint: "Ask the database", icon: Sparkles },
  { id: "intelligence", label: "Intelligence", hint: "Savings, graph, memory", icon: Brain },
  { id: "approvals", label: "Approvals", hint: "Actions awaiting a human", icon: ShieldCheck },
];

/**
 * These five carry the story: run one, look at what happened, see what it
 * learned, change the rules, and read how any of that is possible.
 *
 * The three left behind assume you already understand the project, so they
 * stay under "More" — and Approvals promotes itself the moment something is
 * genuinely waiting, because then it is the most important thing on screen.
 */
const PRIMARY: ViewId[] = [
  "incidents",
  "history",
  "runbooks",
  "policy",
  "architecture",
];

interface Props {
  active: ViewId;
  onSelect: (id: ViewId) => void;
  badges?: Partial<Record<ViewId, number>>;
  onReset: () => void;
  onCommandPalette: () => void;
}

/**
 * VS Code-style activity bar: a narrow icon rail that switches the main view.
 *
 * Icon-only with hover labels rather than a persistent sidebar — the panels
 * below want the horizontal space, and six destinations is few enough to learn
 * by position. Badges surface counts that need attention without opening the
 * view.
 */
export function ActivityBar({
  active,
  onSelect,
  badges = {},
  onReset,
  onCommandPalette,
}: Props) {
  const [moreOpen, setMoreOpen] = useState(false);

  // A view stays on the rail while it is the active one, so selecting from
  // "More" never makes the thing you are looking at disappear from the nav.
  // Approvals joins them whenever something is genuinely waiting.
  const promoted = new Set<ViewId>(PRIMARY);
  promoted.add(active);
  if ((badges.approvals ?? 0) > 0) promoted.add("approvals");

  const visible = VIEWS.filter((v) => promoted.has(v.id));
  const secondary = VIEWS.filter((v) => !promoted.has(v.id));

  return (
    <nav className={styles.bar} aria-label="Primary">
      <div className={styles.brand} title="Cascade">
        <Logo size={22} />
      </div>

      <div className={styles.group}>
        {visible.map((item) => {
          const Icon = item.icon;
          const count = badges[item.id] ?? 0;
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`${styles.item} ${isActive ? styles.itemActive : ""}`}
              data-tour={`nav-${item.id}`}
              onClick={() => onSelect(item.id)}
              aria-current={isActive ? "page" : undefined}
              aria-label={item.label}
            >
              <Icon size={20} strokeWidth={1.75} />
              {count > 0 && <span className={styles.badge}>{count > 99 ? "99+" : count}</span>}
              <span className={styles.tooltip} role="tooltip">
                <strong>{item.label}</strong>
                <em>{item.hint}</em>
              </span>
            </button>
          );
        })}

        {/* The secondary views, one keypress away rather than one glance. */}
        <button
          type="button"
          className={`${styles.item} ${moreOpen ? styles.itemActive : ""}`}
          onClick={() => setMoreOpen((v) => !v)}
          aria-label="More views"
          aria-expanded={moreOpen}
        >
          <MoreHorizontal size={20} strokeWidth={1.75} />
          <span className={styles.tooltip} role="tooltip">
            <strong>More</strong>
            <em>Copilot, intelligence, approvals</em>
          </span>
        </button>

        {moreOpen && (
          <div className={styles.more}>
            {secondary.map((item) => {
              const Icon = item.icon;
              const count = badges[item.id] ?? 0;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={styles.moreItem}
                  onClick={() => {
                    onSelect(item.id);
                    setMoreOpen(false);
                  }}
                >
                  <Icon size={15} strokeWidth={1.75} />
                  <span className={styles.moreLabel}>{item.label}</span>
                  <span className={styles.moreHint}>{item.hint}</span>
                  {count > 0 && <span className={styles.moreBadge}>{count}</span>}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className={styles.spacer} />

      <div className={styles.group}>
        <button
          type="button"
          className={styles.item}
          onClick={onCommandPalette}
          aria-label="Command palette"
        >
          <Command size={20} strokeWidth={1.75} />
          <span className={styles.tooltip} role="tooltip">
            <strong>Commands</strong>
            <em>Ctrl K</em>
          </span>
        </button>
        <a href="/docs" className={styles.item} aria-label="Documentation">
          <BookMarked size={20} strokeWidth={1.75} />
          <span className={styles.tooltip} role="tooltip">
            <strong>Documentation</strong>
            <em>Concepts, API, operations</em>
          </span>
        </a>
        <button
          type="button"
          className={styles.item}
          onClick={onReset}
          aria-label="Reset demo"
        >
          <RotateCcw size={20} strokeWidth={1.75} />
          <span className={styles.tooltip} role="tooltip">
            <strong>Reset demo</strong>
            <em>Restore the clean v1 world</em>
          </span>
        </button>
      </div>
    </nav>
  );
}
