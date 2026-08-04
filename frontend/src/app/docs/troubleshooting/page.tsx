import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  SubSection,
  Callout,
  Code,
  Table,
  C,
  UI,
  Kbd,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Troubleshooting",
  description:
    "Symptoms you can see on screen, what causes each one, and the fix.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Reference"
        title="Troubleshooting"
        lede="Organised by what you can see. Find the symptom, not the subsystem."
      />

      <Section title="Start here">
        <p>
          Three checks settle most problems in under a minute. All three are in
          the command palette: press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd>.
        </p>
        <Table
          head={["Run", "Tells you"]}
          widths={["330px", "auto"]}
          rows={[
            [
              <UI key="a">Check which LLM provider is serving</UI>,
              "Whether the API is reachable at all, and which model provider answered.",
            ],
            [
              <UI key="b">Verify vector index</UI>,
              "Whether the database is reachable and retrieval is using the index.",
            ],
            [
              <UI key="c">Reset demo world</UI>,
              "Clears accumulated state. Fixes anything caused by a half-finished experiment.",
            ],
          ]}
        />
      </Section>

      <Section title="Nothing loads at all">
        <SubSection title="The page is blank or the metric strip is empty">
          <p>The API is not reachable. In order:</p>
          <ol>
            <li>
              Check the API terminal is still running and shows{" "}
              <C>Uvicorn running on http://0.0.0.0:8000</C>.
            </li>
            <li>
              <Code lang="bash">{`curl localhost:8000/health`}</Code>
              Expect <C>{'{"status":"ok"}'}</C>.
            </li>
            <li>
              Confirm <C>NEXT_PUBLIC_API_URL</C> in{" "}
              <C>frontend/.env.local</C> points at the right port. Changing it
              requires restarting the dev server, because it is inlined at build
              time.
            </li>
          </ol>
        </SubSection>

        <SubSection title="The API will not start">
          <Table
            head={["Message contains", "Cause", "Fix"]}
            widths={["270px", "auto", "auto"]}
            rows={[
              [
                <C key="a">ProactorEventLoop</C>,
                "You are on Windows and started uvicorn directly.",
                <span key="a2">
                  Use <C>python run_local.py</C>.
                </span>,
              ],
              [
                <C key="b">connection refused</C>,
                "CockroachDB is not running.",
                <span key="b2">
                  <C>docker start cascade-crdb</C>
                </span>,
              ],
              [
                <C key="c">database &quot;cascade&quot; does not exist</C>,
                "Migrations were never applied.",
                <span key="c2">
                  Re-run the migration block in{" "}
                  <a href="/docs/quickstart">Install and run</a>.
                </span>,
              ],
              [
                <C key="d">relation &quot;playbooks&quot; does not exist</C>,
                "Only some migrations applied.",
                "Drop the database and apply all four in order.",
              ],
            ]}
          />
        </SubSection>
      </Section>

      <Section title="The status bar looks wrong">
        <SubSection title="It reads disconnected">
          <p>
            The live event stream did not open. Runs still work, but nothing will
            update on screen until you switch views.
          </p>
          <ul>
            <li>Confirm the API is up.</li>
            <li>
              If you are behind a proxy or CDN, response buffering is the usual
              cause. The stream must not be compressed or cached. See{" "}
              <a href="/docs/deployment">Deploying</a>.
            </li>
            <li>
              A stream that opens and closes repeatedly usually means the API is
              restarting on file changes.
            </li>
          </ul>
        </SubSection>

        <SubSection title="The provider dot is amber and reads local">
          <p>
            This is correct with no model provider configured, not a fault.
            Everything works on the deterministic local planner. What stops being
            meaningful is the cold versus guided timing comparison, and the
            metric strip says so.
          </p>
          <p>
            To change it, set a key and restart the API. See{" "}
            <a href="/docs/configuration">Settings</a>.
          </p>
        </SubSection>

        <SubSection title="Chat is live but embeddings are still local">
          <p>
            Expected and worth knowing about. The two chains fall back
            independently, so a Groq key gives you a real planner while
            embeddings stay local until you add a HuggingFace key or Bedrock
            credentials. The smoke check reports them separately for exactly
            this reason.
          </p>
        </SubSection>
      </Section>

      <Section title="Runs behave unexpectedly">
        <SubSection title="No runbook appears after a successful run">
          <p>
            Compilation happens in a background job. If nothing shows up after
            ten seconds, the worker is not draining the queue.
          </p>
          <Code lang="bash" caption="backend/.env">{`RUN_WORKER_IN_PROCESS=true`}</Code>
          <p>
            Restart the API. Locally there is no SQS or Lambda, so without this
            the compile event is queued and never picked up. In a deployment
            this must stay <C>false</C>, and the thing to check is the Lambda
            logs instead.
          </p>
        </SubSection>

        <SubSection title="It keeps exploring instead of reusing">
          <p>Four possible causes, in the order worth checking.</p>
          <Table
            head={["Check", "How", "Fix"]}
            widths={["220px", "auto", "auto"]}
            rows={[
              [
                "Is there a runbook at all?",
                <span key="a">
                  <UI>Runbooks</UI> shows a card
                </span>,
                "Run a cold incident first.",
              ],
              [
                "Is it quarantined?",
                "The pill reads suspect and a provenance dot is red",
                <span key="b">
                  Click <UI>Re-learn</UI>.
                </span>,
              ],
              [
                "Is the incident actually similar?",
                "A tier 1 error spike will not match a tier 3 deploy rollback",
                "Use an incident of the same shape. See the table in Running incidents.",
              ],
              [
                "Is the match threshold too tight?",
                <span key="c">
                  Nothing matches even for near-identical incidents
                </span>,
                <span key="c2">
                  Raise <C>RETRIEVAL_L2_THRESHOLD</C> above <C>0.85</C>.
                </span>,
              ],
            ]}
          />
        </SubSection>

        <SubSection title="It reuses a runbook for the wrong problem">
          <p>
            Lower <C>RETRIEVAL_L2_THRESHOLD</C>. This is much more likely on the
            local embedder, whose geometry is a hashed approximation. Configuring
            real embeddings is the better fix.
          </p>
        </SubSection>

        <SubSection title="Every run escalates">
          <p>
            Read the last step of the stream. It names the rule that refused. The
            most common cause is a policy value left over from an experiment, for
            example a rollback window of 4 hours or a tier floor of 1.
          </p>
          <p>
            Check <UI>Policy</UI>, or press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> and run{" "}
            <UI>Reset demo world</UI> to return to the seeded values.
          </p>
        </SubSection>

        <SubSection title="A task is stuck on Running">
          <p>
            Check the API terminal for a traceback. If the process died
            mid-execution the row can be left in flight. Reset the world to
            clear it. Budgets should normally prevent this: a run exceeding 15
            steps, 25 thousand tokens or 60 seconds fails rather than hanging.
          </p>
        </SubSection>

        <SubSection title="Everything works but nothing is real">
          <p>
            Check for <C>CASCADE_STUB_MODE=true</C>. In stub mode every endpoint
            returns fixed sample data, so the interface looks healthy while
            nothing is executed or written.
          </p>
        </SubSection>
      </Section>

      <Section title="Policy changes do not do what you expect">
        <SubSection title="Committing changed nothing">
          <p>
            Confirm the version number beside the rule key went up. If it did
            not, the commit did not land, and the usual cause is a missing or
            insufficient admin token in the proxy configuration.
          </p>
        </SubSection>

        <SubSection title="Runbooks did not turn suspect">
          <p>
            Expand one and look at its provenance. If it does not cite the rule
            you changed, it does not depend on it and correctly stays fresh. Not
            every run consults every rule.
          </p>
        </SubSection>

        <SubSection title="A runbook went back to fresh on its own">
          <p>
            Working as intended. When a change is provably relaxing, for example
            widening a window from 4 hours to 24, triage re-pins the dependency
            forward and the runbook reports fresh through the ordinary check. It
            cannot go the other way: triage can only clear, never permit.
          </p>
        </SubSection>

        <SubSection title="Reverting a value did not restore the runbooks">
          <p>
            Reverting creates a third version rather than restoring the first, so
            the pinned version still does not match. Use <UI>Re-learn</UI> per
            runbook, or reset the world.
          </p>
        </SubSection>
      </Section>

      <Section title="Numbers look wrong">
        <SubSection title="Guided is slower than cold">
          <p>
            Expected without a model provider. Exploring pays no model latency,
            while guided still runs its precondition and parameter checks. The
            delta chip turns amber and the savings panel states the inverse
            honestly rather than printing a meaningless multiplier. Configure a
            provider before quoting any figure.
          </p>
        </SubSection>

        <SubSection title="Hit rate is 0 percent">
          <p>
            You have run cold tasks only. The run that authors a runbook is not
            counted as a miss against itself, so the rate stays undefined until
            there has been at least one reuse attempt.
          </p>
        </SubSection>

        <SubSection title="Savings says it is not available">
          <p>
            There is no baseline yet. It needs at least one cold and one guided
            run. It reports unavailability rather than showing zero, because zero
            would be a claim.
          </p>
        </SubSection>

        <SubSection title="Time travel says history is unavailable">
          <p>
            You rewound past the cluster&apos;s garbage-collection window, which is
            roughly 25 hours. Old versions have been reclaimed. Choose a shorter
            interval.
          </p>
        </SubSection>
      </Section>

      <Section title="Copilot problems">
        <Table
          head={["Symptom", "Cause", "Fix"]}
          widths={["250px", "auto", "auto"]}
          rows={[
            [
              "A refusal with a reason",
              "The question asked for a write, or tried to override the rules.",
              "Rephrase it as a read.",
            ],
            [
              <UI key="b">Could not reach the Copilot API.</UI>,
              "The backend is not responding.",
              "Check the API terminal.",
            ],
            [
              "An empty results table",
              "Valid query, no matching rows.",
              "Read the generated SQL. The filter is usually narrower than you meant.",
            ],
            [
              "It declines open-ended questions",
              "No model provider, so it is on the deterministic fallback which handles common shapes only.",
              "Configure a provider.",
            ],
          ]}
        />
      </Section>

      <Section title="Build and install problems">
        <Table
          head={["Symptom", "Fix"]}
          widths={["290px", "auto"]}
          rows={[
            [
              "Frontend build fails with no space left",
              <span key="a">
                Delete <C>frontend/.next</C> and run <C>npm cache clean --force</C>. A
                build needs a few gigabytes of headroom.
              </span>,
            ],
            [
              "Docker commands hang or error",
              "Docker Desktop has stopped. Start it, then run docker start cascade-crdb. Container data survives a restart.",
            ],
            [
              "Migrations fail on the vector index",
              <span key="b">
                CockroachDB uses <C>CREATE VECTOR INDEX</C>, not the pgvector{" "}
                <C>USING ivfflat</C> syntax, and it must run outside the
                transaction. Migration <C>001</C> already does this. Do not
                hand-edit it.
              </span>,
            ],
            [
              "verify_integration.py refuses to run",
              "It will not run in stub mode, by design, so a green result can never be a canned one. Set CASCADE_STUB_MODE=false.",
            ],
          ]}
        />
      </Section>

      <Section title="Still stuck">
        <p>Collect these three things before digging further:</p>
        <Code lang="bash">{`# 1. Is the API healthy and which provider is serving?
curl localhost:8000/api/admin/smoke -H "x-admin-token: dev-admin-token"

# 2. Is the database healthy and is retrieval using the index?
curl localhost:8000/api/admin/verify-index -H "x-admin-token: dev-admin-token"

# 3. Does the engine still pass end to end?
cd backend && python verify_integration.py`}</Code>
        <Callout kind="note" title="The last one is the decisive check">
          The integration suite talks to the engine directly rather than over
          HTTP, and refuses to run against a stub. If it passes, the problem is
          in configuration or in the interface, not in the engine.
        </Callout>
      </Section>
    </>
  );
}
