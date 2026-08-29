"use client";

import { FlaskConical } from "lucide-react";
import styles from "./EvidencePanel.module.css";
import raw from "../data/eval-results.json";

/**
 * The measured comparison, rendered from a committed artifact.
 *
 * WHY THIS IS NOT LIVE
 * --------------------
 * A run of this evaluation is 48 model calls across three arms, and re-running
 * it whenever somebody opens a tab would be both expensive and dishonest: the
 * number on screen would drift from the number in the changelog every time a
 * provider had a slow afternoon. So the harness writes a dated artifact, the
 * artifact is committed, and this reads it. The command that regenerates it is
 * printed below, which is the part that makes it checkable rather than merely
 * stated.
 *
 * WHAT IT IS SHOWING
 * ------------------
 * The same incidents decided twice, under two policy states. Phase 1 is the
 * policy the runbooks were learned under and is not the interesting half. Phase
 * 2 is the same world with one rule tightened, and the question is which arms
 * notice. An arm holding a remembered procedure has to work out that yesterday's
 * correct answer is today's wrong one, and the only thing that can tell it so is
 * a record of what the procedure was derived from.
 */

const ARMS = ["single_prompt", "naive_cache", "cascade"] as const;
type Arm = (typeof ARMS)[number];

const ARM_LABEL: Record<Arm, string> = {
  single_prompt: "Direct prompt",
  naive_cache: "Cached runbook",
  cascade: "Cascade",
};

const ARM_NOTE: Record<Arm, string> = {
  single_prompt: "Re-reasons from policy every time. No memory to go stale.",
  naive_cache: "Stores what worked and replays it. No provenance.",
  cascade: "Pins each procedure to the rule versions it was derived from.",
};

interface ArmStats {
  cases: number;
  correct_pct: number;
  unsafe_actions: number;
  median_latency_ms: number;
  total_tokens: number;
}

interface PhaseStats {
  correct_pct: number;
  unsafe_actions: number;
}

interface Outcome {
  arm: string;
  phase: number;
  incident_id: string;
  expected: string;
  actual: string;
  correct: boolean;
  unsafe: boolean;
  mode: string | null;
  rationale: string;
}

interface Results {
  started_at: string | null;
  api: string | null;
  model_note: string;
  summary: {
    by_arm: Partial<Record<Arm, ArmStats>>;
    by_phase: Record<string, Partial<Record<Arm, PhaseStats>>>;
  };
  notes: string[];
  outcomes: Outcome[];
}

const results = raw as Results;

const COMMAND =
  "python -m eval.run_eval --api https://<host> --admin-token <token>";

