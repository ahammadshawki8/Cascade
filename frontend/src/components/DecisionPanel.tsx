"use client";

import { useEffect, useState } from "react";
import { Check, X, Minus, ArrowRight } from "lucide-react";
import styles from "./DecisionPanel.module.css";

/** Why a run went guided or cold. Mirrors GET /api/tasks/{id}/explain. */
export interface Explanation {
  task_id: string;
  input: string;
  status: string;
  result: string | null;
  mode: "explore" | "guided" | null;
  interrupt_reason: string | null;
  decision: {
    reason: "reused" | "refused_stale" | "refused_precondition" | "no_match";
    headline: string;
    detail: string;
    stale_deps?: { rule_key: string; compiled_against: number; head: number }[] | null;
    failed_preconditions?: string[] | null;
  };
  incident: {
    incident_id: string;
    kind: string;
    severity: string;
    service_name: string;
    service_tier: number;
    state: string;
    deploy_age_hours: number | null;
  } | null;
  playbook: {
    playbook_id: string;
    name: string;
    version: number;
    status_cache: string;
    confidence: number;
  } | null;
  episode: {
    steps: number;
    latency_ms: number;
    tokens: number;
    outcome: string;
  } | null;
  learned: { playbook_id: string; name: string; version: number } | null;
  comparison: {
    cold_avg_ms: number | null;
    guided_avg_ms: number | null;
    cold_runs: number;
    guided_runs: number;
    cold_avg_tokens: number | null;
    guided_avg_tokens: number | null;
    speedup: number | null;
  };
}

type GateState = "pass" | "fail" | "skipped";

/**
 * The four stages every task passes through, and where this one stopped.
 *
 * This is the part of the system a reviewer cannot see by watching the step
 * stream: a refusal and a cold start produce the same visible behaviour, and
 * only the gate that stopped it distinguishes them.
 */
function gatesFor(reason: Explanation["decision"]["reason"]): {
  label: string;
  state: GateState;
  note: string;
}[] {
  switch (reason) {
    case "reused":
      return [
        { label: "Vector search", state: "pass", note: "matched a runbook" },
        { label: "Freshness gate", state: "pass", note: "every cited rule at head" },
        { label: "Preconditions", state: "pass", note: "hold for this incident" },
        { label: "Replay steps", state: "pass", note: "no planner in the loop" },
      ];
    case "refused_stale":
      return [
        { label: "Vector search", state: "pass", note: "matched a runbook" },
        { label: "Freshness gate", state: "fail", note: "a cited rule has moved" },
        { label: "Preconditions", state: "skipped", note: "never reached" },
        { label: "Re-plan cold", state: "pass", note: "planned from policy instead" },
      ];
    case "refused_precondition":
      return [
        { label: "Vector search", state: "pass", note: "matched a runbook" },
        { label: "Freshness gate", state: "pass", note: "every cited rule at head" },
        { label: "Preconditions", state: "fail", note: "do not hold here" },
        { label: "Re-plan cold", state: "pass", note: "planned from policy instead" },
      ];
    default:
      return [
        { label: "Vector search", state: "fail", note: "nothing close enough" },
        { label: "Freshness gate", state: "skipped", note: "nothing to check" },
        { label: "Preconditions", state: "skipped", note: "nothing to check" },
        { label: "Plan cold", state: "pass", note: "planned from policy and tools" },
      ];
  }
}

const GATE_ICON = {
  pass: <Check size={13} />,
  fail: <X size={13} />,
  skipped: <Minus size={13} />,
};

