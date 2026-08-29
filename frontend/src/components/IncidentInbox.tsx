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
  locked = false,
  only = null,
  onRun,
  onReset,
  onlyMine = false,
}: {
  apiBase: string;
  refreshKey: number;
  runningId?: string | null;
  /** Work is already in flight; starting more would interleave with it. */
  locked?: boolean;
  /**
   * Restrict the list to these ids. The walkthrough shows one incident at a
   * time so there is never a wrong thing to click; `null` means show them all.
   */
  only?: string[] | null;
  onRun: (input: string) => void;
  /**
   * Restore the sample world. Offered here because this is where the aging
   * described below actually shows up, and telling someone their demo is
   * broken without giving them the fix in the same breath is not much help.
   */
  onReset?: () => void;
  /**
   * Work mode: show only incidents the user created.
   *
   * The seeded ones are INC-1xxx and anything authored here is INC-9xxx, so
   * the split is in the id rather than in a flag that could drift.
   */
  onlyMine?: boolean;
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

  const open = incidents
    .filter((i) => i.state !== "resolved")
    .filter((i) => !onlyMine || !/^INC-1\d{3}$/.test(i.incident_id))
    .filter((i) => only === null || only.includes(i.incident_id));

  /**
   * The sample world ages, and past a point it stops being able to tell its
   * own story.
   *
   * `002_seed.sql` writes deploy timestamps as `NOW() - INTERVAL '2 hours'`.
   * That is absolute: it was two hours ago when the seed ran, and it is two
   * hours plus however long the database has been sitting there ever since.
   * After a few days every bad deploy is outside the rollback window, so the
   * cold run escalates instead of remediating, no runbook is ever compiled,
   * and the learn -> reuse -> refuse sequence cannot start. Nothing is broken,
   * and nothing says so either — the incidents look normal and simply all
   * refuse.
   *
   * Detected by asking whether *any* rollback is still possible rather than by
   * comparing against a fixed number of hours, so tightening the window during
   * the demo (24h -> 4h, which is the whole point of the walkthrough) does not
   * trip it: INC-1001 at two hours stays inside a four hour window.
   */
  const badDeploys = incidents.filter(
    (i) => i.kind === "bad_deploy" && i.state !== "resolved"
  );
  const worldAged =
    !loading &&
    !onlyMine && // work mode hides the sample entirely, so its age is moot
    badDeploys.length > 0 &&
    badDeploys.every((i) => i.within_window === false);

  return (
    <div className={styles.inbox}>
      {worldAged && (
        <div className={styles.agedBanner}>
          <div className={styles.agedText}>
            <strong>This sample world has aged.</strong> Every bad deploy here is
            now older than the {policy?.rollback_window_hours ?? 24}h rollback
            window, so all of them refuse and nothing can be learned. Restore the
            sample to bring the deploys back to minutes old.
          </div>
          {onReset && (
            <button
              type="button"
              className={styles.agedAction}
              onClick={onReset}
              disabled={locked}
            >
              <RotateCw size={13} />
              Restore the sample
            </button>
          )}
        </div>
      )}

      {policy && (
        <div className={styles.policyBar}>
          <span className={styles.policyTitle}>
            {onlyMine ? "Policy in force (yours to change)" : "Policy in force"}
          </span>
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
          {only !== null && only.length === 0
            ? "The walkthrough is looking at something else right now."
            : onlyMine
            ? "Nothing here yet. Describe an incident under Author, or let an agent send one in from Connections."
            : "No open incidents. Reset the demo world to bring them back."}
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
              data-tour={`incident-${inc.incident_id}`}
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
                data-tour={`fix-${inc.incident_id}`}
                disabled={running || locked}
                title={locked && !running ? "Waiting for the current work to finish" : undefined}
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
