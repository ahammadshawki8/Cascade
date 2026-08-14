"use client";

import { useState } from "react";
import { Loader2, X, FileText, Check } from "lucide-react";
import styles from "./ImportProcedure.module.css";

/**
 * Bring a runbook you already have under governance.
 *
 * Two steps, and the second is the one that matters. Linking a runbook's
 * sentences to the policy they depend on is model output, and model output does
 * not get to write provenance unreviewed — a wrong citation would not fail
 * loudly, it would just quietly make a procedure look governed while never
 * going stale. So every proposal shows the sentence it came from, and a person
 * confirms it.
 */

const SAMPLE = `# Rolling back a bad checkout deploy

Use this when checkout error rates spike right after a release.

1. Confirm the spike started within 10 minutes of the deploy.
2. Only roll back if the deploy went out in the last 24 hours; past that, escalate instead.
3. Never auto-roll-back a tier 1 service. Page the service owner.
4. Apply exactly one automated action, then stop and observe.
5. Post the outcome to the on-call channel.`;

interface Proposal {
  rule_key: string;
  rule_version: number;
  evidence: string;
  confidence: number;
  rule_body: string;
}

export function ImportProcedure({
  apiBase,
  privileged,
  onClose,
  onImported,
  onToast,
}: {
  apiBase: string;
  privileged: string;
  onClose: () => void;
  onImported: () => void;
  onToast: (message: string) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [parsed, setParsed] = useState<any>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());

  const parse = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${apiBase}/procedures/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (!res.ok) {
        onToast(data.detail || "Could not read that.");
        return;
      }
      setParsed(data);
      // Pre-select what the extractor was confident about. Anything weaker is
      // left for a person to opt into rather than to notice and remove.
      setChosen(
        new Set(
          (data.citations ?? [])
            .filter((c: Proposal) => c.confidence >= 0.6)
            .map((c: Proposal) => c.rule_key)
        )
      );
    } catch {
      onToast("Could not reach the API.");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const citations = (parsed.citations ?? [])
        .filter((c: Proposal) => chosen.has(c.rule_key))
        .map((c: Proposal) => ({
          rule_key: c.rule_key,
          rule_version: c.rule_version,
          evidence: c.evidence,
        }));
      const res = await fetch(`${privileged}/procedures`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: parsed.name,
          goal: parsed.goal,
          steps: parsed.steps,
          citations,
          source_ref: "pasted",
          origin: "imported",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        onToast(data.detail || "Could not import that.");
        return;
      }
      onToast(
        `${data.name} imported. It now goes stale when any of its ${citations.length} cited rule(s) change.`
      );
      onImported();
      onClose();
    } catch {
      onToast("Could not reach the API.");
    } finally {
      setBusy(false);
    }
  };

  const toggle = (key: string) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.sheet} onClick={(e) => e.stopPropagation()}>
        <header className={styles.head}>
          <FileText size={15} strokeWidth={1.9} />
          <h2 className={styles.h2}>
            {parsed ? "Confirm what it depends on" : "Import a runbook you already have"}
          </h2>
          <span className={styles.spacer} />
          <button className={styles.icon} onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </header>

        {!parsed ? (
          <>
            <div className={styles.body}>
              <p className={styles.lead}>
                Paste a runbook in whatever shape it is already in. Cascade reads
                it, then proposes which policy rules it depends on. Nothing is
                saved until you confirm.
              </p>
              <textarea
                className={styles.textarea}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste Markdown, a numbered list, or plain prose…"
                rows={14}
                spellCheck={false}
              />
              <button className={styles.tiny} onClick={() => setText(SAMPLE)}>
                Use an example
              </button>
            </div>
            <footer className={styles.foot}>
              <span className={styles.spacer} />
              <button className={styles.ghost} onClick={onClose}>
                Cancel
              </button>
              <button
                className={styles.primary}
                disabled={busy || text.trim().length < 20}
                onClick={parse}
              >
                {busy && <Loader2 size={12} className={styles.spin} />}
                Read it
              </button>
            </footer>
          </>
        ) : (
          <>
            <div className={styles.body}>
              <div className={styles.summary}>
                <div className={styles.name}>{parsed.name}</div>
                <div className={styles.dim}>
                  {parsed.steps.length} step{parsed.steps.length === 1 ? "" : "s"}
                </div>
              </div>

              <p className={styles.lead}>
                These are the rules it looks like this runbook depends on, each
                with the sentence it was drawn from. Confirming one creates a
                provenance edge: that is what makes this procedure go amber the
                day someone changes the rule.
              </p>

              {(parsed.citations ?? []).length === 0 && (
                <div className={styles.warn}>
                  Nothing in this runbook matched a policy rule. You can still
                  import it, but with no citations it can never be found stale,
                  which is the only thing Cascade would be adding.
                </div>
              )}

              {(parsed.citations ?? []).map((c: Proposal) => (
                <button
                  key={c.rule_key}
                  className={`${styles.cite} ${chosen.has(c.rule_key) ? styles.citeOn : ""}`}
                  onClick={() => toggle(c.rule_key)}
                >
                  <span className={styles.tick}>
                    {chosen.has(c.rule_key) && <Check size={12} strokeWidth={3} />}
                  </span>
                  <span className={styles.citeBody}>
                    <span className={styles.citeHead}>
                      <code>{c.rule_key}</code>
                      <span className={styles.ver}>v{c.rule_version}</span>
                      <span className={styles.conf}>
                        {Math.round(c.confidence * 100)}% confident
                      </span>
                    </span>
                    <span className={styles.evidence}>&ldquo;{c.evidence}&rdquo;</span>
                    <span className={styles.ruleBody}>{c.rule_body}</span>
                  </span>
                </button>
              ))}
            </div>
            <footer className={styles.foot}>
              <button className={styles.ghost} onClick={() => setParsed(null)}>
                Back
              </button>
              <span className={styles.spacer} />
              <span className={styles.count}>
                {chosen.size} citation{chosen.size === 1 ? "" : "s"}
              </span>
              <button
                className={styles.primary}
                disabled={busy || chosen.size === 0}
                onClick={save}
              >
                {busy && <Loader2 size={12} className={styles.spin} />}
                Import
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
