/**
 * Tool calls, in English.
 *
 * `check_remediation_eligibility incident_id=INC-1001, action=rollback` is
 * precise and tells a non-author nothing. Every step is really a question the
 * agent asked and the answer it got, so show it that way and keep the raw call
 * available underneath for anyone who wants to audit it.
 */

export interface Narration {
  /** What the agent wanted to know, or is about to do. */
  question: string;
  /** What came back. Empty when the step carries no readable result. */
  answer: string;
}

const asStr = (v: unknown): string => (v == null ? "" : String(v));

export function narrate(tool: string, args: Record<string, unknown>): Narration {
  const incident = asStr(args.incident_id);
  const action = asStr(args.action);

  switch (tool) {
    case "get_incident":
      return {
        question: "What happened?",
        answer: incident ? `Reading the report for ${incident}` : "Reading the incident report",
      };

    case "get_rules":
      return {
        question: "What are the current rules?",
        answer: "Fetching company policy, at its latest version",
      };

    case "check_remediation_eligibility":
      return {
        question: action ? `Am I allowed to ${verb(action)}?` : "Am I allowed to act?",
        answer: "Checking this incident against policy",
      };

    case "apply_remediation":
      return {
        question: action ? `${Verb(action)}` : "Applying the fix",
        answer: incident ? `Acting on ${incident}` : "",
      };

    case "notify_oncall":
      return {
        question: "Telling the on-call engineer",
        // The message is the interesting part and it is long, so it is left to
        // the raw view rather than truncated into something misleading.
        answer: "Sending a summary of what was done and why",
      };

    default:
      return { question: tool.replace(/_/g, " "), answer: "" };
  }
}

function verb(action: string): string {
  switch (action) {
    case "rollback":
      return "roll back the deploy";
    case "restart":
      return "restart the service";
    case "scale_up":
      return "scale the service up";
    default:
      return action.replace(/_/g, " ");
  }
}

function Verb(action: string): string {
  const v = verb(action);
  return v.charAt(0).toUpperCase() + v.slice(1);
}

/**
 * The single line above the console that says what is going on right now.
 * One sentence, never two, and always in the agent's voice.
 */
export function narrateState(opts: {
  running: boolean;
  mode?: "explore" | "guided";
  playbookName?: string;
  outcome?: string | null;
  refusal?: "refused_stale" | "refused_precondition" | "no_match" | "reused" | null;
}): string | null {
  const { running, mode, playbookName, outcome, refusal } = opts;

  if (running) {
    if (mode === "guided") {
      return `I recognise this. Following the runbook I wrote earlier${
        playbookName ? ` (${playbookName})` : ""
      } — no thinking needed.`;
    }
    if (mode === "explore") {
      return "I have nothing I can reuse here, so I am working it out from scratch. This is the slow path.";
    }
    return "Searching my memory for something I can reuse…";
  }

  if (refusal === "refused_stale") {
    return "I found a matching runbook and refused it: a rule it was built on has changed since.";
  }
  if (refusal === "refused_precondition") {
    return "I found a matching runbook and refused it: it does not apply to this incident.";
  }
  if (refusal === "no_match" && outcome) {
    return "Nothing in memory matched, so I reasoned from policy. If that worked, it becomes a runbook.";
  }
  if (refusal === "reused" && outcome) {
    return "Solved by replaying a runbook, without calling the planner once.";
  }
  if (outcome) return `Finished: ${outcome}.`;
  return null;
}
