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
    title: "Two parts: the idea, then the tool",
    body:
      "The first half is one loop, and takes a few minutes: the agent solves an incident it has never seen, writes down what it did, reuses it, and then throws that knowledge away the moment the rules change underneath it. That is the whole idea, and you can stop there.\n\nThe second half walks every screen and says what it is for. One incident appears at a time, so there is never a wrong thing to click, and Skip works on every step.",
    mechanism:
      "The three runs below are replayed from recordings of real runs against the deployed stack, so you are not waiting thirteen seconds on a model call to see what happens next. They are marked as recordings while they play, and every one of them has a Run it live button that goes to the cluster instead. Everything else here — the policy change, the invalidation, the counts — happens for real as you do it.",
    nextLabel: "Start",
  },

  {
    id: "first-incident",
    title: "An incident, and nothing to reuse",
    body:
      "A bad deploy took out checkout. The agent has never seen this, so it has nothing to fall back on and has to reason from policy: read the incident, read the rules, check whether it is allowed to act, then act.\n\nPress <b>Fix it</b> and watch the floating window.",
    mechanism:
      "This is the expensive path: every step costs a call to the planner, which is exactly what the rest of the system exists to avoid paying twice. The run you are about to watch took 12,962 ms and 8,579 planner tokens when it was recorded. Press Run it live to spend that again now.",
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
    advanceOn: ["runbook:compiled", "compile:settled"],
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
    // `run:finished` is the safety net. If the runbook is matched and then
    // refused on preconditions, reuse never happens and `run:reused` never
    // fires; the window says so plainly, and the tour has to be able to
    // continue rather than wait for an event that is not coming.
    advanceOn: ["run:reused", "run:finished"],
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
    optional: true,
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
    nextLabel: "Now try it on yours",
  },

  /**
   * The handover.
   *
   * Ending on the architecture view left a reviewer having watched something
   * impressive happen to data we shipped, with no obvious next move and every
   * reason to suspect the whole thing was scripted. This step exists to answer
   * that suspicion the only way it can be answered: by pointing at the four
   * things they can do to their own material in the next few minutes.
   */
  /* =====================================================================
   * ACT TWO — every surface, and what it is for.
   *
   * Act one is the argument. It is deliberately narrow: one incident at a
   * time, one thread, nothing on screen that is not part of the story.
   *
   * The cost of that narrowness is a reviewer who has watched something
   * convincing happen and still cannot say what half the interface is. They
   * have seen the numbers change without being told what the numbers are, and
   * they have never been shown the four things that turn a demo into a tool
   * they could run on Monday.
   *
   * So act two is a tour of the product rather than of the idea. Every
   * destination, every number, and the honest answer to "why is this here" for
   * each one. It is long, and it is skippable at every step.
   * ===================================================================== */

  {
    id: "act-two",
    title: "That was the idea. Now the tool.",
    body:
      "You have seen the loop, which is the part worth being convinced by. What you have not seen is most of the interface, or what any of the numbers along the top mean.\n\nThe rest of this walks every screen and answers the same three questions each time: what is this, why is it here, and what would you do with it on your own systems. Leave whenever you like.",
    mechanism:
      "Nothing below runs the model or changes your data unless you ask it to.",
    reveal: [],
    nextLabel: "Start with the numbers",
  },

  {
    id: "the-numbers",
    title: "The two numbers that are the whole claim",
    body:
      "<b>Cold</b> is how long the agent takes when it has to think. <b>Guided</b> is how long it takes when it can reuse something. Watching those two diverge is the entire argument for keeping memory at all.\n\n<b>Hit rate</b> is how often an incident found something to reuse. Low is not bad — it means the agent is still learning. <b>Tasks</b> is a live count by state: queued, running, interrupted, succeeded, failed.",
    mechanism:
      "Cold and guided are averaged over successful runs only. An escalation short-circuits before the expensive part, so averaging it in would drag the two modes together and understate the gap.",
    target: '[data-tour="metrics"]',
    view: "work",
    reveal: [],
    nextLabel: "And the light on the right",
  },

  {
    id: "the-provider",
    title: "Which model is actually serving you",
    body:
      "The <b>LLM</b> dot is green when Amazon Bedrock is answering and amber when something else is. That distinction matters more than it looks: the timings above are only comparable if real model calls are being made.\n\nThe bar along the bottom says the same thing permanently — provider, live connection, and which database you are on.",
    mechanism:
      "Chat and embeddings fall back independently, so <code>/api/admin/smoke</code> reports them separately. The dot is the summary.",
    target: '[data-tour="metrics"]',
    reveal: [],
    nextLabel: "On to the screens",
  },

  {
    id: "tour-work",
    title: "Work — where things actually run",
    body:
      "Three tabs. <b>Inbox</b> is the sample incidents, each carrying its policy verdict so you can see why two similar ones get treated differently. <b>Author</b> is where you describe an incident of your own, in your own words, and watch the same machinery decide it. <b>History</b> is every past run, replayable step by step.\n\nAuthor is the one to try on your own systems. It takes a sentence.",
    mechanism:
      "An incident you write is stored in the same table as the sample ones and goes through the identical path. There is no separate demo mode.",
    target: '[data-tour="nav-work"]',
    view: "work",
    reveal: [],
    nextLabel: "Procedures",
  },

  {
    id: "tour-procedures",
    title: "Procedures — the memory itself",
    body:
      "Every runbook the agent has learned, and every one you have brought. The coloured dots on a card are its provenance: one per policy rule it was derived from, cyan while that rule is unchanged and grey once it has moved.\n\n<b>Import a runbook</b> is how your existing material gets in. Paste a wiki page or a Markdown runbook; the model proposes which policy rules it depends on, you confirm them, and from that moment it is governed exactly like one the agent wrote itself.",
    mechanism:
      "An imported procedure never wins retrieval over a compiled one. It is advisory until it has earned otherwise.",
    target: '[data-tour="nav-procedures"]',
    view: "procedures",
    reveal: [],
    nextLabel: "Policy",
  },

  {
    id: "tour-policy",
    title: "Policy — the rules the agent has to obey",
    body:
      "Not settings. These are the constraints the agent is bound by, and changing one is what invalidates memory.\n\n<b>New rule</b> lets you write your own: pick a fact, pick a comparison, and it becomes something the engine enforces on every run. That is the part most tools do not have — a policy you author is enforced, versioned and cascaded identically to the ones that shipped.",
    mechanism:
      "A rule carries a predicate and an enforcement mode. Advisory rules are prose that still gets cited and still goes stale; enforcing rules decide.",
    target: '[data-tour="nav-policy"]',
    view: "policy",
    reveal: [],
    nextLabel: "Connections",
  },

  {
    id: "tour-connections",
    title: "Connections — using this from your own agent",
    body:
      "The part that makes this a tool rather than an app. Two halves.\n\n<b>Apps Cascade talks to</b>: point it at a Slack or Discord webhook and the next refusal lands in a real channel.\n\n<b>Agents that call Cascade</b>: create a key, and any agent you already run can ask one question over HTTP or MCP — <i>is what I remember still valid?</i> It needs no model and no execution, so it works with any framework you are already using.",
    mechanism:
      "Keys are scoped and revocable. A key that only asks about memory cannot start a remediation.",
    target: '[data-tour="nav-connections"]',
    view: "connections",
    reveal: [],
    nextLabel: "The rest of the screens",
  },

  {
    id: "tour-extensions",
    title: "Four screens are the product. The rest you choose.",
    body:
      "Work, Procedures, Policy and Connections are the whole system: incidents run, memory lives, rules invalidate it, and other things reach it. You have seen all four.\n\nEverything else lives here and starts switched off. Each one explains what it is, when you would open it, how to use it properly and a worked example, so you can decide rather than guess. <b>Adding one puts it on the sidebar; removing it takes the screen away and deletes nothing.</b>",
    mechanism:
      "Continuing adds all four so the rest of this walkthrough can visit them. Remove any of them afterwards and nothing breaks.",
    target: '[data-tour="nav-extensions"]',
    view: "extensions",
    reveal: [],
    nextLabel: "Add them and carry on",
  },

  {
    id: "tour-system",
    title: "System — the machine, read live",
    body:
      "The provenance graph as it actually is, and the query plan retrieval actually used, both read from the cluster rather than drawn in a diagram.\n\nThe useful habit here is checking a claim instead of believing it. The README says a rule change is four writes whatever depends on it; the edge count on this screen moves with what you have learned, and the write count does not.",
    mechanism:
      "If the plan ever stops naming pb_embed_idx, retrieval has quietly become a table scan and every latency number elsewhere in the product is wrong.",
    target: '[data-tour="nav-system"]',
    view: "system",
    reveal: [],
    nextLabel: "Intelligence",
  },

  {
    id: "tour-intelligence",
    title: "Intelligence — what it saved, what a rule holds up, what already failed",
    body:
      "<b>Savings</b> is what reuse has cost and avoided; read it as a ratio, since the total only tells you how much you have run. <b>Blast radius</b> is what a rule is currently holding up, which is worth knowing before you tighten one. <b>Negative memory</b> is approaches that already failed on a class of incident, so the planner does not pay to rediscover them.",
    mechanism:
      "Negative memory is advisory and never blocks anything. Policy blocks things; a warning that could block would be a second policy engine nobody wrote down.",
    target: '[data-tour="nav-intelligence"]',
    view: "intelligence",
    reveal: [],
    nextLabel: "Evidence",
  },

  {
    id: "tour-evidence",
    title: "Evidence — whether any of this is actually better",
    body:
      "The same twelve incidents decided by three systems: a direct prompt, a normal cached-runbook memory, and this one. Same model, same policy, same cases.\n\nIt is worth reading the part where the result went against us. The baselines were expected to execute stale procedures and did not, because a strong model handed the current policy notices the conflict on its own. What separated them is narrower, and it is written down rather than tidied away.",
    mechanism:
      "The page renders a committed result file, and prints the command that regenerates it. A number you cannot re-derive is a claim, not evidence.",
    target: '[data-tour="nav-evidence"]',
    view: "evidence",
    reveal: [],
    nextLabel: "Two more things",
  },

  {
    id: "tour-dock",
    title: "The side panel — asking, and approving",
    body:
      "<b>Ctrl-\\</b> opens it, and it holds the two things you consult rather than visit.\n\n<b>Copilot</b> answers questions about this database in English and shows you the SQL it ran, so you can check it. <b>Approvals</b> is where an action waits when policy permits it but the runbook has not yet earned the right to act unsupervised.",
    mechanism:
      "Copilot is read-only by construction, and refuses anything that is not a single SELECT.",
    target: '[data-tour="nav-dock"]',
    reveal: [],
    nextLabel: "And the fastest way around",
  },

  {
    id: "tour-palette",
    title: "Ctrl-K does everything",
    body:
      "Every destination, every action, and the reset, from one box. Type a few letters of what you want.\n\nIf you only remember one shortcut, this is the one.",
    mechanism: "",
    target: '[data-tour="nav-commands"]',
    reveal: [],
    nextLabel: "Make it yours",
  },

  {
    id: "handover",
    title: "Everything so far ran on our data",
    body:
      "Which is the fair objection to any demo. So here is the same system on yours: import a runbook you already have, write a policy rule the agent must obey, give your own agent a key, or send the next refusal to your Slack.\n\nThe first one takes about ten seconds.",
    mechanism:
      "None of it is a separate mode. Your rules and procedures sit in the same tables as the sample ones, and restoring the sample world leaves every one of them in place.",
    target: '[data-tour="make-it-yours"]',
    view: "work",
    reveal: [],
    nextLabel: "One last thing",
  },

  /**
   * The exit.
   *
   * A walkthrough that has just shown a reviewer nine screens has also just
   * demonstrated that the product has nine screens, which is the opposite of
   * what most people want on a Tuesday. This step exists so the tour can hand
   * back something smaller than it borrowed.
   */
  {
    id: "work-mode",
    title: "Now empty it out and make it yours",
    body:
      "Everything you have seen ran on data that shipped with the product, which is the fair objection to any demo.\n\n<b>Work mode</b> answers it: the sample incidents go, the runbooks the walkthrough compiled go, and you are left with the four screens and nothing in them. Your rules, imported procedures, connections and keys all survive it.\n\nFrom there it is the checklist on the Work screen: bring a runbook you already have, write a rule the agent must obey, or give your own agent a key.",
    mechanism:
      "Nothing is deleted. The sample world comes back from the header button whenever you want it, and the extensions you added stay added.",
    reveal: [],
    nextLabel: "Switch to work mode",
  },
];
