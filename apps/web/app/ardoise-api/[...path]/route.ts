/**
 * Same-origin proxy to the public Railway API.
 * Allow-listed paths only — no webhook, no secrets, no body logging.
 */

import { API_UPSTREAM } from "@/lib/saas-otp";

export const dynamic = "force-dynamic";

const ALLOWED_POST = new Set([
  "v1/auth/otp",
  "v1/auth/otp/verify",
  "v1/billing/checkout",
  "v1/cli/tokens",
  "v1/usage/sync",
  "v1/invoices",
]);

const ALLOWED_GET = new Set([
  "v1/me",
  "v1/usage/status",
  "v1/usage/statement",
]);

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: Request, context: RouteContext, method: "GET" | "POST") {
  const { path } = await context.params;
  const joined = path.join("/");
  const allowed = method === "GET" ? ALLOWED_GET : ALLOWED_POST;
  if (!allowed.has(joined)) {
    return Response.json({ detail: "not found" }, { status: 404 });
  }

  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  if (authorization) {
    headers.set("Authorization", authorization);
  }
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  } else if (method === "POST") {
    headers.set("Content-Type", "application/json");
  }

  const incoming = new URL(request.url);
  const target = `${API_UPSTREAM}/${joined}${incoming.search}`;
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body: method === "POST" ? await request.text() : undefined,
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

export async function GET(request: Request, context: RouteContext) {
  return proxy(request, context, "GET");
}

export async function POST(request: Request, context: RouteContext) {
  return proxy(request, context, "POST");
}
