"use client";

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
} from "lucide-react";

export type ViewId =
  | "incidents"
  | "runbooks"
  | "policy"
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
  { id: "runbooks", label: "Runbooks", hint: "Learned procedures", icon: BookOpen },
  { id: "policy", label: "Policy", hint: "Rules and impact", icon: Shield },
  { id: "copilot", label: "Copilot", hint: "Ask the database", icon: Sparkles },
  { id: "intelligence", label: "Intelligence", hint: "Savings, graph, memory", icon: Brain },
  { id: "approvals", label: "Approvals", hint: "Actions awaiting a human", icon: ShieldCheck },
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
  return (
    <nav className={styles.bar} aria-label="Primary">
      <div className={styles.brand} title="Cascade">
        <Logo size={22} />
      </div>

      <div className={styles.group}>
        {VIEWS.map((item) => {
          const Icon = item.icon;
          const count = badges[item.id] ?? 0;
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`${styles.item} ${isActive ? styles.itemActive : ""}`}
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
