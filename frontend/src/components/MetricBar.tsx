"use client";

import styles from "./MetricBar.module.css";
import { CountUp } from "./CountUp";

interface MetricsData {
  cold?: { avg_ms: number; avg_steps: number };
  guided?: { avg_ms: number; avg_steps: number };
  retrieval?: { hits: number; precondition_misses: number };
  counts_by_status?: Record<string, number>;
  llm?: "ok" | "degraded";
  llm_provider?: string | null;
  llm_reason?: string | null;
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

  // No provider name, or an explicit "local", means nothing real is serving.
  const onLocalPlanner =
    !data?.llm_provider || data.llm_provider === "local";

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
                  : onLocalPlanner
                    ? "Guided was slower on this sample. Expected without a live model: the cold path has no model latency to save, while guided still pays for precondition and parameter checks."
                    : "Guided was slower on this sample, which is worth investigating: a real model is serving, so exploring should be paying planning latency that guided avoids."
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
      
      {/* "Degraded" only means "not Bedrock", and that covers two very
          different situations. A real fallback provider (Groq, OpenRouter,
          HuggingFace) makes genuine model calls, so the timings above ARE
          comparable — only the AWS claim is weaker. The local planner makes
          none, so they are not. Saying "no model provider reachable" when
          Groq is serving is simply false, and it is the timing caveat that an
          operator actually needs to get right. */}
      {data?.llm === "degraded" && (
        <div className={styles.degradedStrip}>
          {onLocalPlanner ? (
            <>
              <strong>Local planner:</strong>
              <span>
                no model provider reachable. Tasks still run, on the
                deterministic local path, but cold-vs-guided timings are not
                comparable.
              </span>
            </>
          ) : (
            <>
              <strong>Fallback provider:</strong>
              <span>
                served by {data.llm_provider} rather than Bedrock. Timings are
                real model calls and are comparable.
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
