import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  SubSection,
  Callout,
  Table,
  Defs,
  C,
  UI,
  Kbd,
  Where,
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Measuring value",
  description:
    "The savings ledger, the dependency graph, negative memory and time travel, and how to read each one honestly.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Using Cascade"
        title="Measuring value"
        lede="Four read-only surfaces that answer the same question from different angles: what has this system actually learned, and what has that been worth?"
      />

      <Where>
        <UI>Intelligence</UI>, the fifth icon in the activity bar. Four tabs
        across the top of the panel.
      </Where>

      <Section title="savings">
        <p>
          A ledger of what reuse has avoided. Every figure is derived from runs
          that actually happened, not projected from a rate card.
        </p>

        <Table
          head={["Stat", "Means"]}
          widths={["220px", "auto"]}
          rows={[
            [
              "Tokens avoided",
              "Model tokens the guided path did not spend, measured against the average cost of exploring the same problem.",
            ],
            ["Cost saved", "Those tokens priced at the serving provider's rate."],
            [
              "Engineer hours",
              "Wall-clock time not spent by a human, using the time an escalated incident takes to reach a human as the baseline.",
            ],
            [
              "Incidents automated",
              "Runs that ended remediated without a human touching them.",
            ],
          ]}
        />

        <p>
          Below the grid, a headline sentence gives the speedup, and under that
          a line naming the basis for the calculation. Read the basis line. It
          tells you what the numbers are actually comparing.
        </p>

        <Callout kind="warn" title="The speedup can read as slower, and that is honest">
          Without a model provider, exploring pays no model latency, while the
          guided path still runs its precondition and parameter checks. In that
          state the panel says <UI>Guided execution is currently 2.5× slower</UI>{" "}
          and explains why, rather than rendering a meaningless{" "}
          <UI>0.4× faster</UI>. Configure a provider before quoting any
          multiplier. See <a href="/docs/configuration">Settings</a>.
        </Callout>

        <p>
          If the panel reads that savings are not available yet, you have not
          run both a cold and a guided execution. Run INC-1001 then INC-1002.
        </p>
      </Section>

      <Section title="graph">
        <p>
          The dependency graph, laid out in three columns: policy rules on the
          left, the runbooks that cite them in the middle, the work that used
          those runbooks on the right.
        </p>

        <Table
          head={["Element", "Means"]}
          widths={["220px", "auto"]}
          rows={[
            ["Left column dot", "A policy rule."],
            ["Middle column dot", "A runbook."],
            ["Right column dot", "A task."],
            [
              "Solid grey line",
              "A live dependency. The runbook was built against the version of that rule that is still current.",
            ],
            [
              "Red dashed line",
              "A stale dependency. The rule moved and the runbook has not been re-learned.",
            ],
            [
              "Dimmed node",
              "A runbook that is suspect or invalidated.",
            ],
          ]}
        />

        <Callout kind="good" title="This is the picture of the whole product">
          Change one rule in the left column and watch a fan of red dashed lines
          appear across the middle. That is blast radius, drawn from real
          provenance rather than sketched. If the panel says there is no graph
          yet, run an incident.
        </Callout>
      </Section>

      <Section title="memory">
        <p>
          Negative memory: things Cascade has learned <em>not</em> to try. A
          runbook records a procedure that worked. An anti-playbook records an
          approach that failed, so the same dead end is not rediscovered.
        </p>

        <Table
          head={["Field", "Means"]}
          widths={["220px", "auto"]}
          rows={[
            ["Incident kind", "The class of problem this applies to."],
            [
              "Attempted action",
              "What was tried. Absent when the failure was not tied to one specific action.",
            ],
            [
              <UI key="a">seen 3×</UI>,
              "How many times this failure has recurred. Repeats strengthen the record rather than duplicating it.",
            ],
            ["Reason", "Why it failed, in one line."],
          ]}
        />

        <p>
          An empty tab is the normal state early on. It fills up when runs fail,
          which is a thing you have to make happen deliberately in a clean demo
          world.
        </p>
      </Section>

      <Section title="time travel">
        <p>
          Reads the database as it was at a point in the past, using
          CockroachDB&apos;s multi-version storage directly. Nothing is reconstructed
          from a log and nothing extra is stored to make this work.
        </p>

        <Defs
          items={[
            {
              term: "Rewind slider",
              def: (
                <>
                  Drag to choose how far back, from 1 to 120 minutes. The value
                  is shown to the right as <UI>−15m</UI>. The view reloads as
                  you move it.
                </>
              ),
            },
            {
              term: "Runbooks column",
              def: "Every runbook that existed at that moment, with the status it had then.",
            },
            {
              term: "Policy column",
              def: "Every rule and the version that was current then.",
            },
          ]}
        />

        <Mermaid
          caption="The same query, addressed at two different points in time."
          chart={`
flowchart LR
    N["Now<br/>rollback_window v2 · 4h<br/>runbook: suspect"] -.-> Q["Rewind 20 minutes"]
    Q --> P["20 minutes ago<br/>rollback_window v1 · 24h<br/>runbook: active"]
`}
        />

        <SubSection title="Using it to prove a claim">
          <p>
            Change a policy rule, then rewind past the change. The policy column
            shows the old version and the runbook column shows the runbook still
            active. That is the strongest available evidence that the quarantine
            was caused by your change and not by something else.
          </p>
        </SubSection>

        <Callout kind="warn" title="History is not kept forever">
          Garbage collection eventually reclaims old versions. Rewinding beyond
          the retention window returns a message saying the history is no longer
          available rather than silently showing the current state.
        </Callout>
      </Section>

      <Section title="Two checks worth running">
        <p>
          Both live in the command palette. Press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd>.
        </p>

        <Defs
          items={[
            {
              term: "Verify vector index",
              def: (
                <>
                  Runs a live query plan and reports whether the vector index{" "}
                  <C>pb_embed_idx</C> is actually being used. The toast is
                  either a confirmation or the error. Retrieval that falls back
                  to a full scan still returns correct answers, which is exactly
                  why this needs checking rather than assuming.
                </>
              ),
            },
            {
              term: "Check which LLM provider is serving",
              def: (
                <>
                  Names the chat provider and the embedding provider separately.
                  They fall back independently, so it is entirely possible for
                  chat to be live while embeddings are local. A green dot alone
                  would blur that.
                </>
              ),
            },
          ]}
        />
      </Section>

      <Section title="What the metric strip adds">
        <p>
          Two numbers live at the top of every view rather than in this panel,
          because you want them while you work.
        </p>
        <Defs
          items={[
            {
              term: "Cold and Guided",
              def: "Average wall-clock time on each path, with a delta chip between them. Amber means guided measured slower, and hovering the chip explains why.",
            },
            {
              term: "Hit Rate",
              def: "Share of eligible runs that reused a runbook. A run that authored a runbook is not counted as a miss against itself, and a refusal on staleness is counted honestly as a miss.",
            },
          ]}
        />
      </Section>
    </>
  );
}
