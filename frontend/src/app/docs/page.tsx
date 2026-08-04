import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  Callout,
  Table,
  CardGrid,
  Card,
  Mermaid,
} from "../../components/docs/Doc";

export const metadata: Metadata = {
  title: "What is Cascade",
  description:
    "Cascade resolves incidents, remembers how it did it, and stops using that memory the moment your policy changes.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Getting started"
        title="What is Cascade"
        lede="An on-call assistant that resolves incidents, remembers how it did it, and stops trusting that memory the moment your policy changes."
      />

      <Section title="What you get">
        <p>
          You describe an incident. Cascade works out what to do, checks your
          policy before it acts, and either resolves the incident or escalates
          it to you with a reason.
        </p>
        <p>
          The next time something similar happens, it already knows the
          procedure and skips straight to executing it. When you change a
          policy rule, every procedure that relied on the old rule stops being
          used until it has been re-checked.
        </p>

        <Table
          head={["You do this", "Cascade does this"]}
          widths={["300px", "auto"]}
          rows={[
            [
              "Type an incident ID and press Run",
              "Reads the incident, checks policy, remediates or escalates, and shows you every step as it happens",
            ],
            [
              "Nothing",
              "Turns that successful run into a reusable runbook, recording which policy rules it depended on",
            ],
            [
              "Run a similar incident",
              "Recognises it, reuses the runbook, and skips the planning",
            ],
            [
              "Change a policy rule",
              "Quarantines every runbook that relied on the old version, and tells you which ones and why",
            ],
            [
              "Nothing",
              "Notices when a policy is blocking work it could safely allow, and suggests a specific change with evidence",
            ],
          ]}
        />
      </Section>

      <Section title="Why the last part matters">
        <p>
          Any tool can cache what worked. The problem is what happens next: your
          rollback window changes from 24 hours to 4, and the cached procedure
          is now a set of confidently wrong instructions.
        </p>

        <Callout kind="good" title="The idea in one sentence">
          A remembered procedure is only usable while the rules it was built on
          are still the current rules, and Cascade checks that immediately
          before every reuse rather than hoping someone updated a flag.
        </Callout>

        <p>
          You will see this in the interface as a runbook card turning amber
          with a red dot next to the rule that changed. Cascade will not run it
          until it has been re-learned under the new policy.
        </p>
      </Section>

      <Section title="The loop">
        <Mermaid
          caption="Learn once, reuse cheaply, and stop reusing the moment policy moves."
          chart={`
flowchart LR
    A["Incident<br/>arrives"] --> B{"Seen this<br/>before?"}
    B -- "No" --> C["Explore:<br/>plan with tools"]
    B -- "Yes" --> D{"Still valid<br/>under policy?"}
    D -- "No" --> C
    D -- "Yes" --> E["Guided:<br/>run the runbook"]
    C --> F["Resolved or<br/>escalated"]
    E --> F
    F --> G["Save as a<br/>runbook"]
    G -.-> B
    H["You change<br/>a policy rule"] --> D
`}
        />
      </Section>

      <Section title="Who this is for">
        <p>
          Cascade is built around SRE incident response: bad deploys, error
          spikes and resource exhaustion, governed by rules about which service
          tiers can be touched automatically, how long after a deploy a
          rollback is still safe, who gets notified, and how many automated
          actions one incident may receive.
        </p>
        <p>
          If your team has a runbook wiki that goes stale the moment policy
          changes, this is the problem Cascade is aimed at.
        </p>
      </Section>

      <Section title="What it will not do">
        <p>Worth knowing before you start:</p>
        <ul>
          <li>
            <strong>It will not act against your policy.</strong> If a rule says
            no, it escalates instead, even when a saved runbook says otherwise.
          </li>
          <li>
            <strong>It will not touch production-critical services
            unsupervised.</strong> Tier-1 actions stop and wait for a human.
          </li>
          <li>
            <strong>It will not silently reuse stale knowledge.</strong> That is
            the entire point.
          </li>
          <li>
            <strong>It does not have user accounts.</strong> There are roles, but
            no login. See <a href="/docs/deployment">Deploying</a> before you put
            it somewhere public.
          </li>
        </ul>
      </Section>

      <Section title="Where to go next">
        <CardGrid>
          <Card href="/docs/quickstart" title="Install and run">
            Get the stack running locally in about ten minutes, with no cloud
            account and no API keys.
          </Card>
          <Card href="/docs/first-incident" title="Your first incident">
            A guided walkthrough of the full loop, with the exact things to type
            and click.
          </Card>
          <Card href="/docs/interface" title="The interface">
            Every panel, badge and control, and what each one is telling you.
          </Card>
          <Card href="/docs/concepts" title="Key concepts">
            Runbooks, provenance, freshness and confidence, explained in terms
            of what you see on screen.
          </Card>
        </CardGrid>
      </Section>
    </>
  );
}
