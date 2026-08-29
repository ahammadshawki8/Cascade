"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Plug,
  Bot,
  Check,
  Copy,
  Loader2,
  Send,
  Trash2,
  AlertTriangle,
  ExternalLink,
  KeyRound,
} from "lucide-react";
import styles from "./ConnectionsPanel.module.css";

/**
 * Connections — outbound to a chat product, inbound from other agents.
 *
 * Both are "how Cascade talks to the rest of your stack", so they are one page
 * with two sections rather than two destinations. The page is built around one
 * primary action each: connect Slack, create a key. Everything else is a
 * consequence of having done one of those.
 */

const KIND_HELP: Record<string, { label: string; where: string; steps: string[] }> = {
  slack: {
    label: "Slack",
    where: "https://api.slack.com/messaging/webhooks",
    steps: [
      "Open api.slack.com/apps and create an app from scratch",
      "Turn on Incoming Webhooks, then Add New Webhook to Workspace",
      "Pick a channel, allow it, and copy the webhook URL",
    ],
  },
  discord: {
    label: "Discord",
    where: "https://support.discord.com/hc/en-us/articles/228383668",
    steps: [
      "Open the channel's settings, then Integrations",
      "New Webhook, then Copy Webhook URL",
      "No app to create and no admin approval needed",
    ],
  },
  webhook: {
    label: "Any webhook",
    where: "",
    steps: ["Paste any https endpoint that accepts a JSON POST"],
  },
};

interface Connection {
  connection_id: string;
  name: string;
  kind: string;
  endpoint_masked: string;
  mode: string;
  enabled: boolean;
  tool_name: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  failures: number;
  healthy: boolean;
  calls: number;
  sent: number;
  replayed: number;
}

interface ApiKey {
  key_id: string;
  name: string;
  prefix: string;
  scopes: string[];
  client: string | null;
  last_used_at: string | null;
  call_count: number;
  revoked: boolean;
}

interface Activity {
  activity_id: string;
  key_name: string;
  operation: string;
  detail: Record<string, unknown>;
  verdict: string | null;
  at: string;
}

function Copyable({ text, label }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className={styles.copy}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1600);
        } catch {
          /* clipboard blocked; the text is on screen to select by hand */
        }
      }}
    >
      {done ? <Check size={12} /> : <Copy size={12} />}
      {done ? "Copied" : label || "Copy"}
    </button>
  );
}

const relative = (iso: string | null) => {
  if (!iso) return "never";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
};

