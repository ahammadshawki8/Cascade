"use client";

import { X } from "lucide-react";
import styles from "./Shortcuts.module.css";

/**
 * The keyboard map, on `?`.
 *
 * Ctrl-K and Ctrl-\ both existed and were invisible, which makes them features
 * only the person who wrote them can use. Every app people already know puts
 * this behind a question mark, so this one does too.
 */

const GROUPS: { title: string; keys: [string, string][] }[] = [
  {
    title: "Getting around",
    keys: [
      ["Ctrl K", "Command palette: go anywhere, run anything"],
      ["Ctrl \\", "Side panel: Copilot and approvals"],
      ["?", "This list"],
      ["Esc", "Close whatever is open"],
    ],
  },
  {
    title: "Doing things",
    keys: [
      ["G then W", "Work: run an incident, review past runs"],
      ["G then P", "Procedures: the runbook library"],
      ["G then R", "Policy: the rules"],
      ["G then C", "Connections: Slack, and agent keys"],
      ["G then S", "System: the machinery, read live"],
    ],
  },
];

export function Shortcuts({ onClose }: { onClose: () => void }) {
  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.sheet} onClick={(e) => e.stopPropagation()}>
        <header className={styles.head}>
          <h2 className={styles.h2}>Keyboard shortcuts</h2>
          <span className={styles.spacer} />
          <button className={styles.icon} onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </header>

        <div className={styles.body}>
          {GROUPS.map((group) => (
            <div key={group.title} className={styles.group}>
              <div className={styles.groupTitle}>{group.title}</div>
              {group.keys.map(([combo, what]) => (
                <div key={combo} className={styles.row}>
                  <kbd className={styles.kbd}>{combo}</kbd>
                  <span className={styles.what}>{what}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
