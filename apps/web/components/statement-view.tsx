"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { ConnectLaptopSteps } from "@/components/connect-laptop";
import {
  GradeBadge,
  StatementDocumentView,
} from "@/components/statement-document";
import { apiGet, type MeResponse, type StatementResponse } from "@/lib/saas-api";
import { getSession } from "@/lib/saas-session";
import { sparseMessage } from "@/lib/saas-errors";
import {
  STATEMENT_COPY,
  copyPayload,
  csvFilename,
  hasPrintableRows,
  isBilledGrade,
  isEmptyStatement,
  monthLabel,
  shouldNudgePro,
  shouldShowPasteHook,
} from "@/lib/statement-chrome";

export function StatementWorkspace({
  month,
  onMonthChange,
  data,
  error,
  copied,
  onCopy,
  onPrint,
  onDownloadCsv,
  canPasteBill,
}: {
  month: string;
  onMonthChange?: (month: string) => void;
  data: StatementResponse | null;
  error?: string | null;
  copied: boolean;
  onCopy: () => void;
  onPrint: () => void;
  onDownloadCsv: () => void;
  canPasteBill?: boolean;
}) {
  const billed = isBilledGrade(data);
  const printable = hasPrintableRows(data);
  const empty = isEmptyStatement(data);
  const chrome = { data, canPasteBill };
  const nudgePro = shouldNudgePro(chrome);
  const pasteHook = shouldShowPasteHook(chrome);

  return (
    <>
      <div className="print-hide">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div className="min-w-0 max-w-xl">
            <p className="text-[11px] font-semibold tracking-[0.22em] text-muted/80 uppercase">
              Statement
            </p>
            <h1 className="mt-2 text-[2.1rem] font-bold tracking-[-0.04em] text-ink">
              {monthLabel(month)}
            </h1>
            <p className="mt-3 max-w-md text-[15px] leading-relaxed text-muted">
              {STATEMENT_COPY.helper}
            </p>
          </div>
          <label className="flex flex-col gap-1.5 text-[11px] font-semibold tracking-[0.18em] text-muted/80 uppercase">
            Month
            <input
              type="month"
              value={month}
              aria-label="Statement month"
              onChange={(event) => onMonthChange?.(event.target.value)}
              className="min-w-[11.5rem] rounded-full border border-black/[0.06] bg-white px-4 py-2 text-[15px] font-semibold tracking-normal text-ink normal-case"
            />
          </label>
        </div>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <GradeBadge billed={billed} />
          <div className="flex flex-wrap items-center gap-3 sm:ml-auto">
            <button
              type="button"
              onClick={onCopy}
              disabled={!printable}
              className={
                printable
                  ? "rounded-full bg-white px-4 py-2 text-[13px] font-semibold text-ink ring-1 ring-black/[0.08] transition hover:bg-mist"
                  : "cursor-not-allowed rounded-full bg-white/70 px-4 py-2 text-[13px] font-semibold text-muted ring-1 ring-black/[0.04]"
              }
            >
              {copied ? STATEMENT_COPY.copied : STATEMENT_COPY.copyTotals}
            </button>
            <button
              type="button"
              onClick={onDownloadCsv}
              disabled={!printable}
              title={printable ? undefined : STATEMENT_COPY.printDisabledHint}
              className={
                printable
                  ? "rounded-full bg-white px-4 py-2 text-[13px] font-semibold text-ink ring-1 ring-black/[0.08] transition hover:bg-mist"
                  : "cursor-not-allowed rounded-full bg-white/70 px-4 py-2 text-[13px] font-semibold text-muted ring-1 ring-black/[0.04]"
              }
            >
              {STATEMENT_COPY.downloadCsv}
            </button>
            <button
              type="button"
              onClick={onPrint}
              disabled={!printable}
              title={printable ? undefined : STATEMENT_COPY.printDisabledHint}
              className={
                printable
                  ? "rounded-full bg-grape px-4 py-2 text-[13px] font-semibold text-white shadow-[0_8px_18px_rgba(124,92,255,0.22)] transition hover:bg-grape-deep"
                  : "cursor-not-allowed rounded-full bg-white/80 px-4 py-2 text-[13px] font-semibold text-grape-ink/75 ring-1 ring-grape/20"
              }
            >
              {STATEMENT_COPY.print}
            </button>
          </div>
        </div>

        {nudgePro ? (
          <p className="mt-3 text-[13px] text-muted">
            <Link href="/pricing" className="text-grape transition hover:text-grape-ink">
              {STATEMENT_COPY.proNudge}
            </Link>
          </p>
        ) : null}
        {pasteHook ? (
          <p
            className="mt-3 text-[13px] text-muted"
            data-ardoise-paste-bill
          >
            {STATEMENT_COPY.pasteHook}
          </p>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="mt-8 text-[15px] text-grape-ink">
          {error}
        </p>
      ) : null}
      {empty && !error ? (
        <section
          aria-labelledby="statement-empty-title"
          className="relative mt-10 overflow-hidden rounded-[28px] bg-[linear-gradient(160deg,#f7f1fc_0%,#efe6fb_52%,#e6daf8_100%)] px-8 py-12 shadow-[0_18px_50px_rgba(124,92,255,0.08)] ring-1 ring-grape/20"
        >
          <div
            aria-hidden
            className="pointer-events-none absolute -top-24 -right-10 h-64 w-64 rounded-full bg-grape/20 blur-3xl"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-28 left-4 h-56 w-56 rounded-full bg-[#d8c8f4]/70 blur-3xl"
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
  const [canPasteBill, setCanPasteBill] = useState<boolean | undefined>(undefined);
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
        const [me, payload] = await Promise.all([
          apiGet<MeResponse>("/v1/me", session.accessToken),
          apiGet<StatementResponse>(
            `/v1/usage/statement?month=${encodeURIComponent(month)}`,
            session.accessToken,
          ),
        ]);
        if (!cancelled) {
          setCanPasteBill(Boolean(me.account.invoice_grade));
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
    if (!data || !hasPrintableRows(data)) {
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

  function downloadCsv() {
    if (!data || !hasPrintableRows(data) || !data.csv) {
      return;
    }
    const blob = new Blob([data.csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = csvFilename(month);
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
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
        onDownloadCsv={downloadCsv}
        canPasteBill={canPasteBill}
      />
    </AppShell>
  );
}
