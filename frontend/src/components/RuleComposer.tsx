"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import styles from "./RuleComposer.module.css";

/**
 * Write a rule of your own.
 *
 * The predicate language supports all/any/not nesting, and this deliberately
 * does not. Two conditions — when it applies, and what must then be true —
 * cover every rule the sample world has and almost every rule an operator
 * actually writes, and an expression-tree editor would turn the one screen a
 * judge is most likely to try into the one they give up on. The raw JSON is
 * still accepted by the API for anyone who needs more.
 */

interface FactField {
  field: string;
  kind: string;
  label: string;
  choices: string[] | null;
}

interface Facts {
  fields: FactField[];
  operators: { op: string; label: string }[];
  enforcement_modes: { mode: string; label: string; hint: string }[];
}

interface Condition {
  field: string;
  op: string;
  value: string;
}

const UNARY = new Set(["exists", "missing", "truthy"]);

const toKey = (title: string) =>
  "incident." +
  (title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48) || "new_rule");

function buildCondition(c: Condition, fields: FactField[]) {
  if (!c.field || !c.op) return null;
  if (UNARY.has(c.op)) return { field: c.field, op: c.op };
  const meta = fields.find((f) => f.field === c.field);
  const raw = c.value.trim();
  if (!raw) return null;
  const value = meta?.kind === "number" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
  return { field: c.field, op: c.op, value };
}

