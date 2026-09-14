/**
 * Browser calls to the hosted API through same-origin `/ardoise-api`.
 * Never put Stripe / JWT secrets here.
 */

import { API_BASE } from "./saas-otp";
import {
  NetworkError,
  SessionRequiredError,
  detailOf,
  isRecord,
} from "./saas-errors";

async function parse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export async function apiGet<T>(path: string, accessToken: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    });
  } catch {
    throw new NetworkError();
  }
  const payload = await parse(response);
  if (response.status === 401) {
    throw new SessionRequiredError();
  }
  if (!response.ok) {
    throw new Error(detailOf(payload, `Request failed (${response.status})`));
  }
  return payload as T;
}

export async function apiPost<T>(
  path: string,
  accessToken: string,
  body: unknown = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new NetworkError();
  }
  const payload = await parse(response);
  if (response.status === 401) {
    throw new SessionRequiredError();
  }
  if (!response.ok) {
    throw new Error(detailOf(payload, `Request failed (${response.status})`));
  }
  return payload as T;
}

export type MeResponse = {
  account: {
    id: string;
    email: string | null;
    plan: string;
    invoice_grade: boolean;
  };
};

export type UsageStatus = {
  month: string;
  entries: number;
  month_entries: number;
  cost_usd: number;
  estimated_usd: number;
  billed_usd: number;
  invoice_grade: boolean;
  connected: boolean;
  cursor_join_sessions?: number;
  notes?: string[];
  section_a?: Array<Record<string, unknown>>;
  by_project?: Array<{
    project: string;
    entries: number;
    cost_usd: number;
    allocated_billed_usd: number | null;
  }>;
  by_model?: Array<{
    model: string;
    entries: number;
    cost_usd: number;
  }>;
  by_person?: Array<{
    person: string;
    entries: number;
    cost_usd: number;
  }>;
  by_agent?: Array<{
    agent: string;
    entries: number;
    cost_usd: number;
  }>;
};

export type StatementResponse = {
  month: string;
  invoice_grade: boolean;
  markdown: string;
  csv: string;
  document?: import("@/components/statement-document").StatementDocument;
  summary?: UsageStatus;
};

export type CliTokenResponse = {
  token: string;
  id: string;
};
