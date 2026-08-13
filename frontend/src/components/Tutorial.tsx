"use client";

import { Compass, MousePointerClick, X } from "lucide-react";
import styles from "./Tutorial.module.css";

/**
 * One decision, on arrival: be shown, or look around.
 *
 * This used to be five screens of prose before you were allowed to touch
 * anything, which is the wrong shape — a viewer who has not seen the product
 * yet has nothing to attach the words to, so they skim and press Skip. The
 * explaining moved into the walkthrough, where each sentence sits next to the
 * thing it is about and arrives at the moment that thing happens.
 */

// Versioned: someone who dismissed the old five-slide introduction should be
// offered the walkthrough once rather than never.
const STORAGE_KEY = "cascade_tutorial_seen_v3";

export function tutorialSeen(): boolean {
  if (typeof window === "undefined") return true;
  return localStorage.getItem(STORAGE_KEY) === "true";
}

export function resetTutorial(): void {
  localStorage.removeItem(STORAGE_KEY);
}

function markSeen(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "true");
  } catch {
    /* private browsing: showing it again is a smaller cost than crashing */
  }
}

export function Tutorial({
  onStartTour,
  onClose,
}: {
  onStartTour: () => void;
  onClose: () => void;
}) {
  const choose = (fn: () => void) => () => {
    markSeen();
    fn();
  };

  return (
    <div className={styles.overlay} role="dialog" aria-label="Introduction">
      <div className={styles.card}>
        <button
          className={styles.close}
          onClick={choose(onClose)}
          aria-label="Close"
        >
          <X size={16} />
        </button>

        <div className={styles.kicker}>Cascade</div>
        <h2 className={styles.headline}>
          An agent that knows when its own memory has expired
        </h2>
        <p className={styles.lead}>
          It learns a procedure by solving an incident, then reuses it. The part
          worth watching is what happens when the rules it learned under change:
          every procedure built on them stops being trusted, in the same
          transaction, without anything going and marking them.
        </p>

        <div className={styles.choices}>
          <button className={styles.primary} onClick={choose(onStartTour)}>
            <Compass size={17} />
            <span className={styles.choiceBody}>
              <b>Show me — six minutes</b>
              <em>
                One incident at a time. Nothing to get wrong, and you can leave
                whenever you like.
              </em>
            </span>
          </button>

          <button className={styles.secondary} onClick={choose(onClose)}>
            <MousePointerClick size={17} />
            <span className={styles.choiceBody}>
              <b>I will explore on my own</b>
              <em>Twelve incidents, real policy, nothing held back.</em>
            </span>
          </button>
        </div>

        <p className={styles.foot}>
          Everything here runs against a live CockroachDB cluster. Nothing is
          scripted, so it can surprise you.
        </p>
      </div>
    </div>
  );
}
