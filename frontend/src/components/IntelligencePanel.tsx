"use client";

import { useEffect, useState, useCallback } from "react";
import styles from "./IntelligencePanel.module.css";

export interface Savings {
  available: boolean;
  message?: string;
  tokens_avoided?: number;
  usd_saved?: number;
  seconds_avoided?: number;
  engineer_hours_saved?: number;
  incidents_automated?: number;
  speedup?: number | null;
  basis?: string;
}

export interface GraphNode {
  id: string;
  type: "rule" | "playbook" | "task";
  label: string;
  status?: string;
  version?: number;
  confidence?: number;
  focused?: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: string;
  stale: boolean;
}

export interface AntiPlaybook {
  anti_id: string;
  incident_kind: string;
  attempted_action: string | null;
  failure_reason: string;
  occurrences: number;
}

type Tab = "savings" | "graph" | "memory" | "history";

interface Props {
  apiBase: string;
  refreshKey: number;
}

/**
 * The three Tier-2 read-only surfaces plus the savings ledger. Grouped into one
 * panel because they answer the same question from different angles: what has
 * this system actually learned, and what has that been worth?
 */
export function IntelligencePanel({ apiBase, refreshKey }: Props) {
  const [tab, setTab] = useState<Tab>("savings");
  const [savings, setSavings] = useState<Savings | null>(null);
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [anti, setAnti] = useState<AntiPlaybook[]>([]);
  const [minutesAgo, setMinutesAgo] = useState(10);
  const [history, setHistory] = useState<any>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, g, a] = await Promise.all([
        fetch(`${apiBase}/savings`).then((r) => (r.ok ? r.json() : null)),
        fetch(`${apiBase}/graph`).then((r) => (r.ok ? r.json() : null)),
        fetch(`${apiBase}/anti-playbooks`).then((r) => (r.ok ? r.json() : null)),
      ]);
      if (s) setSavings(s);
      if (g) setGraph(g);
      if (a) setAnti(a.anti_playbooks ?? []);
    } catch {}
  }, [apiBase]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const loadHistory = useCallback(
    async (minutes: number) => {
      setLoadingHistory(true);
      try {
        const res = await fetch(`${apiBase}/timetravel?minutes_ago=${minutes}`);
        setHistory(res.ok ? await res.json() : null);
      } catch {
        setHistory(null);
      } finally {
        setLoadingHistory(false);
      }
    },
    [apiBase]
  );

  useEffect(() => {
    if (tab === "history") loadHistory(minutesAgo);
  }, [tab, minutesAgo, loadHistory]);

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>Memory Intelligence</span>
        <div className={styles.tabs}>
          {(["savings", "graph", "memory", "history"] as Tab[]).map((t) => (
            <button
              key={t}
              className={`${styles.tab} ${tab === t ? styles.tabActive : ""}`}
              onClick={() => setTab(t)}
            >
              {t === "history" ? "time travel" : t}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.body}>
        {tab === "savings" && <SavingsView savings={savings} />}
        {tab === "graph" && <GraphView graph={graph} />}
        {tab === "memory" && <MemoryView anti={anti} />}
        {tab === "history" && (
          <HistoryView
            history={history}
            minutesAgo={minutesAgo}
            setMinutesAgo={setMinutesAgo}
            loading={loadingHistory}
          />
        )}
      </div>
    </div>
  );
}

