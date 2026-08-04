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
  Kbd,
  Where,
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Managing runbooks",
  description:
    "Reading a runbook card, understanding status and confidence, checking provenance, and re-learning a quarantined procedure.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Using Cascade"
        title="Managing runbooks"
        lede="A runbook is a procedure Cascade wrote for itself after a successful run. This view is where you inspect them, trust them, and put them back into service."
      />

      <Where>
        <UI>Runbooks</UI>, the second icon in the activity bar
      </Where>

      <Section title="Where runbooks come from">
        <p>
          You never write one. After any run that ends <UI>remediated</UI>,
          Cascade turns the episode into a reusable procedure in the background.
          The card appears in this view a second or two later.
        </p>
        <p>
          The header shows a total count. If it stays at zero after a successful
          run, the background worker is not draining. See{" "}
          <a href="/docs/troubleshooting">Troubleshooting</a>.
        </p>
      </Section>

      <Section title="Reading a card">
        <Table
          head={["Element", "Where", "Means"]}
          widths={["190px", "160px", "auto"]}
          rows={[
            [
              "Name",
              "Top left",
              "A short description of the problem shape, derived from the incident it was learned on.",
            ],
            [
              <UI key="v">v1</UI>,
              "Beside the name",
              "Version. Increments each time the procedure is re-learned.",
            ],
            [
              <UI key="s">4 uses · 3 ✓ · 1 ✗</UI>,
              "Middle",
              "How many times it has been reused, and how those runs ended.",
            ],
            [
              "Status pill",
              "Top right",
              "One of five states. Hover it for a one-line explanation.",
            ],
            [
              "Thin bar",
              "Under the card",
              "Confidence, from 0 to 1. It is coloured to match the status.",
            ],
          ]}
        />
        <p>Click anywhere on the card header to expand it.</p>
      </Section>

      <Section title="The five statuses">
        <Table
          head={["Status", "Reusable?", "Means", "What to do"]}
          widths={["130px", "100px", "auto", "auto"]}
          rows={[
            [
              <UI key="a">candidate</UI>,
              "Yes",
              "Learned but unproven. Needs three successes to be promoted.",
              "Nothing. Run more incidents of this shape.",
            ],
            [
              <UI key="b">active</UI>,
              "Yes",
              "Proven against current policy.",
              "Nothing.",
            ],
            [
              <UI key="c">suspect</UI>,
              "No",
              "Quarantined. A rule it depends on changed and it has not been re-checked.",
              <span key="c2">
                Expand it and click <UI>Re-learn</UI>.
              </span>,
            ],
            [
              <UI key="d">invalidated</UI>,
              "No",
              "Superseded by a newer version learned under the current rules.",
              "Nothing. Kept for history and lineage.",
            ],
            [
              <UI key="e">rejected</UI>,
              "No",
              "Retired. Confidence fell below the 0.20 floor after repeated failures.",
              <span key="e2">
                Re-learn if the underlying problem has changed, otherwise leave
                it.
              </span>,
            ],
          ]}
        />
      </Section>

      <Section title="Confidence">
        <p>
          Confidence is earned, not asserted. A freshly compiled runbook starts
          at 0.30, which is deliberately low: it worked once, on one incident.
        </p>

        <Table
          head={["Event", "Effect"]}
          widths={["330px", "auto"]}
          rows={[
            ["Compiled from a successful run", "Starts at 0.30"],
            ["Reused successfully", "Rises toward 1.0"],
            ["Reused and the run failed", "Falls"],
            ["Falls below 0.20", "Status becomes rejected and it stops being offered"],
            [
              "Three successes as a candidate",
              "Status becomes active",
            ],
          ]}
        />

        <Callout kind="note" title="Confidence and staleness are different questions">
          Confidence answers <em>has this worked before</em>. Freshness answers{" "}
          <em>are the rules it assumed still the rules</em>. A runbook with
          confidence 0.9 is quarantined the instant one of its dependencies
          moves, and no amount of past success overrides that.
        </Callout>
      </Section>

      <Section title="The expanded card">
        <SubSection title="Steps">
          <p>
            The exact tool sequence, numbered. This is what will run if the
            runbook is reused. There is no hidden improvisation on the guided
            path.
          </p>
        </SubSection>

        <SubSection title="Preconditions">
          <p>
            Conditions that must hold for the procedure to apply, for example
            that the incident is a bad deploy and the service is above tier 1.
            If a precondition fails at reuse time, Cascade falls back to
            exploring and the miss is counted in the hit rate.
          </p>
        </SubSection>

        <SubSection title="Provenance">
          <p>
            The most important section. One row per policy rule the run actually
            consulted.
          </p>
          <Table
            head={["Column", "Means"]}
            widths={["190px", "auto"]}
            rows={[
              [
                "Dot",
                "Green if the pinned version is still current. Red if the rule has moved since.",
              ],
              ["Rule key", <>For example <C key="a">incident.rollback_window</C></>],
              [
                "Version",
                "The version this runbook was built against. Compare it to the version shown in the Policy view.",
              ],
              [
                "Justification",
                "One sentence recording why that rule mattered to this procedure.",
              ],
            ]}
          />
          <Callout kind="good" title="One red dot quarantines the whole card">
            Freshness is not scored or averaged. If any dependency is out of
            date the runbook is not eligible, full stop. That is checked at the
            moment of reuse by joining against live policy, not read from a flag
            somebody remembered to set.
          </Callout>
        </SubSection>

        <SubSection title="Actions">
          <Defs
            items={[
              {
                term: "Re-learn",
                def: (
                  <>
                    Shown on <UI>suspect</UI> and <UI>invalidated</UI> cards.
                    Queues a fresh exploration under the current rules and
                    compiles the result as the next version.
                  </>
                ),
              },
              {
                term: "View episodes",
                def: "Shows the individual runs that used this runbook, so you can see what actually happened rather than just a success count.",
              },
            ]}
          />
        </SubSection>
      </Section>

      <Section title="Re-learning a quarantined runbook">
        <Steps>
          <Step title="Find the amber card">
            <p>
              Suspect runbooks sort to the top. The status pill reads{" "}
              <UI>suspect</UI>.
            </p>
          </Step>
          <Step title="Expand it and confirm which dependency broke">
            <p>
              In <UI>Provenance</UI>, exactly one dot will be red. Note the rule
              key. That tells you what changed and therefore what the new
              version will have to account for.
            </p>
          </Step>
          <Step title="Click Re-learn">
            <p>
              The button reads <UI>Queueing…</UI> briefly. A background
              exploration runs against a representative incident under the
              current policy.
            </p>
          </Step>
          <Step title="Watch the version change">
            <p>
              A new card appears at v2 with green provenance dots. The old card
              becomes <UI>invalidated</UI> and records that v2 supersedes it.
            </p>
          </Step>
        </Steps>

        <Mermaid
          caption="Nothing is overwritten. The old version stays readable and the lineage is explicit."
          chart={`
flowchart LR
    A["v1<br/>active"] -- "rule changes" --> B["v1<br/>suspect"]
    B -- "Re-learn" --> C["v2 compiled<br/>under new rules"]
    C --> D["v1 → invalidated"]
    C --> E["v2 → candidate<br/>supersedes v1"]
`}
        />

        <Callout kind="warn" title="Re-learning can produce a different procedure">
          That is the point. If the new rules genuinely forbid the old action,
          the fresh exploration will escalate, and no v2 gets compiled. An empty
          result here is information, not a failure.
        </Callout>
      </Section>

      <Section title="Merging near-duplicate runbooks">
        <p>
          Run enough incidents and you will accumulate several runbooks with the
          same tool sequence and slightly different parameters. Press{" "}
          <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> and run{" "}
          <UI>Generalize similar runbooks</UI>.
        </p>

        <p>The merge is deliberately conservative:</p>
        <ul>
          <li>Members must share an identical tool sequence, not a similar one.</li>
          <li>
            The merged provenance is the union of every member dependency,
            pinned at the current version.
          </li>
          <li>
            The merged confidence is the <strong>minimum</strong> of its
            members, never the average. A merge cannot launder a weak runbook.
          </li>
          <li>Members are archived with lineage, not deleted.</li>
        </ul>

        <p>
          If nothing is similar enough, the toast says so and nothing changes.
          That is the common case early on.
        </p>
      </Section>
    </>
  );
}
