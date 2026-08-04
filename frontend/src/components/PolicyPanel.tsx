"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./PolicyPanel.module.css";

export interface Rule {
  rule_key: string;
  version: number;
  domain: string;
  body: string;
  params: Record<string, any>;
  changed_by: string;
}

export interface ImpactedPlaybook {
  playbook_id: string;
  name: string;
  version: number;
  status_cache: string;
}

export interface ImpactedTask {
  task_id: string;
  input: string;
  elapsed_ms: number;
}

export interface ImpactResult {
  rule_key: string;
  old_version: number;
  new_version: number;
  impacted_playbooks: ImpactedPlaybook[];
  impacted_tasks: ImpactedTask[];
  committed: boolean;
}

export interface ReplayResult {
  summary: string;
  incidents_examined: number;
  net_change: number;
  newly_allowed: { incident_id: string; kind: string; service: string }[];
  newly_blocked: { incident_id: string; kind: string; service: string }[];
}

interface PolicyPanelProps {
  rules: Rule[];
  onSimulateImpact?: (ruleKey: string, params: Record<string, any>) => Promise<ImpactResult>;
  onCommitChange?: (ruleKey: string, params: Record<string, any>) => Promise<void>;
  /** T2.2 — counterfactual replay against historical incidents. */
  onReplay?: (ruleKey: string, params: Record<string, any>) => Promise<ReplayResult>;
  // For the demo step ③, we might want to highlight a row
  highlightRuleKey?: string;
  /** Parameters carried over from an insight recommendation. */
  prefillParams?: Record<string, any>;
}

