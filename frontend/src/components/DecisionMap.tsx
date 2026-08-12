"use client";

import styles from "./DecisionMap.module.css";

/**
 * Where the agent is, and which way it went.
 *
 * Two lanes, and the whole visual argument is in the geometry: the TOP lane is
 * the fast path through memory, the BOTTOM lane is thinking from scratch. A
 * refusal is drawn as literally falling out of the fast lane into the slow one,
 * so "it found a runbook and rejected it" is something you watch rather than
 * something you read.
 *
 * The topology is fixed — six nodes, always the same, always in the same place
 * — so there is no layout to compute. Coordinates are constants and only the
 * *state* animates. That is what keeps this a plain SVG with no graph library,
 * and what keeps it looking deliberate instead of like a spring simulation
 * that settled somewhere.
 */

export type Stage = "search" | "freshness" | "preconditions" | "replay" | "plan" | "execute";
/**
 * `miss` and `fail` are deliberately different states.
 *
 * Finding nothing in memory is not a refusal — on a first-ever run it is the
 * only possible outcome, and colouring it amber tells a viewer something went
 * wrong at the exact moment the system is behaving perfectly. Amber is
 * reserved for the case that actually matters: memory was found, and rejected.
 */
export type NodeState = "idle" | "active" | "pass" | "miss" | "fail" | "skipped";

export interface MapModel {
  /** Set once a task is submitted. */
  incident?: string;
  /** Live: which node is lit right now. */
  current?: Stage | null;
  states: Partial<Record<Stage, NodeState>>;
  /** The runbook retrieval matched, if any. */
  playbook?: { name: string; version: number } | null;
  /** Provenance evidence, drawn hanging off the freshness gate. */
  staleRule?: { rule_key: string; compiled_against: number; head: number } | null;
  /** Shown under the plan node while the model is between steps. */
  thinkingMs?: number | null;
  outcome?: string | null;
  stepCount?: number;
}

/**
 * Turn what we know into what to draw.
 *
 * Mid-run the engine only tells us *which* lane it took, not why, because the
 * reason is decided inside `_select_mode` and only lands in the audit trail.
 * So a live explore run shows the cold lane lighting up with the gates still
 * undecided, and the precise verdicts fill in when the explanation arrives.
 * Guessing which gate refused before we know would mean drawing a claim we
 * cannot support, on the one screen whose whole job is to be checkable.
 */
export function buildMapModel(args: {
  incident?: string | null;
  running: boolean;
  mode?: "explore" | "guided";
  playbookName?: string;
  playbookVersion?: number;
  thinkingMs?: number | null;
  explanation?: {
    decision: {
      reason: "reused" | "refused_stale" | "refused_precondition" | "no_match";
      stale_deps?: { rule_key: string; compiled_against: number; head: number }[] | null;
    };
    result: string | null;
    playbook?: { name: string; version: number } | null;
    episode?: { steps: number } | null;
  } | null;
}): MapModel {
  const { incident, running, mode, playbookName, playbookVersion, thinkingMs, explanation } =
    args;

  const playbook =
    playbookName && playbookVersion
      ? { name: playbookName, version: playbookVersion }
      : explanation?.playbook
        ? { name: explanation.playbook.name, version: explanation.playbook.version }
        : null;

  if (!incident) return { states: {} };

  if (running) {
    if (mode === "guided") {
      return {
        incident,
        current: "replay",
        states: {
          search: "pass",
          freshness: "pass",
          preconditions: "pass",
          replay: "active",
          plan: "skipped",
          execute: "skipped",
        },
        playbook,
      };
    }
    if (mode === "explore") {
      return {
        incident,
        current: "plan",
        states: { search: "active", plan: "active", execute: "active" },
        playbook,
        thinkingMs,
      };
    }
    return { incident, current: "search", states: { search: "active" }, thinkingMs };
  }

  if (!explanation) return { incident, states: {} };

  const reason = explanation.decision.reason;
  const stale = explanation.decision.stale_deps?.[0] ?? null;
  const common = {
    incident,
    playbook,
    outcome: explanation.result,
    stepCount: explanation.episode?.steps,
  };

  switch (reason) {
    case "reused":
      return {
        ...common,
        states: {
          search: "pass",
          freshness: "pass",
          preconditions: "pass",
          replay: "pass",
          plan: "skipped",
          execute: "skipped",
        },
      };
    case "refused_stale":
      return {
        ...common,
        staleRule: stale,
        states: {
          search: "pass",
          freshness: "fail",
          preconditions: "skipped",
          replay: "skipped",
          plan: "pass",
          execute: "pass",
        },
      };
    case "refused_precondition":
      return {
        ...common,
        states: {
          search: "pass",
          freshness: "pass",
          preconditions: "fail",
          replay: "skipped",
          plan: "pass",
          execute: "pass",
        },
      };
    default:
      return {
        ...common,
        playbook: null,
        states: {
          search: "miss",
          freshness: "skipped",
          preconditions: "skipped",
          replay: "skipped",
          plan: "pass",
          execute: "pass",
        },
      };
  }
}

