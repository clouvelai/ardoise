/**
 * Stripe Checkout stays on apps/api. This file only POSTs plan + Bearer JWT
 * through the same-origin `/ardoise-api` proxy. Never put STRIPE_SECRET_KEY /
 * STRIPE_WEBHOOK_SECRET / price IDs here.
 */

import { API_BASE } from "./saas-otp";
import {
  COPY,
  NetworkError,
  SessionRequiredError,
  detailOf,
  isRecord,
  sparseMessage,
} from "./saas-errors";

export type PaidPlan = "team" | "business";

export class BillingNotWiredError extends Error {
  readonly code = "BILLING_NOT_WIRED" as const;

  constructor(message = COPY.notWired) {
    super(message);
    this.name = "BillingNotWiredError";
  }
}

export type CheckoutResult = {
  url: string;
  mock: boolean;
  plan: PaidPlan;
};

export async function startCheckout(
  plan: PaidPlan,
  accessToken: string,
): Promise<CheckoutResult> {
  if (!accessToken) {
    throw new SessionRequiredError();
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/v1/billing/checkout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        plan,
        success_url: `${window.location.origin}/billing/success`,
        cancel_url: `${window.location.origin}/billing/cancel`,
      }),
      cache: "no-store",
    });
  } catch {
    throw new NetworkError();
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (response.status === 404 || response.status === 501) {
    throw new BillingNotWiredError();
  }
  if (response.status === 401) {
    throw new SessionRequiredError();
  }
  if (!response.ok) {
    throw new Error(detailOf(payload, `Checkout failed (${response.status})`));
  }
  if (!isRecord(payload) || typeof payload.url !== "string" || !payload.url) {
    throw new BillingNotWiredError();
  }

  return {
    url: payload.url,
    mock: payload.mock === true,
    plan: payload.plan === "business" ? "business" : "team",
  };
}

export function isBillingNotWired(
  error: unknown,
): error is BillingNotWiredError {
  return error instanceof BillingNotWiredError;
}

export function isPaidPlan(value: string | null | undefined): value is PaidPlan {
  return value === "team" || value === "business";
}

export function billingMessage(error: unknown): string {
  if (isBillingNotWired(error)) {
    return COPY.notWired;
  }
  return sparseMessage(error);
}
