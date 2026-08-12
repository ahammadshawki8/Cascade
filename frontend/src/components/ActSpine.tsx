"use client";

import { Check } from "lucide-react";
import styles from "./ActSpine.module.css";

/**
 * The demo is a three-act story, so the app should be too.
 *
 * The old tour strip listed three tasks of equal weight and left every panel
 * visible at all times, so a first-time viewer faced six destinations and no
 * reason to prefer any of them. This makes the current act the organising
 * idea: it says what is happening, why it matters, and what to do next, and
 * the shell hides whatever this act does not need.
 *
 * Acts advance from observed state, never from clicking the spine. A viewer
 * who has not yet taught it anything cannot be "in" act two, and letting them
 * skip there would show an empty screen with no explanation.
 */

export type Act = 1 | 2 | 3;

export interface ActState {
  act: Act;
  /** Acts fully behind us, drawn as done. */
  completed: Act[];
}

const ACTS: {
  n: Act;
  title: string;
  goal: string;
  next: string;
}[] = [
  {
    n: 1,
    title: "Teach it",
    goal: "It has never seen this problem, so it reasons from scratch. Slow and expensive.",
    next: "Pick any incident from the inbox and press Fix it.",
  },
  {
    n: 2,
    title: "Watch it reuse",
    goal: "Same kind of problem. This time it replays what it learned, with no planner at all.",
    next: "Fix a second bad deploy and compare the time.",
  },
  {
    n: 3,
    title: "Change the rules",
    goal: "Its runbook was built on a policy. Change that policy and the runbook must stop being trusted.",
    next: "Open Policy, tighten the rollback window, and commit.",
  },
];

export function ActSpine({
  state,
  onGoToPolicy,
}: {
  state: ActState;
  onGoToPolicy: () => void;
}) {
  const current = ACTS.find((a) => a.n === state.act)!;

  return (
    <div className={styles.spine}>
      <div className={styles.track}>
        {ACTS.map((a, i) => {
          const done = state.completed.includes(a.n);
          const active = state.act === a.n;
          return (
            <div key={a.n} className={styles.node}>
              <span
                className={`${styles.dot} ${done ? styles.dotDone : ""} ${
                  active ? styles.dotActive : ""
                }`}
              >
                {done ? <Check size={11} /> : a.n}
              </span>
              <span
                className={`${styles.label} ${active ? styles.labelActive : ""} ${
                  done ? styles.labelDone : ""
                }`}
              >
                {a.title}
              </span>
              {i < ACTS.length - 1 && (
                <span className={`${styles.rail} ${done ? styles.railDone : ""}`} />
              )}
            </div>
          );
        })}
      </div>

      <div className={styles.copy}>
        <span className={styles.goal}>{current.goal}</span>
        <span className={styles.next}>
          {current.next}
          {state.act === 3 && (
            <button className={styles.jump} onClick={onGoToPolicy}>
              Open Policy
            </button>
          )}
        </span>
      </div>
    </div>
  );
}

/**
 * Which act we are in, derived from what has actually happened.
 *
 * Derived rather than stored so a reload, a reset, or someone poking the API
 * directly can never leave the spine claiming progress the world does not
 * show.
 */
export function deriveAct(opts: {
  runbookCount: number;
  guidedRunHappened: boolean;
  policyChanged: boolean;
}): ActState {
  const { runbookCount, guidedRunHappened, policyChanged } = opts;
  const completed: Act[] = [];
  if (runbookCount > 0) completed.push(1);
  if (guidedRunHappened) completed.push(2);
  if (policyChanged) completed.push(3);

  if (policyChanged) return { act: 3, completed };
  if (guidedRunHappened) return { act: 3, completed };
  if (runbookCount > 0) return { act: 2, completed };
  return { act: 1, completed };
}