// --- fixed geometry ---------------------------------------------------------
const W = 780;
const H = 300;
const TOP_Y = 40;
const BOT_Y = 206;
const NODE_H = 52;

const NODES: Record<
  Stage,
  { x: number; y: number; w: number; label: string; sub: string }
> = {
  search: { x: 138, y: TOP_Y, w: 124, label: "Vector search", sub: "find a runbook" },
  freshness: { x: 278, y: TOP_Y, w: 124, label: "Freshness", sub: "rules still current?" },
  preconditions: { x: 418, y: TOP_Y, w: 124, label: "Preconditions", sub: "does it apply?" },
  replay: { x: 558, y: TOP_Y, w: 124, label: "Replay steps", sub: "no thinking" },
  plan: { x: 278, y: BOT_Y, w: 164, label: "Plan from scratch", sub: "the expensive path" },
  execute: { x: 478, y: BOT_Y, w: 124, label: "Run steps", sub: "" },
};

const INCIDENT = { x: 8, y: 122, w: 104, h: 60 };
const OUTCOME = { x: 700, y: 122, w: 72, h: 60 };

const cx = (s: Stage) => NODES[s].x + NODES[s].w / 2;

export function DecisionMap({ model }: { model: MapModel }) {
  const st = (s: Stage): NodeState => model.states[s] ?? "idle";

  // A drop happens at the first top-lane gate that refused. Only one can, so
  // the first is the whole story.
  const dropAt: Stage | null =
    (["search", "freshness", "preconditions"] as Stage[]).find(
      (s) => st(s) === "fail"
    ) ?? null;

  const coldTaken = dropAt !== null || st("plan") !== "idle";
  const warmTaken = st("replay") === "pass" || st("replay") === "active";

  return (
    <div className={styles.wrap}>
      <div className={styles.laneLabels}>
        <span className={styles.laneWarm}>fast path &mdash; reuse memory</span>
        <span className={styles.laneCold}>slow path &mdash; think from scratch</span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className={styles.svg}
        role="img"
        aria-label="Decision map showing which path the agent took"
      >
        <defs>
          <marker
            id="dm-arrow"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="6"
            markerHeight="6"
            orient="auto"
          >
            <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
          </marker>
        </defs>

        {/* lane backgrounds, so the two paths read as distinct territory */}
        <rect
          x={126}
          y={TOP_Y - 14}
          width={568}
          height={NODE_H + 28}
          rx={10}
          className={`${styles.lane} ${warmTaken ? styles.laneOnWarm : ""}`}
        />
        <rect
          x={266}
          y={BOT_Y - 14}
          width={350}
          height={NODE_H + 28}
          rx={10}
          className={`${styles.lane} ${coldTaken ? styles.laneOnCold : ""}`}
        />

        {/* incident -> search */}
        <Edge
          d={`M ${INCIDENT.x + INCIDENT.w} ${INCIDENT.y + 30}
              C 128 ${INCIDENT.y + 30}, 128 ${TOP_Y + NODE_H / 2}, ${NODES.search.x} ${TOP_Y + NODE_H / 2}`}
          on={Boolean(model.incident)}
        />

        {/* top lane chain */}
        {(["search", "freshness", "preconditions"] as Stage[]).map((s, i) => {
          const next = (["freshness", "preconditions", "replay"] as Stage[])[i];
          return (
            <Edge
              key={s}
              d={`M ${NODES[s].x + NODES[s].w} ${TOP_Y + NODE_H / 2} L ${NODES[next].x} ${TOP_Y + NODE_H / 2}`}
              on={st(s) === "pass"}
            />
          );
        })}

        {/* the drop: falling out of the fast lane into the slow one */}
        {dropAt && (
          <Edge
            d={`M ${cx(dropAt)} ${TOP_Y + NODE_H}
                C ${cx(dropAt)} ${TOP_Y + 130}, ${NODES.plan.x + NODES.plan.w / 2} ${BOT_Y - 90}, ${NODES.plan.x + NODES.plan.w / 2} ${BOT_Y}`}
            on
            refused
          />
        )}

        {/* Nothing in memory at all: one plain edge straight to the cold lane.
            No drop, because nothing was rejected — there was simply nothing
            there. */}
        {st("search") === "miss" && (
          <Edge
            d={`M ${INCIDENT.x + INCIDENT.w / 2} ${INCIDENT.y + INCIDENT.h}
                C ${INCIDENT.x + INCIDENT.w / 2} ${BOT_Y}, 200 ${BOT_Y + NODE_H / 2}, ${NODES.plan.x} ${BOT_Y + NODE_H / 2}`}
            on
          />
        )}

        <Edge
          d={`M ${NODES.plan.x + NODES.plan.w} ${BOT_Y + NODE_H / 2} L ${NODES.execute.x} ${BOT_Y + NODE_H / 2}`}
          on={st("plan") === "pass" || st("execute") !== "idle"}
        />

        {/* both lanes converge on the outcome */}
        <Edge
          d={`M ${NODES.replay.x + NODES.replay.w} ${TOP_Y + NODE_H / 2}
              C 692 ${TOP_Y + NODE_H / 2}, 692 ${OUTCOME.y + 30}, ${OUTCOME.x} ${OUTCOME.y + 30}`}
          on={st("replay") === "pass"}
        />
        <Edge
          d={`M ${NODES.execute.x + NODES.execute.w} ${BOT_Y + NODE_H / 2}
              C 660 ${BOT_Y + NODE_H / 2}, 660 ${OUTCOME.y + 30}, ${OUTCOME.x} ${OUTCOME.y + 30}`}
          on={st("execute") === "pass"}
        />

        {/* provenance evidence, hanging off the gate that used it */}
        {model.staleRule && (
          <>
            <Edge
              d={`M ${cx("freshness")} ${TOP_Y + NODE_H} L ${cx("freshness")} ${BOT_Y - 58}`}
              on
              refused
            />
            <g>
              <rect
                x={cx("freshness") - 96}
                y={BOT_Y - 58}
                width={192}
                height={40}
                rx={6}
                className={styles.ruleBox}
              />
              <text x={cx("freshness")} y={BOT_Y - 42} className={styles.ruleKey}>
                {model.staleRule.rule_key}
              </text>
              <text x={cx("freshness")} y={BOT_Y - 27} className={styles.ruleVer}>
                <tspan className={styles.verOld}>v{model.staleRule.compiled_against}</tspan>
                <tspan className={styles.verArrow}> &rarr; </tspan>
                <tspan className={styles.verNew}>v{model.staleRule.head}</tspan>
                <tspan className={styles.ruleNote}>  changed since compile</tspan>
              </text>
            </g>
          </>
        )}

        {/* incident */}
        <g className={model.incident ? styles.nodeActive : styles.nodeIdle}>
          <rect {...INCIDENT} rx={8} className={styles.box} />
          <text x={INCIDENT.x + INCIDENT.w / 2} y={INCIDENT.y + 25} className={styles.title}>
            {model.incident ?? "no incident"}
          </text>
          <text x={INCIDENT.x + INCIDENT.w / 2} y={INCIDENT.y + 42} className={styles.sub}>
            incoming
          </text>
        </g>

        {(Object.keys(NODES) as Stage[]).map((s) => (
          <Node
            key={s}
            stage={s}
            state={st(s)}
            current={model.current === s}
            badge={
              s === "search" && model.playbook
                ? `${model.playbook.name} v${model.playbook.version}`
                : undefined
            }
            thinkingMs={s === "plan" ? model.thinkingMs : null}
          />
        ))}

        {/* outcome */}
        <g className={model.outcome ? styles.nodeDone : styles.nodeIdle}>
          <rect {...OUTCOME} rx={8} className={styles.box} />
          <text x={OUTCOME.x + OUTCOME.w / 2} y={OUTCOME.y + 28} className={styles.title}>
            {model.outcome ?? "—"}
          </text>
          {model.stepCount != null && model.stepCount > 0 && (
            <text x={OUTCOME.x + OUTCOME.w / 2} y={OUTCOME.y + 44} className={styles.sub}>
              {model.stepCount} steps
            </text>
          )}
        </g>
      </svg>
    </div>
  );
}

