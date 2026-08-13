"use client";

import { useEffect, useState } from "react";
import styles from "./RunHistory.module.css";

/**
 * Everything that has already run.
 *
 * A list and nothing else: picking a run loads it into the floating window,
 * which is where every explanation lives. The detail used to render underneath
 * this list, which meant the same run was described in two places depending on
 * whether it had just finished or was being looked up afterwards.
 */

interface Run {
  task_id: string;
  input: string;
  status: string;
  mode: string | null;
  result: string | null;
  created_at?: string;
}

const OUTCOME_CLASS: Record<string, string> = {
  remediated: "ok",
  escalated: "escalated",
  failed: "bad",
  interrupted: "warn",
};

export function RunHistory({
  apiBase,
  refreshKey,
  selectedId,
  locked = false,
  onSelect,
}: {
  apiBase: string;
  refreshKey: number;
  selectedId: string | null;
  /** Work is in flight; opening a past run would displace it in the window. */
  locked?: boolean;
  onSelect: (taskId: string) => void;
}) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiBase}/tasks?limit=25`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setRuns(data.tasks ?? []);
      } catch {
        /* empty state below is the honest fallback */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, refreshKey]);

  const done = runs.filter((r) => r.status !== "queued" && r.status !== "running");

  return (
    <div className={styles.history}>
      <div className={styles.lead}>
        Every run, and why it went the way it did. Pick one and it opens in the
        floating window, with each step you can click into.
      </div>

      <div className={styles.list}>
        {loading && <div className={styles.empty}>Loading…</div>}
        {!loading && done.length === 0 && (
          <div className={styles.empty}>
            No runs yet. Fix an incident from the Inbox and it will appear here.
          </div>
        )}
        {done.map((r) => {
          const outcome = r.result ?? r.status;
          return (
            <button
              key={r.task_id}
              className={`${styles.row} ${
                selectedId === r.task_id ? styles.rowActive : ""
              }`}
              disabled={locked}
              title={locked ? "Waiting for the current work to finish" : undefined}
              onClick={() => onSelect(r.task_id)}
            >
              <span className={styles.input}>{r.input}</span>
              <span
                className={`${styles.mode} ${
                  r.mode === "guided" ? styles.modeGuided : styles.modeCold
                }`}
              >
                {r.mode === "guided" ? "reused" : "from scratch"}
              </span>
              <span
                className={`${styles.outcome} ${
                  styles[OUTCOME_CLASS[outcome] ?? "warn"]
                }`}
              >
                {outcome}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
