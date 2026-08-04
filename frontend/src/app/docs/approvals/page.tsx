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
  Code,
  C,
  UI,
  Kbd,
  Where,
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Approving actions",
  description:
    "The approvals queue, how a gated action behaves while it waits, and the policy suggestions Cascade brings you.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Using Cascade"
        title="Approving actions"
        lede="Two things land in this view: actions Cascade wants to take but is not trusted enough to take alone, and policy changes it thinks you should consider."
      />

      <Where>
        <UI>Approvals</UI>, the sixth icon in the activity bar
      </Where>

      <Section title="Approvals">
        <p>
          Policy decides whether an action is <em>permitted</em>. Confidence
          decides whether a particular runbook has earned the right to take it{" "}
          <em>unsupervised</em>. Those are different questions, and the second
          one is what parks a task here.
        </p>

        <Mermaid
          caption="A parked task has applied nothing. It stops before the side-effecting step, not after it."
          chart={`
flowchart TD
    A["Run starts"] --> B{"Policy<br/>permits it?"}
    B -- "No" --> C["Escalate"]
    B -- "Yes" --> D{"Runbook confidence<br/>above threshold?"}
    D -- "Yes" --> E["Apply the action"]
    D -- "No" --> F["Park in Approvals<br/>nothing applied"]
    F -- "you approve" --> G["Re-run from the start"]
    F -- "you reject" --> H["Task ends, reason recorded"]
    G --> E
`}
        />

        <SubSection title="Reading an approval card">
          <Table
            head={["Field", "Means"]}
            widths={["190px", "auto"]}
            rows={[
              ["Incident ID", "Which incident this action belongs to."],
              ["Time", "When it was parked."],
              [
                "Action",
                "The exact operation waiting, for example a rollback on a named service.",
              ],
              [
                "Confidence",
                "The runbook's confidence as a percentage. This is why it is here.",
              ],
              [
                "Reason",
                "One sentence explaining what triggered the gate.",
              ],
            ]}
          />
        </SubSection>

        <SubSection title="Approving">
          <p>
            Click <UI>Approve</UI>. The task resumes and the action is applied.
            The queue count in the activity bar and the status bar both drop.
          </p>
          <Callout kind="good" title="Approving re-runs the task, and that is safe">
            Cascade does not suspend a coroutine and wake it up. It replays the
            task from the beginning. Every side-effecting tool is idempotent on
            the pair of task and step index, so a remediation is applied exactly
            once even though the run happened twice. That is asserted directly
            in the test suite.
          </Callout>
        </SubSection>

        <SubSection title="Rejecting">
          <Steps>
            <Step title="Click Reject">
              <p>
                The <UI>Approve</UI> button disappears and a text input takes
                its place.
              </p>
            </Step>
            <Step title="Type a reason">
              <p>
                Required. The input is placeholder-labelled{" "}
                <UI>Reason for rejection...</UI> and the submit stays disabled
                until you have typed something.
              </p>
            </Step>
            <Step title="Press Enter or click Submit Rejection">
              <p>
                Press <Kbd>Esc</Kbd> to back out instead. The reason is written
                to the audit log alongside who rejected it.
              </p>
            </Step>
          </Steps>
        </SubSection>

        <SubSection title="Who is recorded as approving">
          <p>
            Not whoever the browser claims. The server takes the actor from the
            credential on the request and ignores any identity supplied by the
            caller. Who authorised an irreversible action is not a field the
            client gets to assert.
          </p>
          <p>
            Approving requires the <strong>operator</strong> role, not admin. On
            call should be able to release a gated remediation without also
            holding the keys to policy.
          </p>
        </SubSection>
      </Section>

      <Section title="Turning the gate on">
        <p>
          The confidence gate is off by default, because a threshold above zero
          stops every first reuse and that makes a first run of the product
          confusing.
        </p>

        <Code lang="bash" caption="backend/.env">{`AUTONOMY_MIN_CONFIDENCE=0.6`}</Code>

        <p>
          Restart the API. Now a runbook has to earn autonomy over three
          supervised successes, since confidence climbs 0.30, 0.45, 0.60 as it
          proves itself.
        </p>

        <Table
          head={["Threshold", "Effect"]}
          widths={["170px", "auto"]}
          rows={[
            [<C key="a">0</C>, "Gate disabled. Nothing is parked. This is the default."],
            [
              <C key="b">0.6</C>,
              "Recommended for a demo. New runbooks are supervised until they have three successes.",
            ],
            [
              <C key="c">1.0</C>,
              "Every automated action requires a human. Useful for showing the gate, not for using the product.",
            ],
          ]}
        />

        <Callout kind="note" title="This is orthogonal to policy, not a second copy of it">
          Tier 1 services are already refused by the tier rule before autonomy
          is ever consulted, so the gate does no work there. Where it earns its
          place is the case policy <em>permits</em>: the action is allowed, but
          this particular procedure has not proved itself yet.
        </Callout>
      </Section>

      <Section title="Insights">
        <p>
          The lower half of the view. These are policy changes Cascade thinks
          are worth considering, based on what it has watched happen.
        </p>

        <SubSection title="How a proposal is produced">
          <p>
            Not by asking a model what seems reasonable. For each candidate
            change, Cascade re-decides every historical incident under that
            rule, counts what would have been recovered, and keeps the proposal
            only if two things hold:
          </p>
          <ul>
            <li>It is the smallest change sufficient to recover those incidents.</li>
            <li>It blocks nothing that is currently allowed.</li>
          </ul>
          <p>
            The result is a claim you can check. Clicking{" "}
            <UI>Review policy</UI> opens the Policy view with the recommended
            value filled in, and the counterfactual preview there recomputes the
            identical calculation in front of you.
          </p>
        </SubSection>

        <SubSection title="Acting on one">
          <Defs
            items={[
              {
                term: "Review policy",
                def: (
                  <>
                    Jumps to <UI>Policy</UI> with the suggested rule highlighted
                    and the suggested value prefilled. Nothing is committed. You
                    still go through the normal review dialog.
                  </>
                ),
              },
              {
                term: "Ignore it",
                def: "Insights are advisory. Leaving one alone has no effect on anything.",
              },
            ]}
          />
        </SubSection>

        <SubSection title="Generating insights on demand">
          <p>
            Press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> and run{" "}
            <UI>Scan for new insights</UI>. A toast reports how many findings
            the scan produced. Running it twice does not create duplicates.
          </p>
          <p>
            Early on, a scan usually finds nothing, because there is no history
            to reason over. Run several incidents first, including ones you
            expect to be blocked.
          </p>
        </SubSection>
      </Section>

      <Section title="Knowing there is something waiting">
        <p>You do not have to keep this view open.</p>
        <ul>
          <li>
            A number badge appears on the <UI>Approvals</UI> icon in the
            activity bar.
          </li>
          <li>
            The status bar shows <UI>N awaiting approval</UI> with an amber dot.
          </li>
          <li>
            When a run parks an action, Cascade switches you to this view
            automatically, because the run cannot continue until you decide.
          </li>
        </ul>
      </Section>
    </>
  );
}
