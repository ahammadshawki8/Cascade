"use client";

import { useState } from "react";
import { X, ArrowRight } from "lucide-react";
import styles from "./RightRail.module.css";

export interface ApprovalRequest {
  id: string;
  incident_id: string;
  action: string;
  confidence: number;
  reason: string;
  time: string;
}

export interface Insight {
  id: string;
  title: string;
  body: string;
  time: string;
  suggested_rule_key?: string;
  suggested_params?: Record<string, any>;
}

interface RightRailProps {
  approvals: ApprovalRequest[];
  insights: Insight[];
  onClose: () => void;
  onApprove: (id: string) => void;
  onReject: (id: string, reason: string) => void;
  onReviewPolicy: (ruleKey: string, params: Record<string, any>) => void;
  /** Rendered as a full view rather than a floating overlay panel. */
  embedded?: boolean;
}

export function RightRail({
  approvals,
  insights,
  onClose,
  onApprove,
  onReject,
  onReviewPolicy,
  embedded = false,
}: RightRailProps) {
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const handleRejectClick = (id: string) => {
    if (rejectingId === id && rejectReason.trim()) {
      onReject(id, rejectReason);
      setRejectingId(null);
      setRejectReason("");
    } else {
      setRejectingId(id);
    }
  };

  return (
    <div className={`${styles.rail} ${embedded ? styles.railEmbedded : ""}`}>
      <div className={styles.header}>
        <span className={styles.title}>
          {embedded ? "Approvals & Insights" : "Extensions"}
        </span>
        {!embedded && (
          <button className={styles.closeBtn} onClick={onClose}>
            <X size={16} />
          </button>
        )}
      </div>

      <div className={styles.body}>
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Approvals ({approvals.length})</div>
          
          {approvals.length === 0 ? (
            <div className={styles.emptyState}>No pending approvals.</div>
          ) : (
            approvals.map((req) => (
              <div key={req.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.cardTitle}>{req.incident_id}</span>
                  <span className={styles.cardTime}>{req.time}</span>
                </div>
                
                <div className={styles.approvalDetails}>
                  <div className={styles.approvalDetailRow}>
                    <span className={styles.approvalLabel}>Action</span>
                    <span className={styles.approvalVal}>{req.action}</span>
                  </div>
                  <div className={styles.approvalDetailRow}>
                    <span className={styles.approvalLabel}>Confidence</span>
                    <span className={styles.approvalScore}>{Math.round(req.confidence * 100)}%</span>
                  </div>
                </div>

                <div className={styles.cardBody}>
                  {req.reason}
                </div>

                <div className={styles.approvalActions}>
                  {rejectingId !== req.id && (
                    <button 
                      className={`${styles.btn} ${styles.btnApprove}`}
                      onClick={() => onApprove(req.id)}
                    >
                      Approve
                    </button>
                  )}
                  <button 
                    className={`${styles.btn} ${styles.btnReject}`}
                    onClick={() => handleRejectClick(req.id)}
                  >
                    Reject
                  </button>
                </div>

                {rejectingId === req.id && (
                  <>
                    <input
                      autoFocus
                      className={styles.rejectInput}
                      placeholder="Reason for rejection..."
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && rejectReason.trim()) {
                          handleRejectClick(req.id);
                        } else if (e.key === "Escape") {
                          setRejectingId(null);
                          setRejectReason("");
                        }
                      }}
                    />
                    <button 
                      className={styles.rejectSubmit}
                      onClick={() => handleRejectClick(req.id)}
                      disabled={!rejectReason.trim()}
                    >
                      Submit Rejection
                    </button>
                  </>
                )}
              </div>
            ))
          )}
        </div>

        <div className={styles.section}>
          <div className={styles.sectionTitle}>Insights ({insights.length})</div>
          
          {insights.length === 0 ? (
            <div className={styles.emptyState}>No new insights.</div>
          ) : (
            insights.map((insight) => (
              <div key={insight.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.cardTitle}>{insight.title}</span>
                  <span className={styles.cardTime}>{insight.time}</span>
                </div>
                
                {/* Rendered as text, never as HTML. Insight summaries can be
                    phrased by a model, so injecting them into the DOM would be
                    a script-injection path straight from model output. */}
                <div className={styles.cardBody}>{insight.body}</div>

                {insight.suggested_rule_key && insight.suggested_params && (
                  <button 
                    className={styles.insightAction}
                    onClick={() => onReviewPolicy(insight.suggested_rule_key!, insight.suggested_params!)}
                  >
                    Review policy <ArrowRight size={14} />
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
