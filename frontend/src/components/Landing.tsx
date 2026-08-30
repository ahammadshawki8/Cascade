"use client";

import { useEffect, useState } from "react";
import { Compass, ArrowRight } from "lucide-react";
import { Logo } from "./Logo";
import styles from "./Landing.module.css";

/**
 * The first screen, and the only one that gets to explain before it shows.
 *
 * A dashboard is a bad opening argument. Landing straight on an incident list
 * asks a first-time viewer to infer the thesis from the parts, and the thesis
 * is the only interesting thing here: a procedure can be correct when it is
 * written and wrong when it runs, and almost nothing is built to notice.
 *
 * So this states that once, shows it happening in four beats, and then asks the
 * only question worth asking on arrival: do you want to be shown, or do you
 * want to start working.
 *
 * NO AUTHENTICATION, DELIBERATELY
 * -------------------------------
 * There is no login here because there is no authentication anywhere in this
 * system, and a sign-in screen in front of an open API would imply a property
 * that does not exist. The demo is meant to be operated by whoever opens it.
 * That is written down rather than disguised.
 */

const STORAGE_KEY = "cascade_landing_seen_v1";

export function landingSeen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function resetLanding(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private browsing */
  }
}

/** The four beats of the idea, played once as the page settles. */
const BEATS = [
  { label: "A procedure is learned", detail: "rollback within 24h of deploy" },
  { label: "and pinned to the rule it assumed", detail: "rollback_window v1" },
  { label: "then the rule moves", detail: "24h → 4h" },
  { label: "so the procedure stops being trusted", detail: "refused on provenance" },
];

export function Landing({
  onGuided,
  onWork,
}: {
  onGuided: () => void;
  onWork: () => void;
}) {
  /**
   * Beats advance on a timer rather than on scroll or hover.
   *
   * Someone deciding whether to spend eight minutes should not have to
   * discover an interaction to see the argument. It plays itself, once,
   * and then holds on the last frame.
   */
  const [beat, setBeat] = useState(-1);

  useEffect(() => {
    const timers = BEATS.map((_, i) =>
      window.setTimeout(() => setBeat(i), 700 + i * 900)
    );
    return () => timers.forEach(window.clearTimeout);
  }, []);

  const choose = (fn: () => void) => () => {
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      /* showing this again is a smaller cost than crashing */
    }
    fn();
  };

  return (
    <div className={styles.page}>
      <div className={styles.aura} aria-hidden="true" />

      <div className={styles.inner}>
        <div className={styles.brand}>
          <Logo size={30} />
          <span className={styles.wordmark}>Cascade</span>
        </div>

        <h1 className={styles.headline}>
          Agent memory that knows
          <br />
          when it has expired
        </h1>

        <p className={styles.lede}>
          Every procedure this system learns is pinned to the exact version of
          every rule it was derived from. Change one rule and all of them stop
          being trusted at once, in a transaction of four writes, whether one
          procedure depends on it or a hundred thousand.
        </p>

        <ol className={styles.beats} aria-label="How it works">
          {BEATS.map((b, i) => (
            <li
              key={b.label}
              className={`${styles.beat} ${i <= beat ? styles.beatOn : ""} ${
                i === 3 && beat >= 3 ? styles.beatFinal : ""
              }`}
            >
              <span className={styles.beatDot} aria-hidden="true" />
              <span className={styles.beatText}>
                <span className={styles.beatLabel}>{b.label}</span>
                <code className={styles.beatDetail}>{b.detail}</code>
              </span>
            </li>
          ))}
        </ol>

        <div className={styles.choices}>
          <button
            type="button"
            className={`${styles.choice} ${styles.choicePrimary}`}
            onClick={choose(onGuided)}
          >
            <Compass size={19} />
            <span className={styles.choiceText}>
              <strong>Show me how it works</strong>
              <em>
                A guided walkthrough on sample data. Roughly eight minutes, and
                you can leave at any point.
              </em>
            </span>
            <ArrowRight size={17} className={styles.choiceArrow} />
          </button>

          <button
            type="button"
            className={styles.choice}
            onClick={choose(onWork)}
          >
            <span className={styles.choiceText}>
              <strong>Take me straight to work</strong>
              <em>
                An empty workspace. Connect your own agent, import a runbook you
                already have, or write a policy rule.
              </em>
            </span>
            <ArrowRight size={17} className={styles.choiceArrow} />
          </button>
        </div>

        <p className={styles.footnote}>
          No account and no login: everything a reviewer needs to do here is a
          write, so the demo is deliberately open. It runs against a live
          CockroachDB cluster on Amazon Bedrock, and nothing is scripted: the
          walkthrough runs every incident for real as you press the button.
        </p>
      </div>
    </div>
  );
}
