"use client";

import styles from "./MetricBar.module.css";
import { CountUp } from "./CountUp";

interface MetricsData {
  cold?: { avg_ms: number; avg_steps: number };
  guided?: { avg_ms: number; avg_steps: number };
  retrieval?: { hits: number; precondition_misses: number };
  counts_by_status?: Record<string, number>;
  llm?: "ok" | "degraded";
}

interface MetricBarProps {
  data?: MetricsData;
}

export function MetricBar({ data }: MetricBarProps) {
  const coldMs = data?.cold?.avg_ms;
  const guidedMs = data?.guided?.avg_ms;

  /**
   * Sub-second runs are the normal case without a live model in the loop, and
   * one decimal place rendered 43ms as a flat "0s". Switch to milliseconds
   * below a second so the number stays truthful at both scales.
   */
  const scale = (ms?: number) =>
    ms === undefined || ms === null
      ? undefined
      : ms < 1000
        ? ms
        : ms / 1000;
  const unit = (ms?: number) => (ms !== undefined && ms < 1000 ? "ms" : "s");

  const coldValue = scale(coldMs);
  const guidedValue = scale(guidedMs);

  // Negative delta = guided is faster, which is the whole thesis. A positive
  // delta means guided was SLOWER and must not be dressed up as a win.
  let deltaPct: number | undefined;
  if (coldMs && guidedMs && coldMs > 0) {
    deltaPct = Math.round(((guidedMs - coldMs) / coldMs) * 100);
  }
  const guidedIsFaster = deltaPct !== undefined && deltaPct < 0;

  const hitRate = data?.retrieval
    ? data.retrieval.hits / Math.max(1, data.retrieval.hits + data.retrieval.precondition_misses)
    : undefined;

  const hitRatePct = hitRate !== undefined ? Math.round(hitRate * 100) : undefined;

  const getCount = (status: string) => data?.counts_by_status?.[status] ?? 0;

  return (
    <div style={{ position: "relative" }}>
      <div className={styles.metricBar}>
        <div className={styles.primaryStats}>
          <div className={styles.statBlock}>
            <span className={styles.statLabel}>Cold</span>
            <span className={styles.statValue}>
              <CountUp value={coldValue} format={(v) => `${v}${unit(coldMs)}`} />
            </span>
          </div>

          {deltaPct !== undefined && (
            <div
              className={`${styles.deltaChip} ${
                guidedIsFaster ? "" : styles.deltaChipRegression
              }`}
              title={
                guidedIsFaster
                  ? "Guided execution is faster than learning from scratch."
                  : "Guided was slower on this sample. Expected without a live model: the cold path has no LLM latency to save, while guided still pays for precondition and parameter checks."
              }
            >
              Δ {deltaPct > 0 ? "+" : ""}
              {deltaPct}%
            </div>
          )}

          <div className={styles.statBlock}>
            <span className={styles.statLabel}>Guided</span>
            <span className={styles.statValue}>
              <CountUp value={guidedValue} format={(v) => `${v}${unit(guidedMs)}`} />
            </span>
          </div>
        </div>

        <div className={styles.divider} />

        <div className={styles.secondaryStats}>
          <div className={styles.secondaryStatBlock}>
            <span className={styles.secondaryLabel}>Hit Rate</span>
            <span className={styles.secondaryValue}>
              {hitRatePct !== undefined ? `${hitRatePct}%` : "—"}
            </span>
          </div>

          <div className={styles.secondaryStatBlock}>
            <span className={styles.secondaryLabel}>Tasks</span>
            <div className={styles.statusCounts}>
              <div className={styles.statusCount}>
                <div className={`${styles.statusDot} ${styles.dotQueued}`} />
                <CountUp value={data ? getCount("queued") : undefined} />
              </div>
              <div className={styles.statusCount}>
                <div className={`${styles.statusDot} ${styles.dotRunning}`} />
                <CountUp value={data ? getCount("running") : undefined} />
              </div>
              <div className={styles.statusCount}>
                <div className={`${styles.statusDot} ${styles.dotInterrupted}`} />
                <CountUp value={data ? getCount("interrupted") : undefined} />
              </div>
              <div className={styles.statusCount}>
                <div className={`${styles.statusDot} ${styles.dotSucceeded}`} />
                <CountUp value={data ? getCount("succeeded") : undefined} />
              </div>
              <div className={styles.statusCount}>
                <div className={`${styles.statusDot} ${styles.dotFailed}`} />
                <CountUp value={data ? getCount("failed") : undefined} />
              </div>
            </div>
          </div>
        </div>

        <div className={styles.llmHealth}>
          <span className={styles.llmLabel}>LLM</span>
          <div
            className={`${styles.llmDot} ${
              data?.llm === "degraded" ? styles.llmDegraded : styles.llmOk
            }`}
          />
        </div>
      </div>
      
      {/* Tasks are NOT queued when degraded — they run on the deterministic
          local path. Saying otherwise misdescribes what the system is doing,
          and the thing an operator actually needs to know is that the timing
          comparison above is not meaningful in this mode. */}
      {data?.llm === "degraded" && (
        <div className={styles.degradedStrip}>
          <strong>Degraded:</strong>
          <span>
            no model provider reachable — tasks still run on the deterministic
            local planner, but cold-vs-guided timings are not comparable.
          </span>
        </div>
      )}
    </div>
  );
}
