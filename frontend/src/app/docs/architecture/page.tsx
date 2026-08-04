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
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "What happens between pressing Run and seeing a result: retrieval, the freshness gate, the cascade transaction and the interrupt path.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Understanding it"
        title="How it works"
        lede="You do not need this page to use Cascade. Read it when you want to know why a behaviour is guaranteed rather than merely usual."
      />

      <Section title="The pieces">
        <Mermaid
          caption="Four processes and one database. There is deliberately no second source of truth."
          chart={`
flowchart TB
    B["Browser"] -->|https| N["Next.js<br/>interface and proxy"]
    N --> A["FastAPI<br/>on ECS Fargate"]
    A --> D["CockroachDB<br/>all durable state<br/>plus the vector index"]
    A -->|outbox row| Q["SQS"]
    Q --> L["Lambda worker<br/>six background jobs"]
    L --> D
    S["EventBridge<br/>every 60 seconds"] --> L
    L -->|"episode bodies"| O["S3 · optional"]
`}
        />

        <Table
          head={["Piece", "Responsible for"]}
          widths={["190px", "auto"]}
          rows={[
            [
              "FastAPI",
              "The HTTP surface, the live event stream, the in-process interrupt bus, and task execution.",
            ],
            [
              "CockroachDB",
              "Every piece of durable state, including the vector index and the version history that time travel reads.",
            ],
            [
              "Lambda worker",
              "Everything asynchronous: compiling runbooks, fanning out rule changes, re-learning, postmortems, insight scans.",
            ],
            ["SQS", "Near real-time delivery of outbox events."],
            [
              "EventBridge",
              "A 60 second sweeper. The safety net that makes the outbox correct rather than hopeful.",
            ],
            [
              "S3",
              "Full episode trajectories. Optional, because the database row keeps enough to be useful without it.",
            ],
            [
              "Next.js",
              "The interface, this documentation, and the server-side proxy that holds privileged credentials out of the browser.",
            ],
          ]}
        />
      </Section>

      <Section title="What happens when you press Run">
        <Mermaid
          caption="The response returns immediately. Everything below the first box happens in the background and streams to your screen."
          chart={`
flowchart TD
    A["POST /api/tasks<br/>row inserted, 201 returned"] --> B["Retrieve<br/>nearest runbooks by meaning"]
    B --> C{"Anything<br/>close enough?"}
    C -- "No" --> X["EXPLORE"]
    C -- "Yes" --> F{"Freshness<br/>check"}
    F -- "stale" --> X
    F -- "fresh" --> P{"Preconditions<br/>hold?"}
    P -- "No" --> X
    P -- "Yes" --> G["GUIDED"]
    G --> E["Write episode"]
    X --> E
    E --> H{"Cold run,<br/>succeeded?"}
    H -- "Yes" --> I["Queue compile"]
    H -- "No" --> J["Record anti-playbook<br/>queue postmortem"]
`}
        />

        <p>
          Inside guided execution, each step is preceded by an interrupt check
          and an autonomy check, and carries a deterministic idempotency key
          derived from the task and the step index. That key is minted at call
          time and is never stored in a runbook, because a key baked into a
          saved procedure would be reused by every future run of it.
        </p>

        <p>
          A task row always reaches a terminal state. One stuck in <C>running</C>{" "}
          would be counted as in flight forever by the interrupt sweep and would
          skew every number in the metric strip.
        </p>
      </Section>

      <Section title="Retrieval runs in two statements">
        <p>
          Splitting this is not premature optimisation. It is the difference
          between using the vector index and not using it.
        </p>

        <Code lang="sql" caption="Phase 1: pure nearest-neighbour, no predicate at all">{`SELECT playbook_id, embedding <-> $1::vector AS dist
FROM playbooks
ORDER BY embedding <-> $1::vector
LIMIT 20;`}</Code>

        <Code lang="sql" caption="Phase 2: primary key lookup and metadata filter">{`SELECT playbook_id, name, version, confidence, status_cache, spec
FROM playbooks
WHERE playbook_id = ANY($1)
  AND status_cache = ANY($2);`}</Code>

        <Callout kind="danger" title="One predicate cost the index">
          <p>
            An earlier version of phase 1 carried{" "}
            <C>WHERE embedding IS NOT NULL</C>. That alone made the optimizer
            abandon <C>pb_embed_idx</C> and full-scan with a top-k sort. The
            answers were still correct, which is exactly why it went unnoticed.
          </p>
          <p>
            The rule has to be read strictly: <em>no</em> predicate belongs in
            the nearest-neighbour statement, not merely no interesting one. Rows
            with a null embedding come back with a null distance and are dropped
            in application code, which is free because phase 2 re-reads those ids
            anyway.
          </p>
          <p>
            Press <C>Ctrl</C> <C>K</C> and run <UI>Verify vector index</UI> to
            check this against the live database at any time.
          </p>
        </Callout>

        <p>
          The freshness join is a third statement and lives in the executor
          rather than in retrieval. Matching and permission are different
          questions and are kept apart on purpose.
        </p>
      </Section>

      <Section title="Why changing a rule is fast no matter how much has been learned">
        <p>
          Marking every dependent runbook stale would mean an unbounded write
          set and heavy contention on the exact table the retrieval path reads.
          So the transaction is a fixed four writes:
        </p>

        <Code lang="sql">{`BEGIN;
  UPDATE rules SET valid_to = now() WHERE rule_key = $1 AND version = $old;
  INSERT INTO rules (rule_key, version, domain, body, params, changed_by) ...;
  INSERT INTO outbox (kind, payload) VALUES ('rule_changed', ...);
  INSERT INTO audit_log (kind, actor, details) VALUES ('rule.change', ...);
COMMIT;`}</Code>

        <p>
          Staleness then <em>derives</em> from the version bump. Every dependent
          runbook is stale the instant this commits, and no runbook row was
          touched to make that true. That is why the cascade completes in tens
          of milliseconds whether there are three runbooks or three thousand.
        </p>

        <p>Everything after the commit is best-effort presentation:</p>
        <ul>
          <li>Publishing to SQS, so the worker picks the event up in about a second.</li>
          <li>In-process interrupt fan-out to running tasks, in microseconds.</li>
          <li>An SNS broadcast, so other instances interrupt their own tasks too.</li>
          <li>A live event, so open dashboards update immediately.</li>
        </ul>

        <p>
          If every one of those fails, the 60 second sweeper still claims the
          outbox row and the durable interrupt flag still stops any executor
          before its next side effect. Correctness never depends on the fast
          path.
        </p>
      </Section>

      <Section title="Interrupts">
        <p>
          Three layers, ordered by speed and by authority in opposite
          directions.
        </p>

        <Table
          head={["Layer", "Latency", "Authority"]}
          widths={["230px", "150px", "auto"]}
          rows={[
            ["In-process interrupt bus", "microseconds", "None. Pure speed."],
            ["SNS fan-out to peers", "about a second", "None. Pure speed."],
            [
              <C key="a">tasks.interrupt_flag</C>,
              "next step boundary",
              <strong key="b">The guarantee</strong>,
            ],
          ]}
        />

        <p>
          The executor checks for interrupts immediately before every
          side-effecting tool call. Never mid-flight, and never before a
          read-only one. On interrupt it persists its scratchpad along with a
          fresh snapshot of the rules, clears the flag so the same interrupt
          cannot fire twice, and stops.
        </p>
      </Section>

      <Section title="How the screen stays live">
        <p>
          The API publishes named events over a single long-lived stream. Slow
          subscribers drop events rather than blocking publishers, because
          events are notifications and state lives in the database.
        </p>

        <Table
          head={["Topic", "Fires when"]}
          widths={["230px", "auto"]}
          rows={[
            [<C key="a">{"task.{id}.step"}</C>, "A tool call completes"],
            [<C key="b">{"task.{id}.status"}</C>, "A task changes state"],
            [<C key="c">rule.changed</C>, "A policy cascade commits"],
            [
              <C key="d">playbook.changed</C>,
              "A runbook is compiled, invalidated, re-learned or reinforced",
            ],
            [<C key="e">metrics.tick</C>, "Metrics are worth refetching"],
            [<C key="f">approval.requested</C>, "An action is waiting on a human"],
            [<C key="g">insight.created</C>, "A scan produced a finding"],
          ]}
        />

        <Callout kind="warn" title="Named events need explicit listeners">
          <p>
            Every event carries a name. The default message handler on an event
            source only fires for <em>unnamed</em> events, so a handler attached
            there receives nothing. That is exactly what happened in the first
            integration: the backend published correctly and not one step ever
            reached the screen.
          </p>
          <p>
            Per-task topics are dynamic, so the client attaches listeners for a
            task&apos;s topics once its id exists. The connection is already
            subscribed to everything, so this needs no reconnect.
          </p>
        </Callout>
      </Section>

      <Section title="The six background jobs">
        <Table
          head={["Job", "Triggered by", "Does"]}
          widths={["165px", "170px", "auto"]}
          rows={[
            [
              <C key="a">compile</C>,
              "A successful cold run",
              "Turns the trajectory into a runbook with grounded provenance",
            ],
            [
              <C key="b">rule_changed</C>,
              "A policy commit",
              "Triage, status sweep, interrupt flags, queueing re-learns",
            ],
            [
              <C key="c">relearn</C>,
              "A high-confidence stale runbook",
              "Re-explores under current rules and compiles v2 with lineage",
            ],
            [
              <C key="d">recheck_suspect</C>,
              "Periodic",
              "Re-derives freshness, so a reverted rule restores the runbook",
            ],
            [
              <C key="e">postmortem</C>,
              "A run that did not end cleanly",
              "Writes a report grounded in the trajectory",
            ],
            [
              <C key="f">insight_scan</C>,
              "Scheduled, or on demand",
              "Mines history for policy recommendations",
            ],
          ]}
        />

        <p>
          Locally there is no SQS and no Lambda, so with{" "}
          <C>RUN_WORKER_IN_PROCESS=true</C> the API polls the outbox itself.
          Same claim, dispatch and mark-processed path. Only the trigger
          differs.
        </p>

        <p>
          A worker claims a row atomically, so at-least-once delivery and a
          worker dying mid-job are both survivable:
        </p>

        <Code lang="sql">{`UPDATE outbox SET claimed_at = now(), claimed_by = $2
WHERE event_id = $1 AND claimed_at IS NULL AND processed_at IS NULL
RETURNING event_id;`}</Code>

        <p>An empty result means another worker got there first.</p>
      </Section>

      <Section title="Model providers">
        <p>
          Three capabilities, each with a fallback chain. Bedrock is first
          because the AWS story is the one being told. The rest exist so the
          full loop runs on free-tier keys or on none at all.
        </p>

        <Code lang="text">{`chat    bedrock -> groq -> openrouter -> deterministic local planner
embed   bedrock -> huggingface        -> deterministic local embedder`}</Code>

        <p>
          Falling back is never silent. The status flips to degraded, the metric
          strip carries a banner saying so, the status bar names the provider
          actually serving, and the smoke check reports chat and embeddings
          separately because they fall back independently.
        </p>

        <SubSection title="The local fallbacks are honest, not fake">
          <p>
            The local planner is not a latency simulation. It makes the same
            tool calls a competent planner would: inspect the incident, read
            policy, check eligibility, then either remediate and notify or
            escalate. It does this instantly, and it never remediates without a
            passing eligibility check.
          </p>
          <p>
            The local embedder is a 1024 dimension normalized signed-hash bag of
            unigrams and bigrams. It reduces incident identifiers to a single
            token, so <C>Remediate INC-1001</C> and <C>Remediate INC-1002</C>{" "}
            embed identically. That is correct: the id is a parameter, not
            intent.
          </p>
        </SubSection>
      </Section>

      <Section title="The seam between the two halves">
        <p>
          Cascade was built by two people in parallel. The entire interface
          between the halves is one module with five functions:
        </p>

        <Code lang="python">{`async def retrieve(task_text) -> PlaybookCandidate | None
async def check_freshness(playbook_id) -> FreshnessResult
async def run_task(task_id) -> None
async def change_rule(rule_key, new_body, new_params, actor) -> ImpactResult
async def answer_analytics_question(question) -> CopilotAnswer`}</Code>

        <p>
          Routers import nothing else from the engine. Each function has two
          bodies, a canned one for stub mode and the real engine underneath.
          That toggle is what let the interface be built before the engine
          existed.
        </p>

        <Callout kind="warn" title="A caution from experience">
          When the two halves were first merged, this module turned out to have
          no wiring at all. Every function still raised a not-implemented error,
          the router caught it, and marked the task succeeded. Every integration
          check passed while nothing executed. That is why the test suite
          asserts observed behaviour rather than HTTP status codes.
        </Callout>
      </Section>
    </>
  );
}