function Edge({ d, on, refused }: { d: string; on: boolean; refused?: boolean }) {
  return (
    <path
      d={d}
      className={`${styles.edge} ${on ? styles.edgeOn : ""} ${refused ? styles.edgeRefused : ""}`}
      markerEnd="url(#dm-arrow)"
      fill="none"
    />
  );
}

function Node({
  stage,
  state,
  current,
  badge,
  thinkingMs,
}: {
  stage: Stage;
  state: NodeState;
  current: boolean;
  badge?: string;
  thinkingMs?: number | null;
}) {
  const n = NODES[stage];
  const cls =
    state === "pass"
      ? styles.nodePass
      : state === "fail"
        ? styles.nodeFail
        : state === "miss"
          ? styles.nodeMiss
          : state === "skipped"
            ? styles.nodeSkipped
            : state === "active"
              ? styles.nodeActive
              : styles.nodeIdle;

  return (
    <g className={`${cls} ${current ? styles.nodeCurrent : ""}`}>
      <rect x={n.x} y={n.y} width={n.w} height={NODE_H} rx={8} className={styles.box} />
      <text x={n.x + n.w / 2} y={n.y + 22} className={styles.title}>
        {n.label}
      </text>
      <text x={n.x + n.w / 2} y={n.y + 38} className={styles.sub}>
        {state === "fail"
          ? "refused"
          : state === "miss"
            ? "nothing in memory"
            : state === "skipped"
              ? "not reached"
              : n.sub}
      </text>

      {/* a verdict tick sits on the corner rather than in the label, so the
          node's name never moves as its state changes */}
      {(state === "pass" || state === "fail" || state === "miss") && (
        <text x={n.x + n.w - 9} y={n.y + 15} className={styles.tick}>
          {state === "pass" ? "✓" : state === "miss" ? "–" : "✕"}
        </text>
      )}

      {badge && (
        <text x={n.x + n.w / 2} y={n.y + NODE_H + 15} className={styles.badge}>
          {badge}
        </text>
      )}

      {thinkingMs != null && (
        <text x={n.x + n.w / 2} y={n.y + NODE_H + 16} className={styles.thinking}>
          thinking {(thinkingMs / 1000).toFixed(1)}s
        </text>
      )}
    </g>
  );
}
