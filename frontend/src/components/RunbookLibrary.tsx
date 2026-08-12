"use client";

import { useState } from "react";
import styles from "./RunbookLibrary.module.css";

export interface RuleCitation {
  rule_key: string;
  version: number;
  is_stale: boolean;
  justification: string;
}

export interface PlaybookSpec {
  steps: { tool: string; args: Record<string, string> }[];
  preconditions: string[];
  rule_citations: RuleCitation[];
}

export type PlaybookStatus =
  | "active"
  | "candidate"
  | "suspect"
  | "invalidated"
  | "rejected";

export interface Playbook {
  playbook_id: string;
  name: string;
  version: number;
  status_cache: PlaybookStatus;
  confidence: number;
  usage_count: number;
  success_count: number;
  failure_count: number;
  supersedes?: string | null;
  spec: PlaybookSpec;
}

interface RunbookLibraryProps {
  playbooks: Playbook[];
  /**
   * A cold run has finished and its runbook is still being compiled.
   *
   * Compilation is asynchronous — the run writes an outbox row, a worker picks
   * it up, and the runbook lands seconds later. Nothing said so, so the obvious
   * next move (immediately run a second incident) happened before there was
   * anything to reuse, and the headline demo step silently failed. The library
   * looking empty is exactly when a viewer most needs to be told to wait.
   */
  compiling?: boolean;
  onRelearn?: (id: string) => void | Promise<void>;
  onViewEpisodes?: (id: string) => void;
}

