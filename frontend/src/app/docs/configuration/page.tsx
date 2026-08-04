import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  Callout,
  Code,
  Defs,
  Table,
  C,
  UI,
  Kbd,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Settings",
  description:
    "Every setting, what changes on screen when you set it, and when you should bother.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Reference"
        title="Settings"
        lede="Settings live in backend/.env and frontend/.env.local. Names are case-insensitive. Restart the process after changing one."
      />

      <Section title="The five that actually matter">
        <p>
          Most of this page is reference you will never need. These five change
          what you see.
        </p>
        <Table
          head={["Set this", "To get"]}
          widths={["290px", "auto"]}
          rows={[
            [
              <C key="a">GROQ_API_KEY</C>,
              <span key="a2">
                A real planner. The status bar switches from <UI>local</UI> to{" "}
                <UI>groq</UI> and the latency numbers become meaningful.
              </span>,
            ],
            [
              <C key="b">HF_API_KEY</C>,
              "Real embeddings, so retrieval matches on meaning rather than on a hashed approximation of it.",
            ],
            [
              <C key="c">AUTONOMY_MIN_CONFIDENCE=0.6</C>,
              <span key="c2">
                The approvals gate. New runbooks park in <UI>Approvals</UI>{" "}
                until they have three supervised successes.
              </span>,
            ],
            [
              <C key="d">RUN_WORKER_IN_PROCESS=true</C>,
              "Runbooks that actually appear after a successful run when you are running locally. Required outside AWS.",
            ],
            [
              <C key="e">CASCADE_STUB_MODE=true</C>,
              "A working interface with no database at all. Nothing you do is real.",
            ],
          ]}
        />
      </Section>

      <Callout kind="danger" title="Read settings, never os.environ">
        <p>
          pydantic-settings loads <C>.env</C> into the <C>Settings</C> object
          and <strong>does not</strong> export it to the process environment.
          Code that calls <C>os.getenv(&quot;CASCADE_STUB_MODE&quot;)</C> will
          not see a value set in <C>.env</C>.
        </p>
        <p>
          This was a live bug: four routers read <C>os.getenv</C> while the
          lifespan read settings, so enabling stub mode via <C>.env</C> made the
          app skip pool creation while the routers still tried to query.
        </p>
      </Callout>

      <Section title="Core">
        <Defs
          items={[
            {
              term: "DATABASE_URL",
              def: (
                <>
                  CockroachDB connection string. Local:{" "}
                  <C>postgresql://root@localhost:26257/cascade?sslmode=disable</C>.
                  Production comes from Secrets Manager and uses{" "}
                  <C>sslmode=verify-full</C>.
                </>
              ),
            },
            {
              term: "CASCADE_STUB_MODE",
              def: (
                <>
                  Default <C>false</C>. When <C>true</C> the app returns canned
                  data and opens no database connection. Useful for looking at
                  the interface on a machine with no Docker. Nothing you do in
                  this mode is real.
                </>
              ),
            },
            {
              term: "AWS_REGION",
              def: (
                <>
                  Default <C>us-east-1</C>. Used for every AWS client.
                </>
              ),
            },
          ]}
        />
      </Section>

      <Section title="Model providers">
        <p>
          Bedrock is primary. The rest exist so the full loop runs on free-tier
          keys, or on none at all. Chat falls back{" "}
          <C>bedrock, groq, openrouter, local</C>. Embeddings fall back{" "}
          <C>bedrock, huggingface, local</C>. The two chains are independent.
        </p>
        <p>
          To see which one is actually serving, press <Kbd>Ctrl</Kbd>{" "}
          <Kbd>K</Kbd> and run <UI>Check which LLM provider is serving</UI>.
        </p>
        <Defs
          items={[
            {
              term: "BEDROCK_AGENT_MODEL_ID",
              def: (
                <>
                  Planner. Default <C>anthropic.claude-sonnet-5</C>.
                </>
              ),
            },
            {
              term: "BEDROCK_FAST_MODEL_ID",
              def: (
                <>
                  Precondition checks, parameter extraction, SQL synthesis,
                  triage. Default <C>anthropic.claude-haiku-4-5</C>.
                </>
              ),
            },
            {
              term: "BEDROCK_EMBED_MODEL_ID",
              def: (
                <>
                  Default <C>amazon.titan-embed-text-v2:0</C>. Called with{" "}
                  <C>normalize: true</C>, because unit vectors are what make L2
                  ranking equal cosine ranking.
                </>
              ),
            },
            {
              term: "GROQ_API_KEY",
              def: "Chat fallback. Free tier, supports tool calling.",
            },
            {
              term: "OPENROUTER_API_KEY",
              def: (
                <>
                  Second chat fallback. Uses <C>:free</C> models.
                </>
              ),
            },
            {
              term: "HF_API_KEY",
              def: "Embedding fallback via the HuggingFace inference API.",
            },
            {
              term: "HF_EMBED_MODEL",
              def: (
                <>
                  Default <C>BAAI/bge-large-en-v1.5</C>.{" "}
                  <strong>Must be 1024 dimensions</strong> to match{" "}
                  <C>VECTOR(1024)</C>. Another width is reshaped and loudly
                  logged rather than silently stored.
                </>
              ),
            },
            {
              term: "MOCK_BEDROCK",
              def: (
                <>
                  Set <C>true</C> to force the local path even with credentials
                  present.
                </>
              ),
            },
          ]}
        />
      </Section>

      <Section title="Roles and tokens">
        <Defs
          items={[
            {
              term: "ADMIN_TOKEN",
              def: "Change policy, reset the world, run scans, generalize runbooks.",
            },
            {
              term: "OPERATOR_TOKEN",
              def: "Run tasks, resolve approvals, queue re-learns.",
            },
            {
              term: "VIEWER_TOKEN",
              def: "Explicit read role. Without any token, callers are viewers anyway.",
            },
            {
              term: "INTERNAL_SSE_SECRET",
              def: (
                <>
                  Guards <C>/internal/sse</C> and <C>/internal/fanout</C>, the
                  worker to API bridge.
                </>
              ),
            },
          ]}
        />
        <p>
          A token may carry a name prefix, for example{" "}
          <C>ashfaq:the-secret</C>. The audit log then records{" "}
          <C>ashfaq</C> as the actor rather than the literal word{" "}
          <C>admin</C>. That is attribution by convention, not authenticated
          identity: anyone holding the token can claim any name.
        </p>
        <Callout kind="danger" title="Never expose a token to the browser">
          <p>
            <C>NEXT_PUBLIC_*</C> variables are inlined into the client bundle at
            build time. Putting the admin token in one publishes it in the page
            source.
          </p>
          <p>
            The frontend reads <C>ADMIN_TOKEN</C> and <C>CASCADE_API_URL</C>{" "}
            <strong>server side only</strong>, in the proxy route handler. Only{" "}
            <C>NEXT_PUBLIC_API_URL</C> is public, and it is just a URL.
          </p>
        </Callout>
      </Section>

      <Section title="Autonomy">
        <Defs
          items={[
            {
              term: "AUTONOMY_MIN_CONFIDENCE",
              def: (
                <>
                  Default <C>0.0</C>, which disables the gate. Set <C>0.6</C> to
                  require human sign-off for irreversible actions from runbooks
                  below that confidence. A new runbook then earns autonomy over
                  three supervised successes, since confidence climbs 0.30,
                  0.45, 0.60. Off by default because it stops <em>every</em>{" "}
                  first reuse, which is a policy choice a team should make
                  deliberately. See{" "}
                  <a href="/docs/approvals">Approving actions</a>.
                </>
              ),
            },
          ]}
        />
        <p>
          The tier 1 blast-radius gate is always on and is not configurable.
        </p>
      </Section>

      <Section title="Worker and AWS resources">
        <Defs
          items={[
            {
              term: "RUN_WORKER_IN_PROCESS",
              def: (
                <>
                  Default <C>false</C>. Set <C>true</C> locally, because there
                  is no SQS or Lambda and without it the learn loop stops at
                  &ldquo;compile event queued&rdquo; and no runbook ever
                  appears. Deployments <strong>must</strong> leave it false, or
                  two consumers race for the same outbox rows.
                </>
              ),
            },
            {
              term: "LOCAL_WORKER_INTERVAL_SECONDS",
              def: (
                <>
                  Default <C>2.0</C>. How often the in-process worker sweeps.
                </>
              ),
            },
            {
              term: "CASCADE_QUEUE_URL",
              def: "SQS queue. Empty locally, where the sweeper picks rows up instead.",
            },
            {
              term: "EPISODES_BUCKET",
              def: (
                <>
                  S3 bucket for full trajectories. A value ending{" "}
                  <C>-local</C> disables upload.
                </>
              ),
            },
            {
              term: "SNS_BUS_TOPIC_ARN",
              def: "Topic for cross-instance interrupt fan-out.",
            },
            {
              term: "ENABLE_SNS_FANOUT",
              def: (
                <>
                  Default <C>false</C>. Needed above one ECS task, otherwise an
                  interrupt only reaches the instance that issued it.
                </>
              ),
            },
            {
              term: "API_BASE_URL",
              def: "Where the worker posts progress events back to.",
            },
          ]}
        />
      </Section>

      <Section title="Budgets">
        <p>
          Per-task ceilings. Exceeding one fails the task rather than truncating
          it, because a half-executed remediation is worse than none.
        </p>
        <Table
          head={["Variable", "Default", "Applies to"]}
          widths={["250px", "90px", "auto"]}
          rows={[
            [
              <C key="a">MAX_STEPS_PER_TASK</C>,
              "15",
              "Explore. Guided is capped at 8 internally.",
            ],
            [<C key="b">MAX_TOKENS_PER_TASK</C>, "25000", "Explore"],
            [
              <C key="c">MAX_WALL_CLOCK_SECONDS</C>,
              "60",
              "Explore. Guided is capped at 30.",
            ],
            [<C key="d">MAX_CONCURRENT_TASKS</C>, "5", "Advisory"],
          ]}
        />
      </Section>

      <Section title="Retrieval tuning">
        <p>
          Change these if runbooks are matching incidents they should not, or
          failing to match ones they should.
        </p>
        <Defs
          items={[
            {
              term: "RETRIEVAL_L2_THRESHOLD",
              def: (
                <>
                  Default <C>0.85</C>. Distance on unit vectors, so the range is
                  0 to 2. Above this, no candidate is returned. Raise it if
                  Cascade keeps exploring when a suitable runbook exists. Lower
                  it if it reuses runbooks for the wrong problems. Re-tune
                  against the real embedder, since the local fallback has
                  different geometry.
                </>
              ),
            },
            {
              term: "DEDUP_L2_THRESHOLD",
              def: (
                <>
                  Default <C>0.40</C>. Below this at compile time, a new
                  trajectory reinforces the existing runbook instead of forking
                  the library. Lower it if you are getting near-duplicate cards.
                </>
              ),
            },
          ]}
        />
      </Section>

      <Section title="Observability and retention">
        <Defs
          items={[
            {
              term: "OTEL_EXPORTER_OTLP_ENDPOINT",
              def: (
                <>
                  Empty disables tracing entirely, so the app never blocks on a
                  collector that is not there. Spans carry ids, tool names and
                  outcomes. They never carry incident bodies, rule text or model
                  output.
                </>
              ),
            },
            {
              term: "OTEL_SERVICE_NAME",
              def: (
                <>
                  Default <C>cascade-api</C>.
                </>
              ),
            },
            {
              term: "OTEL_CONSOLE_EXPORT",
              def: "Print spans to stdout, for local debugging.",
            },
            {
              term: "AUDIT_LOG_RETENTION_DAYS",
              def: (
                <>
                  Default 90. Applied as a row-level expiry by migration{" "}
                  <C>004</C>.
                </>
              ),
            },
            {
              term: "EPISODE_RETENTION_DAYS",
              def: <>Default 30.</>,
            },
          ]}
        />
      </Section>

      <Section title="Savings">
        <Defs
          items={[
            {
              term: "USD_PER_MTOK",
              def: (
                <>
                  Default <C>1.60</C>. Blended input and output rate per million
                  tokens, applied to <em>measured</em> usage. The usage is a
                  measurement, the rate is an assumption, which is why the
                  savings panel labels the figure an estimate. Set it to your
                  real rate before quoting a number.
                </>
              ),
            },
          ]}
        />
      </Section>

      <Section title="Frontend">
        <Table
          head={["Variable", "Scope", "Purpose"]}
          widths={["230px", "130px", "auto"]}
          rows={[
            [
              <C key="a">NEXT_PUBLIC_API_URL</C>,
              <strong key="b">public</strong>,
              "Reads and the live event stream. The deployed value must be the CloudFront URL over https, never the raw load balancer.",
            ],
            [
              <C key="c">CASCADE_API_URL</C>,
              "server only",
              "Where the proxy forwards privileged calls.",
            ],
            [
              <C key="d">ADMIN_TOKEN</C>,
              "server only",
              "Attached by the proxy, never sent to the browser.",
            ],
          ]}
        />
        <Callout kind="warn" title="Why the API URL must be https">
          Amplify serves the page over https. A browser blocks calls to an http
          origin as mixed content, and takes the live event stream down with
          them. <C>06_deploy_frontend.sh</C> refuses to build against a
          non-https URL.
        </Callout>
      </Section>

      <Section title="A working local .env">
        <Code lang="bash" caption="backend/.env">{`DATABASE_URL=postgresql://root@localhost:26257/cascade?sslmode=disable
CASCADE_STUB_MODE=false
RUN_WORKER_IN_PROCESS=true

ADMIN_TOKEN=dev-admin-token
OPERATOR_TOKEN=dev-operator-token
VIEWER_TOKEN=dev-viewer-token
INTERNAL_SSE_SECRET=dev-internal-secret

# Optional. Without any of these the local fallbacks are used.
# GROQ_API_KEY=
# HF_API_KEY=`}</Code>

        <Code lang="bash" caption="frontend/.env.local">{`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000    # public
CASCADE_API_URL=http://127.0.0.1:8000        # server only
ADMIN_TOKEN=dev-admin-token                  # server only`}</Code>
      </Section>
    </>
  );
}
