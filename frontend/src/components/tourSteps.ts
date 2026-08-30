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
 * A waiting step must never depend on a *successful* outcome. `run:reused`
 * fires on one of four things a run can do, so a step waiting only for that one
 * hangs forever the moment retrieval hits and the precondition check misses,
 * which is a real and recurring possibility because compiled preconditions are
 * model output. Every waiting step therefore also accepts an event that fires
 * whatever happens.
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
  /**
   * The compile poll has ended, whether or not a runbook appeared.
   *
   * `runbook:compiled` only fires on success, and a compile can legitimately
   * produce nothing: it can be rejected by the safety lint, or deduped into an
   * existing runbook. Either leaves the step that waits for it stranded.
   */
  | "compile:settled"
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
  /**
   * Advance when any of these fires. Order does not matter; the first to
   * arrive wins. Always include one that fires regardless of outcome.
   */
  advanceOn?: TourEvent | TourEvent[];
  action?: string;
  waitingLabel?: string;
  nextLabel?: string;
  /**
   * This step waits on something genuinely slow, and may be passed over.
   *
   * The generic "Continue anyway" only appears after 45 seconds of waiting,
   * which is right for a step that has gone wrong and wrong for one that is
   * simply long: a re-learn is a real model call and takes about a minute, so
   * the escape would fire in the middle of a perfectly healthy run. Steps
   * marked optional offer the way past immediately instead.
   */
  optional?: boolean;
}

