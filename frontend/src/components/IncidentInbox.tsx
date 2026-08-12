"use client";

import { useEffect, useState } from "react";
import { Play, RotateCw } from "lucide-react";
import styles from "./IncidentInbox.module.css";

/**
 * The incident list, as things you click.
 *
 * The console's text box required knowing the ids, the exact format, and which
 * incident demonstrates which rule. That is three pieces of hidden knowledge
 * before anything happens, and it was the main reason a first-time viewer had
 * no way in.
 *
 * The cards also carry the policy verdict, so a viewer learns the rules by
 * comparing two incidents rather than by being told: "2 hours ago" next to
 * "30 hours ago, past the 24h window" explains the rollback window without a
 * sentence of documentation.
 */

interface Incident {
  incident_id: string;
  kind: string;
  severity: string;
  service_name: string;
  service_tier: number;
  state: string;
  error_rate: number | null;
  cpu_usage: number | null;
  deploy_age_hours: number | null;
  tier_allowed: boolean;
  within_window: boolean | null;
}

interface Policy {
  min_tier: number;
  rollback_window_hours: number;
}

const KIND_LABEL: Record<string, string> = {
  bad_deploy: "Bad deploy",
  error_spike: "Error spike",
  resource_exhaustion: "Resource exhaustion",
};

const age = (h: number | null) => {
  if (h == null) return null;
  if (h < 1) return `${Math.round(h * 60)} min ago`;
  return `${h < 10 ? h.toFixed(1) : Math.round(h)}h ago`;
};

export function IncidentInbox({
  apiBase,
  refreshKey,
  runningId,
  onRun,
}: {
  apiBase: string;
  refreshKey: number;
  runningId?: string | null;
  onRun: (input: string) => void;
}) {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiBase}/mock/incidents`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setIncidents(data.incidents ?? []);
        setPolicy(data.policy ?? null);
      } catch {
        /* the empty state below is the honest fallback */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, refreshKey]);

  const open = incidents.filter((i) => i.state !== "resolved");

  return (
    <div className={styles.inbox}>
      {policy && (
        <div className={styles.policyBar}>
          <span className={styles.policyTitle}>Policy in force</span>
          <span className={styles.policyItem}>
            roll back only within <b>{policy.rollback_window_hours}h</b> of deploy
          </span>
          <span className={styles.policyItem}>
            never auto-fix above <b>tier {policy.min_tier}</b>
          </span>
        </div>
      )}

      {loading && <div className={styles.empty}>Loading incidents…</div>}
      {!loading && open.length === 0 && (
        <div className={styles.empty}>
          No open incidents. Reset the demo world to bring them back.
        </div>
      )}

      <div className={styles.list}>
        {open.map((inc) => {
          const running = runningId === inc.incident_id;
          // Named so the reason is legible: these are the two gates a viewer is
          // meant to learn, and each one blocks a different action.
          const blockedByTier = !inc.tier_allowed;
          const blockedByWindow = inc.kind === "bad_deploy" && inc.within_window === false;

          return (
            <div
              key={inc.incident_id}
              className={`${styles.card} ${running ? styles.cardRunning : ""}`}
            >
              <div className={styles.top}>
                <span
                  className={`${styles.dot} ${
                    inc.state === "mitigated" ? styles.dotMitigated : styles.dotOpen
                  }`}
                />
                <span className={styles.service}>{inc.service_name}</span>
                <span className={styles.id}>{inc.incident_id}</span>
                <span className={`${styles.tier} ${blockedByTier ? styles.tierBlocked : ""}`}>
                  tier {inc.service_tier}
                </span>
                <span className={styles.sev}>{inc.severity}</span>
              </div>

              <div className={styles.what}>
                {KIND_LABEL[inc.kind] ?? inc.kind}
                {inc.deploy_age_hours != null && (
                  <span className={styles.when}> · deployed {age(inc.deploy_age_hours)}</span>
                )}
                {inc.error_rate != null && inc.error_rate > 1 && (
                  <span className={styles.when}> · {inc.error_rate.toFixed(1)}% errors</span>
                )}
              </div>

              <div className={styles.flags}>
                {blockedByTier && (
                  <span className={styles.flagBlock}>
                    too critical to auto-fix
                  </span>
                )}
                {blockedByWindow && (
                  <span className={styles.flagBlock}>
                    past the rollback window
                  </span>
                )}
                {!blockedByTier && !blockedByWindow && (
                  <span className={styles.flagOk}>policy permits automatic action</span>
                )}
                {inc.state === "mitigated" && (
                  <span className={styles.flagDone}>already mitigated</span>
                )}
              </div>

              <button
                className={styles.run}
                disabled={running}
                onClick={() => onRun(`Remediate ${inc.incident_id}`)}
              >
                {running ? <RotateCw size={13} className={styles.spin} /> : <Play size={13} />}
                {running ? "Working…" : "Fix it"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
