import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  SubSection,
  Callout,
  Table,
  Steps,
  Step,
  Defs,
  C,
  UI,
  Kbd,
  Where,
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Running incidents",
  description:
    "How to submit an incident, read the live step stream, and understand every outcome Cascade can produce.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Using Cascade"
        title="Running incidents"
        lede="The Incidents view is where work happens. This page covers what to type, what the stream is telling you, and what each outcome means."
      />

      <Where>
        <UI>Incidents</UI>, the first icon in the activity bar
      </Where>

      <Section title="Submitting an incident">
        <p>
          Type into the box at the top of the console and press <Kbd>Enter</Kbd>{" "}
          or click <UI>Run</UI>. The form is plain text, but it must contain an
          incident ID that exists.
        </p>

        <Table
          head={["Type this", "Result"]}
          widths={["330px", "auto"]}
          rows={[
            [<C key="a">Remediate INC-1001</C>, "The normal form. Works."],
            [<C key="b">INC-1005</C>, "Also works. The ID is what matters."],
            [
              <C key="c">Fix the checkout service</C>,
              "Fails. No incident ID, so there is nothing to look up.",
            ],
            [
              <C key="d">Remediate INC-9999</C>,
              "Fails on the first step. That incident does not exist.",
            ],
          ]}
        />

        <p>
          The input is disabled while a task is running and the button reads{" "}
          <UI>Running…</UI>. One task at a time keeps the stream readable.
        </p>

        <Callout kind="note" title="The faster way">
          Press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> and start typing an incident
          number. The <UI>Run</UI> group lists six demo incidents, each labelled
          with what it exercises, so you can pick the one that demonstrates the
          behaviour you want without remembering IDs.
        </Callout>
      </Section>

      <Section title="Explore or guided">
        <p>
          As soon as the run starts, a badge appears under the input. It tells
          you which of two paths Cascade took, and it is the single most
          informative thing on the screen.
        </p>

        <Table
          head={["Badge", "Means", "Costs"]}
          widths={["240px", "auto", "160px"]}
          rows={[
            [
              <span key="a">
                <UI>Exploring</UI> with a magnifier
              </span>,
              "No usable runbook. Cascade is planning from scratch, one model call per step.",
              "Slow and token-heavy",
            ],
            [
              <span key="b">
                <UI>Runbook · name v1</UI> with a lightning bolt
              </span>,
              "A saved procedure matched and its policy dependencies were confirmed current. Cascade is executing it directly.",
              "Fast and near-free",
            ],
          ]}
        />

        <SubSection title="Why it explored when you expected reuse">
          <p>Three different reasons, and they are worth telling apart.</p>
          <Defs
            items={[
              {
                term: "Nothing matched",
                def: "No saved runbook is semantically close enough to this incident. Normal for the first run of any new problem shape.",
              },
              {
                term: "Matched but stale",
                def: "A runbook matched, but one of the policy rules it was built on has moved. Cascade refuses to reuse it and plans afresh. Check Runbooks for an amber suspect card.",
              },
              {
                term: "Matched but preconditions failed",
                def: "The runbook matched and is fresh, but its stated preconditions do not hold for this incident. Counted as a precondition miss in the hit rate.",
              },
            ]}
          />
        </SubSection>
      </Section>

      <Section title="Reading the step stream">
        <p>
          Each line is one real tool call as it completes. Left to right: step
          number, tool name, arguments, a tick or a cross, and the duration in
          milliseconds.
        </p>

        <Table
          head={["Tool", "What it does", "Writes anything?"]}
          widths={["250px", "auto", "130px"]}
          rows={[
            [
              <C key="a">get_incident</C>,
              "Reads the incident: kind, service, tier, deploy time, severity.",
              "No",
            ],
            [
              <C key="b">get_rules</C>,
              "Reads the current policy for a domain.",
              "No",
            ],
            [
              <C key="c">check_remediation_eligibility</C>,
              "Asks policy whether this action is permitted for this incident. Returns a verdict and a reason.",
              "No",
            ],
            [
              <C key="d">apply_remediation</C>,
              "Performs the fix: rollback, restart or scale up.",
              "Yes",
            ],
            [
              <C key="e">notify_oncall</C>,
              "Satisfies the notification rule after an automated action.",
              "Yes",
            ],
            [
              <C key="f">final_answer</C>,
              "Ends the run and records the outcome.",
              "Yes",
            ],
          ]}
        />

        <Callout kind="good" title="The eligibility check is not advisory">
          If <C>check_remediation_eligibility</C> returns a refusal, no
          side-effecting step runs afterwards, on either path. Guided execution
          does not replay its saved steps regardless of the verdict. That was a
          real defect once and it is now regression-tested.
        </Callout>
      </Section>

      <Section title="Outcomes">
        <p>
          When the run ends, a chip appears in <UI>Recent Tasks</UI> at the
          bottom of the console.
        </p>

        <Table
          head={["Chip", "Means", "What to do"]}
          widths={["150px", "auto", "auto"]}
          rows={[
            [
              <UI key="a">remediated</UI>,
              "Policy allowed it, the action was applied, on-call was notified.",
              "Nothing. Check Runbooks in a few seconds for what it learned.",
            ],
            [
              <UI key="b">escalated</UI>,
              "Cascade decided it must not act, and said why. Usually a tier or window rule.",
              "This is a correct outcome, not a failure. Read the last step for the reason.",
            ],
            [
              <UI key="c">interrupted</UI>,
              "A policy changed while this task was in flight. It stopped and re-planned under the new rules.",
              "Nothing. Re-run if you want a clean result.",
            ],
            [
              <UI key="d">failed</UI>,
              "A tool errored. The stream shows a red cross on the step that broke.",
              "Check the API terminal. This is the only outcome that indicates something is wrong.",
            ],
          ]}
        />

        <Callout kind="warn" title="Escalated is a success">
          The most common misreading of a Cascade demo is treating an escalation
          as a bug. Refusing to act outside policy is the product working. INC-1003
          and INC-1004 exist specifically to produce escalations.
        </Callout>
      </Section>

      <Section title="What happens after a successful run">
        <Mermaid
          caption="Compilation happens in the background, so the runbook appears a moment after the run finishes."
          chart={`
flowchart LR
    R["Run<br/>succeeds"] --> E["Episode<br/>recorded"]
    E --> O["Outbox event<br/>queued"]
    O --> W["Worker picks<br/>it up"]
    W --> P["Runbook<br/>compiled"]
    W --> V["Policy rules it<br/>depended on, pinned"]
    P --> L["Appears in<br/>Runbooks"]
    V --> L
`}
        />
        <p>
          Nothing is written speculatively. Only a run that actually succeeded
          becomes a runbook, and only the rules that were genuinely consulted
          get recorded as dependencies.
        </p>
      </Section>

      <Section title="The twelve demo incidents">
        <p>
          Seeded by migration <C>002</C>. Each exists to make a specific
          behaviour reproducible.
        </p>

        <Table
          head={["ID", "Shape", "Expected outcome"]}
          widths={["110px", "auto", "auto"]}
          rows={[
            [
              <C key="a">INC-1001</C>,
              "Bad deploy, svc-checkout, tier 2, 2h ago",
              "Remediated. This is the one that teaches the first runbook.",
            ],
            [
              <C key="b">INC-1002</C>,
              "Bad deploy, svc-search, tier 2, 3h ago",
              "Remediated, and should go guided if 1001 ran first.",
            ],
            [
              <C key="c">INC-1003</C>,
              "Bad deploy, svc-payments, tier 1, 1h ago",
              "Escalated. Tier 1 is production critical and cannot be touched automatically.",
            ],
            [
              <C key="d">INC-1004</C>,
              "Bad deploy, svc-checkout, tier 2, 30h ago",
              "Escalated. Outside the 24 hour rollback window.",
            ],
            [
              <C key="e">INC-1005</C>,
              "Error spike, svc-search, tier 2",
              "Remediated by restart. A different runbook shape from the deploy ones.",
            ],
            [
              <C key="f">INC-1006</C>,
              "Error spike, svc-payments, tier 1",
              "Escalated on tier.",
            ],
            [
              <C key="g">INC-1007</C>,
              "Resource exhaustion, svc-recommendations, tier 3",
              "Remediated by scale up.",
            ],
            [
              <C key="h">INC-1008</C>,
              "Resource exhaustion, svc-search, tier 2",
              "Remediated by scale up.",
            ],
            [
              <C key="i">INC-1009</C>,
              "Bad deploy, svc-analytics, tier 3, 5h ago",
              "Remediated under the default window. Escalates once you shorten the window to 4 hours, which is what makes it the freshness demo.",
            ],
            [
              <C key="j">INC-1010</C>,
              "Bad deploy, svc-notifications, deployed exactly 24h ago",
              "The boundary case. Tests inclusive versus exclusive comparison.",
            ],
            [
              <C key="k">INC-1011</C>,
              "Error spike, svc-notifications, tier 3",
              "Remediated by restart.",
            ],
            [
              <C key="l">INC-1012</C>,
              "Bad deploy, already resolved",
              "Present so historical queries and counterfactual replay have closed history to work with.",
            ],
          ]}
        />

        <SubSection title="The six services">
          <Table
            head={["Service", "Tier", "Automatically remediable by default?"]}
            widths={["230px", "90px", "auto"]}
            rows={[
              ["svc-payments", "1", "No. Tier 1 requires a human."],
              ["svc-checkout", "2", "Yes"],
              ["svc-search", "2", "Yes"],
              ["svc-recommendations", "3", "Yes"],
              ["svc-analytics", "3", "Yes"],
              ["svc-notifications", "3", "Yes"],
            ]}
          />
        </SubSection>
      </Section>

      <Section title="Interrupting a run on purpose">
        <p>
          Worth doing once, because it is the most vivid demonstration of the
          idea.
        </p>
        <Steps>
          <Step title="Start a run">
            <p>
              Submit <C>Remediate INC-1001</C> and immediately switch to{" "}
              <UI>Policy</UI>.
            </p>
          </Step>
          <Step title="Commit a rule change while it is still in flight">
            <p>
              Change <C>incident.rollback_window</C> and commit. The
              confirmation dialog will list the running task under{" "}
              <UI>Running tasks that will be interrupted</UI>.
            </p>
          </Step>
          <Step title="Switch back to Incidents">
            <p>
              A banner reads that policy changed mid-flight and the run is
              re-planning under the new rules. The task ends as{" "}
              <UI>interrupted</UI>.
            </p>
          </Step>
        </Steps>
        <Callout kind="good" title="Why this is not just a cancel">
          The interrupt is part of the same atomic write as the rule change. A
          task cannot finish under rules that no longer exist, and it cannot
          half-apply an action under old rules while the new ones are already
          live.
        </Callout>
      </Section>
    </>
  );
}
