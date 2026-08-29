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

/**
 * Start from an intent, not from a blank form.
 *
 * Complete freedom over six fields is freedom to build something that proves
 * nothing — a combination outside the demo's decision space, where the outcome
 * is uninteresting and looks like a bug. Each preset is a question worth
 * asking, and every one of them lands on a different gate. Custom stays right
 * there for anyone who wants it.
 */
const PRESETS: {
  id: string;
  question: string;
  because: string;
  values: { kind: string; severity: string; service_tier: number; deploy_age_hours: number };
}[] = [
  {
    id: "allowed",
    question: "A fix it should allow",
    because: "recent deploy on a tier policy permits, so expect a rollback",
    values: { kind: "bad_deploy", severity: "P2", service_tier: 2, deploy_age_hours: 2 },
  },
  {
    id: "tier",
    question: "A fix policy forbids",
    because: "tier 1 is too critical to touch automatically, so expect an escalation",
    values: { kind: "bad_deploy", severity: "P1", service_tier: 1, deploy_age_hours: 2 },
  },
  {
    id: "window",
    question: "Too old to roll back",
    because: "past the rollback window, so rollback must be refused",
    values: { kind: "bad_deploy", severity: "P2", service_tier: 2, deploy_age_hours: 30 },
  },
  {
    id: "other",
    question: "A different kind of failure",
    because: "no deploy to undo, so it has to find another way",
    values: { kind: "error_spike", severity: "P2", service_tier: 2, deploy_age_hours: 0 },
  },
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
  const [preset, setPreset] = useState<string | null>(null);
  const [showFields, setShowFields] = useState(false);

  const applyPreset = (id: string) => {
    const p = PRESETS.find((x) => x.id === id);
    if (!p) return;
    setPreset(id);
    setAuthored(null);
    setKind(p.values.kind);
    setSeverity(p.values.severity);
    setTier(p.values.service_tier);
    setDeployAge(p.values.deploy_age_hours);
  };

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

      <div className={styles.presets}>
        <div className={styles.presetsTitle}>What do you want to test?</div>
        {PRESETS.map((p) => (
          <button
            key={p.id}
            className={`${styles.preset} ${preset === p.id ? styles.presetOn : ""}`}
            onClick={() => applyPreset(p.id)}
          >
            <span className={styles.presetQ}>{p.question}</span>
            <span className={styles.presetWhy}>{p.because}</span>
          </button>
        ))}
        <button
          className={styles.presetToggle}
          onClick={() => setShowFields((v) => !v)}
          aria-expanded={showFields}
        >
          {showFields ? "Hide the fields" : "Custom — set the fields yourself"}
        </button>
      </div>

      <form
        className={styles.form}
        onSubmit={submit}
        style={{ display: showFields || preset ? "flex" : "none" }}
      >
        {/* A preset already answers all six of these. Showing them anyway is
            the clutter the presets exist to remove, so they stay collapsed
            until someone actually wants to change something. */}
        <div
          className={styles.fields}
          style={{ display: showFields ? "flex" : "none" }}
        >
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

        </div>

        {preset && !showFields && (
          <div className={styles.summary}>
            {KINDS.find((k) => k.value === kind)?.label} on a tier {tier} service,
            {kind === "bad_deploy" ? ` deployed ${deployAge}h ago` : " no deploy involved"}
          </div>
        )}

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
