"use client";

import { useEffect, useRef, useState } from "react";
import { Play, Pause, RotateCcw } from "lucide-react";
import type { Explanation, StepEvent } from "./runTypes";
import { narrate } from "./narrate";
import styles from "./SystemHeart.module.css";

/**
 * The whole machine, with something actually moving through it.
 *
 * A diagram of an architecture is a drawing of a claim. This one is fed by
 * runs that really happened: pick one and watch the path it took, hop by hop,
 * with the reason for each turn read out of the audit trail rather than
 * invented for the animation.
 *
 * The shape is the argument. Knowledge leaves the store on the left, gets
 * used along the top, and — when the top lane refuses it — the work drops to
 * the bottom lane and comes back into the store on the right. A policy change
 * enters underneath and invalidates the store without touching the lanes at
 * all. That circulation is the project, and it is very hard to say in a
 * paragraph.
 */

type NodeId =
  | "store"
  | "incident"
  | "embed"
  | "vector"
  | "freshness"
  | "precond"
  | "replay"
  | "planner"
  | "tools"
  | "episode"
  | "compiler"
  | "policy"
  | "cascade"
  | "outbox"
  | "worker";

type NodeMood = "idle" | "active" | "pass" | "refuse" | "miss";

interface Hop {
  /** Edge to travel to get here. Omitted for the first hop. */
  edge?: string;
  node: NodeId;
  mood: NodeMood;
  /** One sentence, in the system's voice, about what happens here. */
  say: string;
  /** The evidence, when there is any. Monospace, smaller. */
  detail?: string;
  ms?: number;
}

// --- geometry -------------------------------------------------------------
// Wide rather than tall on purpose: the narration underneath is half the
// point, and a square diagram pushed it below the fold on a laptop.
const W = 1300;
const H = 470;
const NH = 52;

const N: Record<NodeId, { x: number; y: number; w: number; label: string; sub: string }> = {
  store: { x: 430, y: 14, w: 440, label: "Runbook store", sub: "playbooks + playbook_deps" },
  incident: { x: 30, y: 130, w: 120, label: "Incident", sub: "arrives" },
  embed: { x: 180, y: 130, w: 120, label: "Embed", sub: "1024 dims" },
  vector: { x: 340, y: 130, w: 170, label: "Vector search", sub: "pb_embed_idx" },
  freshness: { x: 550, y: 130, w: 170, label: "Freshness join", sub: "still true?" },
  precond: { x: 760, y: 130, w: 170, label: "Preconditions", sub: "applies here?" },
  replay: { x: 970, y: 130, w: 150, label: "Replay", sub: "no planner" },
  planner: { x: 340, y: 270, w: 170, label: "Planner", sub: "where tokens go" },
  tools: { x: 550, y: 270, w: 170, label: "Tools", sub: "the real world" },
  episode: { x: 760, y: 270, w: 170, label: "Episode", sub: "what it did" },
  compiler: { x: 970, y: 270, w: 150, label: "Compiler", sub: "+ provenance" },
  policy: { x: 30, y: 396, w: 120, label: "Policy", sub: "rules" },
  cascade: { x: 180, y: 396, w: 180, label: "Cascade", sub: "4 writes" },
  outbox: { x: 400, y: 396, w: 160, label: "Outbox", sub: "transactional" },
  worker: { x: 600, y: 396, w: 160, label: "Worker", sub: "the slow half" },
};

const cx = (id: NodeId) => N[id].x + N[id].w / 2;
const cy = (id: NodeId) => N[id].y + NH / 2;
const right = (id: NodeId) => N[id].x + N[id].w;

/** Straight along the row. */
const across = (a: NodeId, b: NodeId) => `M ${right(a)} ${cy(a)} L ${N[b].x} ${cy(b)}`;

/** Falling out of the top lane into the bottom one. */
const drop = (a: NodeId) =>
  `M ${cx(a)} ${N[a].y + NH} C ${cx(a)} ${N[a].y + 110}, ${cx("planner")} ${N.planner.y - 80}, ${cx("planner")} ${N.planner.y}`;

