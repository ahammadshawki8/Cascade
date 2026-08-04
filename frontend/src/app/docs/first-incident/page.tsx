import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  Callout,
  Steps,
  Step,
  Table,
  C,
  UI,
  Kbd,
  Where,
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Your first incident",
  description:
    "A guided walkthrough of the full loop, with the exact text to type and the exact controls to press.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Getting started"
        title="Your first incident"
        lede="Fifteen minutes end to end. You will resolve an incident, watch a runbook get written, reuse it, then break it on purpose and watch Cascade refuse to use it."
      />

      <Callout kind="note" title="Before you start">
        The stack should be running and the status bar should read{" "}
        <UI>live</UI>. If it does not, go back to{" "}
        <a href="/docs/quickstart">Install and run</a>. If you have used the app
        before, press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> and run{" "}
        <UI>Reset demo world</UI> first so the numbers below match what you see.
      </Callout>

      <Section title="What you are about to do">
        <Mermaid
          caption="Five steps. Each one changes something visible in the interface."
          chart={`
flowchart TD
    S1["1 · Run INC-1001<br/>agent explores"] --> S2["2 · A runbook appears<br/>status: candidate"]
    S2 --> S3["3 · Run INC-1002<br/>agent reuses the runbook"]
    S3 --> S4["4 · Shorten the rollback window<br/>runbook turns suspect"]
    S4 --> S5["5 · Run INC-1009<br/>refused as stale, escalates"]
`}
        />
      </Section>

      <Section title="Step 1: solve something from scratch">
        <Where>
          <UI>Incidents</UI>, the first icon in the left rail
        </Where>

        <Steps>
          <Step title="Type the incident into the box at the top">
            <p>
              Click the input that reads <UI>Remediate INC-1001</UI> as
              placeholder text and type exactly:
            </p>
            <p>
              <C>Remediate INC-1001</C>
            </p>
            <p>
              Then press <Kbd>Enter</Kbd>, or click <UI>Run</UI> to the right of
              the box.
            </p>
          </Step>

          <Step title="Watch the badge under the input">
            <p>
              A badge appears reading <UI>Exploring</UI> with a magnifier icon.
              That means Cascade has no saved procedure for this and is planning
              from scratch. This is the expensive path.
            </p>
          </Step>

          <Step title="Watch the steps stream in">
            <p>
              Each line is one real tool call, numbered, with its arguments and
              how long it took. You should see roughly this shape:
            </p>
            <Table
              head={["Step", "What it is doing"]}
              widths={["260px", "auto"]}
              rows={[
                ["get_incident", "Reads the incident record"],
                [
                  "check_remediation_eligibility",
                  "Asks policy whether it is allowed to act at all",
                ],
                ["apply_remediation", "Performs the rollback"],
                ["notify_oncall", "Satisfies the notification rule"],
              ]}
            />
            <p>
              A green tick means the step succeeded. A red cross means it
              failed, and the run stops there.
            </p>
          </Step>

          <Step title="Check the result">
            <p>
              Under <UI>Recent Tasks</UI> at the bottom of the console, the row
              for this run ends with a green <UI>remediated</UI> chip.
            </p>
          </Step>
        </Steps>

        <Callout kind="good" title="What just happened underneath">
          The successful run was written to memory as an episode. A background
          job then turned it into a runbook and recorded which policy rules the
          run depended on. You did not have to ask for any of that.
        </Callout>
      </Section>

      <Section title="Step 2: look at what it learned">
        <Where>
          <UI>Runbooks</UI>, the second icon in the left rail
        </Where>

        <p>
          There is now one card. Give it a few seconds if the list is still
          empty, since compilation happens in the background.
        </p>

        <Table
          head={["What you see", "What it means"]}
          widths={["260px", "auto"]}
          rows={[
            [
              <span key="a">
                A name and <UI>v1</UI>
              </span>,
              "The procedure and its version. Versions go up when it is re-learned.",
            ],
            [
              <span key="b">
                An amber <UI>candidate</UI> pill
              </span>,
              "Learned but unproven. It needs three successful reuses to be promoted to active.",
            ],
            [
              "A thin bar under the card",
              "Confidence. It starts at 0.30 and rises with each success.",
            ],
            [
              <span key="c">
                <UI>1 uses · 1 ✓ · 0 ✗</UI>
              </span>,
              "How often it has been used and how that went.",
            ],
          ]}
        />

        <p>
          Click anywhere on the card to expand it. The section that matters is{" "}
          <UI>Provenance</UI>: a list of the exact policy rules this procedure
          depends on, each with the version it was built against and a
          one-sentence justification. Every dot should be green.
        </p>

        <Callout kind="good" title="This list is the whole idea">
          Cascade did not just cache a sequence of actions. It recorded the
          assumptions those actions rest on. That is what lets it know, later,
          that the procedure has stopped being valid.
        </Callout>
      </Section>

      <Section title="Step 3: reuse it">
        <Where>
          Back to <UI>Incidents</UI>
        </Where>

        <Steps>
          <Step title="Run a similar incident">
            <p>Type:</p>
            <p>
              <C>Remediate INC-1002</C>
            </p>
            <p>
              This is a different service, but the same class of problem: a bad
              deploy on a tier 2 service inside the rollback window.
            </p>
          </Step>

          <Step title="Look at the badge again">
            <p>
              It now reads <UI>Runbook · [name] v1</UI> with a lightning icon
              instead of <UI>Exploring</UI>. Cascade recognised the incident,
              found the saved procedure, confirmed its policy dependencies are
              still current, and is executing it directly.
            </p>
          </Step>

          <Step title="Go back to Runbooks">
            <p>
              The card now reads <UI>2 uses · 2 ✓</UI> and the confidence bar
              has grown. Two more successful reuses and the pill turns green.
            </p>
          </Step>
        </Steps>

        <Callout kind="warn" title="Do not read anything into the timing yet">
          Without a model provider configured, exploring pays no model latency,
          so guided execution can measure slower than exploring. The status bar
          shows an amber dot next to <UI>local</UI> when you are in that state,
          and the metric strip says so explicitly. See{" "}
          <a href="/docs/intelligence">Measuring value</a>.
        </Callout>
      </Section>

      <Section title="Step 4: change the rules and break it">
        <Where>
          <UI>Policy</UI>, the third icon in the left rail
        </Where>

        <p>
          This is the part that separates Cascade from a cache. You are going to
          change a rule the runbook depends on and watch it get pulled out of
          service automatically.
        </p>

        <Steps>
          <Step title="Find the rollback window rule">
            <p>
              Locate the row headed <C>incident.rollback_window</C>. It reads:
              rollback is allowed only if the deploy happened within the last{" "}
              <C>hours</C> hours.
            </p>
          </Step>

          <Step title="Change the value">
            <p>
              Click into the <UI>hours</UI> input, clear it, and type{" "}
              <C>4</C>. Nothing is committed yet.
            </p>
          </Step>

          <Step title="Read the preview that appears">
            <p>Two blocks fade in under the input:</p>
            <ul>
              <li>
                <strong>Impact.</strong> How many runbooks depend on this rule,
                named individually. Your new runbook is in that list.
              </li>
              <li>
                <strong>Counterfactual.</strong> What would have happened
                differently across historical incidents, with incident IDs
                prefixed <C>+</C> for newly allowed and <C>−</C> for newly
                blocked. Hover any chip to see the reason.
              </li>
            </ul>
            <p>
              Both are read-only. Nothing has been written to the database.
            </p>
          </Step>

          <Step title="Commit">
            <p>
              Click <UI>Review changes</UI>. A dialog lists exactly which
              runbooks will be quarantined and which running tasks will be
              interrupted. Click <UI>Commit change</UI>.
            </p>
          </Step>

          <Step title="Go back to Runbooks">
            <p>
              The card is now amber and the pill reads <UI>suspect</UI>. Expand
              it: in the <UI>Provenance</UI> list, the dot next to{" "}
              <C>incident.rollback_window</C> has turned red, and the version
              beside it is the one the runbook was built against, not the
              current one.
            </p>
          </Step>
        </Steps>

        <Callout kind="good" title="This happened in a single transaction">
          The rule version bump, the quarantine of every dependent runbook and
          the interrupt signal to anything running are one atomic write. There
          is no window in which a runbook is stale but still considered usable.
        </Callout>
      </Section>

      <Section title="Step 5: watch it refuse">
        <Where>
          Back to <UI>Incidents</UI>
        </Where>

        <Steps>
          <Step title="Run an incident that the runbook would have matched">
            <p>Type:</p>
            <p>
              <C>Remediate INC-1009</C>
            </p>
          </Step>

          <Step title="Watch the badge">
            <p>
              It reads <UI>Exploring</UI>, not <UI>Runbook</UI>. The saved
              procedure was found by similarity and then rejected, because one
              of its policy dependencies is out of date. Cascade planned from
              scratch instead.
            </p>
          </Step>

          <Step title="Read the outcome">
            <p>
              Under <UI>Recent Tasks</UI>, the chip reads <UI>escalated</UI>,
              not <UI>remediated</UI>. That deploy was five hours ago, and the
              window you just set is four hours. Cascade correctly declined to
              act and handed it to a human.
            </p>
          </Step>
        </Steps>

        <Callout kind="good" title="Two different refusals, both correct">
          It refused to <em>reuse</em> because the memory was stale. Then, on
          the fresh plan, it refused to <em>act</em> because the new policy says
          no. A system that only did the second would have run a stale procedure
          and hoped the policy check caught it.
        </Callout>
      </Section>

      <Section title="Step 6: put it back into service">
        <Where>
          <UI>Runbooks</UI>, expand the suspect card
        </Where>

        <p>
          Click <UI>Re-learn</UI>. Cascade queues a fresh exploration under the
          current rules and compiles the result as v2, with the old version
          marked <UI>invalidated</UI> and a link recording that v2 supersedes
          it. You keep the history rather than overwriting it.
        </p>
      </Section>

      <Section title="Where to go next">
        <Table
          head={["If you want to", "Read"]}
          widths={["330px", "auto"]}
          rows={[
            [
              "Know what every panel and badge means",
              <a key="a" href="/docs/interface">
                The interface
              </a>,
            ],
            [
              "Understand the twelve demo incidents and what each one proves",
              <a key="b" href="/docs/incidents">
                Running incidents
              </a>,
            ],
            [
              "See what happens when a runbook is not trusted enough to act alone",
              <a key="c" href="/docs/approvals">
                Approving actions
              </a>,
            ],
            [
              "Ask the system questions in plain English",
              <a key="d" href="/docs/copilot">
                Asking questions
              </a>,
            ],
          ]}
        />
      </Section>
    </>
  );
}
