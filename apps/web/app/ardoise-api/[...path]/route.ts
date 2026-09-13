/**
 * Same-origin proxy to the public Railway API.
 * Allow-listed POSTs only — no webhook, no secrets, no body logging.
 */

import { API_UPSTREAM } from "@/lib/saas-otp";

export const dynamic = "force-dynamic";

const ALLOWED = new Set([
  "v1/auth/otp",
  "v1/auth/otp/verify",
  "v1/billing/checkout",
]);

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { path } = await context.params;
  const joined = path.join("/");
  if (!ALLOWED.has(joined)) {
    return Response.json({ detail: "not found" }, { status: 404 });
  }

  const headers = new Headers({ "Content-Type": "application/json" });
  const authorization = request.headers.get("authorization");
  if (authorization) {
    headers.set("Authorization", authorization);
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_UPSTREAM}/${joined}`, {
      method: "POST",
      headers,
      body: await request.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: "Can’t reach Ardoise right now." },
      { status: 502 },
    );
  }

  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") || "application/json",
    },
  });
}
