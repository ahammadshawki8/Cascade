"use client";

import { useEffect, useRef, useState } from "react";
import {
  Minus,
  X,
  Activity,
  Check,
  Lock,
  ChevronRight,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { DecisionMap, MapModel, Stage } from "./DecisionMap";
import { StepDetail } from "./StepDetail";
import type { Explanation, RelearnState, StepEvent } from "./runTypes";
import { narrate } from "./narrate";
import styles from "./RunProgress.module.css";

/**
 * The live view of whatever the system is doing, and the only one.
 *
 * Everything about a run lives here — the gate map, the steps as they stream,
 * the evidence behind a refusal, and what the run cost. Nothing is in a tab, so
 * the tabs are free to be about things you *browse* rather than things that are
 * happening, and a run stays visible while you navigate to Policy to watch the
 * consequences.
 *
 * A past run opened from History loads into exactly this panel rather than a
 * lesser summary somewhere else. A finished run and a historical one are the
 * same object, so making them look different would only teach a viewer that
 * there are two kinds of explanation.
 *
 * Re-learning is the one thing that gets its own body. The gate map describes
 * how an incident is decided, and a re-learn is not deciding an incident — it
 * is picking a representative one, re-solving it cold, compiling the result and
 * checking the new provenance is not weaker. Drawing the map there was showing
 * a diagram of the wrong process.
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

const RELEARN_STAGE: Record<RelearnState["phase"], string> = {
  queued: "Queued",
  started: "Picking an incident to re-solve",
  solving: "Re-solving it from scratch",
  solved: "Re-solved",
  compiling: "Compiling the replacement",
  done: "Re-learned",
  rejected: "No replacement written",
  deferred: "Nothing to re-solve against",
  failed: "Re-learn failed",
};

function summarise(
  model: MapModel,
  running: boolean,
  relearn?: RelearnState | null,
  busyLabel?: string | null
): string {
  if (relearn) return RELEARN_STAGE[relearn.phase];
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
  mode,
  explanation,
  relearn,
  announce,
  busyLabel,
  compiling = false,
  openSignal = 0,
  reviewing = false,
  onOpenPolicy,
  onDismiss,
}: {
  model: MapModel;
  narration: string | null;
  running: boolean;
  steps?: StepEvent[];
  /** The engine's live verdict, known from the first status event. */
  mode?: "explore" | "guided";
  /** The verdict, once the run has one. Drives the evidence and the cost line. */
  explanation?: Explanation | null;
  /** Set while a runbook is being re-learned; replaces the run body entirely. */
  relearn?: RelearnState | null;
  /** A one-off event worth interrupting for. Expands, then settles back. */
  announce?: string | null;
  /** Set while the app is deliberately holding work back. */
  busyLabel?: string | null;
  /** A runbook is being compiled from this run; it has not landed yet. */
  compiling?: boolean;
  /** Bumped by the parent to open the panel — a past run, or a re-learn. */
  openSignal?: number;
  /** This is a run from history, not the one happening now. */
  reviewing?: boolean;
  onOpenPolicy?: (ruleKey: string) => void;
  onDismiss: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [announcing, setAnnouncing] = useState<string | null>(null);
  const [openStep, setOpenStep] = useState<string | null>(null);
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

  // The parent asks for the panel only when the user has asked for detail —
  // opening a run from History, or pressing Re-learn. Both are direct requests
  // to see something, which is a different thing from an announcement.
  //
  // Adjusted during render rather than in an effect: an effect would paint the
  // collapsed pill first and expand on the following frame, which reads as a
  // flicker on the one interaction that is supposed to feel immediate.
  const [seenSignal, setSeenSignal] = useState(openSignal);
  if (openSignal !== seenSignal) {
    setSeenSignal(openSignal);
    if (openSignal > 0) setExpanded(true);
  }

  useEffect(() => {
    if (streamRef.current) streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [steps.length, expanded]);

  const stage = summarise(model, running, relearn, busyLabel);
  const glass = { backdropFilter: GLASS, WebkitBackdropFilter: GLASS };
  const title = relearn
    ? relearn.name
      ? `${relearn.name} v${relearn.version ?? ""}`.trim()
      : "Re-learning"
    : (model.incident ?? "Run");

  const busy = running || Boolean(busyLabel);
  const icon = relearn ? (
    <RefreshCw size={13} />
  ) : busyLabel ? (
    <Lock size={13} />
  ) : running ? (
    <Activity size={13} />
  ) : (
    <Check size={13} />
  );

  if (!expanded) {
    return (
      <button
        className={`${styles.pill} ${announcing ? styles.pillAnnouncing : ""}`}
        style={glass}
        onClick={() => setExpanded(true)}
        aria-label="Show run progress"
      >
        <span className={`${styles.pulse} ${busy ? styles.pulseOn : ""}`}>{icon}</span>
        {announcing ? (
          <span className={styles.announce}>{announcing}</span>
        ) : (
          <>
            <span className={styles.pillIncident}>{title}</span>
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
        <span className={`${styles.pulse} ${busy ? styles.pulseOn : ""}`}>{icon}</span>
        <span className={styles.title}>{title}</span>
        <span className={styles.stage}>{stage}</span>
        {reviewing && !relearn && <span className={styles.pastTag}>from history</span>}
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
          disabled={busy}
        >
          <X size={14} />
        </button>
      </div>

      {announcing && <div className={styles.banner}>{announcing}</div>}

      <div className={styles.body}>
        {relearn ? (
          <RelearnBody relearn={relearn} onOpenPolicy={onOpenPolicy} />
        ) : (
          <>
            <DecisionMap model={model} />
            {narration && <div className={styles.narration}>{narration}</div>}
            <Evidence explanation={explanation} onOpenPolicy={onOpenPolicy} />
          </>
        )}

        {steps.length > 0 && (
          <div className={styles.stream} ref={streamRef}>
            {relearn && (
              <div className={styles.streamTitle}>
                What the re-solve is doing, step by step
              </div>
            )}
            {steps.map((s, i) => {
              const { question, answer } = narrate(s.tool, s.args, s.output);
              const key = s.id || String(i);
              const open = openStep === key;
              return (
                <div key={key} className={styles.stepWrap}>
                  <button
                    className={`${styles.step} ${open ? styles.stepOpen : ""}`}
                    onClick={() => setOpenStep(open ? null : key)}
                    aria-expanded={open}
                  >
                    <span className={styles.stepChevron}>
                      <ChevronRight size={12} />
                    </span>
                    <span className={styles.stepIndex}>
                      {(i + 1).toString().padStart(2, "0")}
                    </span>
                    <span className={styles.stepQ}>{question}</span>
                    <span className={styles.stepA}>{answer}</span>
                    {s.duration_ms != null && (
                      <span className={styles.stepMs}>{s.duration_ms}ms</span>
                    )}
                  </button>
                  {open && <StepDetail tool={s.tool} args={s.args} output={s.output} />}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Cost
        explanation={explanation}
        steps={steps}
        mode={mode}
        running={running}
        relearn={relearn}
        compiling={compiling}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * The proof behind a refusal.
 *
 * "Stale" is a claim; the version mismatch is the evidence, and it is the one
 * thing a viewer should be able to go and check in the Policy panel themselves.
 */
function Evidence({
  explanation,
  onOpenPolicy,
}: {
  explanation?: Explanation | null;
  onOpenPolicy?: (ruleKey: string) => void;
}) {
  const stale = explanation?.decision.stale_deps ?? [];
  const failed = explanation?.decision.failed_preconditions ?? [];
  if (stale.length === 0 && failed.length === 0) return null;

  return (
    <div className={styles.evidence}>
      {stale.length > 0 && (
        <>
          <div className={styles.evidenceTitle}>
            Rules that moved since this runbook was compiled
          </div>
          {stale.map((d) => (
            <button
              key={d.rule_key}
              className={styles.staleRow}
              onClick={() => onOpenPolicy?.(d.rule_key)}
            >
              <span className={styles.ruleKey}>{d.rule_key}</span>
              <span className={styles.versionOld}>compiled against v{d.compiled_against}</span>
              <ArrowRight size={12} />
              <span className={styles.versionNew}>now at v{d.head}</span>
            </button>
          ))}
        </>
      )}

      {failed.length > 0 && (
        <>
          <div className={styles.evidenceTitle}>Preconditions that did not hold</div>
          {failed.map((p, i) => (
            <div key={i} className={styles.failedRow}>
              {p}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

const RELEARN_STEPS: { label: string; note: string }[] = [
  {
    label: "Find an incident this runbook covers",
    note: "One the current policy actually permits acting on, so the re-solve exercises the new rules rather than the old ones.",
  },
  {
    label: "Solve it from scratch",
    note: "A full cold run with the planner in the loop. The old steps are not patched, because the new policy may permit a different shape of fix entirely.",
  },
  {
    label: "Compile the result, but only if it is not weaker",
    note: "The rule versions the run consulted become the replacement's provenance. A successor citing fewer of the rules that moved would be less able to go stale than the version it replaces, so it is refused.",
  },
];

/**
 * Which rows are finished, which one is working, and which one stopped.
 *
 * Written as a table rather than derived from a phase ordering because the
 * three ways a re-learn ends without a new version each stop at a different
 * row, and that is exactly the thing a viewer needs to see.
 */
function relearnProgress(phase: RelearnState["phase"]): {
  done: number;
  active: number;
  failed: number;
} {
  switch (phase) {
    case "queued":
    case "started":
      return { done: 0, active: 0, failed: -1 };
    case "deferred":
      return { done: 0, active: -1, failed: 0 };
    case "solving":
      return { done: 1, active: 1, failed: -1 };
    case "failed":
      return { done: 1, active: -1, failed: 1 };
    case "solved":
    case "compiling":
      return { done: 2, active: 2, failed: -1 };
    case "rejected":
      return { done: 2, active: -1, failed: 2 };
    case "done":
      return { done: 3, active: -1, failed: -1 };
  }
}

function RelearnBody({
  relearn,
  onOpenPolicy,
}: {
  relearn: RelearnState;
  onOpenPolicy?: (ruleKey: string) => void;
}) {
  const progress = relearnProgress(relearn.phase);

  return (
    <div className={styles.relearn}>
      <div className={styles.relearnLead}>
        This runbook is quarantined because policy moved underneath it. Re-learning
        does not edit it: it works the problem again under the current rules and
        writes the answer as a new version.
      </div>

      {relearn.staleRules && relearn.staleRules.length > 0 && (
        <div className={styles.evidence}>
          <div className={styles.evidenceTitle}>Why it needs re-learning</div>
          {relearn.staleRules.map((d) => (
            <button
              key={d.rule_key}
              className={styles.staleRow}
              onClick={() => onOpenPolicy?.(d.rule_key)}
            >
              <span className={styles.ruleKey}>{d.rule_key}</span>
              <span className={styles.versionOld}>compiled against v{d.compiled_against}</span>
              <ArrowRight size={12} />
              <span className={styles.versionNew}>now at v{d.head}</span>
            </button>
          ))}
        </div>
      )}

      <div className={styles.phases}>
        {RELEARN_STEPS.map((s, i) => {
          const done = i < progress.done;
          const active = i === progress.active;
          const failed = i === progress.failed;
          return (
            <div
              key={s.label}
              className={`${styles.phase} ${done ? styles.phaseDone : ""} ${
                active ? styles.phaseActive : ""
              } ${failed ? styles.phaseFailed : ""}`}
            >
              <span className={styles.phaseMark}>
                {done ? (
                  <Check size={12} />
                ) : failed ? (
                  <X size={12} />
                ) : active ? (
                  <Activity size={12} />
                ) : (
                  i + 1
                )}
              </span>
              <span className={styles.phaseLabel}>{s.label}</span>
              <span className={styles.phaseNote}>{s.note}</span>
              {i === 1 && relearn.taskText && (
                <span className={styles.phasePick}>{relearn.taskText}</span>
              )}
            </div>
          );
        })}
      </div>

      {/* The outbox is swept on a timer, so this first phase can sit still for
          a moment. Saying why turns a stalled-looking spinner into the design
          decision it actually is. */}
      {relearn.phase === "queued" && (
        <div className={styles.relearnWait}>
          Queued in the transactional outbox. A worker claims it on the next sweep,
          which is what keeps this identical whether you pressed the button or a
          policy change queued it for you.
        </div>
      )}

      {relearn.phase === "done" && (
        <div className={styles.relearnGood}>
          {relearn.newVersion != null ? (
            <>
              Re-learned as{" "}
              <b>
                {relearn.newName ?? relearn.name} v{relearn.newVersion}
              </b>
              . The old version is marked invalidated and kept, so the lineage stays
              readable.
            </>
          ) : (
            "A newer version of this runbook already exists, so there was nothing left to re-learn."
          )}
        </div>
      )}

      {["rejected", "deferred", "failed"].includes(relearn.phase) && (
        <div className={styles.relearnStop}>
          <b>No new version was written.</b> {relearn.reason}
          <div className={styles.relearnStopNote}>
            The runbook stays quarantined, which is the honest state: nothing was
            proven, so nothing is trusted. The freshness gate already stops it
            running, so no incident is at risk.
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * What the run cost, in the only currency that matters here: thinking.
 *
 * A guided run replays a procedure the system already worked out, so every one
 * of its steps is a planner call that did not happen. That number is the whole
 * claim of the project, and it was previously only visible as an aggregate
 * speedup somewhere else in the app.
 */
function Cost({
  explanation,
  steps,
  mode: liveMode,
  running,
  relearn,
  compiling,
}: {
  explanation?: Explanation | null;
  steps: StepEvent[];
  mode?: "explore" | "guided";
  running: boolean;
  relearn?: RelearnState | null;
  compiling?: boolean;
}) {
  if (relearn) {
    return (
      <div className={styles.cost}>
        <span className={styles.costText}>
          A re-learn deliberately pays full cold-path cost once, so that every run
          after it can skip the planner again.
        </span>
      </div>
    );
  }

  const count = explanation?.episode?.steps ?? steps.length;
  if (!count) return null;

  // The engine settles this before the first step and says so on the status
  // event, so there is never a need to guess. Guessing was wrong in the one
  // direction that matters: a reuse briefly claimed it had planned everything.
  const mode = explanation?.mode ?? liveMode ?? null;
  const guided = mode === "guided";

  if (running) {
    return (
      <div className={styles.cost}>
        <span className={styles.costBig}>{steps.length}</span>
        <span className={styles.costText}>
          {mode === null
            ? "steps so far, while it works out whether it has anything to reuse"
            : guided
              ? "steps replayed so far, with no planner call behind any of them"
              : "steps so far, each one planned by the model"}
        </span>
      </div>
    );
  }

  // Finished, but the verdict has not come back yet. Saying nothing for a
  // moment beats naming the wrong path.
  if (!mode) return null;

  const c = explanation?.comparison;
  const avoided =
    c && c.cold_avg_tokens != null && c.guided_avg_tokens != null
      ? c.cold_avg_tokens - c.guided_avg_tokens
      : null;

  if (guided) {
    return (
      <div className={styles.cost}>
        <span className={styles.costBig}>{count}</span>
        <span className={styles.costText}>
          of {count} steps skipped thinking — the planner was not called once.
          {avoided != null && avoided > 0 && (
            <>
              {" "}
              About <b>{avoided.toLocaleString()}</b> planner tokens avoided against the
              average cold run
              {c && c.cold_runs > 0 ? ` of ${c.cold_runs}` : ""}.
            </>
          )}
        </span>
      </div>
    );
  }

  return (
    <div className={styles.cost}>
      <span className={styles.costBig}>0</span>
      <span className={styles.costText}>
        of {count} steps skipped thinking — this run had nothing to reuse, so the model
        planned every one of them.
        {explanation?.learned ? (
          <>
            {" "}
            It was saved as <b>{explanation.learned.name} v{explanation.learned.version}</b>,
            so the next matching incident skips all {count}.
          </>
        ) : compiling ? (
          " It is being compiled into a runbook now, so the next matching incident will not have to."
        ) : (
          " Nothing was saved from it, so the next one starts cold again."
        )}
      </span>
    </div>
  );
}
