"use client";

import { useState } from "react";
import styles from "./StepDetail.module.css";

/**
 * What one tool call actually decided, and on what evidence.
 *
 * The step list says the agent asked whether it was allowed to roll back. It
 * does not say what came back, which is where every interesting thing lives:
 * the exact rule versions the answer was computed against, and — when the
 * answer was no — the specific clause that did not hold. That is the whole
 * difference between "it refused" and "it refused because the deploy was 30.2h
 * ago and the window is 4h".
 *
 * Everything here is read out of the tool's own return value. Nothing is
 * inferred, because the point of the panel is to be checkable against the raw
 * call printed underneath it.
 */

type Bag = Record<string, unknown>;

const isBag = (v: unknown): v is Bag =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const str = (v: unknown): string => (v == null ? "" : String(v));

export function StepDetail({
  tool,
  args,
  output,
}: {
  tool: string;
  args: Bag;
  output?: unknown;
}) {
  const [rawOpen, setRawOpen] = useState(false);
  const out = isBag(output) ? output : null;

  return (
    <div className={styles.detail}>
      {out?.error ? (
        <Verdict bad>
          The call failed: {str(out.error)}
          {out.message ? ` — ${str(out.message)}` : ""}
        </Verdict>
      ) : (
        <Body tool={tool} args={args} out={out} />
      )}

      {!out && (
        <div className={styles.note}>
          This run was recorded before step detail was retained, so only the call
          itself survives.
        </div>
      )}

      <button className={styles.rawToggle} onClick={() => setRawOpen((o) => !o)}>
        {rawOpen ? "hide the raw call" : "show the raw call"}
      </button>
      {rawOpen && (
        <pre className={styles.raw}>
          {JSON.stringify({ tool, args, output: output ?? null }, null, 2)}
        </pre>
      )}
    </div>
  );
}

function Body({ tool, args, out }: { tool: string; args: Bag; out: Bag | null }) {
  if (!out) return null;

  switch (tool) {
    case "check_remediation_eligibility": {
      const eligible = out.eligible === true;
      const reasons = Array.isArray(out.reasons) ? out.reasons.map(str) : [];
      const versions = isBag(out.rule_versions_used) ? out.rule_versions_used : {};
      return (
        <>
          <Verdict bad={!eligible}>
            {eligible
              ? `Policy permits ${str(args.action) || "this action"} on ${str(args.incident_id)}.`
              : `Policy refuses ${str(args.action) || "this action"} on ${str(args.incident_id)}.`}
          </Verdict>

          {reasons.length > 0 && (
            <Section title="The clauses that did not hold">
              {reasons.map((r, i) => (
                <div key={i} className={styles.reason}>
                  {r}
                </div>
              ))}
            </Section>
          )}

          {Object.keys(versions).length > 0 && (
            <Section title="Decided against these exact rule versions">
              <div className={styles.chips}>
                {Object.entries(versions).map(([key, v]) => (
                  <span key={key} className={styles.chip}>
                    {key} <b>v{str(v)}</b>
                  </span>
                ))}
              </div>
              <div className={styles.note}>
                These become the runbook&rsquo;s provenance. When any of them moves
                past the version recorded here, the runbook is refused rather than
                replayed.
              </div>
            </Section>
          )}
        </>
      );
    }

    case "get_incident": {
      const rows: [string, string][] = [
        ["kind", str(out.kind)],
        ["severity", str(out.severity)],
        ["service", `${str(out.service_name)} (tier ${str(out.service_tier)})`],
        ["state", str(out.state)],
      ];
      if (out.deploy_timestamp) rows.push(["deployed", str(out.deploy_timestamp)]);
      if (out.error_rate != null) rows.push(["error rate", `${str(out.error_rate)}%`]);
      if (out.cpu_usage != null) rows.push(["cpu", `${str(out.cpu_usage)}%`]);
      return (
        <>
          <Verdict>Read the report for {str(out.incident_id)}.</Verdict>
          <Section title="What it says">
            <Facts rows={rows} />
          </Section>
          <div className={styles.note}>
            Everything the agent knows about the incident comes from here. Tier and
            deploy time are what the policy gates are evaluated against.
          </div>
        </>
      );
    }

    case "get_rules": {
      const rules = Array.isArray(out.rules) ? out.rules : [];
      return (
        <>
          <Verdict>Fetched {rules.length} rule(s) at their current version.</Verdict>
          <Section title="Policy as it stands right now">
            {rules.map((r, i) => {
              const rule = isBag(r) ? r : {};
              return (
                <div key={i} className={styles.rule}>
                  <span className={styles.ruleKey}>
                    {str(rule.rule_key)} <b>v{str(rule.version)}</b>
                  </span>
                  {isBag(rule.params) && (
                    <span className={styles.ruleParams}>
                      {Object.entries(rule.params)
                        .map(([k, v]) => `${k}=${str(v)}`)
                        .join("  ")}
                    </span>
                  )}
                </div>
              );
            })}
          </Section>
          <div className={styles.note}>
            Head versions only. A runbook compiled from this run is pinned to the
            versions listed here, which is what lets it go stale later.
          </div>
        </>
      );
    }

    case "apply_remediation": {
      const replay = out.note === "idempotent_replay";
      return (
        <>
          <Verdict bad={out.success === false}>
            {replay
              ? "Already applied. The original action was returned instead of acting a second time."
              : `Applied ${str(out.action) || str(args.action)} to ${str(args.incident_id)}.`}
          </Verdict>
          <Section title="Result">
            <Facts
              rows={[
                ["outcome", str(out.outcome)],
                ["action id", str(out.action_id)],
                ...(out.incident_state
                  ? ([["incident now", str(out.incident_state)]] as [string, string][])
                  : []),
              ]}
            />
          </Section>
          {replay && (
            <div className={styles.note}>
              Side-effecting steps carry a key of task and step index, so a replay
              after an interrupt or an approval collides with the original and is
              refused. This is what makes resuming a parked task safe.
            </div>
          )}
        </>
      );
    }

    case "notify_oncall":
      return (
        <>
          <Verdict>Paged the on-call engineer.</Verdict>
          {Boolean(args.message) && (
            <Section title="Message sent">
              <div className={styles.message}>{str(args.message)}</div>
            </Section>
          )}
        </>
      );

    default:
      return (
        <Section title="Returned">
          <Facts
            rows={Object.entries(out)
              .slice(0, 8)
              .map(([k, v]) => [k, str(v)] as [string, string])}
          />
        </Section>
      );
  }
}

function Verdict({ children, bad }: { children: React.ReactNode; bad?: boolean }) {
  return (
    <div className={`${styles.verdict} ${bad ? styles.verdictBad : ""}`}>{children}</div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      {children}
    </div>
  );
}

function Facts({ rows }: { rows: [string, string][] }) {
  return (
    <div className={styles.facts}>
      {rows
        .filter(([, v]) => v !== "")
        .map(([k, v]) => (
          <div key={k} className={styles.fact}>
            <span className={styles.factKey}>{k}</span>
            <span className={styles.factValue}>{v}</span>
          </div>
        ))}
    </div>
  );
}