const EDGES: Record<string, string> = {
  "store->vector": `M ${N.store.x + 50} ${N.store.y + NH} C ${N.store.x + 50} 105, ${cx("vector")} 92, ${cx("vector")} ${N.vector.y}`,
  "incident->embed": across("incident", "embed"),
  "embed->vector": across("embed", "vector"),
  "vector->freshness": across("vector", "freshness"),
  "freshness->precond": across("freshness", "precond"),
  "precond->replay": across("precond", "replay"),
  "vector->planner": drop("vector"),
  "freshness->planner": drop("freshness"),
  "precond->planner": drop("precond"),
  "replay->tools": `M ${cx("replay")} ${N.replay.y + NH} C ${cx("replay")} ${N.replay.y + 110}, ${right("tools") + 60} ${N.tools.y - 50}, ${right("tools")} ${cy("tools")}`,
  "planner->tools": across("planner", "tools"),
  "tools->episode": across("tools", "episode"),
  "episode->compiler": across("episode", "compiler"),
  "compiler->store": `M ${cx("compiler")} ${N.compiler.y} C ${cx("compiler")} 190, ${right("store") + 20} 110, ${right("store") - 50} ${N.store.y + NH}`,
  "policy->cascade": across("policy", "cascade"),
  "cascade->outbox": across("cascade", "outbox"),
  "outbox->worker": across("outbox", "worker"),
  "worker->store": `M ${right("worker")} ${cy("worker")} C 1050 ${cy("worker")}, 1250 ${cy("worker")}, 1250 250 C 1250 60, 1000 40, ${right("store")} 40`,
};

// --- turning a real run into hops -----------------------------------------

function runHops(explain: Explanation, steps: StepEvent[]): Hop[] {
  const reason = explain.decision.reason;
  const pb = explain.playbook;
  const inc = explain.incident;
  const hops: Hop[] = [
    {
      node: "incident",
      mood: "active",
      say: "An incident arrives.",
      detail: inc
        ? `${inc.incident_id} · ${inc.kind} · ${inc.service_name} tier ${inc.service_tier}`
        : explain.input,
    },
    {
      edge: "incident->embed",
      node: "embed",
      mood: "active",
      say: "Its text becomes a vector, so similarity means what it means rather than which words were used.",
      detail: "1024 dimensions, unit norm",
    },
    {
      edge: "embed->vector",
      node: "vector",
      mood: reason === "no_match" ? "miss" : "pass",
      say:
        reason === "no_match"
          ? "Nothing in memory is close enough. There is nothing to reuse."
          : "Nearest neighbour found, by L2 distance over the vector index.",
      detail: pb ? `${pb.name} v${pb.version}` : "no candidate within the distance threshold",
    },
  ];

  if (reason === "no_match") {
    hops.push({
      edge: "vector->planner",
      node: "planner",
      mood: "active",
      say: "So it plans from scratch. Every step from here costs a call to the model.",
      detail: "the expensive path",
    });
  } else {
    const stale = explain.decision.stale_deps?.[0];
    hops.push({
      edge: "vector->freshness",
      node: "freshness",
      mood: reason === "refused_stale" ? "refuse" : "pass",
      say:
        reason === "refused_stale"
          ? "Refused. A rule this runbook was compiled against has moved since."
          : "Every rule it cites is still at head, so it is still true.",
      detail: stale
        ? `${stale.rule_key}: compiled against v${stale.compiled_against}, head is v${stale.head}`
        : "d.rule_version = r.version for every edge",
    });

    if (reason === "refused_stale") {
      hops.push({
        edge: "freshness->planner",
        node: "planner",
        mood: "active",
        say: "It falls back to planning from scratch, under the policy that exists now.",
        detail: "stale knowledge is worse than none: it would have acted confidently",
      });
    } else {
      const failed = explain.decision.failed_preconditions?.[0];
      hops.push({
        edge: "freshness->precond",
        node: "precond",
        mood: reason === "refused_precondition" ? "refuse" : "pass",
        say:
          reason === "refused_precondition"
            ? "Refused. It is a real procedure, just not one that covers this incident."
            : "Its preconditions hold for this incident.",
        detail: failed ?? "kind, state, tier and deploy age all satisfied",
      });

      if (reason === "refused_precondition") {
        hops.push({
          edge: "precond->planner",
          node: "planner",
          mood: "active",
          say: "Planned from scratch rather than forcing a near miss.",
          detail: "the expensive path",
        });
      } else {
        hops.push({
          edge: "precond->replay",
          node: "replay",
          mood: "pass",
          say: "Replayed. The planner is not called once — this is where the saving is.",
          detail: `${explain.episode?.steps ?? steps.length} steps, bound to this incident`,
        });
      }
    }
  }

  const cameFromReplay = hops[hops.length - 1].node === "replay";
  hops.push({
    edge: cameFromReplay ? "replay->tools" : "planner->tools",
    node: "tools",
    mood: "active",
    say: "The steps run against the world, each one checked for interrupts and given an idempotency key.",
    detail: steps.length
      ? steps.map((s) => narrate(s.tool, s.args, s.output).question).join("  →  ")
      : `${explain.episode?.steps ?? 0} tool calls`,
  });

  hops.push({
    edge: "tools->episode",
    node: "episode",
    mood: "active",
    say: "The run is recorded, call by call.",
    detail: explain.episode
      ? `${explain.episode.steps} steps · ${explain.episode.latency_ms.toLocaleString()}ms · ${explain.episode.tokens.toLocaleString()} tokens`
      : "no episode written",
  });

  if (explain.learned) {
    hops.push({
      edge: "episode->compiler",
      node: "compiler",
      mood: "pass",
      say: "A cold success is worth keeping, so it is compiled into a procedure — together with the rule versions it leaned on.",
      detail: `${explain.learned.name} v${explain.learned.version}`,
    });
    hops.push({
      edge: "compiler->store",
      node: "store",
      mood: "pass",
      say: "Back into the store, with its provenance. That provenance is what lets it be taken away again later.",
      detail: "one playbooks row, one playbook_deps row per cited rule",
    });
  }

  return hops;
}

