"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Check, X, ArrowRight } from "lucide-react";
import styles from "./ArchitecturePanel.module.css";

/**
 * The machinery, answering for itself.
 *
 * The agent is the ordinary part of this project — plenty of things can call a
 * tool in a loop. What is not ordinary is that every learned procedure is
 * pinned to the policy versions it was derived from, so a rule change can
 * invalidate all of them in a transaction whose size does not depend on how
 * much has been learned.
 *
 * That is a claim about data, and a diagram of it would just be a drawing. So
 * every number on this screen is read out of the cluster the viewer has been
 * driving for the last five minutes.
 */

interface Rule {
  rule_key: string;
  version: number;
  domain: string;
}

interface Runbook {
  playbook_id: string;
  name: string;
  version: number;
  status_cache: string;
  confidence: number;
}

interface Edge {
  playbook_id: string;
  rule_key: string;
  pinned_version: number;
  head_version: number;
  is_stale: boolean;
}

interface Arch {
  counts: Record<string, number>;
  rules: Rule[];
  runbooks: Runbook[];
  edges: Edge[];
  last_cascade: {
    rule_key: string;
    from_version: number;
    to_version: number;
    writes: number | null;
    runbooks_stale: number;
    actor: string;
    at: string;
  } | null;
  outbox: { kind: string; pending: number; processed: number }[];
}

