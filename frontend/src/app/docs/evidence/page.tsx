import type { Metadata } from "next";
import {
  PageHeader,
  Section,
  SubSection,
  Callout,
  Table,
  Code,
  C,
  UI,
  Where,
  Mermaid,
} from "../../../components/docs/Doc";

export const metadata: Metadata = {
  title: "The evidence",
  description:
    "How Cascade is measured against two baselines on the same incidents, what the evaluation found, and how to run it yourself.",
};

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Using Cascade"
        title="The evidence"
        lede="Whether any of this is better than not having it, measured against two alternatives on the same incidents, with the same model."
      />

      <Where>
        <UI>Evidence</UI>, the sixth icon in the activity bar
      </Where>

      <Section title="What this view shows">
        <p>
          Every other view shows what Cascade does. This one shows whether it is
          worth doing. It renders a recorded result file rather than running
          anything: a full evaluation is dozens of model calls, and recomputing
          it whenever somebody opens a tab would be both expensive and
          dishonest, because the number on screen would drift from the number in
          the changelog every time a provider had a slow afternoon.
        </p>
        <p>
          So the harness writes a dated artifact, the artifact is committed, and
          the command that regenerates it is printed on the page. That is what
          makes the claim checkable rather than merely stated.
        </p>
      </Section>

      <Section title="The experiment">
        <p>
          Twelve seeded incidents are decided twice, under two policy states.
          Nothing about the incidents changes between them. One rule moves.
        </p>

        <Table
          head={["Phase", "Policy", "What it establishes"]}
          rows={[
            [
              "Phase 1",
              <>
                <C>rollback_window</C> = 24h
              </>,
              "Everyone can read a rule and apply it. Not the interesting half.",
            ],
            [
              "Phase 2",
              <>
                <C>rollback_window</C> = 4h
              </>,
              "The same world, one rule tightened after the runbook was compiled.",
            ],
          ]}
        />

        <Mermaid
          caption="The order matters. Learning happens under the original policy, so the procedure predates the change that invalidates it."
          chart={`
flowchart LR
    A["Reset the world"] --> B["Learn a runbook<br/>under the 24h rule"]
    B --> C["Wait for it to compile<br/>and pin its provenance"]
    C --> D["Tighten the rule<br/>to 4h"]
    D --> E["Score every incident<br/>on all three arms"]
`}
        />

        <SubSection title="The three arms">
          <Table
            head={["Arm", "What it is"]}
            rows={[
              [
                "Direct prompt",
                "One call. The incident and the current policy, decide. No memory, so nothing can go stale.",
              ],
              [
                "Cached runbook",
                "Stores what worked, matches the next incident, replays it. No provenance, no version pinning.",
              ],
              ["Cascade", "The system under test."],
            ]}
          />
          <Callout kind="note" title="The baselines are not strawmen">
            Both call the same provider chain and the same model as Cascade&rsquo;s
            own planner, and both are handed the current policy, with live
            parameter values, on every call. The cached-runbook arm is not
            guessing at a rule it was never shown. It is shown the new rule and
            also holds a procedure that was correct under the old one.
          </Callout>
        </SubSection>

        <SubSection title="What counts as correct">
          <p>
            Ground truth is the seeded rule predicates, applied by the same
            evaluator the product uses. It is data a human wrote in the seed
            file, not an opinion and not Cascade&rsquo;s answer. The primary
            metric is the share of decisions that match it.
          </p>
          <p>
            Two kinds of error are separated, because they are not equally bad.
            Escalating something policy would have permitted costs a human a few
            minutes. Acting where policy forbids it is the only error on the page
            that could hurt somebody, and it is counted and coloured on its own.
          </p>
        </SubSection>
      </Section>

      <Section title="What it found">
        <p>
          The result is reported as measured, including where it was weaker than
          expected.
        </p>

        <Table
          head={["Metric", "Direct prompt", "Cached runbook", "Cascade"]}
          rows={[
            ["Policy-correct decisions", "86.4%", "86.4%", "95.5%"],
            ["Unsafe actions", "0", "0", "1"],
            ["Median latency", "2,530 ms", "2,515 ms", "4,877 ms"],
            ["Planner tokens", "7,118", "9,821", "36,641"],
          ]}
        />

        <Callout kind="warn" title="The expected result did not happen">
          The evaluation was built expecting the baselines to carry a stale
          procedure into phase 2 and execute it. They did not, and neither took
          a single unsafe action. Handed the current policy, the model notices
          that the live rule and the remembered procedure disagree, and sides
          with the rule. So the honest headline is accuracy and cost, not
          safety.
        </Callout>

        <SubSection title="What did separate them">
          <p>
            The cached-runbook arm got <em>worse</em> after the policy change,
            from 90.9% to 81.8%, and its new errors were on resource-exhaustion
            incidents that the rollback window does not apply to at all.
            Tightening one rule made it cautious about unrelated work.
          </p>
          <p>
            A predicate cannot do this. <C>rollback_window</C> carries a{" "}
            <C>when</C> clause naming the action it governs, so a restart is
            untouched by a rollback rule, structurally, on every run.
          </p>
          <p>
            Reuse also costs nothing when it happens: a guided run makes no model
            call at all. That is why Cascade&rsquo;s token total is highest here
            rather than lowest, though. When the rule change invalidated the
            runbook, everything correctly fell back to re-planning, and
            re-planning is what tokens are spent on.
          </p>
        </SubSection>

        <SubSection title="The unsafe action was a reporting defect">
          <p>
            Cascade&rsquo;s single unsafe result was an incident that was already
            resolved being recorded as remediated. Nothing was applied: the
            trajectory for that run is one step long, and it is{" "}
            <C>get_incident</C>. The planner read the state, correctly concluded
            there was nothing to do, and finished successfully, and the executor
            filed that as a remediation.
          </p>
          <p>
            The world was safe. The record was wrong, which is its own problem,
            and it is fixed: a run now counts as remediated only if a remediation
            tool returned success. The number above is left as measured, because
            the defect is the more useful artifact.
          </p>
        </SubSection>
      </Section>

      <Section title="Running it yourself">
        <p>From the backend directory, against any running stack:</p>
        <Code lang="bash">{`python -m eval.run_eval --api https://<host> --admin-token <token>`}</Code>

        <Table
          head={["Flag", "What it does"]}
          rows={[
            [<C key="a">--arm baseline</C>, "Baselines only. Executes no tasks and changes no policy."],
            [<C key="b">--arm cascade</C>, "Cascade only. Needs no model credentials locally."],
            [<C key="c">--limit N</C>, "Score the first N cases per phase. Smoke mode."],
            [<C key="d">--phase 1</C>, "One phase only."],
            [<C key="e">--keep</C>, "Do not restore the sample world afterwards."],
            [<C key="f">--dry-run</C>, "Print the plan and call nothing."],
          ]}
        />

        <Callout kind="note" title="It writes to the world it measures">
          The harness resets the demo world at the start of each phase, commits a
          real policy change, and runs real incidents. It restores the sample
          when it finishes. Point it at a stack you are willing to disturb.
        </Callout>

        <p>
          Results land in <C>eval/out/results.json</C> and{" "}
          <C>eval/out/RESULTS.md</C>. Copy the JSON to{" "}
          <C>frontend/src/data/eval-results.json</C> to publish it into this
          view.
        </p>
      </Section>

      <Section title="Trajectories">
        <p>
          The same directory produces the record of what the agents actually did,
          exported from what was stored at the time rather than written up
          afterwards:
        </p>
        <Code lang="bash">{`python -m eval.export_trajectories --api <host> --admin-token <token>`}</Code>
        <p>
          It selects one run of each shape it can find, by reading back what each
          run turned out to be: explored, reused, refused on provenance, refused
          on preconditions, or parked for a human. Shapes with no recent example
          are listed as absent rather than invented.
        </p>
      </Section>
    </>
  );
}