function cascadeHops(last: {
  rule_key: string;
  from_version: number;
  to_version: number;
  writes: number | null;
  runbooks_stale: number;
}): Hop[] {
  return [
    {
      node: "policy",
      mood: "active",
      say: "Someone changes a rule.",
      detail: `${last.rule_key} v${last.from_version} → v${last.to_version}`,
    },
    {
      edge: "policy->cascade",
      node: "cascade",
      mood: "pass",
      say: "The transaction is four writes, and it is four whether one runbook depends on this rule or a hundred thousand.",
      detail: "close the old version · insert the new · one outbox row · one audit row",
    },
    {
      edge: "cascade->outbox",
      node: "outbox",
      mood: "active",
      say: "The fan-out is deliberately not in the transaction. One row is queued instead.",
      detail: "same queue whether a human pressed the button or the cascade did",
    },
    {
      edge: "outbox->worker",
      node: "worker",
      mood: "active",
      say: "A worker picks it up afterwards to demote badges, interrupt running tasks and queue re-learns.",
      detail: "if all of that fails, nothing incorrect happens — it is only tidying",
    },
    {
      edge: "worker->store",
      node: "store",
      mood: "refuse",
      say:
        last.runbooks_stale > 0
          ? `${last.runbooks_stale} runbook${last.runbooks_stale === 1 ? "" : "s"} stopped being trusted — and not one of them was written to.`
          : "Nothing is stale right now: whatever depended on this rule has since been re-learned or cleared away. The question is answered fresh on every read, so the answer can change without anything being updated.",
      detail: "staleness is the join disagreeing, not a column anyone maintains",
    },
  ];
}

// --- component -------------------------------------------------------------

const HOP_MS = 1100;

