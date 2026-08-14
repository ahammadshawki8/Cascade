#!/usr/bin/env node
/**
 * Cascade MCP server — lets any MCP-capable agent ask whether what it
 * remembers is still valid.
 *
 * Zero dependencies, on purpose. "Plug and play" cannot mean "first run npm
 * install and hope the lockfile resolves": the whole value of this file is that
 * someone pastes four lines into a config, restarts their editor, and it works.
 * Node 18+ has fetch and that is all this needs.
 *
 *   CASCADE_URL   where the API lives      (default http://127.0.0.1:8000)
 *   CASCADE_KEY   an API key, csk_...      (create one under Connections)
 *
 * Speaks newline-delimited JSON-RPC 2.0 over stdio, which is the MCP stdio
 * transport.
 */

const API = (process.env.CASCADE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const KEY = process.env.CASCADE_KEY || "";
const PROTOCOL_FALLBACK = "2024-11-05";

const TOOLS = [
  {
    name: "check_memory",
    description:
      "Check whether a remembered procedure is still valid under current policy. " +
      "Give it the policy rules and versions the procedure was written against, " +
      "and it reports which of them have changed since. Call this BEFORE acting " +
      "on any procedure you recall from earlier, especially one that touches " +
      "production.",
    inputSchema: {
      type: "object",
      properties: {
        citations: {
          type: "array",
          description: "The rules this procedure was written against.",
          items: {
            type: "object",
            properties: {
              rule_key: { type: "string" },
              rule_version: { type: "integer" },
            },
            required: ["rule_key", "rule_version"],
          },
        },
        procedure_id: {
          type: "string",
          description:
            "Alternatively, the id of a procedure Cascade already holds. It " +
            "carries its own provenance, so no citations are needed.",
        },
      },
    },
  },
  {
    name: "list_policy",
    description:
      "List the policy rules that exist, with the version to cite for each. Use " +
      "this to discover what a procedure can be grounded in.",
    inputSchema: {
      type: "object",
      properties: {
        domain: { type: "string", description: "Defaults to 'incident'." },
      },
    },
  },
  {
    name: "find_procedures",
    description:
      "Search the governed procedure library. Each result says whether it is " +
      "still valid and which rules have moved underneath it.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "What you are trying to do." },
        limit: { type: "integer" },
      },
    },
  },
  {
    name: "register_procedure",
    description:
      "Hand Cascade a procedure to govern. You keep executing it however you " +
      "like; what you gain is that its citations are watched, so a later " +
      "check_memory can tell you it has expired.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string" },
        goal: { type: "string" },
        steps: { type: "array", items: { type: "string" } },
        citations: {
          type: "array",
          items: {
            type: "object",
            properties: {
              rule_key: { type: "string" },
              rule_version: { type: "integer" },
            },
            required: ["rule_key", "rule_version"],
          },
        },
      },
      required: ["name", "goal", "citations"],
    },
  },
];

