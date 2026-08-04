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
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "Key concepts",
  description:
    "Rules, runbooks, provenance, freshness, confidence and the two execution modes, explained in terms of what you see on screen.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Understanding it"
        title="Key concepts"
        lede="Seven ideas. Once you have these, every screen in Cascade reads as an expression of one of them."
      />

      <Section title="Rule">
        <p>
          A statement of policy, written in English, with a version number. Rules
          are the boundary Cascade is not allowed to cross.
        </p>
        <p>
          They are never edited in place and never deleted. Changing a rule
          closes the current version and opens a new one, which is why the number
          beside the rule key in <UI>Policy</UI> goes up rather than the text
          simply changing. The old version stays queryable, which is what makes{" "}
          <UI>time travel</UI> possible.
        </p>
        <p>
          There are four seeded rules. See{" "}
          <a href="/docs/policy">Changing policy</a> for what each one governs.
        </p>
        <Callout kind="note" title="Rules are data, not code">
          No policy logic is compiled into the agent or baked into a runbook.
          The tools read the rules at the moment they run and report what policy
          says. That is why changing a rule takes effect immediately rather than
          on the next deploy.
        </Callout>
      </Section>

      <Section title="Runbook">
        <p>
          A procedure Cascade wrote for itself after a run that worked. You see
          them as cards in <UI>Runbooks</UI>. Each one carries:
        </p>
        <Defs
          items={[
            { term: "A goal", def: "What problem shape it solves." },
            {
              term: "Preconditions",
              def: "What must be true for it to apply. Checked before every reuse.",
            },
            {
              term: "Steps",
              def: "The exact tool sequence, with placeholders for the incident-specific values.",
            },
            {
              term: "Rule citations",
              def: "The policy rules the original run actually consulted, each pinned to the version in force at the time. This is the provenance list on the expanded card.",
            },
          ]}
        />
        <p>
          A compiled runbook must pass a safety check before it is stored: known
          tools only, between two and eight steps, and never a remediation step
          without an eligibility check before it. Output that does not pass is
          rejected rather than repaired, because a procedure nobody can validate
          is not a procedure.
        </p>
      </Section>

      <Section title="Provenance">
        <p>
          The record of which rules a runbook depends on. It is the difference
          between a cache and Cascade.
        </p>
        <p>
          You see it as the <UI>Provenance</UI> section of an expanded runbook
          card: one row per rule, with a coloured dot, the pinned version and a
          one-sentence justification.
        </p>

        <SubSection title="Citations are grounded, not trusted">
          <p>
            A model asked to summarise a run will happily cite a
            plausible-sounding rule it never actually saw. Cascade cross-checks
            every citation against what was genuinely observed during the run:
            the policy snapshot the run read, and the versions the eligibility
            check reported using. A citation corroborated by neither is dropped.
          </p>
          <Callout kind="good" title="Why an invented citation would be worse than none">
            A fabricated dependency points at a rule the runbook does not really
            rely on. It would never go stale when the rule that actually matters
            changes. The runbook would look fresh forever, which is precisely
            the failure the whole system exists to prevent.
          </Callout>
        </SubSection>
      </Section>

      <Section title="Freshness">
        <p>
          The check that runs immediately before every reuse. It compares each
          pinned version in the runbook&apos;s provenance against the version of that
          rule that is current right now.
        </p>

        <Mermaid
          caption="Any mismatch at all means stale. There is no partial credit and no score."
          chart={`
flowchart TD
    A["Runbook matched<br/>by similarity"] --> B["Compare each pinned rule version<br/>to the current version"]
    B --> C{"Any<br/>mismatch?"}
    C -- "No" --> D["Fresh · execute guided"]
    C -- "Yes" --> E["Stale · refuse and explore instead"]
    F["Check itself errors"] --> E
`}
        />

        <Defs
          items={[
            {
              term: "It returns a reason, not a boolean",
              def: (
                <>
                  The answer names which dependency is out of date, which is
                  what the red dot on the card is showing you and what tells the
                  re-learn what it has to account for.
                </>
              ),
            },
            {
              term: "It fails closed",
              def: "If the check itself errors, the runbook is treated as stale. An unverifiable procedure must not run.",
            },
            {
              term: "The amber pill is not the gate",
              def: (
                <>
                  The <UI>suspect</UI> status shown on a card is a convenience
                  for you and can lag by a moment. The decision about whether
                  execution is allowed is made by the live comparison, never by
                  reading that badge.
                </>
              ),
            },
          ]}
        />
      </Section>

      <Section title="The two execution modes">
        <Table
          head={["", "Explore", "Guided"]}
          widths={["190px", "auto", "auto"]}
          rows={[
            [
              "Badge shown",
              <UI key="a">Exploring</UI>,
              <UI key="b">Runbook · name v1</UI>,
            ],
            [
              "When",
              "No runbook matched, or one matched and was refused as stale",
              "A matching runbook passed the freshness check and its preconditions hold",
            ],
            [
              "Who decides the next step",
              "The planner, one model call at a time",
              "The stored step list. No planner in the loop.",
            ],
            [
              "Cost",
              "Slow, token-heavy",
              "Fast, near free",
            ],
            [
              "Produces a runbook?",
              "Yes, if it succeeds",
              "No. It reinforces the one it used.",
            ],
          ]}
        />

        <Callout kind="danger" title="A runbook is a plan, not a licence">
          <p>
            Guided execution replays its steps mechanically, so it must still
            obey the eligibility verdict at run time. An early version of
            Cascade recorded a refusal and then applied the remediation anyway.
            Exploring was safe only because the planner <em>reads</em> the
            answer before deciding what to do next.
          </p>
          <p>
            A tier 2 incident outside the rollback window would have been
            remediated in direct violation of policy. That is fixed and covered
            by a dedicated regression test.
          </p>
        </Callout>

        <p>
          A precondition miss is not a failure. Cascade falls back to exploring
          and the runbook&apos;s confidence is untouched, because the runbook was
          right to decline.
        </p>
      </Section>

      <Section title="Confidence">
        <p>
          A score from 0 to 1 attached to each runbook, shown as the thin bar
          under its card. It moves only on guided outcomes, so a runbook is
          judged on reuse rather than on the single run that authored it.
        </p>

        <Table
          head={["Event", "Effect"]}
          widths={["280px", "auto"]}
          rows={[
            [
              "Compiled",
              <span key="a">
                Starts at <strong>0.30</strong>, status <C>candidate</C>
              </span>,
            ],
            ["Reused successfully", "Rises by 0.15, capped at 0.99"],
            ["Reused and failed", "Multiplied by 0.6"],
            [
              "Promotion",
              <span key="b">
                Three successes and at least 0.60 makes it <C>active</C>
              </span>,
            ],
            [
              "Rejection",
              <span key="c">
                Below 0.20 makes it <C>rejected</C>, which is terminal
              </span>,
            ],
            ["Idle decay", "Multiplied by 0.98 for every seven unused days"],
          ]}
        />

        <Callout kind="note" title="Confidence and freshness answer different questions">
          Confidence asks <em>has this worked before</em>. Freshness asks{" "}
          <em>are the rules it assumed still the rules</em>. A runbook at 0.99
          is quarantined the instant a dependency moves. Past success never
          overrides current policy.
        </Callout>
      </Section>

      <Section title="Episode">
        <p>
          The record of one completed run: which mode, what outcome, how many
          steps, how long, how many tokens. Episodes are the evidence base.
        </p>
        <p>
          The metric strip, the savings ledger, the counterfactual preview in{" "}
          <UI>Policy</UI> and the insight proposals in <UI>Approvals</UI> all
          read from episodes rather than from anything the system asserts about
          itself. That is why the numbers can be checked and why they sometimes
          say something unflattering.
        </p>
        <p>
          Click <UI>View episodes</UI> on any runbook card to see the individual
          runs behind its success count.
        </p>
      </Section>

      <Section title="Negative memory">
        <p>
          Only successes become runbooks. Without something more, a failed
          approach is forgotten the moment the task ends, and Cascade pays full
          exploration cost to rediscover the same dead end next week.
        </p>
        <p>
          Failures are recorded as anti-playbooks: this class of incident, this
          action, this is why it failed. You see them under{" "}
          <UI>Intelligence</UI> then <UI>memory</UI>. Relevant ones are surfaced
          to the planner as warnings.
        </p>
        <Callout kind="warn" title="Advisory, never authoritative">
          An anti-playbook says a previous attempt failed and why. It does not
          forbid the action. Policy is enforced by the eligibility check, and a
          stale memory of failure must not be able to veto something the rules
          now permit.
        </Callout>
      </Section>

      <Section title="How they fit together">
        <Mermaid
          caption="The seven concepts in one picture."
          chart={`
flowchart TB
    R["Rules<br/>versioned policy"] --> E["Eligibility check<br/>during a run"]
    E --> EP["Episode<br/>what happened"]
    EP --> PB["Runbook<br/>reusable procedure"]
    EP --> NM["Negative memory<br/>what not to try"]
    R -.-> PV["Provenance<br/>pinned rule versions"]
    PB --- PV
    PV --> F{"Freshness<br/>check"}
    F --> G["Guided execution"]
    PB --- CF["Confidence<br/>earned by reuse"]
    CF --> G
`}
        />
      </Section>
    </>
  );
}
