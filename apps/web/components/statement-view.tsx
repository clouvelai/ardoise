"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import {
  GradeBadge,
  StatementDocumentView,
  money,
} from "@/components/statement-document";
import { apiGet, type StatementResponse } from "@/lib/saas-api";
import { getSession } from "@/lib/saas-session";
import { sparseMessage } from "@/lib/saas-errors";

function copyPayload(data: StatementResponse, month: string): string {
  const billed = Boolean(data.invoice_grade);
  const total = money(data.document?.total_usd, billed ? 2 : 4);
  return `Statement ${month} · ${billed ? "Billed" : "Estimate"} · Total ${total}`;
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
      <div className="print-hide flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.22em] text-muted/80 uppercase">
            Statement
          </p>
          <h1 className="mt-2 text-[2.1rem] font-bold tracking-[-0.04em] text-ink">
            {month}
          </h1>
          {data ? (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
              <GradeBadge billed={Boolean(data.invoice_grade)} />
              <button
                type="button"
                onClick={copyTotals}
                className="text-[13px] text-muted transition hover:text-ink"
              >
                {copied ? "Copied" : "Copy totals into your invoice"}
              </button>
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-[13px] text-muted">
            Month
            <input
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
              className="ml-2 rounded-full border border-black/[0.06] bg-white px-3 py-1.5 text-[14px] text-ink"
            />
          </label>
          <button
            type="button"
            onClick={() => window.print()}
            className="rounded-full bg-grape px-4 py-2 text-[13px] font-semibold text-white shadow-[0_8px_18px_rgba(124,92,255,0.22)] transition hover:bg-grape-deep"
          >
            Print statement
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className="mt-8 text-[15px] text-grape-ink">
          {error}
        </p>
      ) : null}
      {data?.document ? (
        <StatementDocumentView document={data.document} />
      ) : data ? (
        <pre className="mt-8 overflow-x-auto whitespace-pre-wrap rounded-[24px] bg-white px-6 py-5 text-[13px] leading-relaxed text-ink/80 ring-1 ring-black/[0.04]">
          {data.markdown}
        </pre>
      ) : null}
    </AppShell>
  );
}
