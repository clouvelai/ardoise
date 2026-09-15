/**
 * Hosted statement chrome lock: Estimate·Billed, Print statement,
 * and the copy-totals path. Empty months stay sparse — no invented rows.
 * Pro copy appears only when paste-bill would upgrade Estimate → Billed.
 */

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
  downloadCsv: "Download CSV",
  copied: "Copied",
  estimate: "Estimate",
  billed: "Billed",
  emptyTitle: "Nothing to print yet",
  printDisabledHint: "Nothing to print until rows sync",
  helper: "Attach the schedule. Keep your invoice in the tool you already use.",
  proNudge:
    "Paste a vendor bill on Pro to upgrade this Estimate to Billed.",
  pasteHook: "Paste a vendor bill to upgrade this Estimate to Billed.",
} as const;

export type StatementChromeContext = {
  data: StatementResponse | null | undefined;
  /** Account can paste vendor bills (hosted Pro+). */
  canPasteBill?: boolean;
};

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

/** Estimate with rows: a pasted vendor bill would flip the badge to Billed. */
export function canUpgradeToBilled(
  data: StatementResponse | null | undefined,
): boolean {
  return hasPrintableRows(data) && !isBilledGrade(data);
}

/** One-line Pro nudge only when paste-bill is locked behind Pro. */
export function shouldNudgePro(ctx: StatementChromeContext): boolean {
  return canUpgradeToBilled(ctx.data) && ctx.canPasteBill === false;
}

/** Quiet paste hook for Pro+ Estimate months (no form until Craie ships it). */
export function shouldShowPasteHook(ctx: StatementChromeContext): boolean {
  return canUpgradeToBilled(ctx.data) && ctx.canPasteBill === true;
}

export function monthLabel(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month.trim());
  if (!match) {
    return month;
  }
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1));
  return date.toLocaleString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function csvFilename(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month.trim());
  return match ? `ardoise-${match[1]}-${match[2]}.csv` : "ardoise-statement.csv";
}

export function copyPayload(
  data: StatementResponse,
  month: string,
): string {
  const billed = isBilledGrade(data);
  const total = money(data.document?.total_usd, billed ? 2 : 4);
  return `Statement ${month} · ${billed ? STATEMENT_COPY.billed : STATEMENT_COPY.estimate} · Total ${total}`;
}
