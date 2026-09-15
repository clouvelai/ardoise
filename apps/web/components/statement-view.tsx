"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { ConnectLaptopSteps } from "@/components/connect-laptop";
import {
  GradeBadge,
  StatementDocumentView,
} from "@/components/statement-document";
import { apiGet, type StatementResponse } from "@/lib/saas-api";
import { getSession } from "@/lib/saas-session";
import { sparseMessage } from "@/lib/saas-errors";
import {
  STATEMENT_COPY,
  copyPayload,
  hasPrintableRows,
  isBilledGrade,
  isEmptyStatement,
} from "@/lib/statement-chrome";

export function StatementWorkspace({
  month,
  onMonthChange,
  data,
  error,
  copied,
  onCopy,
  onPrint,
}: {
  month: string;
  onMonthChange?: (month: string) => void;
  data: StatementResponse | null;
  error?: string | null;
  copied: boolean;
  onCopy: () => void;
  onPrint: () => void;
}) {
  const billed = isBilledGrade(data);
  const printable = hasPrintableRows(data);
  const empty = isEmptyStatement(data);

  return (
    <>
      <div className="print-hide flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.22em] text-muted/80 uppercase">
            Statement
          </p>
          <h1 className="mt-2 text-[2.1rem] font-bold tracking-[-0.04em] text-ink">
            {month}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
            <GradeBadge billed={billed} />
            <button
              type="button"
              onClick={onCopy}
              disabled={!data}
              className="text-[13px] text-muted transition hover:text-ink disabled:cursor-default disabled:hover:text-muted"
            >
              {copied ? STATEMENT_COPY.copied : STATEMENT_COPY.copyTotals}
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-[13px] text-muted">
            Month
            <input
              type="month"
              value={month}
              onChange={(event) => onMonthChange?.(event.target.value)}
              className="ml-2 rounded-full border border-black/[0.06] bg-white px-3 py-1.5 text-[14px] text-ink"
            />
          </label>
          <button
            type="button"
            onClick={onPrint}
            disabled={!printable}
            title={printable ? undefined : STATEMENT_COPY.printDisabledHint}
            className={
              printable
                ? "rounded-full bg-grape px-4 py-2 text-[13px] font-semibold text-white shadow-[0_8px_18px_rgba(124,92,255,0.22)] transition hover:bg-grape-deep"
                : "cursor-not-allowed rounded-full bg-lavender px-4 py-2 text-[13px] font-semibold text-grape-ink/70 ring-1 ring-grape/15"
            }
          >
            {STATEMENT_COPY.print}
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className="mt-8 text-[15px] text-grape-ink">
          {error}
        </p>
      ) : null}
      {empty && !error ? (
        <section
          aria-labelledby="statement-empty-title"
          className="relative mt-10 overflow-hidden rounded-[28px] bg-lavender px-8 py-12 ring-1 ring-grape/15"
        >
          <div
            aria-hidden
            className="pointer-events-none absolute -top-20 -right-16 h-56 w-56 rounded-full bg-grape/12 blur-2xl"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-24 left-8 h-48 w-48 rounded-full bg-white/55 blur-2xl"
          />
          <div className="relative max-w-lg">
            <h2
              id="statement-empty-title"
              className="text-[1.45rem] font-semibold tracking-tight text-ink"
            >
              {STATEMENT_COPY.emptyTitle}
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              No synced rows this month. Connect this laptop, then{" "}
              <code className="text-[13px] text-ink/80">ardoise sync</code>.
              Print statement stays ready — it will not invent an estimate.
            </p>
            <ConnectLaptopSteps />
          </div>
        </section>
      ) : null}
      {printable && data?.document ? (
        <StatementDocumentView document={data.document} />
      ) : printable && data ? (
        <pre className="mt-8 overflow-x-auto whitespace-pre-wrap rounded-[24px] bg-white px-6 py-5 text-[13px] leading-relaxed text-ink/80 ring-1 ring-black/[0.04]">
          {data.markdown}
        </pre>
      ) : null}
    </>
  );
}

export function StatementView() {
  const [data, setData] = useState<StatementResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
  });

  useEffect(() => {
    const session = getSession();
    if (!session) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const payload = await apiGet<StatementResponse>(
          `/v1/usage/statement?month=${encodeURIComponent(month)}`,
          session.accessToken,
        );
        if (!cancelled) {
          setData(payload);
          setError(null);
          setCopied(false);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(sparseMessage(caught));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [month]);

  async function copyTotals() {
    if (!data) {
      return;
    }
    const text = copyPayload(data, month);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <AppShell>
      <StatementWorkspace
        month={month}
        onMonthChange={setMonth}
        data={data}
        error={error}
        copied={copied}
        onCopy={copyTotals}
        onPrint={() => window.print()}
      />
    </AppShell>
  );
}
