import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  SubSection,
  Callout,
  Table,
  Defs,
  Steps,
  Step,
  C,
  UI,
  Where,
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Changing policy",
  description:
    "The four rules, how to preview the impact of a change before committing it, and what happens the instant you do.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Using Cascade"
        title="Changing policy"
        lede="Policy is the set of rules Cascade must obey. Changing one is the single most consequential thing you can do in this product, so the interface makes you look at the consequences first."
      />

      <Where>
        <UI>Policy</UI>, the third icon in the activity bar
      </Where>

      <Section title="The four rules">
        <p>
          Each row shows the rule key, its current version, the rule stated in
          English with its variables highlighted, and an input per variable.
        </p>

        <Table
          head={["Rule", "Says", "Variables"]}
          widths={["230px", "auto", "150px"]}
          rows={[
            [
              <C key="a">incident.auto_remediate_tier</C>,
              "Automated remediation is allowed only for services at this tier or higher. Tier 1 is production critical and always requires a human.",
              <C key="a2">min_tier</C>,
            ],
            [
              <C key="b">incident.rollback_window</C>,
              "Rollback is allowed only if the deploy happened within this many hours. Beyond it, rollback is considered too risky.",
              <C key="b2">hours</C>,
            ],
            [
              <C key="c">incident.notify</C>,
              "On-call must be notified after any automated remediation.",
              "None",
            ],
            [
              <C key="d">incident.single_action</C>,
              "At most one automated remediation per incident. More than that requires escalation.",
              "None",
            ],
          ]}
        />

        <Callout kind="note" title="Tier numbers run the opposite way to importance">
          Tier 1 is the most critical. So <C>min_tier: 2</C> means tier 2 and
          below may be remediated automatically, and tier 1 may not. Raising{" "}
          <C>min_tier</C> to 3 is a <em>tightening</em>, not a loosening.
        </Callout>
      </Section>

      <Section title="Previewing a change">
        <p>
          Click into any variable input and type a new value. Nothing is
          committed. Two previews appear underneath after a short pause, and
          both are recomputed as you keep typing.
        </p>

        <SubSection title="Impact">
          <p>
            Counts the runbooks whose provenance cites this rule, and names them
            individually. These are the procedures that will be quarantined if
            you commit.
          </p>
          <p>
            If it reads <UI>No runbooks depend on this yet</UI>, the change is
            free. That is normal before you have run any incidents.
          </p>
        </SubSection>

        <SubSection title="Counterfactual">
          <p>
            A different and more interesting question: not which memories break,
            but what would actually have happened differently. Cascade re-decides
            every historical incident under the proposed rule and reports the
            net change.
          </p>
          <Table
            head={["Chip", "Means"]}
            widths={["190px", "auto"]}
            rows={[
              [
                <span key="a">
                  <C>+INC-1004</C> in teal
                </span>,
                "This incident was blocked before and would now be auto-remediated. Hover for the kind and service.",
              ],
              [
                <span key="b">
                  <C>−INC-1009</C> in amber
                </span>,
                "This incident was handled before and would now be blocked.",
              ],
            ]}
          />
          <Callout kind="good" title="Why both previews exist">
            Impact tells you what it costs you: memory you are throwing away.
            The counterfactual tells you what you are buying: incidents that
            move from blocked to handled, or the reverse. A policy decision
            needs both numbers.
          </Callout>
        </SubSection>
      </Section>

      <Section title="Committing a change">
        <Steps>
          <Step title="Click Review changes">
            <p>
              The button is disabled until the impact preview has finished. It
              reads <UI>Checking impact…</UI> while that is in progress.
            </p>
          </Step>
          <Step title="Read the two columns in the dialog">
            <p>
              Left: <UI>Runbooks that will be quarantined</UI>, each landing on{" "}
              <UI>Suspect</UI>. Right:{" "}
              <UI>Running tasks that will be interrupted</UI>. Either can read{" "}
              <UI>None</UI>.
            </p>
          </Step>
          <Step title="Click Commit change, or Cancel">
            <p>
              <UI>Cancel</UI> discards everything, including the edited value.
              Nothing was written at any point before this click.
            </p>
          </Step>
        </Steps>

        <Mermaid
          caption="One transaction. There is no moment at which a stale runbook is still considered usable."
          chart={`
flowchart TD
    C["Commit change"] --> T{"Single<br/>transaction"}
    T --> A["Rule version<br/>bumped"]
    T --> B["Dependent runbooks<br/>marked suspect"]
    T --> D["In-flight tasks<br/>flagged interrupted"]
    T --> E["Audit entry<br/>written"]
    A --> F["Committed together<br/>or not at all"]
    B --> F
    D --> F
    E --> F
`}
        />

        <p>
          The whole cascade completes in tens of milliseconds regardless of how
          many runbooks are affected, because staleness is derived by comparing
          the pinned version to the current one rather than stamped onto each
          row.
        </p>
      </Section>

      <Section title="After the change">
        <Table
          head={["Where", "What you will see"]}
          widths={["230px", "auto"]}
          rows={[
            [
              <UI key="a">Policy</UI>,
              "The version beside the rule key has gone up by one.",
            ],
            [
              <UI key="b">Runbooks</UI>,
              "Affected cards are amber and read suspect. Expanding one shows a red provenance dot on the rule you changed.",
            ],
            [
              <UI key="c">Incidents</UI>,
              "Any run that was in flight shows the interrupt banner and ends as interrupted.",
            ],
            [
              <span key="d">
                <UI>Intelligence</UI> then <UI>graph</UI>
              </span>,
              "The edge from that rule to each affected runbook is drawn red and dashed.",
            ],
          ]}
        />
      </Section>

      <Section title="Reverting">
        <p>
          There is no undo button. Set the value back and commit again. That
          creates a third version rather than restoring the first, which is
          deliberate: the audit log should show that a change was made and then
          reversed, not pretend it never happened.
        </p>
        <p>
          Runbooks quarantined by the original change do not automatically come
          back. Their provenance is pinned to v1 and current is now v3. Use{" "}
          <UI>Re-learn</UI> on each, or press <C>Ctrl</C> <C>K</C> and run{" "}
          <UI>Reset demo world</UI> to start from a clean v1 state.
        </p>
      </Section>

      <Section title="When a change is provably harmless">
        <p>
          Not every rule change invalidates the runbooks that cite it. Widening
          the rollback window from 4 hours to 24 cannot make a previously valid
          procedure unsafe, and Cascade recognises that.
        </p>
        <p>
          On commit, a triage pass runs over each quarantined runbook. When the
          change is provably relaxing, the dependency is re-pinned forward and
          the runbook reports fresh again through the ordinary check.
        </p>
        <Defs
          items={[
            {
              term: "Numeric comparison runs first",
              def: "Deterministically, before any model is consulted. A model is never asked to decide whether 24 is greater than 4.",
            },
            {
              term: "Triage can only clear, never permit",
              def: "It cannot mark a stale runbook usable while a version mismatch stands. It re-pins the dependency so the normal freshness join answers fresh on its own.",
            },
            {
              term: "Uncertainty leaves everything quarantined",
              def: "An unclear verdict, an unknown parameter, or any error means the runbook stays suspect. The safe direction is the default.",
            },
          ]}
        />
      </Section>

      <Section title="Cascade suggesting a change to you">
        <p>
          Cascade watches for policy that is blocking work it could safely
          allow, and proposes the smallest sufficient change. Those proposals
          appear in <UI>Approvals</UI> under <UI>Insights</UI>, and clicking{" "}
          <UI>Review policy</UI> opens this view with the recommended value
          already filled in and both previews computed.
        </p>
        <p>
          See <a href="/docs/approvals">Approving actions</a> for how those
          proposals are produced and why they are measured rather than guessed.
        </p>
      </Section>
    </>
  );
}
