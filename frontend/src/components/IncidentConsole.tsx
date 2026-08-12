"use client";

import { useEffect, useRef, useState } from "react";
import { Search, Zap, Check, X } from "lucide-react";
import { narrate } from "./narrate";
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

  /**
   * Tool calls take single-digit milliseconds; the seconds between them are the
   * planner deciding what to do next. With nothing rendered in the gap the app
   * looks frozen for most of a cold run, and the one thing a viewer most needs
   * to understand — that thinking is the entire cost — is invisible.
   *
   * Inferred from the gap since the last step rather than reported by the
   * server: the gap *is* the thinking, so no new event is needed.
   */
  const [thinkingMs, setThinkingMs] = useState<number | null>(null);
  const lastStepAt = useRef<number>(Date.now());

  useEffect(() => {
    lastStepAt.current = Date.now();
    setThinkingMs(null);
  }, [steps.length]);

  useEffect(() => {
    if (!isRunning) {
      setThinkingMs(null);
      return;
    }
    const timer = setInterval(() => {
      const gap = Date.now() - lastStepAt.current;
      // Below a second a spinner would just flicker between fast steps.
      setThinkingMs(gap > 900 ? gap : null);
    }, 100);
    return () => clearInterval(timer);
  }, [isRunning]);

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
          {steps.length === 0 && !isRunning && (
            <div className={styles.empty}>
              Pick an incident and the agent&rsquo;s reasoning will appear here,
              one step at a time.
            </div>
          )}

          {steps.map((step, idx) => {
            const { question, answer } = narrate(step.tool, step.args);
            return (
              <div key={step.id || idx} className={styles.stepCard}>
                <div className={styles.stepHead}>
                  <span className={styles.stepIndex}>
                    {(idx + 1).toString().padStart(2, "0")}
                  </span>
                  <span className={styles.stepQuestion}>{question}</span>
                  {step.error ? (
                    <X size={14} color="var(--st-invalid)" />
                  ) : (
                    <Check size={14} color="var(--st-active)" />
                  )}
                  {/* `0 && …` renders a literal 0 in JSX — a sub-millisecond
                      step would print a stray "0" next to the tool name. */}
                  {step.duration_ms != null && (
                    <span className={styles.stepDuration}>{step.duration_ms}ms</span>
                  )}
                </div>
                {answer && <div className={styles.stepAnswer}>{answer}</div>}
                {/* The exact call stays one click away, so nothing is hidden
                    from anyone who wants to audit what actually ran. */}
                <details className={styles.stepRaw}>
                  <summary>{step.tool}</summary>
                  <code>{formatArgs(step.args)}</code>
                </details>
              </div>
            );
          })}

          {thinkingMs != null && (
            <div className={styles.thinking}>
              <span className={styles.thinkingDots}>
                <i /> <i /> <i />
              </span>
              deciding what to do next
              <span className={styles.thinkingTime}>
                {(thinkingMs / 1000).toFixed(1)}s
              </span>
            </div>
          )}
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
