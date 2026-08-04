"use client";

import styles from "./StatusBar.module.css";

interface Props {
  llm?: "ok" | "degraded";
  llmProvider?: string | null;
  connected: boolean;
  running: number;
  succeeded: number;
  failed: number;
  awaitingApproval: number;
  hitRate?: number;
  onOpenPalette: () => void;
  onOpenIntelligence: () => void;
}

/**
 * Persistent status strip, VS Code style: ambient state that should always be
 * visible but never competes with the work.
 *
 * The LLM segment names the provider rather than showing a bare green dot —
 * "it works" and "Bedrock works" are different claims, and the demo must not
 * blur them.
 */
export function StatusBar({
  llm,
  llmProvider,
  connected,
  running,
  succeeded,
  failed,
  awaitingApproval,
  hitRate,
  onOpenPalette,
  onOpenIntelligence,
}: Props) {
  const degraded = llm === "degraded";

  return (
    <footer className={styles.bar}>
      <button
        type="button"
        className={`${styles.item} ${styles.button}`}
        onClick={onOpenIntelligence}
        title={
          !degraded
            ? "Bedrock is serving requests."
            : !llmProvider || llmProvider === "local"
              ? "No model provider reachable. Running on the local deterministic planner, so latency comparisons are not meaningful."
              : `Running on ${llmProvider} rather than Bedrock. These are real model calls, so latency comparisons hold; only the Bedrock claim does not.`
        }
      >
        <span
          className={`${styles.dot} ${degraded ? styles.dotWarn : styles.dotOk}`}
        />
        <span>{llmProvider ?? (degraded ? "local" : "bedrock")}</span>
      </button>

      <span className={styles.item}>
        <span
          className={`${styles.dot} ${connected ? styles.dotOk : styles.dotBad}`}
        />
        <span>{connected ? "live" : "disconnected"}</span>
      </span>

      <span className={styles.item}>
        CockroachDB <span className={styles.value}>cascade</span>
      </span>

      <span className={styles.spacer} />

      {awaitingApproval > 0 && (
        <span className={styles.item}>
          <span className={`${styles.dot} ${styles.dotWarn}`} />
          <span className={styles.value}>{awaitingApproval}</span> awaiting approval
        </span>
      )}

      {running > 0 && (
        <span className={styles.item}>
          <span className={`${styles.dot} ${styles.dotOk}`} />
          <span className={styles.value}>{running}</span> running
        </span>
      )}

      {hitRate !== undefined && (
        <span className={styles.item}>
          reuse <span className={styles.value}>{hitRate}%</span>
        </span>
      )}

      <span className={styles.item}>
        <span className={styles.value}>{succeeded}</span> ok
        {failed > 0 && (
          <>
            <span className={styles.muted}>/</span>
            <span className={styles.value}>{failed}</span> failed
          </>
        )}
      </span>

      <button
        type="button"
        className={`${styles.item} ${styles.button}`}
        onClick={onOpenPalette}
      >
        <span className={styles.kbd}>Ctrl K</span>
      </button>
    </footer>
  );
}
