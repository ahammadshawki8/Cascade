"use client";

import { useState } from "react";
import { Play, Plus } from "lucide-react";
import styles from "./IncidentComposer.module.css";

/**
 * Author an incident the system has never seen.
 *
 * The seeded world covers the decision space, but a reviewer who can only
 * replay canned ids has no way to tell a learning agent from a scripted one.
 * The important detail is the prediction: the API states what policy should
 * decide *before* the run, so the outcome is falsifiable rather than merely
 * impressive.
 */

const KINDS = [
  { value: "bad_deploy", label: "Bad deploy", hint: "rollback is the candidate action" },
  { value: "error_spike", label: "Error spike", hint: "no deploy to roll back" },
  { value: "resource_exhaustion", label: "Resource exhaustion", hint: "scaling path" },
];

interface Authored {
  incident_id: string;
  expect: string;
}

export function IncidentComposer({
  apiBase,
  onRun,
}: {
  apiBase: string;
  onRun: (input: string) => void;
}) {
  const [kind, setKind] = useState("bad_deploy");
  const [severity, setSeverity] = useState("P2");
  const [serviceName, setServiceName] = useState("svc-judge-test");
  const [tier, setTier] = useState(2);
  const [deployAge, setDeployAge] = useState(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authored, setAuthored] = useState<Authored | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setAuthored(null);
    try {
      const res = await fetch(`${apiBase}/mock/incidents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          severity,
          service_name: serviceName.trim() || "svc-custom",
          service_tier: tier,
          deploy_age_hours: deployAge,
        }),
      });
      if (!res.ok) {
        setError(`Could not author the incident (${res.status}).`);
        return;
      }
      const data = await res.json();
      setAuthored({ incident_id: data.incident_id, expect: data.expect });
    } catch {
      setError("Could not reach the API.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.composer}>
      <div className={styles.intro}>
        <div className={styles.introTitle}>Test it on data it has never seen</div>
        <div className={styles.introBody}>
          Everything below writes a real incident into the same tables the seeded
          ones live in. Before you run it, the system states what policy says
          should happen, so you can check the agent against the rules rather than
          against a script.
        </div>
      </div>

      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          <span className={styles.label}>What happened</span>
          <select className={styles.select} value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
          <span className={styles.hint}>{KINDS.find((k) => k.value === kind)?.hint}</span>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Severity</span>
          <select
            className={styles.select}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>
          <span className={styles.hint}>reported urgency, not a policy input</span>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Service</span>
          <input
            className={styles.input}
            value={serviceName}
            onChange={(e) => setServiceName(e.target.value)}
            placeholder="svc-judge-test"
            maxLength={64}
          />
          <span className={styles.hint}>any name; created if it does not exist</span>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Service tier</span>
          <select
            className={styles.select}
            value={tier}
            onChange={(e) => setTier(Number(e.target.value))}
          >
            <option value={1}>Tier 1 — most critical</option>
            <option value={2}>Tier 2</option>
            <option value={3}>Tier 3</option>
          </select>
          <span className={styles.hint}>
            policy refuses to self-remediate above a configured tier
          </span>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Last deploy was {deployAge}h ago</span>
          <input
            className={styles.range}
            type="range"
            min={0}
            max={72}
            step={1}
            value={deployAge}
            onChange={(e) => setDeployAge(Number(e.target.value))}
          />
          <span className={styles.hint}>
            the rollback window is evaluated against this; cross it and automatic
            rollback should be refused
          </span>
        </label>

        <button type="submit" className={styles.create} disabled={busy}>
          <Plus size={14} />
          {busy ? "Creating…" : "Create incident"}
        </button>
      </form>

      {error && <div className={styles.error}>{error}</div>}

      {authored && (
        <div className={styles.result}>
          <div className={styles.resultId}>{authored.incident_id}</div>
          <div className={styles.predictionLabel}>Before you run it, policy says</div>
          <div className={styles.prediction}>{authored.expect}</div>
          <button
            className={styles.run}
            onClick={() => onRun(`Remediate ${authored.incident_id}`)}
          >
            <Play size={14} />
            Run the agent on it
          </button>
          <div className={styles.resultHint}>
            The agent is not told any of this. It reads the incident, reads
            policy, and decides.
          </div>
        </div>
      )}
    </div>
  );
}