export function ArchitecturePanel({
  apiBase,
  refreshKey,
}: {
  apiBase: string;
  refreshKey: number;
}) {
  const [data, setData] = useState<Arch | null>(null);
  const [index, setIndex] = useState<{
    uses_index: boolean;
    plan: string;
    error?: string;
  } | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiBase}/architecture`);
        if (res.ok && !cancelled) setData(await res.json());
      } catch {
        /* the empty state below is the honest fallback */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, refreshKey]);

  const checkIndex = useCallback(async () => {
    setChecking(true);
    try {
      const res = await fetch(`${apiBase}/architecture/index`);
      if (res.ok) setIndex(await res.json());
    } catch {
      setIndex({ uses_index: false, plan: "", error: "could not reach the API" });
    } finally {
      setChecking(false);
    }
  }, [apiBase]);

  if (!data) {
    return <div className={styles.panel}>
      <div className={styles.empty}>Reading the cluster…</div>
    </div>;
  }

  const staleEdges = data.edges.filter((e) => e.is_stale).length;

  return (
    <div className={styles.panel}>
      <div className={styles.lead}>
        <h2 className={styles.leadTitle}>
          Learned knowledge, pinned to the policy it was derived from
        </h2>
        <p className={styles.leadBody}>
          An agent that solves incidents is ordinary. What is not ordinary is
          being able to answer, at any moment, <b>which of the things it learned
          are still true</b> — and to stop trusting all of them at once, in a
          transaction that does not grow with how much has been learned.
        </p>
      </div>

      {/* --- the cascade, with the two numbers side by side ---------------- */}
      <section className={styles.section}>
        <h3 className={styles.h3}>The unlearn transaction</h3>
        {data.last_cascade ? (
          <div className={styles.cascade}>
            <div className={styles.cascadeRule}>
              <span className={styles.ruleKey}>{data.last_cascade.rule_key}</span>
              <span className={styles.vOld}>v{data.last_cascade.from_version}</span>
              <ArrowRight size={13} />
              <span className={styles.vNew}>v{data.last_cascade.to_version}</span>
            </div>
            <div className={styles.cascadeNumbers}>
              <div className={styles.big}>
                <span className={styles.bigValue}>
                  {data.last_cascade.writes ?? "—"}
                </span>
                <span className={styles.bigLabel}>
                  writes in the
                  <br />
                  transaction
                </span>
              </div>
              <span className={styles.versus}>against</span>
              <div className={styles.big}>
                <span className={styles.bigValue}>
                  {data.last_cascade.runbooks_stale}
                </span>
                <span className={styles.bigLabel}>
                  runbooks it left
                  <br />
                  stale, right now
                </span>
              </div>
            </div>
            <p className={styles.note}>
              Close the old version, insert the new one, one outbox row, one audit
              row. That is the whole write set, and it is the same four whether one
              runbook depends on this rule or a hundred thousand. Nothing marked
              those runbooks stale, because nothing had to.
            </p>
          </div>
        ) : (
          <div className={styles.empty}>
            No rule has been changed yet. Commit one in Policy and the numbers
            appear here.
          </div>
        )}
      </section>

      {/* --- provenance ---------------------------------------------------- */}
      <section className={styles.section}>
        <h3 className={styles.h3}>
          Provenance
          <span className={styles.h3note}>
            {data.edges.length} edges in <code>playbook_deps</code>
            {staleEdges > 0 && <span className={styles.staleCount}> · {staleEdges} stale</span>}
          </span>
        </h3>

        {data.edges.length === 0 ? (
          <div className={styles.empty}>
            Nothing learned yet. Fix an incident and the first edges appear.
          </div>
        ) : (
          <div className={styles.graph}>
            <div className={styles.column}>
              <div className={styles.columnHead}>Policy, at head</div>
              {data.rules.map((r) => (
                <div key={r.rule_key} className={styles.ruleNode}>
                  <span className={styles.nodeName}>{r.rule_key}</span>
                  <span className={styles.nodeVer}>v{r.version}</span>
                </div>
              ))}
            </div>

            <div className={styles.column}>
              <div className={styles.columnHead}>Runbooks, and what they cite</div>
              {data.runbooks.map((pb) => {
                const mine = data.edges.filter((e) => e.playbook_id === pb.playbook_id);
                return (
                  <div key={pb.playbook_id} className={styles.pbNode}>
                    <div className={styles.pbHead}>
                      <span className={styles.nodeName}>{pb.name}</span>
                      <span className={styles.nodeVer}>v{pb.version}</span>
                      <span className={`${styles.status} ${styles[`st_${pb.status_cache}`] ?? ""}`}>
                        {pb.status_cache}
                      </span>
                    </div>
                    {mine.length === 0 ? (
                      <div className={styles.noDeps}>no provenance recorded</div>
                    ) : (
                      mine.map((e) => (
                        <div
                          key={e.rule_key}
                          className={`${styles.edge} ${e.is_stale ? styles.edgeStale : ""}`}
                        >
                          <span className={styles.edgeKey}>{e.rule_key}</span>
                          <span className={styles.edgeVer}>
                            pinned v{e.pinned_version}
                          </span>
                          <span className={styles.edgeVerdict}>
                            {e.is_stale ? (
                              <>
                                <X size={11} /> head is v{e.head_version}
                              </>
                            ) : (
                              <>
                                <Check size={11} /> at head
                              </>
                            )}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <p className={styles.note}>
          Staleness is never written down. It is this comparison, run fresh every
          time anyone asks: <code>d.rule_version != r.version</code> where{" "}
          <code>r.valid_to IS NULL</code>. A stored flag can drift out of sync
          with the thing it describes. A join cannot.
        </p>
      </section>

      {/* --- retrieval ------------------------------------------------------ */}
      <section className={styles.section}>
        <h3 className={styles.h3}>
          Retrieval
          <span className={styles.h3note}>1024-dimension vectors, L2 distance</span>
        </h3>
        <div className={styles.indexRow}>
          <button className={styles.check} onClick={checkIndex} disabled={checking}>
            <RefreshCw size={13} className={checking ? styles.spin : ""} />
            {checking ? "Asking the database…" : "Show me the query plan"}
          </button>
          {index && (
            <span className={index.uses_index ? styles.good : styles.bad}>
              {index.uses_index ? (
                <>
                  <Check size={13} /> vector index in use
                </>
              ) : (
                <>
                  <X size={13} /> index not in the plan
                </>
              )}
            </span>
          )}
        </div>
        {index?.plan && <pre className={styles.plan}>{index.plan}</pre>}
        <p className={styles.note}>
          Worth running yourself rather than taking on trust: a single extra
          predicate on this query is enough to drop the index and full-scan the
          table, and nothing about the results would look different.
        </p>
      </section>

      {/* --- outbox --------------------------------------------------------- */}
      <section className={styles.section}>
        <h3 className={styles.h3}>
          Transactional outbox
          <span className={styles.h3note}>how the slow half is kept honest</span>
        </h3>
        {data.outbox.length === 0 ? (
          <div className={styles.empty}>Nothing queued yet.</div>
        ) : (
          <div className={styles.outbox}>
            {data.outbox.map((o) => (
              <div key={o.kind} className={styles.job}>
                <span className={styles.jobKind}>{o.kind}</span>
                <span className={styles.jobDone}>{o.processed} processed</span>
                {o.pending > 0 && <span className={styles.jobPending}>{o.pending} pending</span>}
              </div>
            ))}
          </div>
        )}
        <p className={styles.note}>
          The cascade commits one row here rather than doing the fan-out itself.
          A worker picks it up afterwards to demote badges, interrupt running
          tasks and queue re-learns. If every bit of that fails, the freshness
          join is already refusing the stale runbooks — so correctness never
          depends on the queue being drained.
        </p>
      </section>

      {/* --- the ledger ------------------------------------------------------ */}
      <section className={styles.section}>
        <h3 className={styles.h3}>In the cluster right now</h3>
        <div className={styles.counts}>
          <Count label="rules at head" value={data.counts.rules_head} />
          <Count label="rule versions ever" value={data.counts.rule_versions} />
          <Count label="runbooks" value={data.counts.runbooks} />
          <Count label="provenance edges" value={data.counts.provenance_edges} />
          <Count label="episodes" value={data.counts.episodes} />
          <Count label="tasks" value={data.counts.tasks} />
        </div>
      </section>
    </div>
  );
}

function Count({ label, value }: { label: string; value?: number }) {
  return (
    <div className={styles.count}>
      <span className={styles.countValue}>{value ?? 0}</span>
      <span className={styles.countLabel}>{label}</span>
    </div>
  );
}