function SavingsView({ savings }: { savings: Savings | null }) {
  if (!savings) return <div className={styles.empty}>Loading…</div>;
  if (!savings.available) {
    return <div className={styles.empty}>{savings.message}</div>;
  }

  return (
    <div className={styles.savings}>
      <div className={styles.savingsGrid}>
        <Stat label="Tokens avoided" value={(savings.tokens_avoided ?? 0).toLocaleString()} />
        <Stat label="Cost saved" value={`$${(savings.usd_saved ?? 0).toFixed(2)}`} />
        <Stat
          label="Engineer hours"
          value={`${(savings.engineer_hours_saved ?? 0).toFixed(1)}h`}
        />
        <Stat label="Incidents automated" value={String(savings.incidents_automated ?? 0)} />
      </div>
      {/* "0.4× faster" is not a thing. Below 1× guided was slower, and the
          honest reading is the inverse — say that instead of dressing it up. */}
      {savings.speedup != null && savings.speedup >= 1 && (
        <div className={styles.headline}>
          Guided execution is <strong>{savings.speedup}×</strong> faster than
          learning from scratch.
        </div>
      )}
      {savings.speedup != null && savings.speedup < 1 && (
        <div className={styles.headline}>
          Guided execution is currently{" "}
          <strong>{(1 / savings.speedup).toFixed(1)}× slower</strong> than the
          cold path. Expected without a live model: exploring pays no LLM
          latency here, while the guided path still runs precondition and
          parameter checks.
        </div>
      )}
      <div className={styles.basis}>{savings.basis}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

/**
 * Deliberately a dependency-free layered layout rather than a physics
 * simulation: rules on the left, the runbooks they govern in the middle, the
 * work underneath on the right. Stale edges are the whole point, so they are
 * drawn red and dashed.
 */
function GraphView({ graph }: { graph: { nodes: GraphNode[]; edges: GraphEdge[] } | null }) {
  if (!graph || graph.nodes.length === 0) {
    return <div className={styles.empty}>No provenance graph yet — run an incident.</div>;
  }

  const columns: Record<string, GraphNode[]> = { rule: [], playbook: [], task: [] };
  for (const node of graph.nodes) columns[node.type]?.push(node);

  const width = 640;
  const height = Math.max(
    220,
    Math.max(columns.rule.length, columns.playbook.length, columns.task.length) * 34 + 40
  );
  const xFor = { rule: 80, playbook: width / 2, task: width - 80 };

  const position: Record<string, { x: number; y: number }> = {};
  for (const [type, nodes] of Object.entries(columns)) {
    const spacing = height / (nodes.length + 1);
    nodes.forEach((node, i) => {
      position[node.id] = {
        x: xFor[type as keyof typeof xFor],
        y: spacing * (i + 1),
      };
    });
  }

  return (
    <div className={styles.graphWrap}>
      <svg viewBox={`0 0 ${width} ${height}`} className={styles.graph}>
        {graph.edges.map((edge, i) => {
          const a = position[edge.source];
          const b = position[edge.target];
          if (!a || !b) return null;
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              className={edge.stale ? styles.edgeStale : styles.edge}
            />
          );
        })}
        {graph.nodes.map((node) => {
          const p = position[node.id];
          if (!p) return null;
          return (
            <g key={node.id}>
              <circle
                cx={p.x}
                cy={p.y}
                r={6}
                className={`${styles.node} ${styles[`node_${node.type}`]} ${
                  node.status === "suspect" || node.status === "invalidated"
                    ? styles.nodeStale
                    : ""
                }`}
              />
              <text
                x={node.type === "task" ? p.x - 12 : p.x + 12}
                y={p.y + 4}
                textAnchor={node.type === "task" ? "end" : "start"}
                className={styles.nodeLabel}
              >
                {node.label.length > 20 ? `${node.label.slice(0, 20)}…` : node.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className={styles.legend}>
        <span><i className={styles.dotRule} /> policy</span>
        <span><i className={styles.dotPlaybook} /> runbook</span>
        <span><i className={styles.dotTask} /> task</span>
        <span><i className={styles.dotStale} /> stale dependency</span>
      </div>
    </div>
  );
}

function MemoryView({ anti }: { anti: AntiPlaybook[] }) {
  if (anti.length === 0) {
    return (
      <div className={styles.empty}>
        Nothing learned to avoid yet. Failed runs are recorded here so the agent
        doesn&apos;t rediscover the same dead end.
      </div>
    );
  }
  return (
    <div className={styles.list}>
      {anti.map((item) => (
        <div key={item.anti_id} className={styles.antiCard}>
          <div className={styles.antiHead}>
            <span className={styles.antiKind}>{item.incident_kind}</span>
            {item.attempted_action && (
              <span className={styles.antiAction}>{item.attempted_action}</span>
            )}
            <span className={styles.antiCount}>
              seen {item.occurrences}×
            </span>
          </div>
          <div className={styles.antiReason}>{item.failure_reason}</div>
        </div>
      ))}
    </div>
  );
}

function HistoryView({
  history,
  minutesAgo,
  setMinutesAgo,
  loading,
}: {
  history: any;
  minutesAgo: number;
  setMinutesAgo: (n: number) => void;
  loading: boolean;
}) {
  return (
    <div className={styles.history}>
      <div className={styles.scrubber}>
        <label htmlFor="tt">Rewind</label>
        <input
          id="tt"
          type="range"
          min={1}
          max={120}
          value={minutesAgo}
          onChange={(e) => setMinutesAgo(Number(e.target.value))}
        />
        <span className={styles.scrubberValue}>−{minutesAgo}m</span>
      </div>

      {loading && <div className={styles.empty}>Reading MVCC history…</div>}

      {!loading && history && !history.available && (
        <div className={styles.empty}>{history.message}</div>
      )}

      {!loading && history?.available && (
        <>
          <div className={styles.historyNote}>{history.note}</div>
          <div className={styles.historyCols}>
            <div>
              <div className={styles.historyTitle}>
                Runbooks ({history.playbooks.length})
              </div>
              {history.playbooks.length === 0 ? (
                <div className={styles.empty}>none yet</div>
              ) : (
                history.playbooks.map((p: any) => (
                  <div key={p.playbook_id} className={styles.historyRow}>
                    <span>{p.name} v{p.version}</span>
                    <span className={styles.historyStatus}>{p.status_cache}</span>
                  </div>
                ))
              )}
            </div>
            <div>
              <div className={styles.historyTitle}>Policy ({history.rules.length})</div>
              {history.rules.map((r: any) => (
                <div key={r.rule_key} className={styles.historyRow}>
                  <span>{r.rule_key}</span>
                  <span className={styles.historyStatus}>v{r.version}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
