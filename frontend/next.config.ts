import type { NextConfig } from "next";

/**
 * Amplify's console environment variables are available to the *build*, not to
 * the SSR runtime. The privileged proxy route reads `process.env.ADMIN_TOKEN`
 * at request time, found nothing there, and silently fell back to
 * `dev-admin-token` — so every privileged call on the deployed site came back
 * `403 invalid token`, which took out reset, policy commits and approvals.
 *
 * `env` inlines the value at build time. It only reaches code that actually
 * references it, and the sole reference is the proxy route handler, which is
 * server-only — so this lands in `.next/server/`, never in `.next/static/`.
 * That boundary is the whole reason the proxy exists, so it is worth
 * re-checking after any change here:
 *
 *     grep -rl "$ADMIN_TOKEN" .next/static/   # must find nothing
 *
 * Trimmed because a value pasted into the Amplify console can carry trailing
 * whitespace, which fails auth in a way that reads as a wrong token rather
 * than a padded one.
 *
 * Deliberately named apart from ADMIN_TOKEN so the runtime variable still wins
 * when the platform does provide one — see the proxy route.
 */
const nextConfig: NextConfig = {
  env: {
    BUILD_ADMIN_TOKEN: (process.env.ADMIN_TOKEN ?? "").trim(),
  },
};

export default nextConfig;