export function EvidencePanel() {
  const { summary, outcomes, notes, started_at } = results;
  const hasRun = outcomes.length > 0;

  if (!hasRun) {
    return (
      <div className={styles.panel}>
        <div className={styles.empty}>
          <FlaskConical size={26} className={styles.emptyIcon} />
          <h2>No evaluation recorded yet</h2>
          <p>
            This view renders a committed result artifact, not a live query. It
            fills in once the harness has been run against a stack and the
            artifact is checked in.
          </p>
          <p className={styles.emptyMethod}>
            Twelve incidents, decided twice: once under the policy the runbooks
            were learned under, then again with the rollback window tightened
            from 24h to 4h. Same cases for all three arms, same model.
          </p>
          <code className={styles.command}>{COMMAND}</code>
        </div>
      </div>
    );
  }

  const phases = [1, 2];
  const incidents = Array.from(
    new Set(outcomes.map((o) => o.incident_id))
  ).sort();

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>Measured against a baseline</h2>
          <p className={styles.sub}>
            Recorded {started_at?.replace("T", " ").replace("+00:00", " UTC")}.
            Same incidents, same model, three arms.
          </p>
        </div>
        <code className={styles.commandInline}>{COMMAND}</code>
      </header>

      {/* The headline. Correctness first and deliberately: for someone on
          call, success is not speed, it is not running the wrong procedure. */}
      <section className={styles.arms}>
        {ARMS.map((arm) => {
          const s = summary.by_arm[arm];
          if (!s) return null;
          const isCascade = arm === "cascade";
          return (
            <div
              key={arm}
              className={`${styles.arm} ${isCascade ? styles.armPrimary : ""}`}
            >
              <div className={styles.armName}>{ARM_LABEL[arm]}</div>
              <div className={styles.armScore}>
                {s.correct_pct}
                <span className={styles.armPct}>%</span>
              </div>
              <div className={styles.armScoreLabel}>policy-correct</div>
              <div
                className={`${styles.armUnsafe} ${
                  s.unsafe_actions > 0 ? styles.armUnsafeBad : ""
                }`}
              >
                {s.unsafe_actions === 0
                  ? "no unsafe actions"
                  : `${s.unsafe_actions} unsafe action${
                      s.unsafe_actions === 1 ? "" : "s"
                    }`}
              </div>
              <div className={styles.armMeta}>
                {s.median_latency_ms.toLocaleString()} ms median ·{" "}
                {s.total_tokens.toLocaleString()} tokens
              </div>
              <div className={styles.armNote}>{ARM_NOTE[arm]}</div>
            </div>
          );
        })}
      </section>

      {/* The argument. Phase 1 says everyone can read a rule. Phase 2 says
          what happens when the rule moves underneath a stored procedure. */}
      <section className={styles.phases}>
        <h3 className={styles.sectionTitle}>What happens when a rule moves</h3>
        <table className={styles.phaseTable}>
          <thead>
            <tr>
              <th />
              {ARMS.map((a) => (
                <th key={a}>{ARM_LABEL[a]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {phases.map((p) => {
              const block = summary.by_phase[`phase${p}`] ?? {};
              return (
                <tr key={p}>
                  <th scope="row" className={styles.phaseLabel}>
                    <span className={styles.phaseNum}>Phase {p}</span>
                    <span className={styles.phaseWhat}>
                      {p === 1
                        ? "rollback window 24h — as learned"
                        : "rollback window 4h — tightened"}
                    </span>
                  </th>
                  {ARMS.map((a) => {
                    const s = block[a];
                    if (!s) return <td key={a}>—</td>;
                    return (
                      <td key={a}>
                        <span
                          className={`${styles.cellPct} ${
                            s.correct_pct === 100 ? styles.cellGood : styles.cellBad
                          }`}
                        >
                          {s.correct_pct}%
                        </span>
                        {s.unsafe_actions > 0 && (
                          <span className={styles.cellUnsafe}>
                            {s.unsafe_actions} unsafe
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className={styles.cases}>
        <h3 className={styles.sectionTitle}>Every case</h3>
        <table className={styles.caseTable}>
          <thead>
            <tr>
              <th>Phase</th>
              <th>Incident</th>
              <th>Policy requires</th>
              {ARMS.map((a) => (
                <th key={a}>{ARM_LABEL[a]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {phases.flatMap((p) =>
              incidents.map((inc) => {
                const row = outcomes.filter(
                  (o) => o.phase === p && o.incident_id === inc
                );
                if (row.length === 0) return null;
                const expected = row[0].expected;
                return (
                  <tr key={`${p}-${inc}`}>
                    <td className={styles.dim}>{p}</td>
                    <td className={styles.mono}>{inc}</td>
                    <td className={styles.dim}>{expected}</td>
                    {ARMS.map((a) => {
                      const hit = row.find((o) => o.arm === a);
                      if (!hit) return <td key={a}>—</td>;
                      return (
                        <td key={a}>
                          <span
                            className={
                              hit.unsafe
                                ? styles.tagUnsafe
                                : hit.correct
                                ? styles.tagOk
                                : styles.tagWrong
                            }
                            title={hit.rationale}
                          >
                            {hit.actual}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>

      {notes.length > 0 && (
        <section className={styles.notes}>
          <h3 className={styles.sectionTitle}>Run notes</h3>
          <ul>
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </section>
      )}

      <p className={styles.fairness}>{results.model_note}</p>
    </div>
  );
}