export function ConnectionsPanel({
  apiBase,
  privileged,
  refreshKey,
  onToast,
}: {
  apiBase: string;
  privileged: string;
  refreshKey: number;
  onToast: (message: string) => void;
}) {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [calls, setCalls] = useState<any[]>([]);

  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState("slack");
  const [endpoint, setEndpoint] = useState("");
  const [connName, setConnName] = useState("On-call channel");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);

  const [keyName, setKeyName] = useState("Claude Code");
  const [client, setClient] = useState("claude-code");
  const [canRun, setCanRun] = useState(false);
  const [issued, setIssued] = useState<{ key: string; name: string } | null>(null);
  const [snippet, setSnippet] = useState<any>(null);

  const load = useCallback(async () => {
    const get = async (path: string) => {
      try {
        const res = await fetch(`${apiBase}${path}`);
        return res.ok ? await res.json() : null;
      } catch {
        return null;
      }
    };
    const [c, k, a, l] = await Promise.all([
      get("/connections"),
      get("/keys"),
      get("/agent-activity?limit=12"),
      get("/connections/calls?limit=8"),
    ]);
    if (c) setConnections(c.connections ?? []);
    if (k) setKeys(k.keys ?? []);
    if (a) setActivity(a.activity ?? []);
    if (l) setCalls(l.calls ?? []);
  }, [apiBase]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // An agent calling in is the moment this page is worth looking at, and it
  // happens in another process. Polling while the page is open is the only way
  // the console reacts to it.
  useEffect(() => {
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const addConnection = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${privileged}/connections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: connName.trim() || "On-call channel",
          kind,
          endpoint: endpoint.trim(),
          tool_name: "notify_oncall",
          mode: "live",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        onToast(data.detail || "Could not add that connection.");
        return;
      }
      setEndpoint("");
      setAdding(false);
      onToast(`${data.name} connected. Send a test to check it.`);
      load();
    } catch {
      onToast("Could not reach the API.");
    } finally {
      setBusy(false);
    }
  };

  const test = async (id: string) => {
    setTesting(id);
    try {
      const res = await fetch(`${privileged}/connections/${id}/test`, { method: "POST" });
      const data = await res.json();
      onToast(
        data.delivered
          ? `Delivered in ${data.duration_ms}ms (HTTP ${data.status_code}). Check the channel.`
          : `Not delivered: ${data.error || data.note || "unknown"}`
      );
      load();
    } catch {
      onToast("Test failed to run.");
    } finally {
      setTesting(null);
    }
  };

  const setMode = async (id: string, mode: string) => {
    await fetch(`${privileged}/connections/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    load();
  };

  const remove = async (id: string) => {
    await fetch(`${privileged}/connections/${id}`, { method: "DELETE" });
    load();
  };

  const createKey = async () => {
    setBusy(true);
    try {
      const scopes = ["memory:read", "memory:write"];
      if (canRun) scopes.push("runs:write");
      const res = await fetch(`${privileged}/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: keyName.trim() || "Agent", scopes, client }),
      });
      const data = await res.json();
      if (!res.ok) {
        onToast(data.detail || "Could not create a key.");
        return;
      }
      setIssued({ key: data.key, name: data.name });
      const snip = await fetch(
        `${apiBase}/connect-snippet?client=${client}&key=${encodeURIComponent(data.key)}`
      );
      if (snip.ok) setSnippet(await snip.json());
      load();
    } catch {
      onToast("Could not reach the API.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    await fetch(`${privileged}/keys/${id}`, { method: "DELETE" });
    load();
  };

  const help = KIND_HELP[kind];
  const snippetText =
    snippet?.format === "json"
      ? JSON.stringify(snippet.snippet, null, 2)
      : snippet?.snippet ?? "";

  return (
    <div className={styles.panel}>
      {/* ------------------------------------------------------------ apps */}
      <section className={styles.section} data-tour="connections-apps">
        <header className={styles.head}>
          <Plug size={15} strokeWidth={1.9} />
          <h2 className={styles.h2}>Apps Cascade talks to</h2>
          <span className={styles.spacer} />
          {!adding && (
            <button className={styles.primary} onClick={() => setAdding(true)}>
              Connect an app
            </button>
          )}
        </header>
        <p className={styles.lead}>
          When the agent notifies on-call, the message goes here as well as into
          the demo log. Nothing is required: with no connection configured the
          engine works exactly as it does now.
        </p>

        {adding && (
          <div className={styles.form}>
            <div className={styles.kinds}>
              {Object.entries(KIND_HELP).map(([id, k]) => (
                <button
                  key={id}
                  className={`${styles.kind} ${kind === id ? styles.kindOn : ""}`}
                  onClick={() => setKind(id)}
                >
                  {k.label}
                </button>
              ))}
            </div>

            <ol className={styles.steps}>
              {help.steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
            {help.where && (
              <a className={styles.link} href={help.where} target="_blank" rel="noreferrer">
                Official instructions <ExternalLink size={11} />
              </a>
            )}

            <label className={styles.field}>
              <span className={styles.label}>Name</span>
              <input
                className={styles.input}
                value={connName}
                onChange={(e) => setConnName(e.target.value)}
                maxLength={60}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Webhook URL</span>
              <input
                className={styles.input}
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                placeholder="https://hooks.slack.com/services/..."
                spellCheck={false}
              />
              <span className={styles.hint}>
                Stored server side and never shown again. It is a credential, so
                the list below only ever displays the host and last four characters.
              </span>
            </label>

            <div className={styles.actions}>
              <button
                className={styles.primary}
                disabled={busy || !endpoint.startsWith("https://")}
                onClick={addConnection}
              >
                {busy ? "Connecting…" : "Connect"}
              </button>
              <button className={styles.ghost} onClick={() => setAdding(false)}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {connections.length === 0 && !adding && (
          <div className={styles.empty}>No apps connected yet.</div>
        )}

        {connections.map((c) => (
          <div key={c.connection_id} className={styles.row}>
            <div className={styles.rowMain}>
              <span className={styles.rowName}>{c.name}</span>
              <span className={styles.chip}>{c.kind}</span>
              <span className={styles.mono}>{c.endpoint_masked}</span>
              {!c.healthy && (
                <span className={styles.bad}>
                  <AlertTriangle size={11} /> {c.failures} failures, paused
                </span>
              )}
            </div>
            <div className={styles.rowMeta}>
              fires on <code>{c.tool_name}</code> · {c.sent} sent · {c.replayed}{" "}
              replay{c.replayed === 1 ? "" : "s"} suppressed · last ok{" "}
              {relative(c.last_ok_at)}
            </div>
            <div className={styles.rowActions}>
              <div className={styles.toggle}>
                {["live", "dry_run"].map((m) => (
                  <button
                    key={m}
                    className={`${styles.toggleOpt} ${c.mode === m ? styles.toggleOn : ""}`}
                    onClick={() => setMode(c.connection_id, m)}
                  >
                    {m === "live" ? "Live" : "Dry run"}
                  </button>
                ))}
              </div>
              <button
                className={styles.ghost}
                disabled={testing === c.connection_id}
                onClick={() => test(c.connection_id)}
              >
                {testing === c.connection_id ? (
                  <Loader2 size={12} className={styles.spin} />
                ) : (
                  <Send size={12} />
                )}
                Send test
              </button>
              <button className={styles.iconGhost} onClick={() => remove(c.connection_id)}>
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}

        {calls.length > 0 && (
          <details className={styles.details}>
            <summary>What actually went out ({calls.length})</summary>
            <table className={styles.table}>
              <tbody>
                {calls.map((c) => (
                  <tr key={c.call_id}>
                    <td className={styles.mono}>{c.connection_name ?? "—"}</td>
                    <td>
                      <span
                        className={
                          c.outcome === "sent"
                            ? styles.good
                            : c.outcome === "replayed"
                              ? styles.warn
                              : styles.dim
                        }
                      >
                        {c.outcome}
                      </span>
                    </td>
                    <td className={styles.mono}>{c.status_code ?? "—"}</td>
                    <td className={styles.dim}>{c.duration_ms ?? 0}ms</td>
                    <td className={styles.mono} title={c.idempotency_key}>
                      {String(c.idempotency_key).slice(0, 28)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className={styles.note}>
              A row marked <b>replayed</b> is the safety property working: the
              approval flow resumes a task by re-running it, and this ledger is
              what stops the second run paging anyone a second time.
            </p>
          </details>
        )}
      </section>

      {/* ---------------------------------------------------------- agents */}
      <section className={styles.section} data-tour="connections-agents">
        <header className={styles.head}>
          <Bot size={15} strokeWidth={1.9} />
          <h2 className={styles.h2}>Agents that call Cascade</h2>
          <span className={styles.spacer} />
        </header>
        <p className={styles.lead}>
          Another agent, with its own planner and its own tools, can ask one
          question here: <b>is what I remember still valid?</b> Answering needs
          no model and no execution, so it works for any agent in any framework.
        </p>

        {!issued && (
          <div className={styles.form}>
            <div className={styles.inline}>
              <label className={styles.field}>
                <span className={styles.label}>Name it</span>
                <input
                  className={styles.input}
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  maxLength={60}
                />
              </label>
              <label className={styles.field}>
                <span className={styles.label}>Where will it run</span>
                <select
                  className={styles.select}
                  value={client}
                  onChange={(e) => setClient(e.target.value)}
                >
                  <option value="claude-code">Claude Code</option>
                  <option value="claude-desktop">Claude Desktop</option>
                  <option value="cursor">Cursor</option>
                  <option value="python">Python</option>
                  <option value="http">curl / HTTP</option>
                </select>
              </label>
            </div>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={canRun}
                onChange={(e) => setCanRun(e.target.checked)}
              />
              <span>
                Also let it start incidents
                <em>
                  Off by default. Checking memory is read-only; starting a run
                  is not, and most agents only need the first.
                </em>
              </span>
            </label>
            <div className={styles.actions}>
              <button className={styles.primary} disabled={busy} onClick={createKey}>
                <KeyRound size={13} />
                {busy ? "Creating…" : "Create key"}
              </button>
            </div>
          </div>
        )}

        {issued && (
          <div className={styles.issued}>
            <div className={styles.issuedHead}>
              Key for {issued.name}
              <span className={styles.once}>shown once</span>
            </div>
            <div className={styles.secretRow}>
              <code className={styles.secret}>{issued.key}</code>
              <Copyable text={issued.key} />
            </div>

            {snippet?.setup && (
              <>
                <div className={styles.snipHead}>
                  First, download the connector (no install, no dependencies)
                  <Copyable text={snippet.setup} label="Copy command" />
                </div>
                <pre className={styles.pre}>{snippet.setup}</pre>
              </>
            )}

            {snippet && (
              <>
                <div className={styles.snipHead}>
                  {snippet.setup ? "Then paste this into" : "Paste this into"}{" "}
                  <b>{snippet.target}</b>
                  <Copyable text={snippetText} label="Copy config" />
                </div>
                <pre className={styles.pre}>{snippetText}</pre>
                {snippet.format === "json" && (
                  <p className={styles.note}>
                    Restart the editor afterwards, then ask it something like
                    <i> &ldquo;is my rollback procedure still valid?&rdquo;</i>.
                    The call shows up below within a few seconds.
                  </p>
                )}
              </>
            )}

            <button
              className={styles.ghost}
              onClick={() => {
                setIssued(null);
                setSnippet(null);
              }}
            >
              Done
            </button>
          </div>
        )}

        {keys.filter((k) => !k.revoked).map((k) => (
          <div key={k.key_id} className={styles.row}>
            <div className={styles.rowMain}>
              <span className={styles.rowName}>{k.name}</span>
              <span className={styles.mono}>{k.prefix}…</span>
              {k.call_count > 0 && <span className={styles.live}>live</span>}
            </div>
            <div className={styles.rowMeta}>
              {k.scopes.join(" · ")} · {k.call_count} call
              {k.call_count === 1 ? "" : "s"} · last seen {relative(k.last_used_at)}
            </div>
            <div className={styles.rowActions}>
              <button className={styles.ghost} onClick={() => revoke(k.key_id)}>
                Revoke
              </button>
            </div>
          </div>
        ))}

        {activity.length > 0 && (
          <div className={styles.feed}>
            <div className={styles.feedHead}>What agents have been asking</div>
            {activity.map((a) => (
              <div key={a.activity_id} className={styles.feedRow}>
                <span className={styles.feedWho}>{a.key_name}</span>
                <span className={styles.feedOp}>{a.operation}</span>
                <span
                  className={
                    a.verdict === "stale"
                      ? styles.warn
                      : a.verdict === "valid"
                        ? styles.good
                        : styles.dim
                  }
                >
                  {a.verdict ?? ""}
                </span>
                <span className={styles.feedWhen}>{relative(a.at)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
