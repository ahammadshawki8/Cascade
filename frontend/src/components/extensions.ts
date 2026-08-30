import type { ViewId } from "./ActivityBar";

/**
 * Auxiliary surfaces, as things you choose rather than things you are given.
 *
 * Four destinations are the product: incidents run in Work, memory lives in
 * Procedures, the rules that invalidate it live in Policy, and Connections is
 * how anything outside this tab reaches any of it. Remove one and the system
 * cannot demonstrate what it is for.
 *
 * Everything else is real, works, and is not needed by everyone. Shipping all
 * of it on the rail by default was the honest mistake: it read as a feature
 * tour, and a viewer with eight icons and no explanation assumes the tool is
 * complicated rather than that they have been given too much.
 *
 * So the auxiliaries start uninstalled and each one has to argue for itself
 * here, in the same terms a person would ask: what is it, when would I open it,
 * how do I use it properly, and what does that look like. If an extension
 * cannot answer those four questions it should not exist, which is a useful
 * test to have to pass.
 */

export interface Extension {
  id: string;
  name: string;
  /** One line, shown in the list. */
  blurb: string;
  /** Which destination this adds, if it adds one. */
  view?: ViewId;
  /** Where it appears once installed. */
  surface: string;
  /** What it is, in a paragraph. */
  about: string;
  /** The moment you would actually reach for it. */
  whenToUse: string;
  /** Getting value out of it rather than just opening it. */
  howToUse: string[];
  /** A concrete situation, start to finish. */
  example: { title: string; body: string };
}

