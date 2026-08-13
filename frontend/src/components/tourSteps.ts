import type { ViewId } from "./ActivityBar";

/**
 * The walkthrough, as data.
 *
 * Each step names one control, one thing to do, and the mechanism underneath
 * it. The mechanism line is the point of the whole tour: the actions are
 * ordinary, and what makes them worth watching is what the database is doing
 * while they happen.
 *
 * Steps advance on events the app really emits. A step with no `advanceOn` is
 * a reading step and gets a Next button; everything else waits for the system.
 */

export type TourEvent =
  | "run:finished"
  | "run:reused"
  | "run:refused"
  | "runbook:compiled"
  | "policy:committed"
  | "relearn:done";

export interface TourStep {
  id: string;
  title: string;
  /** What to do, and what it means. Plain sentences. */
  body: string;
  /** What the database is doing underneath. Rendered as the accented block. */
  mechanism?: string;
  /**
   * CSS selector(s) for the control to spotlight. Omitted = centred card.
   *
   * A list is tried in order and the first one that is actually on screen
   * wins, which is how a step can follow an interaction into a dialog.
   */
  target?: string | string[];
  /** Force this view before the step is shown. */
  view?: ViewId;
  /**
   * Incident ids the inbox may show during this step.
   *
   * One at a time, so there is never a wrong thing to click. Twelve cards on
   * screen means eleven ways to take the tour somewhere it did not plan for.
   */
  reveal?: string[];
  advanceOn?: TourEvent;
  action?: string;
  waitingLabel?: string;
  nextLabel?: string;
}

