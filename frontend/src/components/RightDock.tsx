"use client";

import { useEffect, useState } from "react";
import { Sparkles, ShieldCheck, X } from "lucide-react";
import styles from "./RightDock.module.css";

export type DockTab = "copilot" | "approvals";

interface Props {
  open: boolean;
  tab: DockTab;
  approvalCount: number;
  /** Which panels are installed. A tab for an absent one would be a dead end. */
  available: DockTab[];
  onTab: (tab: DockTab) => void;
  onClose: () => void;
  children: React.ReactNode;
}

const WIDTH_KEY = "cascade_dock_width";
const MIN = 320;
const MAX = 640;

/**
 * The side panel, in the VS Code sense.
 *
 * Copilot and Approvals were destinations, which was wrong for both. Asking the
 * Copilot a question navigated you away from the thing that prompted the
 * question, and an approval is something you deal with *while* watching a run,
 * not instead of watching it. Neither is a place; both are things you consult.
 *
 * Draggable rather than fixed because the Copilot returns SQL and a table, and
 * a width that suits a two-line answer does not suit a six-column result.
 */
export function RightDock({
  open,
  tab,
  approvalCount,
  available,
  onTab,
  onClose,
  children,
}: Props) {
  const [width, setWidth] = useState(400);
  const [dragging, setDragging] = useState(false);

  // localStorage is unavailable during SSR, so the stored width can only be
  // read after mount. Starting from the default and correcting avoids a
  // hydration mismatch.
  useEffect(() => {
    const stored = Number(window.localStorage.getItem(WIDTH_KEY));
    if (stored >= MIN && stored <= MAX) setWidth(stored);
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (e: MouseEvent) => {
      // The dock is anchored right, so its width is the distance from the
      // pointer to the viewport edge.
      const next = Math.min(MAX, Math.max(MIN, window.innerWidth - e.clientX));
      setWidth(next);
    };
    const onUp = () => {
      setDragging(false);
      setWidth((w) => {
        window.localStorage.setItem(WIDTH_KEY, String(w));
        return w;
      });
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    // Without this the drag selects text across the whole page.
    document.body.style.userSelect = "none";
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
    };
  }, [dragging]);

  if (!open) return null;

  return (
    <aside className={styles.dock} style={{ width }} data-tour="dock">
      <div
        className={`${styles.grip} ${dragging ? styles.gripOn : ""}`}
        onMouseDown={() => setDragging(true)}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
      />

      {/* Only tabs for panels that are installed. Both are extensions now, so
          a dock that always showed two would offer a tab leading nowhere. */}
      <div className={styles.head}>
        {available.includes("copilot") && (
          <button
            className={`${styles.tab} ${tab === "copilot" ? styles.tabOn : ""}`}
            onClick={() => onTab("copilot")}
          >
            <Sparkles size={13} strokeWidth={1.9} />
            Copilot
          </button>
        )}
        {available.includes("approvals") && (
          <button
            className={`${styles.tab} ${tab === "approvals" ? styles.tabOn : ""}`}
            onClick={() => onTab("approvals")}
            data-tour="dock-approvals"
          >
            <ShieldCheck size={13} strokeWidth={1.9} />
            Approvals
            {approvalCount > 0 && <span className={styles.count}>{approvalCount}</span>}
          </button>
        )}
        <span className={styles.spacer} />
        <button className={styles.close} onClick={onClose} aria-label="Close panel">
          <X size={14} strokeWidth={2} />
        </button>
      </div>

      <div className={styles.body}>{children}</div>
    </aside>
  );
}
