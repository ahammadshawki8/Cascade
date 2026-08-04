import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  SubSection,
  Callout,
  Code,
  Table,
  C,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "HTTP API",
  description: "Every endpoint, the role it requires, and what it returns.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Reference"
        title="HTTP API"
        lede="Everything the interface does, you can do from a terminal. All routes are under /api, and interactive OpenAPI docs are served at /docs on the backend itself."
      />

      <Callout kind="note" title="You do not need this to use Cascade">
        This page is for scripting the product, wiring it into something else,
        or debugging a deployment. Everything here has a button.
      </Callout>

      <Section title="Authentication">
        <p>
          Send a token as <C>x-admin-token</C> or as{" "}
          <C>Authorization: Bearer</C>. Without a token the caller is a{" "}
          <strong>viewer</strong>, which is enough for every read endpoint.
        </p>

        <Table
          head={["Role", "May"]}
          widths={["120px", "auto"]}
          rows={[
            ["viewer", "Read everything"],
            ["operator", "Run tasks, resolve approvals, queue re-learns"],
            [
              "admin",
              "Change policy, scan insights, generalize runbooks, reset the world",
            ],
          ]}
        />

        <p>
          A token may carry a <C>name:</C> prefix so actions are attributable:
        </p>
        <Code lang="bash">{`curl -X POST localhost:8000/api/rules/incident.rollback_window \\
  -H "x-admin-token: ashfaq:dev-admin-token" \\
  -H "Content-Type: application/json" \\
  -d '{"body":"Rollback allowed within {hours}h of deploy.","params":{"hours":6}}'`}</Code>
        <p>
          The audit log then records <C>ashfaq</C> as the actor rather than a
          shared literal. It is attribution by convention, not authenticated
          identity: anyone holding the token can claim any name. See{" "}
          <a href="/docs/deployment">Deploying</a> for what that means in
          practice.
        </p>
      </Section>

      <Section title="Tasks">
        <SubSection title="POST /api/tasks">
          <p>
            Submit an incident. Returns immediately. Execution continues in the
            background and streams over the event endpoint.
          </p>
          <Code lang="bash">{`curl -X POST localhost:8000/api/tasks \\
  -H "Content-Type: application/json" \\
  -d '{"input": "Remediate INC-1001"}'

# 201
{ "task_id": "0e5f...", "status": "queued" }`}</Code>
        </SubSection>

        <SubSection title="GET /api/tasks and GET /api/tasks/{'{id}'}">
          <p>
            List recent tasks with <C>?limit=</C> and <C>?status=</C>, or fetch
            one. Terminal states are <C>succeeded</C>, <C>failed</C> and{" "}
            <C>interrupted</C>. <C>awaiting_approval</C> means parked, not
            finished.
          </p>
        </SubSection>
      </Section>

      <Section title="Streaming">
        <SubSection title="GET /api/events">
          <p>
            Server-sent events with a 15 second heartbeat. <C>?topics=</C> takes
            a comma-separated list, <C>*</C> means everything, and a trailing{" "}
            <C>*</C> works as a prefix wildcard.
          </p>
          <Code lang="javascript">{`const es = new EventSource("/api/events?topics=*");

// Every event is NAMED after its topic, so onmessage never fires.
es.addEventListener("playbook.changed", (e) => refresh(JSON.parse(e.data)));

// Per-task topics are dynamic. Attach once the id exists.
es.addEventListener(\`task.\${taskId}.step\`, onStep);`}</Code>
          <Callout kind="warn">
            <C>EventSource.onmessage</C> only fires for <em>unnamed</em> events.
            A handler attached there will receive nothing from this API.
          </Callout>
        </SubSection>
      </Section>

      <Section title="Playbooks">
        <Table
          head={["Endpoint", "Role", "Returns"]}
          widths={["270px", "100px", "auto"]}
          rows={[
            [
              <C key="a">GET /api/playbooks</C>,
              "any",
              "All runbooks with their dependencies and inline freshness",
            ],
            [
              <C key="b">{"GET /api/playbooks/{id}"}</C>,
              "any",
              "One runbook in full",
            ],
            [
              <C key="c">{"GET /api/playbooks/{id}/freshness"}</C>,
              "any",
              <span key="c2">
                The authoritative provenance check: <C>is_fresh</C> plus{" "}
                <C>stale_deps</C>
              </span>,
            ],
            [
              <C key="d">{"GET /api/playbooks/{id}/episodes"}</C>,
              "any",
              "Runs that executed this runbook",
            ],
            [
              <C key="e">{"POST /api/playbooks/{id}/relearn"}</C>,
              "operator",
              "Queues an explore pass that compiles as the next version",
            ],
          ]}
        />

        <Callout kind="note">
          <C>status_cache</C> on the list endpoint is an asynchronous
          convenience and can lag. <C>/freshness</C> is the check that actually
          decides whether a runbook may execute.
        </Callout>
      </Section>

      <Section title="Rules and impact">
        <Table
          head={["Endpoint", "Role", "Effect"]}
          widths={["260px", "100px", "auto"]}
          rows={[
            [<C key="a">GET /api/rules</C>, "any", "Current versions"],
            [
              <C key="b">{"GET /api/rules/{key}"}</C>,
              "any",
              "Current version plus full history",
            ],
            [
              <C key="c">{"POST /api/rules/{key}/dry-run"}</C>,
              "any",
              "Impact preview. Writes nothing.",
            ],
            [
              <C key="d">{"POST /api/rules/{key}/replay"}</C>,
              "any",
              "Counterfactual over recorded incidents",
            ],
            [
              <C key="e">{"POST /api/rules/{key}"}</C>,
              <strong key="f">admin</strong>,
              "Commits the cascade transaction",
            ],
            [
              <C key="g">GET /api/impact?rule_key=</C>,
              "any",
              "Deterministic impact query",
            ],
          ]}
        />

        <SubSection title="Counterfactual replay">
          <p>
            Answers a different question from the impact preview. Impact says{" "}
            <em>which runbooks go stale</em>. Replay says{" "}
            <em>what would have happened differently</em>.
          </p>
          <Code lang="bash">{`curl -X POST localhost:8000/api/rules/incident.rollback_window/replay \\
  -H "Content-Type: application/json" -d '{"params":{"hours":72}}'

{
  "incidents_examined": 12,
  "newly_allowed": [ { "incident_id": "INC-1004", "kind": "bad_deploy" } ],
  "newly_blocked": [],
  "net_change": 3,
  "summary": "Across 12 historical incidents, 3 incident(s) would now be auto-remediated."
}`}</Code>
          <p>
            Deterministic and side-effect free. It re-decides eligibility, it
            does not re-execute anything.
          </p>
        </SubSection>
      </Section>

      <Section title="Approvals">
        <Table
          head={["Endpoint", "Role", "Effect"]}
          widths={["290px", "100px", "auto"]}
          rows={[
            [
              <C key="a">GET /api/approvals</C>,
              "any",
              "Pending queue with reason and context",
            ],
            [
              <C key="b">{"POST /api/approvals/{id}/resolve"}</C>,
              "operator",
              <span key="b2">
                Body <C>{'{"decision":"approved"|"rejected"}'}</C>
              </span>,
            ],
          ]}
        />
        <Callout kind="note">
          The resolver is taken from the authenticated caller. A client-supplied{" "}
          <C>resolved_by</C> is ignored. Who authorised an irreversible action
          is not a field the caller gets to assert.
        </Callout>
        <p>
          Approving re-runs the task. Earlier steps replay safely because every
          side-effecting tool is idempotent on{" "}
          <C>{"{task_id}:{step_index}"}</C>. Rejecting terminates it as
          escalated.
        </p>
      </Section>

      <Section title="Intelligence">
        <Table
          head={["Endpoint", "Role", "Returns"]}
          widths={["280px", "100px", "auto"]}
          rows={[
            [
              <C key="a">GET /api/insights</C>,
              "any",
              "Policy recommendations with evidence",
            ],
            [
              <C key="b">{"POST /api/insights/{id}/dismiss"}</C>,
              "any",
              "Hides one. A dismissed insight is never re-raised.",
            ],
            [
              <C key="c">POST /api/insights/scan</C>,
              "admin",
              "Runs the detectors now",
            ],
            [
              <C key="d">GET /api/savings</C>,
              "any",
              "Tokens, dollars and engineer hours avoided",
            ],
            [
              <C key="e">GET /api/graph</C>,
              "any",
              "Rules, runbooks and tasks, with stale edges marked",
            ],
            [
              <C key="f">GET /api/timetravel?minutes_ago=</C>,
              "any",
              <span key="f2">
                Past state via <C>AS OF SYSTEM TIME</C>
              </span>,
            ],
            [
              <C key="g">GET /api/anti-playbooks</C>,
              "any",
              "What the system learned not to do",
            ],
            [<C key="h">GET /api/postmortems</C>, "any", "Generated writeups"],
            [
              <C key="i">GET /api/generalize/candidates</C>,
              "any",
              "Mergeable runbook clusters",
            ],
            [<C key="j">POST /api/generalize</C>, "admin", "Merges them"],
          ]}
        />

        <SubSection title="Savings">
          <p>
            Returns <C>available: false</C> with a message when there is no
            baseline yet, rather than reporting zero. Token and latency deltas
            are measured from recorded episodes. The dollar figure applies a
            published rate to that measured usage and is labelled an estimate.
          </p>
        </SubSection>

        <SubSection title="Time travel">
          <p>
            Reads directly from CockroachDB version history. Beyond the
            cluster&apos;s garbage-collection window, roughly 25 hours, it returns{" "}
            <C>available: false</C> with an explanation rather than empty data.
          </p>
        </SubSection>
      </Section>

      <Section title="Ops Copilot">
        <SubSection title="POST /api/copilot">
          <Code lang="bash">{`curl -X POST localhost:8000/api/copilot \\
  -H "Content-Type: application/json" \\
  -d '{"question": "Which runbooks are stale?"}'

{
  "question": "Which runbooks are stale?",
  "sql": "SELECT p.name, d.rule_key, ...",
  "columns": ["name", "rule_key", "compiled_against", "current_version"],
  "rows": [["rollback for bad deploy", "incident.rollback_window", 1, 2]],
  "refused": false,
  "disclaimer": "Exploratory. Generated SQL shown above; verify before acting."
}`}</Code>
          <p>Four layers of defence, because a model writes the query:</p>
          <ol>
            <li>
              It must parse as a single <C>SELECT</C> or <C>WITH</C>.
            </li>
            <li>Mutating keywords are rejected on word boundaries.</li>
            <li>
              It is wrapped in <C>LIMIT 200</C> with a 3 second timeout.
            </li>
            <li>
              It runs as <C>cascade_readonly</C>, which holds no write grants.
            </li>
          </ol>
          <p>
            Layer four is the one that actually matters. The first three exist
            so a bad query fails loudly and cheaply instead of reaching the
            database at all.
          </p>
          <Callout kind="note">
            Word boundaries matter. A naive substring check rejects{" "}
            <C>SELECT created_at ...</C> because it contains
            &ldquo;create&rdquo;, which was a real defect.
          </Callout>
        </SubSection>
      </Section>

      <Section title="Admin">
        <Table
          head={["Endpoint", "Role", "Effect"]}
          widths={["250px", "100px", "auto"]}
          rows={[
            [
              <C key="a">POST /api/admin/reset</C>,
              "admin",
              <span key="a2">
                Clears learned state and re-seeds v1. Preserves{" "}
                <C>audit_log</C>.
              </span>,
            ],
            [
              <C key="b">GET /api/admin/verify-index</C>,
              "admin",
              <span key="b2">
                Live <C>EXPLAIN</C> proof that the vector index is used
              </span>,
            ],
            [
              <C key="c">GET /api/admin/smoke</C>,
              "admin",
              "Which provider is actually serving",
            ],
          ]}
        />
        <p>
          <C>verify-index</C> asserts rather than assumes. The whole distributed
          vector search claim rests on the planner picking the index, so it can
          be re-proven on the production cluster and on camera.
        </p>
      </Section>

      <Section title="Internal">
        <p>
          Mounted at the root rather than under <C>/api</C>, and authenticated
          with <C>x-internal-secret</C>. These exist because a Lambda has no
          socket to the browser.
        </p>
        <Table
          head={["Endpoint", "Purpose"]}
          widths={["230px", "auto"]}
          rows={[
            [
              <C key="a">POST /internal/sse</C>,
              "The worker publishes an event to connected dashboards",
            ],
            [
              <C key="b">POST /internal/fanout</C>,
              "Applies an interrupt broadcast from another instance",
            ],
          ]}
        />
      </Section>

      <Section title="Errors">
        <Table
          head={["Status", "Means"]}
          widths={["100px", "auto"]}
          rows={[
            [
              "400",
              "Stub mode, or a request the endpoint cannot serve in the current configuration",
            ],
            ["403", "Missing, invalid, or insufficiently privileged token"],
            ["404", "No such rule, runbook, task or episode"],
            ["422", "Request body failed schema validation"],
            ["500", "Unhandled. Check the API logs."],
          ]}
        />
      </Section>
    </>
  );
}