async function call(path, { method = "GET", body } = {}) {
  if (!KEY) {
    throw new Error(
      "No CASCADE_KEY is set. Create an API key under Connections in the " +
        "Cascade console, then put it in this server's env as CASCADE_KEY."
    );
  }
  const response = await fetch(`${API}/api${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${KEY}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await response.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = { raw: text };
  }
  if (!response.ok) {
    // Surfaced as the tool's own message rather than a transport error, so the
    // calling model can read it and correct itself instead of just failing.
    throw new Error(parsed.detail || `Cascade returned HTTP ${response.status}`);
  }
  return parsed;
}

async function runTool(name, args = {}) {
  if (name === "check_memory") {
    const result = await call("/memory/check", { method: "POST", body: args });
    const lines = [result.summary];
    for (const s of result.stale || []) {
      lines.push(
        `  - ${s.rule_key}: v${s.pinned_version} -> v${s.head_version}` +
          (s.what_changed ? ` (${s.what_changed})` : "") +
          (s.changed_by ? `, changed by ${s.changed_by}` : "")
      );
      if (s.rule_now) lines.push(`    now reads: ${s.rule_now}`);
    }
    for (const key of result.unknown_rules || []) {
      lines.push(`  - ${key}: this rule no longer exists`);
    }
    return lines.join("\n");
  }

  if (name === "list_policy") {
    const result = await call(
      `/memory/rules?domain=${encodeURIComponent(args.domain || "incident")}`
    );
    return (result.rules || [])
      .map(
        (r) =>
          `${r.rule_key} (v${r.version}, ${r.enforcement})\n  ${r.body}\n` +
          `  params: ${JSON.stringify(r.params)}`
      )
      .join("\n\n");
  }

  if (name === "find_procedures") {
    const params = new URLSearchParams();
    if (args.query) params.set("q_", args.query);
    if (args.limit) params.set("limit", String(args.limit));
    const result = await call(`/memory/procedures?${params}`);
    if (!(result.procedures || []).length) return "No procedures matched.";
    return result.procedures
      .map((p) => {
        const status = p.valid
          ? "VALID"
          : `STALE (${(p.stale_rules || []).join(", ")})`;
        return (
          `${p.name} [${status}]\n  id: ${p.procedure_id}\n  goal: ${p.goal || "-"}\n` +
          `  cites: ${(p.citations || [])
            .map((c) => `${c.rule_key} v${c.rule_version}`)
            .join(", ")}`
        );
      })
      .join("\n\n");
  }

  if (name === "register_procedure") {
    const result = await call("/memory/procedures", { method: "POST", body: args });
    return (
      `Registered "${result.name}" as ${result.procedure_id}. ` +
      `It now goes stale automatically when any of its cited rules change.`
    );
  }

  throw new Error(`Unknown tool: ${name}`);
}

// --- JSON-RPC plumbing -----------------------------------------------------

function send(message) {
  process.stdout.write(JSON.stringify(message) + "\n");
}

function reply(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function fail(id, message) {
  send({ jsonrpc: "2.0", id, error: { code: -32000, message } });
}

async function handle(request) {
  const { id, method, params } = request;

  // Notifications carry no id and must never be answered.
  if (id === undefined || id === null) return;

  if (method === "initialize") {
    reply(id, {
      protocolVersion: params?.protocolVersion || PROTOCOL_FALLBACK,
      capabilities: { tools: {} },
      serverInfo: { name: "cascade", version: "1.0.0" },
    });
    return;
  }

  if (method === "tools/list") {
    reply(id, { tools: TOOLS });
    return;
  }

  if (method === "tools/call") {
    try {
      const text = await runTool(params?.name, params?.arguments || {});
      reply(id, { content: [{ type: "text", text }] });
    } catch (err) {
      // isError, not a protocol error: the model should see what went wrong.
      reply(id, {
        content: [{ type: "text", text: `Cascade error: ${err.message}` }],
        isError: true,
      });
    }
    return;
  }

  if (method === "ping") {
    reply(id, {});
    return;
  }

  fail(id, `Unsupported method: ${method}`);
}

let buffer = "";
// Requests still awaiting a network round trip. Exiting the moment stdin closes
// would drop whatever is in flight, which silently truncates the last answer of
// any piped session and would lose a genuine reply if a client ever closed its
// end early.
let inFlight = 0;
let stdinClosed = false;

function maybeExit() {
  if (stdinClosed && inFlight === 0) process.exit(0);
}

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let newline;
  while ((newline = buffer.indexOf("\n")) !== -1) {
    const line = buffer.slice(0, newline).trim();
    buffer = buffer.slice(newline + 1);
    if (!line) continue;
    let request;
    try {
      request = JSON.parse(line);
    } catch {
      continue; // a partial or malformed frame is not worth killing the server
    }
    inFlight += 1;
    handle(request)
      .catch((err) => {
        if (request?.id !== undefined && request?.id !== null) {
          fail(request.id, err.message);
        }
      })
      .finally(() => {
        inFlight -= 1;
        maybeExit();
      });
  }
});

process.stdin.on("end", () => {
  stdinClosed = true;
  maybeExit();
});