export function RunbookLibrary({
  playbooks,
  compiling = false,
  onRelearn,
  onViewEpisodes,
}: RunbookLibraryProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case "active": return styles.statusActive;
      case "candidate": return styles.statusCandidate;
      // 'rejected' is terminal (confidence fell below 0.20) and 'invalidated'
      // means superseded — both read as dead, so they share the invalid style.
      case "invalidated":
      case "rejected": return styles.statusInvalid;
      case "suspect": return styles.statusSuspect;
      default: return "";
    }
  };

  const statusHint = (status: string) => {
    switch (status) {
      case "suspect":
        return "Quarantined pending re-check — a related policy changed.";
      case "invalidated":
        return "Superseded by a newer version learned under the current rules.";
      case "rejected":
        return "Retired — confidence fell below the 0.20 floor.";
      case "candidate":
        return "Learned but unproven — needs 3 successes to be promoted.";
      case "active":
        return "Proven against current policy.";
      default:
        return "";
    }
  };

  return (
    <div className={styles.library}>
      <div className={styles.header}>
        <span className={styles.title}>Runbook Library</span>
        <span className={styles.title}>{playbooks.length} entries</span>
      </div>

      <div className={styles.list}>
        {compiling && (
          <div className={styles.compiling}>
            <span className={styles.compilingDots}>
              <i /> <i /> <i />
            </span>
            <div>
              <div className={styles.compilingTitle}>Writing a runbook from that run</div>
              <div className={styles.compilingBody}>
                Give it a few seconds. Until it lands there is nothing to reuse,
                and the next incident would explore from scratch again.
              </div>
            </div>
          </div>
        )}

        {playbooks.length === 0 && !compiling && (
          <div className={styles.empty}>
            Nothing learned yet. Fix an incident from the Inbox and the runbook
            compiled from it will appear here.
          </div>
        )}

        {playbooks.map((pb) => {
          const isExpanded = expandedId === pb.playbook_id;
          const statusClass = getStatusClass(pb.status_cache);

          return (
            <div key={pb.playbook_id} className={styles.card}>
              <div 
                className={styles.cardHeader} 
                onClick={() => toggleExpand(pb.playbook_id)}
              >
                <div className={styles.nameBlock}>
                  <span className={styles.name}>{pb.name}</span>
                  <span className={styles.version}>v{pb.version}</span>
                </div>
                
                <div className={styles.stats}>
                  {pb.usage_count} uses · {pb.success_count} ✓ · {pb.failure_count} ✗
                </div>

                <div className={`${styles.statusPill} ${statusClass}`}>
                  <div className={styles.statusDot} />
                  <span className={styles.statusText}>{pb.status_cache}</span>
                  {statusHint(pb.status_cache) && (
                    <div className={styles.tooltip}>{statusHint(pb.status_cache)}</div>
                  )}
                </div>
              </div>
              
              <div className={styles.confidenceBar}>
                <div
                  className={`${styles.confidenceFill} ${statusClass}`}
                  style={{ width: `${pb.confidence * 100}%` }}
                />
              </div>

              {/* A quarantined runbook has exactly one useful next action, and
                  it was buried behind expanding the card — so the moment the
                  demo builds up to was followed by a dead end. Surfaced on the
                  collapsed card, with the reason next to it. */}
              {(pb.status_cache === "suspect" || pb.status_cache === "invalidated") &&
                onRelearn && (
                  <div className={styles.quarantine}>
                    <span className={styles.quarantineText}>
                      Quarantined: a rule it was built on changed. Re-learn to
                      rebuild it under current policy as v{pb.version + 1}.
                    </span>
                    <button
                      className={styles.quarantineBtn}
                      disabled={busyId === pb.playbook_id}
                      onClick={async (e) => {
                        e.stopPropagation();
                        setBusyId(pb.playbook_id);
                        try {
                          await onRelearn(pb.playbook_id);
                        } finally {
                          setBusyId(null);
                        }
                      }}
                    >
                      {busyId === pb.playbook_id ? "Queueing…" : "Re-learn"}
                    </button>
                  </div>
                )}

              {isExpanded && (
                <div className={styles.cardBody}>
                  <div className={styles.section}>
                    <div className={styles.sectionTitle}>Steps</div>
                    <div className={styles.stepList}>
                      {pb.spec.steps.map((step, idx) => (
                        <div key={idx} className={styles.stepItem}>
                          <span className={styles.stepNum}>{(idx + 1).toString().padStart(2, "0")}</span>
                          <span>{step.tool}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className={styles.section}>
                    <div className={styles.sectionTitle}>Preconditions</div>
                    <div className={styles.precondList}>
                      {pb.spec.preconditions.map((pre, idx) => (
                        <div key={idx} className={styles.precondItem}>{pre}</div>
                      ))}
                    </div>
                  </div>

                  <div className={styles.section}>
                    <div className={styles.sectionTitle}>Provenance</div>
                    <div className={styles.provenanceList}>
                      {pb.spec.rule_citations.map((rule, idx) => (
                        <div key={idx} className={styles.provRow}>
                          <div className={`${styles.provDot} ${rule.is_stale ? styles.provStale : styles.provFresh}`} />
                          <span className={styles.provKey}>{rule.rule_key}</span>
                          <span className={styles.provVer}>v{rule.version}</span>
                          <span className={styles.provJust}>{rule.justification}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className={styles.actions}>
                    {/* Offered for suspect too: that is the state a runbook lands
                        in the moment a policy changes, and re-learning it is
                        exactly what an operator wants to do next. */}
                    {(pb.status_cache === "invalidated" ||
                      pb.status_cache === "suspect") &&
                      onRelearn && (
                        <button
                          className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                          disabled={busyId === pb.playbook_id}
                          onClick={async (e) => {
                            e.stopPropagation();
                            setBusyId(pb.playbook_id);
                            try {
                              await onRelearn(pb.playbook_id);
                            } finally {
                              setBusyId(null);
                            }
                          }}
                        >
                          {busyId === pb.playbook_id ? "Queueing…" : "Re-learn"}
                        </button>
                      )}
                    {onViewEpisodes && (
                      <button
                        className={styles.actionBtn}
                        onClick={(e) => {
                          e.stopPropagation();
                          onViewEpisodes(pb.playbook_id);
                        }}
                      >
                        View episodes
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
