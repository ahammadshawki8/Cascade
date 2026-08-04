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
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Deploying",
  description:
    "Putting Cascade on AWS, in order, with the traps called out, and what to lock down before you share the link.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Reference"
        title="Deploying"
        lede="Seven scripts, run in a specific order. The order is not cosmetic: two of the dependencies are resolved at build time, not at run time."
      />

      <Callout kind="warn" title="Request Bedrock model access first">
        Model access is granted manually per account and region, and the
        approval is not instant. Until it lands, every call returns{" "}
        <C>AccessDeniedException</C>. Do this before anything else. The rest of
        the setup can proceed in parallel.
      </Callout>

      <Section title="What you need first">
        <Table
          head={["Requirement", "Notes"]}
          widths={["230px", "auto"]}
          rows={[
            [
              "AWS credentials",
              "Bedrock, ECS, Lambda, SQS, S3, Secrets Manager, ECR, CloudFront, Amplify",
            ],
            ["Bedrock model access", "The three pinned models, in your region"],
            [
              "CockroachDB Cloud cluster",
              "The free tier is sufficient for a single-region demo",
            ],
            [
              "Docker",
              "For building the API image. It must produce linux/amd64, because Fargate rejects arm64.",
            ],
            ["GitHub repo and a token", "Optional. Enables CI builds on Amplify."],
          ]}
        />
      </Section>

      <Section title="The order">
        <Mermaid
          caption="Note that 07 runs before 06. That is not a typo."
          chart={`
flowchart TD
    S1["01 · ccloud_provision<br/>CockroachDB Cloud cluster"] --> S2["02 · migrate<br/>001 to 004, vector index"]
    S2 --> S3["03 · aws_bootstrap<br/>S3, SQS, Secrets, IAM, ECR"]
    S3 --> S3b["Store the real connection strings<br/>before anything tries to connect"]
    S3b --> S4["04 · deploy_ecs<br/>image to ECR, load balancer, Fargate"]
    S4 --> S5["05 · deploy_lambda<br/>worker, SQS trigger, 60s sweeper"]
    S5 --> S7["07 · deploy_cloudfront<br/>HTTPS in front of the load balancer"]
    S7 --> S6["06 · deploy_frontend<br/>Amplify, built against CloudFront"]
`}
        />

        <Callout kind="danger" title="Why 07 runs before 06">
          <p>
            <C>NEXT_PUBLIC_API_URL</C> is baked into the frontend bundle at{" "}
            <strong>build</strong> time, so the CloudFront URL has to exist
            before the build starts.
          </p>
          <p>
            Pointing the frontend at the raw load balancer produces a page that
            fails silently. Amplify serves https, the load balancer is http, and
            the browser blocks every request as mixed content, taking the live
            event stream with it. <C>06</C> refuses to build against a non-https
            URL for exactly this reason.
          </p>
        </Callout>
      </Section>

      <Section title="Walkthrough">
        <Steps>
          <Step title="Provision the database">
            <Code lang="bash">{`cd infra && ./01_ccloud_provision.sh`}</Code>
            <p>
              Creates the cluster and three SQL users: <C>cascade_app</C>,{" "}
              <C>cascade_worker</C> and <C>cascade_readonly</C>. The last of
              those is what makes the Ops Copilot safe, since it holds no write
              grants at all.
            </p>
          </Step>

          <Step title="Migrate">
            <Code lang="bash">{`./02_migrate.sh`}</Code>
            <p>
              Applies all four migrations. Confirm the vector index exists
              before continuing, because everything about retrieval depends on
              it:
            </p>
            <Code lang="sql">{`SHOW INDEXES FROM playbooks;   -- expect pb_embed_idx`}</Code>
          </Step>

          <Step title="Bootstrap AWS resources">
            <Code lang="bash">{`./03_aws_bootstrap.sh`}</Code>
            <p>
              S3 bucket, SQS queue, Secrets Manager entries, IAM roles, ECR
              repository.
            </p>
          </Step>

          <Step title="Store the real connection strings">
            <Code lang="bash">{`aws secretsmanager update-secret --secret-id cascade/dsn-app \\
  --secret-string "postgresql://cascade_app:...@...cockroachlabs.cloud:26257/cascade?sslmode=verify-full"

aws secretsmanager update-secret --secret-id cascade/dsn-worker   --secret-string "..."
aws secretsmanager update-secret --secret-id cascade/dsn-readonly --secret-string "..."`}</Code>
            <p>
              Do this before <C>04</C>. The ECS task definition references these
              by ARN and the container will fail its health check without them.
            </p>
          </Step>

          <Step title="Deploy the API">
            <Code lang="bash">{`./04_deploy_ecs.sh`}</Code>
            <p>
              Builds <C>linux/amd64</C>, pushes to ECR, creates the load
              balancer, target group and Fargate service. Health checks hit{" "}
              <C>/health</C>.
            </p>
            <p>
              Desired count is <strong>1</strong> on purpose: the interrupt bus
              and the event broadcaster are in-process singletons. To go above
              one task, see the scaling section below.
            </p>
          </Step>

          <Step title="Deploy the worker">
            <Code lang="bash">{`./05_deploy_lambda.sh`}</Code>
            <p>
              Packages the application and worker code, wires the SQS trigger
              with partial-batch failure reporting, and schedules the sweeper at
              one minute.
            </p>
            <Callout kind="warn" title="Platform-specific wheels">
              The build pins{" "}
              <C>--platform manylinux2014_x86_64 --only-binary=:all:</C>.
              Without those flags, pip resolves host wheels for the database
              driver&apos;s binary extension and the function dies at import with an
              ELF error.
            </Callout>
            <p>
              <C>AWS_REGION</C> is deliberately not set, because Lambda reserves
              it and rejects the deployment. <C>RUN_WORKER_IN_PROCESS=false</C>{" "}
              so the API does not also drain the outbox and race the worker for
              the same rows.
            </p>
          </Step>

          <Step title="Put HTTPS in front">
            <Code lang="bash">{`./07_deploy_cloudfront.sh`}</Code>
            <Callout kind="danger" title="Compression must stay off for /api">
              <p>
                CloudFront buffers a compressed response. For{" "}
                <C>/api/events</C> the stream never ends, so the dashboard would
                receive <em>nothing at all</em>.
              </p>
              <p>
                The distribution sets <C>Compress: false</C> and disables
                caching on both behaviours, and the API sends{" "}
                <C>X-Accel-Buffering: no</C> for the same reason.
              </p>
            </Callout>
            <p>Note the printed URL. The next step needs it.</p>
          </Step>

          <Step title="Deploy the frontend">
            <Code lang="bash">{`./06_deploy_frontend.sh

# or, to put a password on the site:
DEMO_USER=judge DEMO_PASSWORD=... ./06_deploy_frontend.sh`}</Code>
            <p>
              Auto-discovers the CloudFront URL. The platform is{" "}
              <C>WEB_COMPUTE</C>, because the app router and the server-side
              proxy need real compute rather than a static export.
            </p>
            <p>
              The admin token is passed <strong>without</strong> a{" "}
              <C>NEXT_PUBLIC_</C> prefix. Adding one back re-opens the
              credential leak described below.
            </p>
          </Step>
        </Steps>
      </Section>

      <Section title="Verify">
        <Code lang="bash">{`curl https://<cloudfront>/health
curl https://<cloudfront>/api/metrics

# Re-prove the vector index on the production cluster
curl https://<cloudfront>/api/admin/verify-index -H "x-admin-token: $ADMIN_TOKEN"

# Which provider is actually serving
curl https://<cloudfront>/api/admin/smoke -H "x-admin-token: $ADMIN_TOKEN"

# Must stream, not buffer
curl -N https://<cloudfront>/api/events`}</Code>

        <Table
          head={["Check", "Expect"]}
          widths={["260px", "auto"]}
          rows={[
            [<C key="a">/health</C>, <C key="b">{'{"status":"ok"}'}</C>],
            [
              <C key="c">verify-index</C>,
              <span key="c2">
                <C>uses_index: true</C>, and a plan naming <C>pb_embed_idx</C>
              </span>,
            ],
            [
              <C key="d">smoke</C>,
              <span key="d2">
                <C>chat_provider</C> and <C>embed_provider</C> both reading{" "}
                <C>bedrock</C>
              </span>,
            ],
            [
              <C key="e">/api/events</C>,
              "Heartbeats arriving every 15 seconds or so, not one buffered blob at the end",
            ],
            [
              "A cold run",
              "The task succeeds and a runbook appears within a few seconds",
            ],
            ["CloudWatch", "Lambda invoked on the compile event, with no errors"],
          ]}
        />

        <Callout kind="note" title="Then re-measure the speed number">
          Any cold versus guided figure taken before this point was measured
          without a live planner and reflects database round-trips only. Re-run
          the demo sequence and use the number the deployed system actually
          produces.
        </Callout>
      </Section>

      <Section title="Before you share the link">
        <p>
          Be precise about what protects a deployed Cascade, because the honest
          answer is less than people assume.
        </p>

        <SubSection title="What exists">
          <Table
            head={["Control", "What it does"]}
            widths={["230px", "auto"]}
            rows={[
              [
                "Three roles",
                "Viewer reads. Operator runs tasks and resolves approvals. Admin changes policy and resets the world. Enforced on every write endpoint.",
              ],
              [
                "Server-side proxy",
                "Privileged calls go through a route handler on the web server that attaches the token out of the browser's reach, with an explicit allowlist of permitted paths.",
              ],
              [
                "Read-only Copilot connection",
                "Generated SQL runs as a database user with no write grants.",
              ],
              [
                "Audit log",
                "Every policy change and approval decision is recorded with an actor, and survives a demo reset.",
              ],
            ]}
          />
        </SubSection>

        <SubSection title="What does not exist">
          <Callout kind="danger" title="There is no authentication">
            <p>
              No login, no user store, no sessions, no single sign-on. Tokens
              are shared secrets, not per-user credentials. The <C>name:</C>{" "}
              prefix is self-asserted, so anyone holding the admin token can
              claim to be anyone.
            </p>
            <p>
              Most read endpoints, including submitting a task and asking the
              Copilot, require no credential at all. That is a deliberate demo
              choice. The proxy stops the token leaking into the page source. It
              is <strong>not</strong> access control: anyone who can reach the
              site can still change policy or reset the world.
            </p>
          </Callout>

          <p>
            For a judging link that is usually fine and arguably intended, since
            a judge is meant to be able to change policy. When it is not, gate
            the whole site at the edge:
          </p>
          <Code lang="bash">{`DEMO_USER=judge DEMO_PASSWORD=... ./infra/06_deploy_frontend.sh`}</Code>
          <p>
            Real authentication would be an identity provider in front of
            CloudFront, with the caller resolved from a verified token. The role
            layer was designed around that seam.
          </p>
        </SubSection>

        <SubSection title="The credential bug worth knowing about">
          <p>
            An earlier version put the admin token in a{" "}
            <C>NEXT_PUBLIC_</C> variable. Those are inlined into the client
            bundle at build time, and the deploy script was reading the token{" "}
            <em>out of Secrets Manager</em> in order to publish it in the page
            source. It took a managed secret and made it public while looking
            secure.
          </p>
          <p>
            After a clean build, the token now appears only in the server
            bundle. What the browser downloads is clean. Do not add the prefix
            back.
          </p>
        </SubSection>
      </Section>

      <Section title="Scaling past one task">
        <p>
          The interrupt bus is in-process, so a rule change handled by one
          instance cannot reach executors on another through the local bus.
          Above one ECS task, set:
        </p>
        <Code lang="bash">{`ENABLE_SNS_FANOUT=true
SNS_BUS_TOPIC_ARN=arn:aws:sns:us-east-1:<account>:cascade-bus`}</Code>
        <p>
          Each instance subscribes at <C>POST /internal/fanout</C> and applies
          the broadcast to its own bus. Best-effort by design: the durable
          interrupt flag remains the guarantee, so a missed broadcast costs at
          most one extra step.
        </p>
        <p>
          Multi-region survival goals, per-table localities and what each one
          changes in the application are documented in{" "}
          <C>docs/multi-region.md</C> in the repository.
        </p>
      </Section>

      <Section title="Cost">
        <Table
          head={["Service", "Demo footprint"]}
          widths={["210px", "auto"]}
          rows={[
            ["CockroachDB Cloud", "Free tier"],
            ["ECS Fargate", "One task at 0.5 vCPU and 1 GB"],
            [
              "Load balancer",
              "Hourly plus capacity units. The largest fixed line item.",
            ],
            ["Lambda", "Well inside the free tier"],
            ["SQS and S3", "Negligible"],
            ["CloudFront", "Free tier covers demo traffic"],
            ["Amplify", "Free tier covers one app"],
            [
              "Bedrock",
              "Pay per token. Titan embeddings are about $0.02 per million tokens, so a full demo costs cents.",
            ],
          ]}
        />
        <p>
          Set an AWS Budget before the first deploy. The load balancer and the
          Fargate task bill whether or not anyone is using them.
        </p>
      </Section>

      <Section title="Teardown">
        <Code lang="bash">{`aws ecs update-service --cluster cascade-cluster --service cascade-api --desired-count 0
aws ecs delete-service --cluster cascade-cluster --service cascade-api --force
aws elbv2 delete-load-balancer --load-balancer-arn <arn>
aws lambda delete-function --function-name cascade-worker
aws events delete-rule --name cascade-sweeper --force
aws cloudfront delete-distribution --id <id> --if-match <etag>   # disable first
aws amplify delete-app --app-id <id>`}</Code>
        <p>
          Delete the CockroachDB cluster from the Cloud console. S3 and Secrets
          Manager cost effectively nothing and are worth keeping until the
          submission has been judged.
        </p>
      </Section>
    </>
  );
}
