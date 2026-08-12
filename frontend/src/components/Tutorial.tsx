"use client";

import { useEffect, useState } from "react";
import { ArrowRight, ArrowLeft, X } from "lucide-react";
import styles from "./Tutorial.module.css";

/**
 * First-run explainer.
 *
 * A judge arriving cold sees an incident console and a runbook library and has
 * no reason to know that the interesting part is what the system *refuses* to
 * do. Five screens, skippable at any point, and never shown twice.
 *
 * Deliberately not a tour with highlighted targets: those break the moment the
 * layout moves, and they explain where things are rather than why they matter.
 */

// Versioned: the screens now cover the Why and Author tabs, which did not
// exist when the first version was written. Someone who dismissed the old
// introduction should be shown the new one once rather than never.
const STORAGE_KEY = "cascade_tutorial_seen_v2";

interface Slide {
  title: string;
  body: React.ReactNode;
}

const SLIDES: Slide[] = [
  {
    title: "An agent that remembers what it learned",
    body: (
      <>
        <p>
          Cascade resolves infrastructure incidents. The first time it sees a
          kind of failure it reasons from scratch, which is slow and expensive.
          When that works, it compiles what it did into a reusable runbook.
        </p>
        <p>
          The next matching incident skips the planner entirely and replays the
          runbook with fresh parameters. That is where the speedup comes from.
        </p>
      </>
    ),
  },
  {
    title: "The hard part is knowing when to forget",
    body: (
      <>
        <p>
          Any agent can cache what worked. The problem is that the world moves:
          a policy changes, and every runbook compiled against the old rule is
          now confidently wrong.
        </p>
        <p>
          Cascade records which policy rules each runbook was compiled against.
          When a rule changes, every runbook that depended on it is quarantined
          in one transaction, and the agent refuses to use it until it relearns.
        </p>
      </>
    ),
  },
  {
    title: "Watch for the refusal",
    body: (
      <>
        <p>
          The moment worth watching is not a success. It is when vector search
          finds a matching runbook and the system refuses it anyway, because a
          rule it cited has moved.
        </p>
        <p>
          Every run has a <strong>Why</strong> tab showing which gate stopped it
          and what the evidence was. A refusal is the system working correctly,
          not failing.
        </p>
      </>
    ),
  },
  {
    title: "Try it on your own data",
    body: (
      <>
        <p>
          The <strong>Author</strong> tab in the incident view lets you create an
          incident that has never existed. Set the service tier and how long ago
          it deployed, and the system tells you what policy says should happen
          before you run it.
        </p>
        <p>
          Then run the agent and check it against that prediction. Nothing about
          the expected answer is passed to the agent.
        </p>
      </>
    ),
  },
  {
    title: "Where to start",
    body: (
      <>
        <p>
          The strip at the top tracks a three-act story: teach it on one
          incident, watch it reuse that on a second, then change the policy they
          both depend on and watch the runbook get quarantined. It tells you
          what to do at each step.
        </p>
        <p>
          Press <kbd>Ctrl</kbd>
          <kbd>K</kbd> at any time for the command palette. Full documentation is
          at <code>/docs</code>.
        </p>
      </>
    ),
  },
];

export function Tutorial({ onClose }: { onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const last = index === SLIDES.length - 1;

  const finish = () => {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {}
    onClose();
  };

  // Escape skips, arrows page. A modal that traps someone who already knows
  // the product is worse than no modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, SLIDES.length - 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const slide = SLIDES[index];

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Introduction">
      <div className={styles.card}>
        <button className={styles.skip} onClick={finish} aria-label="Skip introduction">
          <X size={14} />
          Skip
        </button>

        <div className={styles.step}>
          {index + 1} of {SLIDES.length}
        </div>
        <h2 className={styles.title}>{slide.title}</h2>
        <div className={styles.body}>{slide.body}</div>

        <div className={styles.footer}>
          <div className={styles.dots}>
            {SLIDES.map((s, i) => (
              <button
                key={s.title}
                className={`${styles.dot} ${i === index ? styles.dotActive : ""}`}
                onClick={() => setIndex(i)}
                aria-label={`Go to screen ${i + 1}`}
              />
            ))}
          </div>

          <div className={styles.nav}>
            {index > 0 && (
              <button className={styles.back} onClick={() => setIndex((i) => i - 1)}>
                <ArrowLeft size={14} />
                Back
              </button>
            )}
            <button
              className={styles.next}
              onClick={() => (last ? finish() : setIndex((i) => i + 1))}
            >
              {last ? "Get started" : "Next"}
              {!last && <ArrowRight size={14} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Whether the tutorial has already been dismissed on this browser. */
export function tutorialSeen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return true;
  }
}

/** Let the command palette bring it back. */
export function resetTutorial(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {}
}
