"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./CommandPalette.module.css";

export interface Command {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void | Promise<void>;
}

interface Props {
  open: boolean;
  commands: Command[];
  onClose: () => void;
}

/**
 * Ctrl/Cmd-K command palette.
 *
 * Every action in the app is reachable from here, so an operator never has to
 * remember which panel a thing lives in — the same reason editors and Linear
 * and Slack all converged on this. Matching is a simple subsequence test:
 * "rinc" finds "Run incident INC-1001".
 */
export function CommandPalette({ open, commands, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      // Focus after paint, or the input isn't mounted yet.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) =>
      isSubsequence(needle, `${command.group} ${command.label}`.toLowerCase())
    );
  }, [commands, query]);

  useEffect(() => {
    setIndex((current) => Math.min(current, Math.max(0, matches.length - 1)));
  }, [matches.length]);

  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${index}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [index]);

  if (!open) return null;

  const runAt = (position: number) => {
    const command = matches[position];
    if (!command) return;
    onClose();
    void command.run();
  };

  let lastGroup = "";

  return (
    <div className={styles.overlay} onMouseDown={onClose}>
      <div
        className={styles.palette}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className={styles.input}
          value={query}
          placeholder="Type a command…"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setIndex((i) => Math.min(i + 1, matches.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIndex((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              runAt(index);
            }
          }}
        />

        <div className={styles.list} ref={listRef}>
          {matches.length === 0 && (
            <div className={styles.empty}>No matching commands.</div>
          )}
          {matches.map((command, position) => {
            const showGroup = command.group !== lastGroup;
            lastGroup = command.group;
            return (
              <div key={command.id}>
                {showGroup && <div className={styles.group}>{command.group}</div>}
                <button
                  type="button"
                  data-index={position}
                  className={`${styles.row} ${position === index ? styles.rowActive : ""}`}
                  onMouseEnter={() => setIndex(position)}
                  onClick={() => runAt(position)}
                >
                  <span className={styles.label}>{command.label}</span>
                  {command.hint && <span className={styles.hint}>{command.hint}</span>}
                </button>
              </div>
            );
          })}
        </div>

        <div className={styles.footer}>
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> run</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}

/** "rinc" matches "Run incident" — order matters, adjacency doesn't. */
function isSubsequence(needle: string, haystack: string): boolean {
  let cursor = 0;
  for (const character of haystack) {
    if (character === needle[cursor]) cursor++;
    if (cursor === needle.length) return true;
  }
  return cursor === needle.length;
}