export const EXTENSIONS: Extension[] = [
  {
    id: "evidence",
    name: "Evidence",
    blurb: "The measured comparison against two baselines, on the same incidents.",
    view: "evidence",
    surface: "Adds an Evidence destination",
    about:
      "A recorded evaluation of this system against two alternatives: a direct prompt with the policy in its context, and an ordinary cached-runbook memory with no provenance. Same twelve incidents, same model, decided twice — once under the policy the runbooks were learned under, then again with one rule tightened.",
    whenToUse:
      "Before you trust any claim made anywhere else in this interface, and whenever someone asks whether provenance is worth the cost. It is also the honest answer to 'is this better than just prompting a good model', which is the right question to ask.",
    howToUse: [
      "Read the phase table before the headline. Phase one only establishes that every arm can apply a rule; phase two is the experiment.",
      "Look at the unsafe-action count separately from the correctness percentage. Over-escalating costs a human five minutes, acting where policy forbids it is the error that hurts.",
      "Open the per-case grid and find the disagreements. Three arms agreeing tells you nothing; the cases where they split are the entire result.",
      "Re-run it yourself with the command printed on the page. A number you cannot reproduce is a claim, not evidence.",
    ],
    example: {
      title: "Where the cached-runbook baseline actually fails",
      body: "In phase two it drops from 90.9% to 81.8%, and its two new errors are on resource-exhaustion incidents — which the rollback window does not govern at all. Tightening one rule made it cautious about unrelated work, because a policy held in a prompt is absorbed as a mood rather than as a scope. A predicate carrying a `when` clause cannot make that mistake, and that difference is the honest argument for this design.",
    },
  },
  {
    id: "architecture",
    name: "Architecture",
    blurb: "The live provenance graph and the query plan retrieval actually used.",
    view: "system",
    surface: "Adds a System destination",
    about:
      "A read of the running cluster rather than a diagram of one: the provenance edges between procedures and the rule versions they were derived from, the counts behind them, and the EXPLAIN output proving retrieval used the vector index instead of scanning the table.",
    whenToUse:
      "When you want to check that the mechanism is real rather than described, and when you are explaining to somebody else how invalidation can be constant-time.",
    howToUse: [
      "Follow one procedure's edges to the rules it cites. That fan-out is what a policy change has to reach, and the reason it does not have to write to any of it.",
      "Read the query plan and look for the index name. One stray predicate is enough to drop a vector index and full-scan while still returning correct answers.",
      "Compare the edge count with the write count of a rule change. They are unrelated on purpose.",
    ],
    example: {
      title: "Checking a claim rather than believing it",
      body: "The README says a rule change is four writes whatever depends on it. Change a rule in Policy, then come here: the edge count moves with what you have learned, and the write count does not move at all. If the plan ever stops naming `pb_embed_idx`, retrieval has quietly become a table scan and every latency number elsewhere is wrong.",
    },
  },
  {
    id: "intelligence",
    name: "Intelligence",
    blurb: "Savings, blast radius before a change, and approaches that already failed.",
    view: "intelligence",
    surface: "Adds an Intelligence destination",
    about:
      "Three read-only views over what the engine has already recorded. Savings is what reuse has cost and avoided. Blast radius is what a given rule is currently holding up. Negative memory is the set of approaches that failed on a class of incident, so the planner does not pay to rediscover them.",
    whenToUse:
      "Savings when someone asks what this is worth. Blast radius before touching a rule you are unsure about. Negative memory when a cold run seems to be repeating a mistake you have seen before.",
    howToUse: [
      "Read savings as a ratio, not a total. The absolute number scales with how much you have run; the ratio is the property.",
      "Check blast radius before a policy change, not after. The Policy dry-run answers the same question at the moment you are making the decision, so use this when you are exploring rather than committing.",
      "Treat negative memory as advisory. It warns the planner; it never blocks an action, because policy is what blocks actions.",
    ],
    example: {
      title: "Deciding whether a rule is safe to tighten",
      body: "You are about to cut the rollback window and want to know the cost. Blast radius shows the rule is currently cited by every rollback procedure you have. That does not mean do not change it — it means the change will quarantine all of them at once, and you should expect the next few incidents to run cold while they are re-derived.",
    },
  },
  {
    id: "approvals",
    name: "Approvals and insights",
    blurb: "Actions parked for a human, and policy changes the engine suggests.",
    surface: "Adds an Approvals icon, opening the right panel",
    about:
      "Two queues. Approvals holds actions that policy permits but that a procedure has not yet earned the right to take unsupervised. Insights holds policy changes the engine has worked out from your own history — a widening it can show would have recovered incidents that escalated, without permitting anything new.",
    whenToUse:
      "Only once you have turned autonomy gating on. It is off by default, because a threshold above zero stops every first reuse for a human, which is the right behaviour for production and a poor one for a demo.",
    howToUse: [
      "Set AUTONOMY_MIN_CONFIDENCE to about 0.6 to make the gate real. A procedure then earns autonomy over three supervised successes, 0.30 to 0.45 to 0.60.",
      "Approving re-runs the task rather than resuming it mid-flight. That is only safe because every side-effecting tool is idempotent on the task and step, which is asserted in the suite.",
      "Read an insight as a proposal, not a recommendation. It is computed by re-deciding every historical incident under the change, and you can re-run that computation before committing.",
      "Expect both to be empty on a fresh install. That is the honest default, not a fault.",
    ],
    example: {
      title: "The gate that does independent work",
      body: "Policy already refuses tier-1 services, so the tier gate never reaches autonomy. The one that earns its keep is confidence: policy permits the action, and the procedure simply has not been right often enough yet to take it alone. That is a different question from whether the action is allowed, and it is the reason this exists as its own queue.",
    },
  },
  {
    id: "commands",
    name: "Command palette button",
    blurb: "A button for Ctrl-K, for people who would rather click than remember.",
    surface: "Adds Commands to the sidebar",
    about:
      "The palette reaches every destination, every incident, the copilot and the reset from one box, with subsequence matching so `gint` finds Go to Intelligence. This extension only adds the button; the keyboard shortcut works whether or not it is installed.",
    whenToUse:
      "Install it if you are new here or you share a screen with people who are. Remove it once Ctrl-K is in your fingers.",
    howToUse: [
      "Type a few letters of what you want rather than navigating. It matches on subsequences, not prefixes.",
      "It reaches destinations you have not installed and adds them as it opens them, so nothing is ever truly out of reach.",
    ],
    example: {
      title: "Getting somewhere you removed",
      body: "You took Intelligence off the sidebar last week and now want the blast radius before changing a rule. Ctrl-K, type `blast`, and it comes back with the screen. Removing something here has never meant losing it.",
    },
  },
  {
    id: "docs",
    name: "Documentation link",
    blurb: "A sidebar link to the product documentation.",
    surface: "Adds Docs to the sidebar",
    about:
      "Seventeen pages covering what to type, what to press and what each badge means, written for someone using the product rather than reading its source. It opens in the same tab and comes back.",
    whenToUse:
      "When a screen has not explained itself and you want more than a tooltip. The extension pages you are reading now cover the auxiliary screens; the docs cover the four that are always here.",
    howToUse: [
      "Start at Key concepts if the vocabulary is unfamiliar. Provenance, freshness and staleness have precise meanings here and the rest of the docs assume them.",
      "The API reference lists every endpoint with the role it needs, which is the fastest way to see what an agent of your own could do.",
    ],
    example: {
      title: "Working out what a badge means",
      body: "A procedure reads `suspect` and you want to know whether that is bad. Managing runbooks explains the four states, which transitions are automatic, and why a suspect procedure is refused rather than repaired.",
    },
  },
  {
    id: "copilot",
    name: "Ops Copilot",
    blurb: "Ask about this database in English and see the SQL it ran.",
    surface: "Adds a Copilot icon, opening the right panel",
    about:
      "A read-only question answerer over the same tables everything else reads. It turns a question into a single SELECT, runs it, and shows you both the answer and the statement, so you can check the query rather than trust the summary.",
    whenToUse:
      "When the question you have does not match any view on screen. 'Which procedures cite the rule I am about to change' is faster to ask than to assemble by clicking.",
    howToUse: [
      "Read the SQL it shows you. That is the point of showing it; an answer whose query you have not checked is a guess with formatting.",
      "Ask about things, not about opinions. It queries state well and speculates badly.",
      "Expect refusals. Anything that is not a single SELECT is rejected outright, including a valid SELECT with a second statement stacked behind it.",
    ],
    example: {
      title: "A question no view answers directly",
      body: "Ask 'which procedures have been reused most and what do they depend on'. It joins the procedure table to its provenance edges and shows you the statement it used. If the SQL names a column that does not exist, you have found a hallucination rather than an answer — which is exactly why the statement is on screen.",
    },
  },
];

const STORAGE_KEY = "cascade_extensions_v1";

export function loadInstalled(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((id) => EXTENSIONS.some((e) => e.id === id))
      : [];
  } catch {
    return [];
  }
}

export function saveInstalled(ids: string[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* private browsing: the choice simply does not persist */
  }
}

/** Destinations contributed by the installed set. */
export function installedViews(ids: string[]): ViewId[] {
  return EXTENSIONS.filter((e) => ids.includes(e.id) && e.view).map(
    (e) => e.view as ViewId
  );
}
