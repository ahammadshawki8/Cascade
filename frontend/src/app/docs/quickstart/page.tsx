import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  SubSection,
  Callout,
  Code,
  Steps,
  Step,
  Table,
  C,
  Mermaid,
  UI,
  Kbd,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Install and run",
  description:
    "Get Cascade running on your machine in about ten minutes. No cloud account, no API keys.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Getting started"
        title="Install and run"
        lede="Ten minutes, one Docker container and two terminals. No cloud account and no API keys are required to see the whole product work."
      />

      <Section title="What you need">
        <Table
          head={["Requirement", "Why", "Check it"]}
          widths={["170px", "auto", "230px"]}
          rows={[
            [
              "Docker",
              "Runs CockroachDB locally in a single container",
              <C key="d">docker --version</C>,
            ],
            [
              "Python 3.11 or newer",
              "Runs the API and the background worker",
              <C key="p">python --version</C>,
            ],
            [
              "Node.js 20 or newer",
              "Runs the web interface",
              <C key="n">node --version</C>,
            ],
          ]}
        />

        <Callout kind="note" title="You do not need an API key">
          Cascade ships with a deterministic local planner and a local embedder.
          Everything you can click works without a model provider. Adding one
          later is a single environment variable. See{" "}
          <a href="/docs/configuration">Settings</a>.
        </Callout>
      </Section>

      <Section title="What you are starting">
        <Mermaid
          caption="Three processes. The browser only ever talks to the web app, which proxies privileged calls for you."
          chart={`
flowchart LR
    U["You<br/>localhost:3000"] --> W["Web interface<br/>Next.js"]
    W --> A["API<br/>localhost:8000"]
    A --> D["CockroachDB<br/>localhost:26257"]
    A --> K["Worker<br/>in process"]
    K --> D
`}
        />
      </Section>

      <Section title="Run it">
        <Steps>
          <Step title="Start CockroachDB">
            <p>
              One container, insecure single node. It is the only piece of
              infrastructure Cascade needs.
            </p>
            <Code lang="bash">{`docker run -d --name cascade-crdb \\
  -p 26257:26257 -p 8080:8080 \\
  cockroachdb/cockroach:latest start-single-node --insecure`}</Code>
            <p>
              If you have run this before, the container already exists. Start
              it again instead:
            </p>
            <Code lang="bash">{`docker start cascade-crdb`}</Code>
          </Step>

          <Step title="Create the database and apply the four migrations">
            <p>
              Order matters. <C>001</C> creates the schema and the vector index,{" "}
              <C>002</C> seeds policy and twelve demo incidents, <C>003</C> adds
              negative memory, <C>004</C> adds retention and merge lineage.
            </p>
            <Code lang="bash">{`cd cascade/backend

for f in 001_schema 002_seed 003_extensions 004_production; do
  docker cp migrations/$f*.sql cascade-crdb:/tmp/$f.sql
done

docker exec cascade-crdb ./cockroach sql --insecure \\
  -e "DROP DATABASE IF EXISTS cascade CASCADE; CREATE DATABASE cascade;"

for f in 001 002 003 004; do
  docker exec cascade-crdb ./cockroach sql --insecure \\
    --database=cascade --file=//tmp/$f.sql
done`}</Code>
          </Step>

          <Step title="Start the API">
            <p>
              In its own terminal. This also runs the background worker in
              process, so there is nothing else to start.
            </p>
            <Code lang="bash">{`cd cascade/backend
pip install -e .
python run_local.py`}</Code>
            <p>
              Wait for <C>Uvicorn running on http://0.0.0.0:8000</C>.
            </p>
          </Step>

          <Step title="Start the web interface">
            <p>In a second terminal.</p>
            <Code lang="bash">{`cd cascade/frontend
npm install
npm run dev`}</Code>
            <p>
              Open <C>http://localhost:3000</C>.
            </p>
          </Step>
        </Steps>

        <Callout kind="warn" title="On Windows, use run_local.py rather than uvicorn">
          The database driver cannot run on the event loop Windows picks by
          default, and as of Python 3.14 setting an event loop policy no longer
          changes the loop uvicorn builds for itself. <C>run_local.py</C>{" "}
          constructs the right loop and then starts uvicorn inside it. On Linux
          and macOS either way works.
        </Callout>
      </Section>

      <Section title="Check that it worked">
        <SubSection title="In the browser">
          <p>
            Look at the status bar along the bottom of the window. You want to
            see:
          </p>
          <Table
            head={["Segment", "Healthy value", "If it is wrong"]}
            widths={["150px", "220px", "auto"]}
            rows={[
              [
                "Provider name",
                <span key="l">
                  <UI>local</UI> with an amber dot
                </span>,
                "Amber is correct with no model configured. The metric strip going blank is the signal that the API itself is unreachable.",
              ],
              [
                "Connection",
                <UI key="c">live</UI>,
                <span key="d">
                  <UI>disconnected</UI> means the event stream did not open.
                  Confirm the API terminal is still running.
                </span>,
              ],
              [
                "Database",
                <UI key="db">CockroachDB cascade</UI>,
                "Always shown. Run an incident to confirm the connection really works.",
              ],
            ]}
          />
        </SubSection>

        <SubSection title="From the command line">
          <p>
            The integration suite talks to the engine directly and refuses to
            run against a stubbed backend, so a pass cannot be a canned one.
          </p>
          <Code lang="bash">{`cd cascade/backend
python verify_integration.py`}</Code>
          <p>
            Expect <C>81 passed, 0 failed, 0 skipped</C>. It takes about a
            minute and leaves the demo world clean.
          </p>
        </SubSection>
      </Section>

      <Section title="Running without a database">
        <p>
          Stub mode answers every endpoint with fixed sample data and never
          opens a connection. It is for looking at the interface on a machine
          with no Docker, and for smoke-testing a deployment before the database
          is wired up.
        </p>
        <Code lang="bash">{`cd cascade/backend
CASCADE_STUB_MODE=true python run_local.py`}</Code>
        <Callout kind="warn" title="Nothing you do in stub mode is real">
          Runs do not execute, policy changes are not committed, and no runbook
          is learned. Use it to check that a page renders, never to check that a
          behaviour is correct.
        </Callout>
      </Section>

      <Section title="Connecting a real model">
        <p>
          Optional, and worth doing before you judge the latency numbers. Set
          any one of these in <C>cascade/backend/.env</C> and restart the API.
        </p>
        <Code lang="bash" caption="backend/.env">{`# Any one of these is enough. The first that answers wins.
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
HF_API_KEY=hf_...

# Or AWS Bedrock, which needs no key here, only credentials on the machine
AWS_REGION=us-east-1`}</Code>
        <p>
          Then confirm which provider actually answered. Press <Kbd>Ctrl</Kbd>{" "}
          <Kbd>K</Kbd> and run <UI>Check which LLM provider is serving</UI>. The
          toast names the chat provider and the embedding provider separately,
          because they fall back independently.
        </p>
        <Callout kind="note" title="Why this matters for the numbers">
          With no provider, planning is instant, so the cold path pays no model
          latency and the guided path can look slower than exploring. The
          interface says so rather than hiding it. Timing comparisons only mean
          something once a provider is live.
        </Callout>
      </Section>

      <Section title="Starting over">
        <p>
          Press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> and run <UI>Reset demo world</UI>.
          That restores the clean v1 policy and clears every runbook, task and
          approval, while preserving the audit log so you can still show what
          happened. It is the fastest way to re-run a demo.
        </p>
      </Section>
    </>
  );
}
