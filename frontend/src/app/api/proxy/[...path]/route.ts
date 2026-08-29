import { NextRequest } from "next/server";

/**
 * Server-side proxy for privileged API calls.
 *
 * WHY THIS EXISTS
 * ---------------
 * The admin token used to reach the browser via `NEXT_PUBLIC_ADMIN_TOKEN`.
 * Anything prefixed `NEXT_PUBLIC_` is inlined into the client bundle at build
 * time, so the deployed site shipped its own admin credential in the page
 * source — and `06_deploy_frontend.sh` was reading it out of Secrets Manager to
 * put it there, which made a managed secret public.
 *
 * These handlers run server-side (Amplify `WEB_COMPUTE`), so the token is read
 * from a non-public env var and attached here. The browser calls a same-origin
 * path and never sees a credential.
 *
 * WHAT THIS DOES *NOT* DO
 * -----------------------
 * It stops the credential leaking. It is not access control: anyone who can
 * reach the site can still invoke these operations through the proxy, because
 * there is no login. That is acceptable for a public demo where a judge is
 * meant to change policy and reset the world — but it must not be mistaken for
 * authentication. To gate the demo itself, enable Amplify basic auth
 * (`06_deploy_frontend.sh --protect`), or put Cognito/OIDC in front of
 * CloudFront and resolve `Principal` from a verified JWT.
 */

const API_ROOT =
  process.env.CASCADE_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000";

/**
 * Runtime first, build-time inlined value second (see next.config.ts).
 *
 * Amplify console variables reach the build but not the SSR runtime, so on the
 * deployed site `process.env.ADMIN_TOKEN` was undefined and this fell through
 * to `dev-admin-token`. The backend rejects that token, so every privileged
 * call returned `403 invalid token` — reset, policy commits and approvals were
 * all dead on the deployed demo while working perfectly in local dev.
 *
 * Trimmed on both paths: a console-pasted secret can carry trailing
 * whitespace.
 */
// `||`, not `??`: an unset Amplify variable inlines as an empty string, which
// `??` would happily accept as the token.
const ADMIN_TOKEN = (
  process.env.ADMIN_TOKEN ||
  process.env.BUILD_ADMIN_TOKEN ||
  "dev-admin-token"
).trim();

/**
 * Explicit allowlist. Without it this is an open relay that grants admin
 * rights to *every* backend route, which would be a worse hole than the one
 * it replaces. Patterns are anchored and match the full path.
 */
const UUID = "[0-9a-fA-F-]{36}";

const ALLOWED: Record<string, RegExp[]> = {
  GET: [
    /^admin\/verify-index$/,
    /^admin\/smoke$/,
    /^generalize\/candidates$/,
  ],
  POST: [
    /^admin\/reset$/,
    // Create a rule, and change one. The second pattern must not be widened to
    // match sub-paths: `rules/{key}` is the cascade, and anything else under a
    // rule key is a different operation that has to be listed on its own.
    /^rules$/,
    /^rules\/[A-Za-z0-9._-]+$/,
    /^rules\/[A-Za-z0-9._-]+\/definition$/,
    /^procedures$/,
    /^connections$/,
    new RegExp(`^connections\\/${UUID}\\/test$`),
    /^keys$/,
    new RegExp(`^approvals\\/${UUID}\\/resolve$`),
    new RegExp(`^playbooks\\/${UUID}\\/relearn$`),
    /^insights\/scan$/,
    new RegExp(`^insights\\/${UUID}\\/dismiss$`),
    /^generalize$/,
  ],
  PATCH: [new RegExp(`^connections\\/${UUID}$`)],
  DELETE: [
    new RegExp(`^connections\\/${UUID}$`),
    new RegExp(`^keys\\/${UUID}$`),
  ],
};

function isAllowed(method: string, path: string): boolean {
  return (ALLOWED[method] ?? []).some((pattern) => pattern.test(path));
}

async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  // Next 16: route params are a Promise and must be awaited.
  const { path: segments } = await context.params;
  const path = (segments ?? []).join("/");

  if (!isAllowed(request.method, path)) {
    return Response.json(
      { error: `not proxyable: ${request.method} /${path}` },
      { status: 403 }
    );
  }

  const search = request.nextUrl.search ?? "";
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();

  try {
    const upstream = await fetch(`${API_ROOT}/api/${path}${search}`, {
      method: request.method,
      headers: {
        "content-type":
          request.headers.get("content-type") ?? "application/json",
        // Attached here, never in the browser.
        "x-admin-token": ADMIN_TOKEN,
      },
      body: body && body.length > 0 ? body : undefined,
      cache: "no-store",
    });

    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (error) {
    return Response.json(
      { error: `upstream unreachable: ${(error as Error).message}` },
      { status: 502 }
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;

// Never prerender or cache: every call is a privileged mutation or a live check.
export const dynamic = "force-dynamic";
