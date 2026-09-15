/**
 * Hosted statement chrome lock (#58): Estimate·Billed, Print statement,
 * and the copy-totals whisper. Empty months stay sparse — no invented rows.
 */

import type { StatementDocument } from "../components/statement-document";
import type { StatementResponse } from "./saas-api";

function money(value: number | undefined, places = 2): string {
  const n = Number(value || 0);
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  })}`;
}

export const STATEMENT_COPY = {
  print: "Print statement",
  copyTotals: "Copy totals into your invoice",
  copied: "Copied",
  estimate: "Estimate",
  billed: "Billed",
  emptyTitle: "Nothing to print yet",
  printDisabledHint: "Nothing to print until rows sync",
} as const;

export function isBilledGrade(
  data: StatementResponse | null | undefined,
): boolean {
  if (!data) {
    return false;
  }
  const document = data.document;
  if (document && typeof document.invoice_grade === "boolean") {
    return document.invoice_grade;
  }
  return Boolean(data.invoice_grade);
}

export function isEmptyStatement(
  data: StatementResponse | null | undefined,
): boolean {
  if (!data) {
    return false;
  }
  const groups = data.document?.groups ?? [];
  if (groups.length > 0) {
    return false;
  }
  const entries =
    data.summary?.month_entries ??
    (typeof data.document?.entries === "number" ? data.document.entries : undefined);
  if (typeof entries === "number") {
    return entries === 0;
  }
  return Number(data.document?.total_usd || 0) === 0;
}

export function hasPrintableRows(
  data: StatementResponse | null | undefined,
): boolean {
  return Boolean(data) && !isEmptyStatement(data);
}

export function copyPayload(
  data: StatementResponse,
  month: string,
): string {
  const billed = isBilledGrade(data);
  const total = money(data.document?.total_usd, billed ? 2 : 4);
  return `Statement ${month} · ${billed ? STATEMENT_COPY.billed : STATEMENT_COPY.estimate} · Total ${total}`;
}

export function emptyDocument(month: string): StatementDocument {
  return {
    title: "Statement",
    number: month,
    invoice_grade: false,
    total_usd: 0,
    groups: [],
    entries: 0,
    month,
  };
}
