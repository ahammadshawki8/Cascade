"use client";

import { useEffect, useState } from "react";
import { Minus, X, Activity } from "lucide-react";
import { DecisionMap, MapModel, Stage } from "./DecisionMap";
import styles from "./RunProgress.module.css";

/**
 * The decision map, floating over the app instead of living in a tab.
 *
 * In the Run tab it competed with the step stream for the same vertical space
 * and vanished the moment you looked at anything else — so the one view that
 * shows *where the agent is* was invisible exactly when you navigated to
 * Policy or Runbooks to see the consequences. Floating, it follows you.
 *
 * Minimised it collapses to a pill that still reports the current stage, so
 * the run never becomes invisible; it only becomes small.
 */

const STAGE_LABEL: Record<Stage, string> = {
  search: "Searching memory",
  freshness: "Checking the runbook is still valid",
  preconditions: "Checking it applies here",
  replay: "Replaying the runbook",
  plan: "Planning from scratch",
  execute: "Running the steps",
};

/** One short line for the collapsed pill. */
function summarise(model: MapModel, running: boolean): string {
  if (!running && model.outcome) return `Done — ${model.outcome}`;
  if (model.current) return STAGE_LABEL[model.current];

  const failed = (["search", "freshness", "preconditions"] as Stage[]).find(
    (s) => model.states[s] === "fail"
  );
  if (failed) return `Refused at ${STAGE_LABEL[failed].toLowerCase()}`;
  return running ? "Working…" : "Ready";
}

export function RunProgress({
  model,
  narration,
  running,
  onDismiss,
}: {
  model: MapModel;
  narration: string | null;
  running: boolean;
  onDismiss: () => void;
}) {
  const [minimized, setMinimized] = useState(false);

  // A new run re-opens the window: the user just asked for this, so hiding it
  // because they minimised the previous one would be the wrong memory to keep.
  useEffect(() => {
    if (running) setMinimized(false);
  }, [running, model.incident]);

  if (minimized) {
    return (
      <button
        className={styles.pill}
        onClick={() => setMinimized(false)}
        aria-label="Show run progress"
      >
        <span className={`${styles.pulse} ${running ? styles.pulseOn : ""}`}>
          <Activity size={13} />
        </span>
        <span className={styles.pillIncident}>{model.incident}</span>
        <span className={styles.pillStage}>{summarise(model, running)}</span>
      </button>
    );
  }

  return (
    <div className={styles.window} role="dialog" aria-label="Run progress">
      <div className={styles.header}>
        <span className={`${styles.pulse} ${running ? styles.pulseOn : ""}`}>
          <Activity size={13} />
        </span>
        <span className={styles.title}>{model.incident ?? "Run"}</span>
        <span className={styles.stage}>{summarise(model, running)}</span>
        <span className={styles.spacer} />
        <button
          className={styles.iconBtn}
          onClick={() => setMinimized(true)}
          aria-label="Minimise"
          title="Minimise"
        >
          <Minus size={14} />
        </button>
        <button
          className={styles.iconBtn}
          onClick={onDismiss}
          aria-label="Close"
          title="Close"
          disabled={running}
        >
          <X size={14} />
        </button>
      </div>

      <DecisionMap model={model} />

      {narration && <div className={styles.narration}>{narration}</div>}
    </div>
  );
}
