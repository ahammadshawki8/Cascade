"use client";

import { useEffect, useState } from "react";
import styles from "./ActivityBar.module.css";
import { Logo } from "./Logo";
import {
  Terminal,
  BookOpen,
  Shield,
  Plug,
  Network,
  FlaskConical,
  RotateCcw,
  Command,
  BookMarked,
  PanelRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";

const EXPANDED_KEY = "cascade_rail_expanded";

/**
 * Six destinations, one per noun.
 *
 * There used to be eight, which was a tour of features rather than a product:
 * Incidents, History, Runbooks, Policy, Architecture, Copilot, Intelligence and
 * Approvals, with three of them hidden behind a "More" menu that nobody opens.
 * Adding importing, rule authoring and connections to that would have made it
 * eleven.
 *
 * Cascade has four things in it and one place they run:
 *
 *   Work         incidents, runs, history
 *   Procedures   the runbook library, however a runbook got here
 *   Policy       the rules, and what changing one costs
 *   Connections  outbound to Slack, inbound from other agents
 *   System       the machinery, read live
 *
 * Copilot and Approvals are not destinations at all. You consult a copilot
 * *while* looking at something, and navigating away from what prompted the
 * question was always the wrong shape; they live in the right dock now.
 *
 * Evidence is the sixth, and it had to earn the slot against the rule above.
 * It qualifies on the same test as the other five: it is a noun, and it is a
 * thing this system holds rather than a feature it performs. Every other
 * destination shows what Cascade does; this one shows whether it is any better
 * than not having it, measured against two baselines on the same incidents.
 * That claim is the reason the rest of the product is worth navigating, and
 * burying it inside System would have filed the argument under plumbing.
 */
export type ViewId =
  | "work"
  | "procedures"
  | "policy"
  | "connections"
  | "system"
  | "evidence";

interface Item {
  id: ViewId;
  label: string;
  hint: string;
  icon: typeof Terminal;
}

export const VIEWS: Item[] = [
  { id: "work", label: "Work", hint: "Run incidents and review past runs", icon: Terminal },
  {
    id: "procedures",
    label: "Procedures",
    hint: "Runbooks, learned or imported",
    icon: BookOpen,
  },
  { id: "policy", label: "Policy", hint: "Rules, and what changing one costs", icon: Shield },
  {
    id: "connections",
    label: "Connections",
    hint: "Slack, and agents that call in",
    icon: Plug,
  },
  { id: "system", label: "System", hint: "The machinery, read live", icon: Network },
  {
    id: "evidence",
    label: "Evidence",
    hint: "How this compares to a baseline, measured",
    icon: FlaskConical,
  },
];

interface Props {
  active: ViewId;
  onSelect: (id: ViewId) => void;
  badges?: Partial<Record<ViewId, number>>;
  dockBadge?: number;
  onReset: () => void;
  onCommandPalette: () => void;
  onToggleDock: () => void;
}

export function ActivityBar({
  active,
  onSelect,
  badges = {},
  dockBadge = 0,
  onReset,
  onCommandPalette,
  onToggleDock,
}: Props) {
  /**
   * Labels on, until you turn them off.
   *
   * Five unlabeled icons is five guesses, and hover tooltips only help someone
   * who already suspects there is something worth hovering over. Starting
   * expanded costs a first-time viewer nothing and saves them the guessing;
   * anyone who wants the horizontal space back collapses it once and it stays
   * collapsed.
   */
  const [expanded, setExpanded] = useState(true);

  // localStorage is unavailable during SSR, so the stored preference can only
  // be read after mount. Defaulting to expanded means first visit is right.
  useEffect(() => {
    setExpanded(window.localStorage.getItem(EXPANDED_KEY) !== "false");
  }, []);

  const toggleExpanded = () =>
    setExpanded((open) => {
      window.localStorage.setItem(EXPANDED_KEY, String(!open));
      return !open;
    });

  return (
    <nav
      className={`${styles.bar} ${expanded ? styles.barWide : ""}`}
      aria-label="Primary"
    >
      <div className={styles.brand} title="Cascade">
        <Logo size={22} />
        {expanded && <span className={styles.wordmark}>Cascade</span>}
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
              data-tour={`nav-${item.id}`}
              onClick={() => onSelect(item.id)}
              aria-current={isActive ? "page" : undefined}
              aria-label={item.label}
            >
              <Icon size={20} strokeWidth={1.75} />
              {expanded && <span className={styles.itemLabel}>{item.label}</span>}
              {count > 0 && (
                <span className={styles.badge}>{count > 99 ? "99+" : count}</span>
              )}
              {!expanded && (
                <span className={styles.tooltip} role="tooltip">
                  <strong>{item.label}</strong>
                  <em>{item.hint}</em>
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className={styles.spacer} />

      <button
        type="button"
        className={styles.collapse}
        onClick={toggleExpanded}
        aria-label={expanded ? "Collapse the sidebar" : "Expand the sidebar"}
      >
        {expanded ? <ChevronsLeft size={15} /> : <ChevronsRight size={15} />}
        {expanded && <span className={styles.itemLabel}>Collapse</span>}
      </button>

      <div className={styles.group}>
        <button
          type="button"
          className={styles.item}
          onClick={onToggleDock}
          data-tour="nav-dock"
          aria-label="Copilot and approvals"
        >
          <PanelRight size={20} strokeWidth={1.75} />
          {expanded && <span className={styles.itemLabel}>Side panel</span>}
          {dockBadge > 0 && <span className={styles.badge}>{dockBadge}</span>}
          {!expanded && (
            <span className={styles.tooltip} role="tooltip">
              <strong>Side panel</strong>
              <em>Copilot and approvals · Ctrl \</em>
            </span>
          )}
        </button>
        <button
          type="button"
          className={styles.item}
          onClick={onCommandPalette}
          aria-label="Command palette"
        >
          <Command size={20} strokeWidth={1.75} />
          {expanded && <span className={styles.itemLabel}>Commands</span>}
          {!expanded && (
            <span className={styles.tooltip} role="tooltip">
              <strong>Commands</strong>
              <em>Ctrl K</em>
            </span>
          )}
        </button>
        <a href="/docs" className={styles.item} aria-label="Documentation">
          <BookMarked size={20} strokeWidth={1.75} />
          {expanded && <span className={styles.itemLabel}>Docs</span>}
          {!expanded && (
            <span className={styles.tooltip} role="tooltip">
              <strong>Documentation</strong>
              <em>Concepts, API, operations</em>
            </span>
          )}
        </a>
        <button
          type="button"
          className={styles.item}
          onClick={onReset}
          aria-label="Restore sample world"
        >
          <RotateCcw size={20} strokeWidth={1.75} />
          {expanded && <span className={styles.itemLabel}>Restore sample</span>}
          {!expanded && (
            <span className={styles.tooltip} role="tooltip">
              <strong>Restore sample</strong>
              <em>Keeps everything you made</em>
            </span>
          )}
        </button>
      </div>
    </nav>
  );
}
