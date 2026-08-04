"use client";

import { useEffect, useRef, useState } from "react";
import { Search, Zap, Check, X } from "lucide-react";
import styles from "./IncidentConsole.module.css";

export interface StepEvent {
  id: string;
  tool: string;
  args: Record<string, any>;
  duration_ms?: number;
  error?: boolean;
}

export interface TaskHistoryItem {
  id: string;
  time: string;
  input: string;
  outcome: "remediated" | "escalated" | "failed" | "interrupted";
}

interface IncidentConsoleProps {
  initialInput?: string;
  isRunning?: boolean;
  mode?: "explore" | "guided";
  activePlaybookName?: string;
  activePlaybookVersion?: number;
  isInterrupted?: boolean;
  steps?: StepEvent[];
  history?: TaskHistoryItem[];
  onSubmit: (input: string) => void;
  onInputChange?: (val: string) => void;
}

export function IncidentConsole({
  initialInput = "",
  isRunning = false,
  mode,
  activePlaybookName,
  activePlaybookVersion,
  isInterrupted = false,
  steps = [],
  history = [],
  onSubmit,
  onInputChange,
}: IncidentConsoleProps) {
  const [inputValue, setInputValue] = useState(initialInput);
  const streamRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of step stream when new steps arrive
  useEffect(() => {
    if (streamRef.current) {
      const { scrollHeight, clientHeight, scrollTop } = streamRef.current;
      const isNearBottom = scrollHeight - clientHeight - scrollTop < 50;
      if (isNearBottom || steps.length === 1) {
        streamRef.current.scrollTop = scrollHeight;
      }
    }
  }, [steps.length]);

  // Sync external input changes (e.g. from OnboardingRail)
  useEffect(() => {
    setInputValue(initialInput);
  }, [initialInput]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim() && !isRunning) {
      onSubmit(inputValue);
    }
  };

  const formatArgs = (args: Record<string, any>) => {
    return Object.entries(args)
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
  };

  return (
    <div className={styles.console}>
      <div className={styles.header}>
        <form className={styles.inputWrapper} onSubmit={handleSubmit}>
          <input
            className={styles.input}
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value);
              onInputChange?.(e.target.value);
            }}
            placeholder="Remediate INC-1001"
            disabled={isRunning}
          />
          <button
            type="submit"
            className={styles.submitBtn}
            disabled={isRunning || !inputValue.trim()}
          >
            {isRunning ? "Running…" : "Run"}
          </button>
        </form>

        {mode && (
          <div className={`${styles.modeBadge} ${mode === "guided" ? styles.modeGuided : styles.modeExplore}`}>
            <span className={styles.modeIcon}>
              {mode === "guided" ? <Zap size={14} /> : <Search size={14} />}
            </span>
            {mode === "guided" 
              ? `Runbook · ${activePlaybookName || "unknown"} v${activePlaybookVersion || 1}`
              : "Exploring"}
          </div>
        )}
      </div>

      <div className={styles.body}>
        <div className={`${styles.interruptBanner} ${isInterrupted ? styles.interruptBannerVisible : ""}`}>
          Policy changed mid-flight — re-planning under the new rules.
        </div>

        <div className={styles.stepStream} ref={streamRef}>
          {steps.map((step, idx) => (
            <div key={step.id || idx} className={styles.stepRow}>
              <span className={styles.stepIndex}>
                {(idx + 1).toString().padStart(2, "0")}
              </span>
              <span className={styles.stepTool}>{step.tool}</span>
              <span className={styles.stepArgs}>{formatArgs(step.args)}</span>
              {step.error ? (
                <X size={14} color="var(--st-invalid)" />
              ) : (
                <Check size={14} color="var(--st-active)" />
              )}
              {/* `0 && …` renders a literal 0 in JSX — a sub-millisecond step
                  would print a stray "0" next to the tool name. */}
              {step.duration_ms != null && (
                <span className={styles.stepDuration}>{step.duration_ms}ms</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {history.length > 0 && (
        <div className={styles.history}>
          <div className={styles.historyTitle}>Recent Tasks</div>
          <div className={styles.historyList}>
            {history.map((item) => (
              <div key={item.id} className={styles.historyRow}>
                <span className={styles.historyTime}>{item.time}</span>
                <span className={styles.historyInput}>{item.input}</span>
                <span className={`${styles.chip} ${styles[`chip${item.outcome.charAt(0).toUpperCase() + item.outcome.slice(1)}`]}`}>
                  {item.outcome}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
