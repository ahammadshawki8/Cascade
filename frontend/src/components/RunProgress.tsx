"use client";

import { useEffect, useRef, useState } from "react";
import { Minus, X, Activity, Check, Lock } from "lucide-react";
import { DecisionMap, MapModel, Stage } from "./DecisionMap";
import type { StepEvent } from "./IncidentConsole";
import { narrate } from "./narrate";
import styles from "./RunProgress.module.css";

/**
 * The live view of whatever the system is doing, and the only one.
 *
 * Everything about a run in flight lives here — the gate map, the steps as
 * they stream, and any wait the app imposes. Nothing about it is in a tab, so
 * the tabs are free to be about things you *browse* rather than things that
 * are happening, and a run stays visible while you navigate to Policy to watch
 * the consequences.
 *
 * Three states, after the Dynamic Island: a compact pill at rest, a brief
 * sideways expansion to announce something that just happened, and a full
 * panel when you ask for detail. The announcement matters most — a policy
 * cascade or a compile finishing is exactly the kind of event that used to
 * happen silently while the user stared at an unchanged screen.
 */

const GLASS = "blur(22px) saturate(180%)";

const STAGE_LABEL: Record<Stage, string> = {
  search: "Searching memory",
  freshness: "Checking it is still valid",
  preconditions: "Checking it applies here",
  replay: "Replaying the runbook",
  plan: "Planning from scratch",
  execute: "Running the steps",
};

function summarise(model: MapModel, running: boolean, busyLabel?: string | null): string {
  if (busyLabel) return busyLabel;
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
  steps = [],
  announce,
  busyLabel,
  onDismiss,
}: {
  model: MapModel;
  narration: string | null;
  running: boolean;
  steps?: StepEvent[];
  /** A one-off event worth interrupting for. Expands, then settles back. */
  announce?: string | null;
  /** Set while the app is deliberately holding work back. */
  busyLabel?: string | null;
  onDismiss: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [announcing, setAnnouncing] = useState<string | null>(null);
  const seen = useRef<string | null>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  // Announce, then settle. Deliberately does not force the panel open: an
  // interruption that hijacks the whole view is worse than one you can ignore.
  useEffect(() => {
    if (!announce || announce === seen.current) return;
    seen.current = announce;
    setAnnouncing(announce);
    const t = setTimeout(() => setAnnouncing(null), 4200);
    return () => clearTimeout(t);
  }, [announce]);

  useEffect(() => {
    if (streamRef.current) streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [steps.length, expanded]);

  const stage = summarise(model, running, busyLabel);
  const glass = { backdropFilter: GLASS, WebkitBackdropFilter: GLASS };

  if (!expanded) {
    return (
      <button
        className={`${styles.pill} ${announcing ? styles.pillAnnouncing : ""}`}
        style={glass}
        onClick={() => setExpanded(true)}
        aria-label="Show run progress"
      >
        <span className={`${styles.pulse} ${running || busyLabel ? styles.pulseOn : ""}`}>
          {busyLabel ? <Lock size={13} /> : running ? <Activity size={13} /> : <Check size={13} />}
        </span>
        {announcing ? (
          <span className={styles.announce}>{announcing}</span>
        ) : (
          <>
            <span className={styles.pillIncident}>{model.incident}</span>
            <span className={styles.pillStage}>{stage}</span>
            {steps.length > 0 && <span className={styles.pillCount}>{steps.length}</span>}
          </>
        )}
      </button>
    );
  }

  return (
    <div className={styles.window} style={glass} role="dialog" aria-label="Run progress">
      <div className={styles.header}>
        <span className={`${styles.pulse} ${running || busyLabel ? styles.pulseOn : ""}`}>
          {busyLabel ? <Lock size={13} /> : running ? <Activity size={13} /> : <Check size={13} />}
        </span>
        <span className={styles.title}>{model.incident ?? "Run"}</span>
        <span className={styles.stage}>{stage}</span>
        <span className={styles.spacer} />
        <button
          className={styles.iconBtn}
          onClick={() => setExpanded(false)}
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
          disabled={running || Boolean(busyLabel)}
        >
          <X size={14} />
        </button>
      </div>

      {announcing && <div className={styles.banner}>{announcing}</div>}

      <DecisionMap model={model} />

      {narration && <div className={styles.narration}>{narration}</div>}

      {steps.length > 0 && (
        <div className={styles.stream} ref={streamRef}>
          {steps.map((s, i) => {
            const { question, answer } = narrate(s.tool, s.args);
            return (
              <div key={s.id || i} className={styles.step}>
                <span className={styles.stepIndex}>{(i + 1).toString().padStart(2, "0")}</span>
                <span className={styles.stepQ}>{question}</span>
                <span className={styles.stepA}>{answer}</span>
                {s.duration_ms != null && (
                  <span className={styles.stepMs}>{s.duration_ms}ms</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