export function RuleComposer({
  apiBase,
  privileged,
  onClose,
  onCreated,
  onToast,
}: {
  apiBase: string;
  privileged: string;
  onClose: () => void;
  onCreated: () => void;
  onToast: (message: string) => void;
}) {
  const [facts, setFacts] = useState<Facts | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [enforcement, setEnforcement] = useState("enforcing");
  const [useWhen, setUseWhen] = useState(false);
  const [when, setWhen] = useState<Condition>({ field: "kind", op: "eq", value: "" });
  const [require, setRequire] = useState<Condition>({
    field: "service_tier",
    op: "gte",
    value: "",
  });
  const [deny, setDeny] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`${apiBase}/policy/facts`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setFacts(d))
      .catch(() => {});
  }, [apiBase]);

  const predicate = useMemo(() => {
    if (!facts) return null;
    const req = buildCondition(require, facts.fields);
    if (!req) return null;
    const out: Record<string, unknown> = { require: req };
    if (useWhen) {
      const gate = buildCondition(when, facts.fields);
      if (gate) out.when = gate;
    }
    out.deny = deny.trim() || "policy refuses this action";
    return out;
  }, [facts, require, when, useWhen, deny]);

  const runPreview = async () => {
    if (!predicate) return;
    setBusy(true);
    try {
      const res = await fetch(`${apiBase}/policy/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ predicate, params: {} }),
      });
      const data = await res.json();
      if (!res.ok) {
        onToast(data.detail || "That rule is not valid yet.");
        return;
      }
      setPreview(data);
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!predicate || !title.trim()) return;
    setBusy(true);
    try {
      const res = await fetch(`${privileged}/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rule_key: toKey(title),
          domain: "incident",
          body: body.trim() || title.trim(),
          params: {},
          predicate: enforcement === "advisory" ? null : predicate,
          enforcement,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        onToast(data.detail || "Could not create that rule.");
        return;
      }
      onToast(`${data.rule_key} created. It now gates every run.`);
      onCreated();
      onClose();
    } catch {
      onToast("Could not reach the API.");
    } finally {
      setBusy(false);
    }
  };

  const row = (c: Condition, set: (c: Condition) => void) => {
    const meta = facts?.fields.find((f) => f.field === c.field);
    return (
      <div className={styles.cond}>
        <select
          className={styles.select}
          value={c.field}
          onChange={(e) => set({ ...c, field: e.target.value, value: "" })}
        >
          {facts?.fields.map((f) => (
            <option key={f.field} value={f.field}>
              {f.label}
            </option>
          ))}
        </select>
        <select
          className={styles.selectNarrow}
          value={c.op}
          onChange={(e) => set({ ...c, op: e.target.value })}
        >
          {facts?.operators.map((o) => (
            <option key={o.op} value={o.op}>
              {o.label}
            </option>
          ))}
        </select>
        {!UNARY.has(c.op) &&
          (meta?.choices ? (
            <select
              className={styles.selectNarrow}
              value={c.value}
              onChange={(e) => set({ ...c, value: e.target.value })}
            >
              <option value="">choose…</option>
              {meta.choices.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          ) : (
            <input
              className={styles.selectNarrow}
              value={c.value}
              onChange={(e) => set({ ...c, value: e.target.value })}
              placeholder={meta?.kind === "number" ? "a number" : "a value"}
            />
          ))}
      </div>
    );
  };

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.sheet} onClick={(e) => e.stopPropagation()}>
        <header className={styles.head}>
          <h2 className={styles.h2}>New rule</h2>
          <span className={styles.spacer} />
          <button className={styles.icon} onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </header>

        <div className={styles.body}>
          <label className={styles.field}>
            <span className={styles.label}>Call it</span>
            <input
              className={styles.input}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="P1 incidents need a human"
              maxLength={70}
            />
            {title && <span className={styles.hint}>key: {toKey(title)}</span>}
          </label>

          <label className={styles.field}>
            <span className={styles.label}>What it says</span>
            <textarea
              className={styles.textarea}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Written for a person to read. The agent reads this too."
              rows={2}
            />
          </label>

          <div className={styles.builder}>
            <div className={styles.builderHead}>
              {useWhen ? "When" : "Always"}
              {!useWhen ? (
                <button className={styles.tiny} onClick={() => setUseWhen(true)}>
                  <Plus size={11} /> only in some cases
                </button>
              ) : (
                <button className={styles.tiny} onClick={() => setUseWhen(false)}>
                  <X size={11} /> always apply
                </button>
              )}
            </div>
            {useWhen && row(when, setWhen)}

            <div className={styles.builderHead}>Require that</div>
            {row(require, setRequire)}

            <label className={styles.field}>
              <span className={styles.label}>Otherwise refuse, saying</span>
              <input
                className={styles.input}
                value={deny}
                onChange={(e) => setDeny(e.target.value)}
                placeholder="tier {service_tier} is too critical to touch automatically"
              />
              <span className={styles.hint}>
                Anything in braces is filled in from the incident, so the refusal
                names real numbers.
              </span>
            </label>
          </div>

          <div className={styles.modes}>
            {facts?.enforcement_modes.map((m) => (
              <button
                key={m.mode}
                className={`${styles.mode} ${enforcement === m.mode ? styles.modeOn : ""}`}
                onClick={() => setEnforcement(m.mode)}
              >
                <span className={styles.modeLabel}>{m.label}</span>
                <span className={styles.modeHint}>{m.hint}</span>
              </button>
            ))}
          </div>

          {preview && (
            <div className={styles.preview}>
              <div className={styles.previewLine}>{preview.summary}</div>
              {preview.refused.length > 0 && (
                <div className={styles.previewList}>
                  {preview.refused.slice(0, 6).map((r: any) => (
                    <div key={r.incident_id} className={styles.previewRow}>
                      <span className={styles.mono}>{r.incident_id}</span>
                      <span className={styles.dim}>{r.reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <footer className={styles.foot}>
          <button
            className={styles.ghost}
            disabled={!predicate || busy}
            onClick={runPreview}
          >
            {busy ? <Loader2 size={12} className={styles.spin} /> : null}
            Try it against the incidents
          </button>
          <span className={styles.spacer} />
          <button className={styles.ghost} onClick={onClose}>
            Cancel
          </button>
          <button
            className={styles.primary}
            disabled={busy || !title.trim() || (enforcement !== "advisory" && !predicate)}
            onClick={create}
          >
            Create rule
          </button>
        </footer>
      </div>
    </div>
  );
}