export function DecisionPanel({
  apiBase,
  taskId,
  onOpenPolicy,
}: {
  apiBase: string;
  taskId: string | null;
  onOpenPolicy?: (ruleKey: string) => void;
}) {
  const [data, setData] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!taskId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await fetch(`${apiBase}/tasks/${taskId}/explain`);
        if (!res.ok) throw new Error(String(res.status));
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, taskId]);

  if (!taskId) {
    return (
      <div className={styles.panel}>
        <div className={styles.empty}>
          Run an incident to see why the agent chose the path it did.
        </div>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className={styles.panel}>
        <div className={styles.empty}>{loading ? "Reading the audit trail…" : "No explanation available."}</div>
      </div>
    );
  }

  const { decision, incident, playbook, episode, comparison, learned } = data;
  const refused =
    decision.reason === "refused_stale" || decision.reason === "refused_precondition";
  const gates = gatesFor(decision.reason);

  return (
    <div className={styles.panel}>
      <div
        className={`${styles.verdict} ${
          refused
            ? styles.verdictRefused
            : decision.reason === "reused"
              ? styles.verdictReused
              : styles.verdictCold
        }`}
      >
        <div className={styles.verdictHead}>{decision.headline}</div>
        <div className={styles.verdictDetail}>{decision.detail}</div>
      </div>

      {/* The refusal evidence, named. "Stale" is a claim; the version mismatch
          is the proof, and it is the one thing a reviewer should be able to
          check against the Policy panel themselves. */}
      {decision.stale_deps && decision.stale_deps.length > 0 && (
        <div className={styles.evidence}>
          <div className={styles.evidenceTitle}>Rules that moved since this runbook was compiled</div>
          {decision.stale_deps.map((d) => (
            <button
              key={d.rule_key}
              className={styles.staleRow}
              onClick={() => onOpenPolicy?.(d.rule_key)}
            >
              <span className={styles.ruleKey}>{d.rule_key}</span>
              <span className={styles.versionOld}>compiled against v{d.compiled_against}</span>
              <ArrowRight size={12} />
              <span className={styles.versionNew}>now at v{d.head}</span>
            </button>
          ))}
        </div>
      )}

      {decision.failed_preconditions && decision.failed_preconditions.length > 0 && (
        <div className={styles.evidence}>
          <div className={styles.evidenceTitle}>Preconditions that did not hold</div>
          {decision.failed_preconditions.map((p, i) => (
            <div key={i} className={styles.preconditionRow}>
              {p}
            </div>
          ))}
        </div>
      )}

      <div className={styles.gates}>
        {gates.map((g, i) => (
          <div key={g.label} className={styles.gateWrap}>
            <div className={`${styles.gate} ${styles[`gate_${g.state}`]}`}>
              <span className={styles.gateIcon}>{GATE_ICON[g.state]}</span>
              <span className={styles.gateLabel}>{g.label}</span>
              <span className={styles.gateNote}>{g.note}</span>
            </div>
            {i < gates.length - 1 && <div className={styles.connector} />}
          </div>
        ))}
      </div>

      <div className={styles.facts}>
        {incident && (
          <div className={styles.factGroup}>
            <div className={styles.factTitle}>Incident</div>
            <Fact k="id" v={incident.incident_id} />
            <Fact k="kind" v={`${incident.kind} · ${incident.severity}`} />
            <Fact k="service" v={`${incident.service_name} (tier ${incident.service_tier})`} />
            {incident.deploy_age_hours != null && (
              <Fact k="last deploy" v={`${incident.deploy_age_hours.toFixed(1)}h ago`} />
            )}
          </div>
        )}

        {playbook && (
          <div className={styles.factGroup}>
            <div className={styles.factTitle}>
              {refused ? "Runbook that was refused" : "Runbook used"}
            </div>
            <Fact k="name" v={`${playbook.name} v${playbook.version}`} />
            <Fact k="status" v={playbook.status_cache} />
            <Fact k="confidence" v={playbook.confidence.toFixed(2)} />
          </div>
        )}

        {episode && (
          <div className={styles.factGroup}>
            <div className={styles.factTitle}>This run</div>
            <Fact k="outcome" v={data.result ?? data.status} />
            <Fact k="steps" v={String(episode.steps)} />
            <Fact k="latency" v={`${episode.latency_ms.toLocaleString()}ms`} />
            {episode.tokens > 0 && <Fact k="tokens" v={episode.tokens.toLocaleString()} />}
          </div>
        )}
      </div>

      {learned && (
        <div className={styles.learned}>
          This cold run was compiled into a reusable runbook:{" "}
          <strong>
            {learned.name} v{learned.version}
          </strong>
          . The next matching incident can skip the planner entirely.
        </div>
      )}

      {/* Averages, labelled as averages, with the sample size attached. A bare
          speedup number is the easiest thing in this UI to overclaim with.
          Tokens sit alongside latency deliberately: latency is dominated by
          model round-trip variance, so tokens avoided is the steadier measure
          of what reuse actually saves. */}
      {comparison.cold_runs > 0 && comparison.guided_runs > 0 && (
        <div className={styles.comparison}>
          {comparison.speedup != null && (
            <div className={styles.metric}>
              <span className={styles.speedup}>{comparison.speedup}x</span>
              <span className={styles.metricLabel}>
                faster
                <br />
                {comparison.cold_avg_ms?.toLocaleString()}ms &rarr;{" "}
                {comparison.guided_avg_ms?.toLocaleString()}ms
              </span>
            </div>
          )}
          {/* Stated as an absolute saving, not a ratio. Guided reuse routinely
              spends exactly zero planner tokens, and a ratio against zero is
              undefined — which would hide the strongest number here. */}
          {comparison.cold_avg_tokens != null && comparison.guided_avg_tokens != null && (
            <div className={styles.metric}>
              <span className={styles.speedup}>
                {(comparison.cold_avg_tokens - comparison.guided_avg_tokens).toLocaleString()}
              </span>
              <span className={styles.metricLabel}>
                planner tokens avoided
                <br />
                {comparison.cold_avg_tokens.toLocaleString()} &rarr;{" "}
                {comparison.guided_avg_tokens.toLocaleString()} per run
              </span>
            </div>
          )}
          <span className={styles.comparisonText}>
            Averaged over successful runs only: {comparison.cold_runs} cold,{" "}
            {comparison.guided_runs} guided. An escalation short-circuits before the
            expensive part, so including one would flatter both sides.
          </span>
        </div>
      )}
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className={styles.fact}>
      <span className={styles.factKey}>{k}</span>
      <span className={styles.factValue}>{v}</span>
    </div>
  );
}