export function PolicyPanel({
  rules,
  onSimulateImpact,
  onCommitChange,
  onReplay,
  highlightRuleKey,
  prefillParams,
}: PolicyPanelProps) {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editParams, setEditParams] = useState<Record<string, any>>({});
  const [impact, setImpact] = useState<ImpactResult | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [replay, setReplay] = useState<ReplayResult | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Monotonic id so a slow earlier response cannot overwrite a newer one —
  // typing "24" fires for "2" then "24", and they can land out of order.
  const requestSeq = useRef(0);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleFocus = (ruleKey: string, params: Record<string, any>) => {
    if (editingKey !== ruleKey) {
      setEditingKey(ruleKey);
      setEditParams(params);
      setImpact(null);
      setReplay(null);
    }
  };

  /** An insight recommended concrete parameters — open that rule pre-filled. */
  useEffect(() => {
    if (!highlightRuleKey || !prefillParams) return;
    const rule = rules.find((r) => r.rule_key === highlightRuleKey);
    if (!rule) return;

    setEditingKey(highlightRuleKey);
    setEditParams({ ...rule.params, ...prefillParams });
    setImpact(null);
    setReplay(null);

    const merged = { ...rule.params, ...prefillParams };
    onSimulateImpact?.(highlightRuleKey, merged).then(setImpact).catch(() => {});
    onReplay?.(highlightRuleKey, merged).then(setReplay).catch(() => {});
  }, [highlightRuleKey, prefillParams, rules, onSimulateImpact, onReplay]);

  const handleChange = (ruleKey: string, paramKey: string, val: string) => {
    // An empty field must stay empty. Number("") is 0, so the previous
    // coercion silently turned a cleared input into a committed `0`.
    const trimmed = val.trim();
    const newVal =
      trimmed === "" || isNaN(Number(trimmed)) ? val : Number(trimmed);

    const newParams = { ...editParams, [paramKey]: newVal };
    setEditParams(newParams);

    if (!onSimulateImpact) return;

    // Debounced: this hits /dry-run, and one request per keystroke both floods
    // the API and makes the preview flicker between intermediate values.
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setSimulating(true);
    const seq = ++requestSeq.current;

    debounceRef.current = setTimeout(() => {
      onSimulateImpact(ruleKey, newParams)
        .then((res) => {
          if (seq === requestSeq.current) setImpact(res);
        })
        .catch(() => {
          if (seq === requestSeq.current) setImpact(null);
        })
        .finally(() => {
          if (seq === requestSeq.current) setSimulating(false);
        });

      // Counterfactual runs alongside: "which runbooks go stale" and "what
      // would actually have happened differently" are different questions.
      onReplay?.(ruleKey, newParams)
        .then((res) => {
          if (seq === requestSeq.current) setReplay(res);
        })
        .catch(() => {
          if (seq === requestSeq.current) setReplay(null);
        });
    }, 350);
  };

  const handleSaveClick = () => {
    setShowModal(true);
  };

  const [committing, setCommitting] = useState(false);

  const handleCommit = async () => {
    if (!editingKey || !onCommitChange || committing) return;
    setCommitting(true);
    try {
      await onCommitChange(editingKey, editParams);
      setShowModal(false);
      setEditingKey(null);
      setImpact(null);
    } finally {
      setCommitting(false);
    }
  };

  return (
    <>
      <div className={styles.panel}>
        <div className={styles.header}>
          <span className={styles.title}>Policy Engine</span>
          <span className={styles.title}>{rules.length} active rules</span>
        </div>

        <div className={styles.list}>
          {rules.map((rule) => {
            const isEditing = editingKey === rule.rule_key;
            const currentParams = isEditing ? editParams : rule.params;
            const isHighlighted = highlightRuleKey === rule.rule_key;

            return (
              <div 
                key={rule.rule_key} 
                className={styles.ruleRow}
                style={isHighlighted ? { borderColor: "var(--accent)" } : undefined}
                id={`rule-${rule.rule_key}`}
              >
                <div className={styles.ruleHeader}>
                  <span className={styles.ruleKey}>{rule.rule_key}</span>
                  <span className={styles.ruleVer}>v{rule.version}</span>
                </div>
                
                <div className={styles.ruleBody}>
                  {/* Highlight variables in body text */}
                  {rule.body.split(/({[^}]+})/).map((part, i) => 
                    part.startsWith("{") ? (
                      <span key={i} style={{ color: "var(--text)" }}>{part}</span>
                    ) : (
                      <span key={i}>{part}</span>
                    )
                  )}
                </div>

                <div className={styles.paramsForm}>
                  {Object.entries(rule.params).map(([pk, pv]) => (
                    <div key={pk} className={styles.paramInputGroup}>
                      <span className={styles.paramLabel}>{pk}</span>
                      <input
                        className={styles.paramInput}
                        type="text"
                        value={currentParams[pk] ?? pv}
                        onFocus={() => handleFocus(rule.rule_key, rule.params)}
                        onChange={(e) => handleChange(rule.rule_key, pk, e.target.value)}
                      />
                    </div>
                  ))}

                  {isEditing && impact && (
                    <div className={styles.impactPreview}>
                      {impact.impacted_playbooks.length > 0 ? (
                        <>
                          <span className={styles.impactText}>
                            {impact.impacted_playbooks.length} active runbooks depend on this policy
                          </span>
                          <div className={styles.impactList}>
                            {impact.impacted_playbooks.map(pb => (
                              <span key={pb.playbook_id} className={styles.impactItem}>
                                {pb.name} v{pb.version}
                              </span>
                            ))}
                          </div>
                        </>
                      ) : (
                        <span className={styles.impactTextZero}>No runbooks depend on this yet.</span>
                      )}
                    </div>
                  )}

                  {isEditing && replay && (
                    <div className={styles.impactPreview}>
                      <span className={styles.impactText}>{replay.summary}</span>
                      {(replay.newly_allowed.length > 0 ||
                        replay.newly_blocked.length > 0) && (
                        <div className={styles.impactList}>
                          {replay.newly_allowed.map((i) => (
                            <span
                              key={`a-${i.incident_id}`}
                              className={styles.impactItem}
                              title={`${i.kind} on ${i.service} — would now be auto-remediated`}
                            >
                              +{i.incident_id}
                            </span>
                          ))}
                          {replay.newly_blocked.map((i) => (
                            <span
                              key={`b-${i.incident_id}`}
                              className={styles.impactItem}
                              title={`${i.kind} on ${i.service} — would now be blocked`}
                            >
                              −{i.incident_id}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {isEditing && (
                    <div className={styles.actions}>
                      <button 
                        className={styles.btn}
                        onClick={() => {
                          setEditingKey(null);
                          setImpact(null);
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        className={styles.btnSave}
                        onClick={handleSaveClick}
                        disabled={!impact || simulating}
                      >
                        {simulating ? "Checking impact…" : "Review changes"}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {showModal && editingKey && impact && (
        <div className={styles.modalOverlay}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              Change {editingKey} to v{impact.new_version}?
            </div>
            
            <div className={styles.modalBody}>
              <div className={styles.modalCols}>
                <div className={styles.modalCol}>
                  <div className={styles.modalColTitle}>Runbooks that will be quarantined</div>
                  {impact.impacted_playbooks.length > 0 ? (
                    <div className={styles.modalList}>
                      {impact.impacted_playbooks.map(pb => (
                        <div key={pb.playbook_id} className={styles.modalItem}>
                          <span className={styles.modalItemName}>{pb.name}</span>
                          <span className={styles.modalItemStatus}>Suspect</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span style={{ fontSize: 13, color: "var(--text-dim)" }}>None</span>
                  )}
                </div>
                
                <div className={styles.modalCol}>
                  <div className={styles.modalColTitle}>Running tasks that will be interrupted</div>
                  {impact.impacted_tasks.length > 0 ? (
                    <div className={styles.modalList}>
                      {impact.impacted_tasks.map(t => (
                        <div key={t.task_id} className={styles.modalItem}>
                          <span className={styles.modalItemName}>{t.input}</span>
                          <span className={styles.modalItemStatus}>Interrupted</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span style={{ fontSize: 13, color: "var(--text-dim)" }}>None</span>
                  )}
                </div>
              </div>
            </div>

            <div className={styles.modalFooter}>
              <button 
                className={styles.btn} 
                onClick={() => setShowModal(false)}
              >
                Cancel
              </button>
              <button
                className={styles.btnSave}
                onClick={handleCommit}
                disabled={committing}
              >
                {committing ? "Committing…" : "Commit change"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