export const TOUR: TourStep[] = [
  {
    id: "welcome",
    title: "Six minutes, and you will have seen the whole idea",
    body:
      "This walks through one loop: the agent solves an incident it has never seen, writes down what it did, reuses it, and then throws that knowledge away the moment the rules change underneath it.\n\nOne incident appears at a time, so there is never a wrong thing to click. You can leave at any point and the full world comes back.",
    mechanism:
      "Everything you are about to see runs against a real CockroachDB cluster. No step is scripted; if the model does something different, you will see that instead.",
    nextLabel: "Start",
  },

  {
    id: "first-incident",
    title: "An incident, and nothing to reuse",
    body:
      "A bad deploy took out checkout. The agent has never seen this, so it has nothing to fall back on and has to reason from policy: read the incident, read the rules, check whether it is allowed to act, then act.\n\nPress <b>Fix it</b> and watch the floating window.",
    mechanism:
      "This is the expensive path. Every step costs a call to the planner, which is exactly what the rest of the system exists to avoid paying twice.",
    target: '[data-tour="incident-INC-1001"]',
    view: "incidents",
    reveal: ["INC-1001"],
    advanceOn: "runbook:compiled",
    action: "Click Fix it",
    waitingLabel: "Solving, then compiling what it did",
  },

  {
    id: "what-it-learned",
    title: "It wrote the procedure down — and what the procedure assumed",
    body:
      "The run became a runbook. Look at the rules listed on it: those are the exact policy versions the agent consulted while solving the incident.\n\nThat second part is the whole system. Most tools remember the procedure. Almost none remember what the procedure was based on.",
    mechanism:
      "Each of those citations is a row in <code>playbook_deps</code>, pinning this runbook to <code>rule_key</code> at a specific <code>rule_version</code>.",
    target: '[data-tour="runbook-card"]',
    view: "runbooks",
    reveal: [],
    nextLabel: "Now reuse it",
  },

  {
    id: "reuse",
    title: "The same kind of problem, a second time",
    body:
      "A different service, a different incident id, the same shape of failure. This time the agent should recognise it.\n\nPress <b>Fix it</b> and watch the top lane of the map light up instead of the bottom one.",
    mechanism:
      "Vector search finds the runbook by meaning, not by keyword. Then the freshness gate checks every rule it cited is still at head before a single step runs.",
    target: '[data-tour="incident-INC-1002"]',
    view: "incidents",
    reveal: ["INC-1002"],
    advanceOn: "run:reused",
    action: "Click Fix it",
    waitingLabel: "Searching memory, then replaying",
  },

  {
    id: "what-reuse-saved",
    title: "Four steps, no thinking",
    body:
      "Every step was replayed from memory. The planner was not called once, which is where the speed and the cost saving both come from.",
    mechanism:
      "Measured, not claimed: cold and guided runs are averaged separately over successful episodes only, so the same workload is on both sides of the comparison.",
    target: '[data-tour="cost"]',
    reveal: [],
    nextLabel: "Now break it",
  },

  {
    id: "change-policy",
    title: "Change the rule the runbook was built on",
    body:
      "Rollback is currently allowed within 24 hours of a deploy. Tighten it to <b>4</b> and commit.\n\nThis is the moment every runbook wiki in the world quietly goes wrong, and nobody finds out until one of them fires.",
    mechanism:
      "The commit is four writes: close the old version, insert the new one, one outbox row, one audit row. Four — whether one runbook depends on this rule or a hundred thousand.",
    target: ['[data-tour="commit-modal"]', '[id="rule-incident.rollback_window"]'],
    view: "policy",
    reveal: [],
    advanceOn: "policy:committed",
    action: "Set hours to 4, review, then commit",
    waitingLabel: "Committing, and cascading",
  },

  {
    id: "gone-red",
    title: "Nobody marked it stale. It just is.",
    body:
      "The runbook is quarantined and its provenance dot is red. No process went and updated it — the cascade never touched this row at all.",
    mechanism:
      "Staleness is a <b>JOIN</b>, not a column: the runbook says it was built on v1, the rules table says head is v2, and <code>1 != 2</code> is computed fresh every time anyone asks. A stored flag can drift. This cannot.",
    target: '[data-tour="runbook-card"]',
    view: "runbooks",
    reveal: [],
    nextLabel: "Watch it refuse itself",
  },

  {
    id: "refusal",
    title: "The part that matters",
    body:
      "Another bad deploy. Vector search will find that runbook — it is still the closest match by meaning, and it still looks perfectly good.\n\nWatch it get refused anyway.",
    mechanism:
      "Being similar is not enough. The runbook has to still be true, and the provenance join is what decides that. Acting on superseded policy confidently is worse than having no memory at all.",
    target: '[data-tour="incident-INC-1009"]',
    view: "incidents",
    reveal: ["INC-1009"],
    advanceOn: "run:finished",
    action: "Click Fix it",
    waitingLabel: "Matching, refusing, re-planning",
  },

  {
    id: "evidence",
    title: "And it shows its work",
    body:
      "Matched by vector search, refused by provenance, re-planned from scratch — and it will tell you exactly which rule moved and between which versions. Click that row to go and check the rule yourself.",
    mechanism:
      "This is the difference between a system that is confident and a system that is checkable.",
    target: '[data-tour="evidence"]',
    reveal: [],
    nextLabel: "Repair it",
  },

  {
    id: "relearn",
    title: "Re-derive it under the new rules",
    body:
      "The runbook is not edited and it is not patched. The agent takes one incident of the same kind, solves it again from scratch under today's policy, and saves that as version 2.\n\nPress <b>Re-learn</b>. This one takes a minute; the window will narrate each phase.",
    mechanism:
      "It has to actually perform the work, because the new provenance comes from the rule versions the run really consulted. You cannot type citations in by hand.",
    target: '[data-tour="relearn"]',
    view: "runbooks",
    reveal: [],
    advanceOn: "relearn:done",
    action: "Click Re-learn",
    waitingLabel: "Picking an incident, re-solving, compiling",
  },

  {
    id: "architecture",
    title: "That is the loop. Here is what made it possible.",
    body:
      "Learn, reuse, invalidate, re-derive. The agent is the ordinary part — plenty of things can call a tool.\n\nThe Architecture view shows the part that is not ordinary: the provenance edges, the cascade that stays four writes, and the vector index the retrieval actually used.",
    mechanism:
      "Every number on that screen is read live from the cluster you have just been driving.",
    target: '[data-tour="nav-architecture"]',
    reveal: [],
    nextLabel: "Finish, and bring back the full world",
  },
];
