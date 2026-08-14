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
 *
 * Every run is two steps, always the same shape: click the incident, then hand
 * over to the floating window. The spotlight blocks whatever it does not cover,
 * so a single step pointing at the card would leave the viewer unable to open
 * the one surface where the run is actually visible.
 */

export type TourEvent =
  | "run:started"
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
    view: "work",
    reveal: ["INC-1001"],
    advanceOn: "run:started",
    action: "Click Fix it",
  },

  {
    id: "the-island",
    title: "Everything it is doing shows up down here",
    body:
      "That floating pill is the only live surface in the app. <b>Click it</b> to open it while the run is still going.\n\nThree things are inside. The <b>map</b> at the top has two lanes: the upper one is the fast path through memory, the lower one is thinking from scratch, and you can watch which one lights up. Below it, each <b>step</b> as it happens — click any of them for the tool call and what came back. At the very bottom, <b>how much thinking it skipped</b>.",
    mechanism:
      "It is in the lower lane right now, because there is nothing in memory for it to be in the upper one.",
    target: '[data-tour="island"]',
    reveal: ["INC-1001"],
    advanceOn: "runbook:compiled",
    action: "Click the pill to open it",
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
    view: "procedures",
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
    view: "work",
    reveal: ["INC-1002"],
    advanceOn: "run:started",
    action: "Click Fix it",
  },

  {
    id: "reuse-watch",
    title: "This time the upper lane lights up",
    body:
      "Open the window again. <b>Vector search</b>, <b>Freshness</b> and <b>Preconditions</b> all tick and it goes straight to <b>Replay steps</b> — the lower lane stays dark.\n\nThe name of the runbook it matched is printed under the first node.",
    mechanism:
      "No planner ran. These are the steps it worked out last time, re-bound to this incident's parameters.",
    target: '[data-tour="island"]',
    reveal: ["INC-1002"],
    advanceOn: "run:reused",
    action: "Click the pill and watch the top lane",
    waitingLabel: "Searching memory, then replaying",
  },

  {
    id: "what-reuse-saved",
    title: "Four steps, no thinking",
    body:
      "The number at the bottom of the window is what reuse bought: every step replayed from memory, and the planner not called once.",
    mechanism:
      "Measured, not claimed: cold and guided runs are averaged separately over successful episodes only, so the same workload is on both sides of the comparison.",
    target: ['[data-tour="cost"]', '[data-tour="island"]'],
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
    view: "procedures",
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
    view: "work",
    reveal: ["INC-1009"],
    advanceOn: "run:started",
    action: "Click Fix it",
  },

  {
    id: "refusal-watch",
    title: "Open it and watch where it stops",
    body:
      "It will set off along the upper lane, get as far as the freshness gate, and go no further.",
    mechanism:
      "The gate runs before any step executes, so nothing is applied on the strength of a runbook that has gone out of date.",
    target: '[data-tour="island"]',
    reveal: ["INC-1009"],
    advanceOn: "run:finished",
    action: "Click the pill to open it",
    waitingLabel: "Matching, refusing, re-planning",
  },

  {
    id: "the-drop",
    title: "You can see it fall out of the fast lane",
    body:
      "<b>Vector search</b> has a tick — it did find the runbook, and the name is printed under it. <b>Freshness</b> has a cross.\n\nThe line then drops out of the upper lane into the lower one, and the run finishes along the bottom. That drop is the refusal, drawn.",
    mechanism:
      "A refusal and a cold start produce the same steps. Only the gate that stopped it tells them apart, which is why it is drawn rather than described.",
    target: ['[data-tour="map"]', '[data-tour="island"]'],
    reveal: [],
    nextLabel: "And the evidence",
  },

  {
    id: "evidence",
    title: "And here is the rule that moved",
    body:
      "Named, with both version numbers: what the runbook was compiled against, and what policy is at now. <b>Click that row</b> and it takes you to the rule so you can check it yourself.",
    mechanism:
      "This is the difference between a system that is confident and a system that is checkable.",
    target: ['[data-tour="evidence"]', '[data-tour="island"]'],
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
    view: "procedures",
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
    target: '[data-tour="nav-system"]',
    reveal: [],
    nextLabel: "Finish, and bring back the full world",
  },
];
