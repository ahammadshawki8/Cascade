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
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "The interface",
  description:
    "Every panel, badge, colour and control in Cascade, and what each one is telling you.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Getting started"
        title="The interface"
        lede="A reference for everything on screen. Use it when you see a colour or a badge you do not recognise."
      />

      <Section title="Layout">
        <Mermaid
          caption="Five fixed regions. Only the middle one changes when you switch views."
          chart={`
flowchart TB
    subgraph W[" "]
      direction TB
      M["Metric strip · cold, guided, hit rate, task counts"]
      T["Guided tour · three steps, dismissible"]
      V["Active view · Incidents, Runbooks, Policy, Copilot, Intelligence or Approvals"]
      S["Status bar · provider, connection, database, counts"]
      M --> T --> V --> S
    end
    A["Activity<br/>bar"] --- W
`}
        />
      </Section>

      <Section title="The activity bar">
        <p>
          The narrow icon rail down the left edge. Hover any icon to see its
          name and a one-line hint. The active view has a coloured accent on its
          left edge. A number badge means something in that view needs you.
        </p>

        <Table
          head={["Icon", "View", "What it is for"]}
          widths={["150px", "150px", "auto"]}
          rows={[
            [
              "Terminal",
              <UI key="a">Incidents</UI>,
              "Type an incident, run it, watch each step stream in.",
            ],
            [
              "Book",
              <UI key="b">Runbooks</UI>,
              "Every procedure Cascade has learned, its status and what policy it depends on.",
            ],
            [
              "Shield",
              <UI key="c">Policy</UI>,
              "The rules. Edit a value to preview its impact before committing.",
            ],
            [
              "Sparkles",
              <UI key="d">Copilot</UI>,
              "Ask questions in plain English. Answers come with the SQL that produced them.",
            ],
            [
              "Brain",
              <UI key="e">Intelligence</UI>,
              "Savings ledger, dependency graph, negative memory and time travel.",
            ],
            [
              "Shield with tick",
              <UI key="f">Approvals</UI>,
              "Actions parked waiting for a human, plus policy suggestions Cascade has found.",
            ],
          ]}
        />

        <p>Below the divider, three utilities:</p>

        <Defs
          items={[
            {
              term: "Commands",
              def: (
                <>
                  Opens the command palette. Same as <Kbd>Ctrl</Kbd>{" "}
                  <Kbd>K</Kbd>.
                </>
              ),
            },
            {
              term: "Documentation",
              def: "Opens this site.",
            },
            {
              term: "Reset demo",
              def: "Restores the clean v1 world. Clears runbooks, tasks and approvals, keeps the audit log.",
            },
          ]}
        />
      </Section>

      <Section title="The metric strip">
        <p>Always visible, directly under the header.</p>

        <Defs
          items={[
            {
              term: "Cold",
              def: "Average wall-clock time for runs where Cascade had to plan from scratch. Shown in milliseconds below one second, otherwise seconds.",
            },
            {
              term: "Δ chip",
              def: (
                <>
                  Percentage difference between guided and cold. Teal and
                  negative means guided is faster. Amber and positive means it
                  was slower, which is expected without a model provider. Hover
                  it for the reason.
                </>
              ),
            },
            {
              term: "Guided",
              def: "Average wall-clock time for runs that reused a saved runbook.",
            },
            {
              term: "Hit Rate",
              def: "Share of eligible runs that successfully reused a runbook. A dash means there is not enough history yet.",
            },
            {
              term: "Tasks",
              def: "Five coloured dots with counts: queued, running, interrupted, succeeded, failed.",
            },
            {
              term: "LLM",
              def: "Green when a model provider is serving, amber when Cascade has fallen back to the local planner.",
            },
          ]}
        />

        <Callout kind="warn" title="The degraded strip">
          When no provider is reachable, a strip appears below the metrics
          reading <UI>Degraded</UI>. Read it carefully: tasks still run, on the
          deterministic local planner. Nothing is queued or blocked. The only
          thing that stops being meaningful is the cold versus guided timing
          comparison.
        </Callout>
      </Section>

      <Section title="The status bar">
        <p>
          The thin strip along the bottom. Ambient state that should always be
          visible and never compete with your work.
        </p>

        <Table
          head={["Segment", "Reading it"]}
          widths={["230px", "auto"]}
          rows={[
            [
              "Provider name",
              <span key="a">
                Names the provider actually serving, for example{" "}
                <UI>bedrock</UI>, <UI>groq</UI> or <UI>local</UI>. Green dot
                means a real model, amber means the local fallback. Click it to
                jump to Intelligence.
              </span>,
            ],
            [
              <span key="b">
                <UI>live</UI> or <UI>disconnected</UI>
              </span>,
              "Whether the event stream is open. This is read from the connection itself, so a transient blip does not latch it red.",
            ],
            ["CockroachDB cascade", "The database and schema in use."],
            [
              "N awaiting approval",
              "Only shown when there are parked actions. Amber dot.",
            ],
            ["N running", "Only shown while tasks are in flight."],
            ["reuse N%", "The same hit rate as the metric strip, in short form."],
            [
              "N ok / N failed",
              "Completed task counts since the last reset.",
            ],
            [
              <Kbd key="c">Ctrl K</Kbd>,
              "Click to open the command palette.",
            ],
          ]}
        />
      </Section>

      <Section title="The command palette">
        <p>
          Press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> anywhere, or <Kbd>Cmd</Kbd>{" "}
          <Kbd>K</Kbd> on a Mac. Every action in the product is reachable from
          here, so you never have to remember which panel something lives in.
        </p>

        <Table
          head={["Key", "Does"]}
          widths={["150px", "auto"]}
          rows={[
            [<Kbd key="a">↑</Kbd>, "Move up the list"],
            [<Kbd key="b">↓</Kbd>, "Move down the list"],
            [<Kbd key="c">Enter</Kbd>, "Run the highlighted command"],
            [<Kbd key="d">Esc</Kbd>, "Close without running anything"],
          ]}
        />

        <SubSection title="Matching is by subsequence, not prefix">
          <p>
            Type the first letters of the words you want. Order matters,
            adjacency does not.
          </p>
          <Table
            head={["Type", "Finds"]}
            widths={["150px", "auto"]}
            rows={[
              [<C key="a">gint</C>, "Go to Intelligence"],
              [<C key="b">rinc</C>, "Run incident INC-1001"],
              [<C key="c">rst</C>, "Reset demo world"],
              [<C key="d">vvi</C>, "Verify vector index"],
            ]}
          />
        </SubSection>

        <SubSection title="The four groups">
          <Defs
            items={[
              {
                term: "Navigate",
                def: "One entry per view. The fastest way to move around.",
              },
              {
                term: "Run",
                def: "Six pre-loaded demo incidents, each labelled with what it exercises, for example bad deploy · tier 1 · policy blocks.",
              },
              {
                term: "Copilot",
                def: "Four ready-made questions. Running one switches to the Copilot view with the answer already loading.",
              },
              {
                term: "Actions",
                def: "Scan for insights, generalize runbooks, verify the vector index, check the provider, reset the world, toggle the tour, open these docs.",
              },
            ]}
          />
        </SubSection>
      </Section>

      <Section title="The guided tour">
        <p>
          The three-step strip under the metrics. Clicking a step performs it
          rather than just describing it, so it doubles as a demo remote
          control.
        </p>
        <Table
          head={["Step", "Clicking it"]}
          widths={["240px", "auto"]}
          rows={[
            ["Run an incident", "Fills the console with INC-1001 and runs it"],
            ["Reuse what it learned", "Runs INC-1002, which should go guided"],
            ["Change a policy", "Opens Policy with the rollback window ready to edit"],
          ]}
        />
        <p>
          Once all three are done the strip collapses to <UI>Tour complete</UI>{" "}
          with a reset link. To bring it back, press <Kbd>Ctrl</Kbd>{" "}
          <Kbd>K</Kbd> and run <UI>Show guided tour</UI>.
        </p>
      </Section>

      <Section title="Colours and status words">
        <p>
          Cascade uses the same four states everywhere. Learning them once
          covers runbook pills, provenance dots, graph nodes and time travel.
        </p>

        <Table
          head={["Appearance", "Word", "Means"]}
          widths={["120px", "150px", "auto"]}
          rows={[
            [
              "Green",
              <UI key="a">active</UI>,
              "Proven against the current policy. Safe to reuse.",
            ],
            [
              "Teal",
              <UI key="b">candidate</UI>,
              "Learned but unproven. Needs three successes to be promoted.",
            ],
            [
              "Amber",
              <UI key="c">suspect</UI>,
              "Quarantined. A rule it depends on changed and it has not been re-checked.",
            ],
            [
              "Red",
              <UI key="d">invalidated</UI>,
              "Superseded by a newer version learned under the current rules.",
            ],
            [
              "Red",
              <UI key="e">rejected</UI>,
              "Retired. Confidence fell below the 0.20 floor.",
            ],
          ]}
        />

        <Callout kind="note" title="Hover the pill">
          Every status pill carries a tooltip with the same one-line
          explanation, so you do not have to come back here.
        </Callout>
      </Section>

      <Section title="Scrolling and window size">
        <p>
          Scrollbars are transparent until you hover a scrollable region, and
          they reserve no width, so panels do not shift as content grows.
          Cascade is designed for a desktop window. Below about 900 pixels wide
          the layout stacks rather than breaking, but it is not the intended
          shape.
        </p>
      </Section>
    </>
  );
}
