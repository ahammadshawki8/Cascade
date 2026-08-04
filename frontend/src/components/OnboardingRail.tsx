"use client";

import { useEffect, useState } from "react";
import styles from "./OnboardingRail.module.css";

export type StepState = "locked" | "available" | "running" | "done";

interface OnboardingRailProps {
  step1State: StepState;
  step2State: StepState;
  step3State: StepState;
  onStep1Click: () => void;
  onStep2Click: () => void;
  onStep3Click: () => void;
  onReset: () => void;
}

export function OnboardingRail({
  step1State,
  step2State,
  step3State,
  onStep1Click,
  onStep2Click,
  onStep3Click,
  onReset,
}: OnboardingRailProps) {
  const [isCompleted, setIsCompleted] = useState(false);

  useEffect(() => {
    if (step1State === "done" && step2State === "done" && step3State === "done") {
      setIsCompleted(true);
    } else {
      setIsCompleted(false);
    }
  }, [step1State, step2State, step3State]);

  if (isCompleted) {
    return (
      <div className={`${styles.rail} ${styles.railCollapsed}`}>
        <span className={styles.collapsedText}>Tour complete</span>
        <span className={styles.collapsedText}>·</span>
        <button className={styles.collapsedAction} onClick={onReset}>
          Reset demo
        </button>
      </div>
    );
  }

  const renderStep = (
    num: number,
    title: string,
    desc: string,
    state: StepState,
    onClick: () => void
  ) => {
    const isRunning = state === "running";
    // Only "running" is genuinely un-clickable. Previously anything other than
    // "available" dropped the handler entirely, so a stale localStorage entry
    // (or a re-run of a finished step) left the rail permanently inert with no
    // way back except clearing site data.
    const isDisabled = isRunning;

    return (
      <button
        type="button"
        className={`${styles.step} ${styles[state]}`}
        onClick={isDisabled ? undefined : onClick}
        disabled={isDisabled}
        aria-current={isRunning ? "step" : undefined}
        aria-label={`${title}. ${desc}`}
      >
        <div className={styles.stepNumber}>{state === "done" ? "✓" : num}</div>
        <div className={styles.stepContent}>
          <span className={styles.stepTitle}>{title}</span>
          <span className={styles.stepDesc}>{desc}</span>
        </div>
        {isRunning && <div className={styles.runningUnderline} />}
      </button>
    );
  };

  return (
    <div className={styles.rail}>
      <div className={styles.stepsContainer}>
        {renderStep(
          1,
          "Run an incident",
          "Watch the agent solve it from scratch.",
          step1State,
          onStep1Click
        )}
        {renderStep(
          2,
          "Reuse what it learned",
          "Same class of problem — now it has a runbook.",
          step2State,
          onStep2Click
        )}
        {renderStep(
          3,
          "Change a policy",
          "Watch every stale runbook get quarantined.",
          step3State,
          onStep3Click
        )}
      </div>
    </div>
  );
}