export function SystemHeart({
  hops,
  title,
  onReplay,
}: {
  hops: Hop[];
  title: string;
  onReplay: () => void;
}) {
  const [at, setAt] = useState(0);
  const [playing, setPlaying] = useState(true);
  /**
   * "It is all mocked" only sounds damning while the boundary is invisible.
   * Exactly one node in this diagram is simulated, so it says so, and says
   * what it would be instead.
   */
  const [seam, setSeam] = useState(false);
  const dotRef = useRef<SVGCircleElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const raf = useRef<number | null>(null);

  // Restart whenever a different run is chosen.
  const key = hops.map((h) => h.node).join(",") + title;
  const [seenKey, setSeenKey] = useState(key);
  if (key !== seenKey) {
    setSeenKey(key);
    setAt(0);
    setPlaying(true);
  }

  /**
   * The dot is moved by writing attributes rather than by state, so travelling
   * an edge costs no React renders. Only arriving somewhere is a render, and
   * that is once a second rather than sixty times.
   */
  useEffect(() => {
    if (!playing || at >= hops.length) return;
    const hop = hops[at];
    const svg = svgRef.current;
    const dot = dotRef.current;
    const path = hop.edge && svg ? (svg.querySelector(`#e-${cssId(hop.edge)}`) as SVGPathElement | null) : null;
    const total = hop.ms ?? HOP_MS;
    const started = performance.now();

    const tick = (now: number) => {
      const t = Math.min((now - started) / total, 1);
      if (dot && path) {
        const p = path.getPointAtLength(path.getTotalLength() * ease(t));
        dot.setAttribute("cx", String(p.x));
        dot.setAttribute("cy", String(p.y));
        dot.setAttribute("opacity", "1");
      } else if (dot) {
        dot.setAttribute("cx", String(cx(hop.node)));
        dot.setAttribute("cy", String(cy(hop.node)));
        dot.setAttribute("opacity", "1");
      }
      if (t < 1) {
        raf.current = requestAnimationFrame(tick);
      } else {
        raf.current = window.setTimeout(() => setAt((i) => i + 1), 900) as unknown as number;
      }
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) {
        cancelAnimationFrame(raf.current);
        clearTimeout(raf.current);
      }
    };
  }, [at, playing, hops]);

  const done = at >= hops.length;
  const current = hops[Math.min(at, hops.length - 1)];
  const visited = new Map<NodeId, NodeMood>();
  hops.slice(0, Math.min(at + 1, hops.length)).forEach((h) => visited.set(h.node, h.mood));
  const travelled = new Set(hops.slice(0, Math.min(at + 1, hops.length)).map((h) => h.edge).filter(Boolean) as string[]);

  return (
    <div className={styles.heart}>
      <div className={styles.bar}>
        <span className={styles.title}>{title}</span>
        <span className={styles.progress}>
          {Math.min(at + 1, hops.length)} / {hops.length}
        </span>
        <span className={styles.spacer} />
        <button
          className={styles.ctl}
          onClick={() => (done ? (setAt(0), setPlaying(true)) : setPlaying((v) => !v))}
        >
          {done ? <RotateCcw size={13} /> : playing ? <Pause size={13} /> : <Play size={13} />}
          {done ? "Again" : playing ? "Pause" : "Play"}
        </button>
        <button className={styles.ctl} onClick={onReplay}>
          <RotateCcw size={13} />
          Another run
        </button>
      </div>

      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className={styles.svg} role="img" aria-label="System diagram">
        <defs>
          <marker id="sh-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
          </marker>
          <filter id="sh-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <text x={30} y={106} className={styles.lane}>
          reuse what is already known
        </text>
        <text x={30} y={246} className={styles.lane}>
          work it out, and keep the answer
        </text>
        <text x={30} y={372} className={styles.lane}>
          take it all away again
        </text>

        {Object.entries(EDGES).map(([id, d]) => (
          <path
            key={id}
            id={`e-${cssId(id)}`}
            d={d}
            fill="none"
            markerEnd="url(#sh-arrow)"
            className={`${styles.edge} ${travelled.has(id) ? styles.edgeOn : ""} ${
              travelled.has(id) && id.endsWith("->planner") ? styles.edgeRefuse : ""
            } ${travelled.has(id) && id === "worker->store" ? styles.edgeRefuse : ""}`}
          />
        ))}

        {(Object.keys(N) as NodeId[]).map((id) => {
          const n = N[id];
          const mood = visited.get(id) ?? "idle";
          const here = !done && current?.node === id;
          return (
            <g
              key={id}
              className={`${styles.node} ${styles[`m_${mood}`]} ${here ? styles.here : ""} ${
                id === "tools" ? styles.seamNode : ""
              }`}
              onClick={id === "tools" ? () => setSeam((v) => !v) : undefined}
            >
              <rect x={n.x} y={n.y} width={n.w} height={NH} rx={9} className={styles.box} />
              <text x={n.x + n.w / 2} y={n.y + 22} className={styles.nlabel}>
                {n.label}
              </text>
              <text x={n.x + n.w / 2} y={n.y + 38} className={styles.nsub}>
                {n.sub}
              </text>
              {id === "tools" && (
                <>
                  <circle cx={n.x + n.w - 13} cy={n.y + 13} r={8} className={styles.seamDot} />
                  <text x={n.x + n.w - 13} y={n.y + 17} className={styles.seamMark}>
                    ?
                  </text>
                </>
              )}
            </g>
          );
        })}

        <circle ref={dotRef} r={7} className={styles.dot} filter="url(#sh-glow)" opacity="0" />
      </svg>

      {seam && (
        <div className={styles.seam}>
          <div className={styles.seamTitle}>
            Tools is the only simulated component on this diagram
          </div>
          <div className={styles.seamGrid}>
            <div>
              <code>get_incident</code>
              <span>→ PagerDuty, Datadog, Sentry</span>
            </div>
            <div>
              <code>apply_remediation</code>
              <span>→ kubectl rollout undo, ArgoCD, your deploy API</span>
            </div>
            <div>
              <code>notify_oncall</code>
              <span>→ Slack, PagerDuty</span>
            </div>
            <div className={styles.seamReal}>
              <code>get_rules</code>
              <span>not simulated — your real policy table</span>
            </div>
            <div className={styles.seamReal}>
              <code>check_remediation_eligibility</code>
              <span>not simulated — deterministic Python over those rules, no model</span>
            </div>
          </div>
          <p className={styles.seamNote}>
            Five functions in one file, and swapping them is the whole
            integration. Bounded on purpose: the spec requires the demo world to
            have zero external dependencies, precisely so a live call to someone
            else&rsquo;s API can never hang this while you are watching it.
            Everything else on this diagram — retrieval, the provenance join, the
            cascade, the outbox — is running against a real CockroachDB cluster
            right now.
          </p>
        </div>
      )}

      <div className={styles.say}>
        <div className={styles.sayText}>{current?.say}</div>
        {current?.detail && <div className={styles.sayDetail}>{current.detail}</div>}
      </div>
    </div>
  );
}

const cssId = (s: string) => s.replace(/[^a-z]/gi, "");
const ease = (t: number) => 1 - Math.pow(1 - t, 3);

export { runHops, cascadeHops };
export type { Hop };