export const TOUR: TourStep[] = [
  {
    id: "welcome",
    title: "Two parts: what everything is, then watch it work",
    body: "First a short pass over the five screens, so nothing later is a surprise. Then one incident end to end: the agent solves something it has never seen, writes down what it did, reuses it, and refuses it once the rules move.\n\nThe second half runs for real against a live cluster, so it takes a couple of minutes. Skip works on every step.",
    mechanism: "Nothing in this first part changes any data.",
    view: "work",
    nextLabel: "Start",
  },

  {
    id: "tour-work",
    title: "Work is where incidents run",
    body: "This is the only screen where anything happens. Everything else describes or governs what happens here.\n\nThe list is incidents waiting to be dealt with. Each card already carries the policy verdict, so you can see why two similar failures get treated differently before anything runs.",
    mechanism: "The verdict on a card is computed from the same rules the agent is bound by. It is not a label somebody typed.",
    target: '[data-tour="nav-work"]',
    view: "work",
    nextLabel: "What the numbers mean",
  },

  {
    id: "tour-metrics",
    title: "Cold and guided are the whole claim, as two numbers",
    body: "<b>Cold</b> is how long the agent takes when it has to think. <b>Guided</b> is how long it takes when it can reuse something it already worked out. Watching those two diverge is the argument for keeping memory at all.\n\n<b>Hit rate</b> is how often an incident found something to reuse; low is not bad, it means the agent is still learning. <b>Tasks</b> counts runs by state. The <b>LLM</b> dot is green when Amazon Bedrock is answering.",
    mechanism: "Both averages use successful runs only. An escalation stops before the expensive part, so averaging it in would drag the two together and understate the gap.",
    target: '[data-tour="metrics"]',
    view: "work",
    nextLabel: "The three tabs",
  },

  {
    id: "tour-work-tabs",
    title: "Inbox, Author, History",
    body: "<b>Inbox</b> is the sample incidents. <b>Author</b> is where you describe one of your own, in a sentence, and watch the same machinery decide it. That is the tab to try on your own systems. <b>History</b> is every past run, replayable step by step.\n\nAn incident you write goes through the identical path. There is no separate demo mode.",
    mechanism: "Anything you author is stored in the same table as the samples and is told apart only by its id.",
    target: '[data-tour="work-tabs"]',
    view: "work",
    nextLabel: "Procedures",
  },

  {
    id: "tour-procedures",
    title: "Procedures is the memory",
    body: "Every runbook the agent has learned, and every one you have brought. It is empty right now because nothing has been learned yet, and you will watch one appear here shortly.\n\n<b>Import a runbook</b> is how your existing material gets in. Paste a wiki page; the model proposes which policy rules it depends on, you confirm them, and from then on it is governed exactly like one the agent wrote itself.",
    mechanism: "An imported procedure never wins retrieval over a compiled one. It is advisory until it has earned otherwise.",
    target: '[data-tour="nav-procedures"]',
    view: "procedures",
    nextLabel: "Policy",
  },

  {
    id: "tour-policy",
    title: "Policy is what the agent has to obey",
    body: "Not settings. These are constraints the engine enforces on every run, and changing one is what makes a remembered procedure stop being trusted.\n\nEach rule shows its parameters. <b>incident.rollback_window</b> is the one the rest of this walkthrough turns on: right now it permits a rollback within 24 hours of a deploy.",
    mechanism: "A rule carries a predicate and an enforcement mode. Advisory rules are prose that is still cited and still goes stale; enforcing rules decide.",
    target: '[data-tour="nav-policy"]',
    view: "policy",
    nextLabel: "Writing your own",
  },

  {
    id: "tour-new-rule",
    title: "You can write rules the engine will enforce",
    body: "<b>New rule</b> opens a form: pick a fact about an incident, pick a comparison, give it a value. That becomes something the agent is bound by on every run, versioned and cascaded exactly like the rules that shipped.\n\nThis is the part most tools do not have. A policy you invent is enforced, not merely stored.",
    mechanism: "The form only offers fields the engine can actually evaluate, so a rule that would silently never match cannot be written.",
    target: '[data-tour="new-rule"]',
    view: "policy",
    nextLabel: "Connections",
  },

  {
    id: "tour-connections",
    title: "Connections is how anything outside reaches this",
    body: "Two directions. <b>Apps</b> is outbound: point it at a Slack or Discord webhook and the next refusal lands in a real channel.\n\n<b>Agents</b> is inbound, and it is the part worth caring about. Create a key and any agent you already run can ask one question over HTTP or MCP: <i>is what I remember still valid?</i> No model, no execution, and no framework to adopt.",
    mechanism: "Keys are scoped and revocable. A key that only asks about memory cannot start a remediation.",
    target: '[data-tour="connections-agents"]',
    view: "connections",
    nextLabel: "Extensions",
  },

  {
    id: "tour-extensions",
    title: "Those four screens are the product. The rest you choose.",
    body: "Everything else lives here and starts switched off: the measured evaluation, the live architecture view, savings and blast radius, the copilot, and the approvals queue.\n\nEach explains what it is, when you would open it, how to use it properly, and a worked example, so you can decide rather than guess. Adding one puts it on the sidebar; removing it takes the screen away and deletes nothing.",
    mechanism: "This screen exists because shipping all of it on the sidebar by default read as a complicated tool rather than a generous one.",
    target: '[data-tour="nav-extensions"]',
    view: "extensions",
    nextLabel: "Now watch it work",
  },

  {
    id: "act-two",
    title: "One incident, start to finish",
    body: "From here everything runs for real against the cluster, which is why it is at the end rather than the beginning: a cold run takes about thirteen seconds because a model is genuinely thinking.\n\nFour beats. It learns, it reuses, you change a rule, and it refuses the thing it learned.",
    mechanism: "No step is scripted. If the model does something different, you will see that instead.",
    view: "work",
    nextLabel: "Begin",
  },

  {
    id: "first-incident",
    title: "An incident, and nothing to reuse",
    body: "A bad deploy took out checkout. The agent has never seen this, so it reasons from policy: read the incident, read the rules, check whether it is allowed to act, then act.\n\nPress <b>Fix it</b>.",
    mechanism: "This is the expensive path. Every step costs a call to the planner, which is exactly what the rest of the system exists to avoid paying twice.",
    target: '[data-tour="incident-INC-1001"]',
    view: "work",
    reveal: ["INC-1001"],
    advanceOn: "run:started",
    action: "Click Fix it",
  },

  {
    id: "the-island",
    title: "Everything it is doing shows up down here",
    body: "Click the floating pill to open it. The <b>map</b> has two lanes: the upper one is the fast path through memory, the lower one is thinking from scratch. Watch which one lights up.\n\nBelow it, each step as it happens. Click any of them for the tool call and what came back.",
    mechanism: "It is in the lower lane, because there is nothing in memory for it to be in the upper one.",
    target: '[data-tour="island"]',
    reveal: ["INC-1001"],
    advanceOn: ["runbook:compiled", "compile:settled"],
    action: "Click the pill to open it",
    waitingLabel: "Solving, then compiling what it did",
  },

  {
    id: "what-it-learned",
    title: "It wrote down the procedure, and what the procedure assumed",
    body: "The run became a runbook. Look at the rules listed on it: those are the exact policy versions the agent consulted while solving the incident.\n\nThat second part is the whole system. Most tools remember the procedure. Almost none remember what the procedure was based on.",
    mechanism: "Each citation is a row in playbook_deps, pinning this runbook to a rule_key at a specific rule_version.",
    target: '[data-tour="runbook-card"]',
    view: "procedures",
    nextLabel: "Now reuse it",
  },

  {
    id: "reuse",
    title: "The same kind of problem, a second time",
    body: "A different service, a different id, the same shape of failure. Press <b>Fix it</b> and watch the upper lane light up instead of the lower one.",
    mechanism: "Vector search finds it by meaning. Then the freshness check confirms every rule it cited is still current, before a single step runs.",
    target: '[data-tour="incident-INC-1002"]',
    view: "work",
    reveal: ["INC-1002"],
    advanceOn: "run:started",
    action: "Click Fix it",
  },

  {
    id: "reuse-watch",
    title: "This time nothing thinks",
    body: "Vector search, freshness and preconditions all tick, and it goes straight to replaying the stored steps. The lower lane stays dark.\n\nLook at the cost line at the bottom of the window.",
    mechanism: "No model was called anywhere on this path. Retrieval is an index, freshness is a join, preconditions are an evaluation.",
    target: '[data-tour="island"]',
    reveal: ["INC-1002"],
    advanceOn: ["run:reused", "run:finished"],
    action: "Open the window",
    waitingLabel: "Matching, checking, replaying",
  },

  {
    id: "change-policy",
    title: "Now change the rule it was built on",
    body: "Open <b>incident.rollback_window</b> and change 24 to 4. You get an impact preview before anything commits.\n\nThen commit it.",
    mechanism: "One transaction: a new rule version, the head pointer moved, an audit row, one event. Four writes, whether one procedure depends on it or a hundred thousand.",
    target: '[data-tour="nav-policy"]',
    view: "policy",
    advanceOn: "policy:committed",
    action: "Change 24 to 4, then Commit",
    waitingLabel: "Committing the cascade",
  },

  {
    id: "gone-red",
    title: "The runbook is no longer trusted",
    body: "Nothing wrote to it. Its provenance dot has drained and it reads <b>suspect</b>, because a rule it cited is no longer at the version it cited.\n\nStaleness here is a join, not a column somebody had to remember to set.",
    mechanism: "No row on the procedure changed. The answer to 'is this still valid' is computed at the moment it is asked.",
    target: '[data-tour="runbook-card"]',
    view: "procedures",
    nextLabel: "Now try to use it",
  },

  {
    id: "refusal",
    title: "A third incident, of exactly the kind it knows",
    body: "This one still matches the runbook by meaning. It is still the closest thing in memory. Press <b>Fix it</b> and watch it get refused anyway.",
    mechanism: "Retrieval will hit. The freshness check is what stops it.",
    target: '[data-tour="incident-INC-1009"]',
    view: "work",
    reveal: ["INC-1009"],
    advanceOn: "run:started",
    action: "Click Fix it",
  },

  {
    id: "refusal-watch",
    title: "Matched by meaning, refused by provenance",
    body: "Watch the line travel along the upper lane, tick vector search, and then drop into the lower lane at the freshness check.\n\nOpen the evidence row and you get the rule name with both version numbers. That refusal is the whole product.",
    mechanism: "It re-plans from scratch under today's policy and escalates, because a five hour old deploy is outside a four hour window.",
    target: '[data-tour="island"]',
    reveal: ["INC-1009"],
    advanceOn: ["run:refused", "run:finished"],
    action: "Open the window",
    waitingLabel: "Matching, refusing, re-planning",
  },

  {
    id: "relearn",
    title: "And it can re-derive itself",
    body: "The runbook is not edited or patched. The agent takes an incident of the same kind, solves it again under today's policy, and saves that as version 2 with fresh provenance.\n\nThis one takes about a minute, so skip it if you would rather not wait.",
    mechanism: "The new provenance has to come from the rule versions the run really consulted. You cannot type citations in by hand.",
    target: '[data-tour="relearn"]',
    view: "procedures",
    advanceOn: "relearn:done",
    action: "Click Re-learn",
    waitingLabel: "Picking an incident, re-solving, compiling",
    optional: true,
  },

  {
    id: "handover",
    title: "All of that ran on our data",
    body: "Which is the fair objection to any demo. This checklist is the same system on yours: import a runbook you already have, write a policy rule the agent must obey, give your own agent a key, or send the next refusal to your Slack.\n\nThe first one takes about ten seconds.",
    mechanism: "Your rules and procedures sit in the same tables as the sample ones, and restoring the sample world leaves every one of them in place.",
    target: '[data-tour="make-it-yours"]',
    view: "work",
    nextLabel: "One last thing",
  },

  {
    id: "work-mode",
    title: "Now empty it out",
    body: "<b>Work mode</b> clears the sample incidents and the runbooks this walkthrough compiled, and leaves you the four screens with nothing in them. Your rules, imported procedures, connections and keys all survive it.\n\nThe sample world comes back from the header button whenever you want it.",
    mechanism: "Nothing is deleted, and the extensions you added stay added.",
    nextLabel: "Switch to work mode",
  },
];
