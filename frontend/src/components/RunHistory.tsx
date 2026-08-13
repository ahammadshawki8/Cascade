"use client";

import { useEffect, useState } from "react";
import { DecisionPanel } from "./DecisionPanel";
import styles from "./RunHistory.module.css";

/**
 * Everything that has already run, and why it went the way it did.
 *
 * Live progress belongs to the floating island; this is the other half of that
 * split. Explanations used to be pinned to whichever run happened last, so a
 * second run destroyed the evidence from the first — exactly when a reviewer
 * wants to compare a cold run against the reuse that followed it.
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
  onSelect,
  onOpenPolicy,
}: {
  apiBase: string;
  refreshKey: number;
  selectedId: string | null;
  onSelect: (taskId: string) => void;
  onOpenPolicy?: (ruleKey: string) => void;
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
      <div className={styles.list}>
        {loading && <div className={styles.empty}>Loading…</div>}
        {!loading && done.length === 0 && (
          <div className={styles.empty}>
            No runs yet. Fix an incident from the Inbox and it will appear here,
            with the reason it went the way it did.
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

      <div className={styles.detail}>
        {selectedId ? (
          <DecisionPanel apiBase={apiBase} taskId={selectedId} onOpenPolicy={onOpenPolicy} />
        ) : (
          <div className={styles.empty}>
            Pick a run to see which gate decided it, and on what evidence.
          </div>
        )}
      </div>
    </div>
  );
}
