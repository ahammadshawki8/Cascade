/**
 * The shapes a run is described by, in one place.
 *
 * A step arrives twice in this app's life: live over SSE while a task runs,
 * and again from `GET /api/tasks/{id}/steps` when someone opens a past run.
 * Both are normalised to the same object at the edge so there is exactly one
 * renderer, and a historical run is never a lesser view of a live one.
 */

export interface StepEvent {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  /** The tool's return value. Absent only for runs recorded before 005. */
  output?: unknown;
  duration_ms?: number;
  error?: boolean;
}

/** Why a run went guided or cold. Mirrors GET /api/tasks/{id}/explain. */
export interface Explanation {
  task_id: string;
  input: string;
  status: string;
  result: string | null;
  mode: "explore" | "guided" | null;
  interrupt_reason: string | null;
  decision: {
    reason: "reused" | "refused_stale" | "refused_precondition" | "no_match";
    headline: string;
    detail: string;
    stale_deps?: { rule_key: string; compiled_against: number; head: number }[] | null;
    failed_preconditions?: string[] | null;
  };
  incident: {
    incident_id: string;
    kind: string;
    severity: string;
    service_name: string;
    service_tier: number;
    state: string;
    deploy_age_hours: number | null;
  } | null;
  playbook: {
    playbook_id: string;
    name: string;
    version: number;
    status_cache: string;
    confidence: number;
  } | null;
  episode: {
    steps: number;
    latency_ms: number;
    tokens: number;
    outcome: string;
  } | null;
  learned: { playbook_id: string; name: string; version: number } | null;
  comparison: {
    cold_avg_ms: number | null;
    guided_avg_ms: number | null;
    cold_runs: number;
    guided_runs: number;
    cold_avg_tokens: number | null;
    guided_avg_tokens: number | null;
    speedup: number | null;
  };
}

/**
 * A re-learn in flight.
 *
 * Four distinct things happen inside one button press, and the phase is the
 * only way to tell which of them is currently taking the time — or which one
 * declined to produce a new version, since that is a legitimate outcome.
 */
export type RelearnPhase =
  | "queued"
  | "started"
  | "solving"
  | "solved"
  | "compiling"
  | "done"
  | "rejected"
  | "deferred"
  | "failed";

export interface RelearnState {
  playbookId: string;
  phase: RelearnPhase;
  name?: string;
  version?: number;
  staleRules?: { rule_key: string; compiled_against: number; head: number }[];
  taskId?: string;
  taskText?: string;
  result?: string | null;
  newName?: string;
  newVersion?: number;
  reason?: string;
}
