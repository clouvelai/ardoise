"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { ConnectLaptopSteps } from "@/components/connect-laptop";
import { apiGet, type MeResponse, type UsageStatus } from "@/lib/saas-api";
import { clearSession, getSession } from "@/lib/saas-session";
import { sparseMessage } from "@/lib/saas-errors";

function money(value: number, places = 4) {
  return `$${value.toFixed(places)}`;
}

export function LedgerView() {
  const [status, setStatus] = useState<UsageStatus | null>(null);
  const [plan, setPlan] = useState("free");
  const [error, setError] = useState<string | null>(null);
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
        const [me, usage] = await Promise.all([
          apiGet<MeResponse>("/v1/me", session.accessToken),
          apiGet<UsageStatus>(
            `/v1/usage/status?month=${encodeURIComponent(month)}`,
            session.accessToken,
          ),
        ]);
        if (cancelled) {
          return;
        }
        setPlan(me.account.plan || "free");
        setStatus(usage);
        setError(null);
      } catch (caught) {
        if (cancelled) {
          return;
        }
        if (String(caught).includes("Sign in")) {
          clearSession();
        }
        setError(sparseMessage(caught));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [month]);

  const empty = !status || status.month_entries === 0;

  return (
    <AppShell>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.22em] text-muted/80 uppercase">
            Ledger
          </p>
          <h1 className="mt-2 text-[2.1rem] font-bold tracking-[-0.04em] text-ink">
            {month}
          </h1>
          <p className="mt-1 text-[14px] text-muted">
            Plan: {plan}
            {status?.invoice_grade ? " · Billed" : " · Estimate"}
          </p>
        </div>
        <label className="text-[13px] text-muted">
          Month
          <input
            type="month"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            className="ml-2 rounded-full border border-black/[0.06] bg-white px-3 py-1.5 text-[14px] text-ink"
          />
        </label>
      </div>

      {error ? (
        <p role="alert" className="mt-8 text-[15px] text-grape-ink">
          {error}
        </p>
      ) : null}

      {status ? (
        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          <article className="rounded-[24px] bg-white px-6 py-5 ring-1 ring-black/[0.04]">
            <p className="text-[12px] text-muted">T0 estimate</p>
            <p className="mt-1 text-[1.8rem] font-semibold tracking-tight">
              {money(status.estimated_usd)}
            </p>
          </article>
          <article className="rounded-[24px] bg-white px-6 py-5 ring-1 ring-black/[0.04]">
            <p className="text-[12px] text-muted">Billed</p>
            <p className="mt-1 text-[1.8rem] font-semibold tracking-tight">
              {status.invoice_grade ? money(status.billed_usd, 2) : "—"}
            </p>
          </article>
          <article className="rounded-[24px] bg-white px-6 py-5 ring-1 ring-black/[0.04]">
            <p className="text-[12px] text-muted">Entries</p>
            <p className="mt-1 text-[1.8rem] font-semibold tracking-tight">
              {status.month_entries}
            </p>
          </article>
        </div>
      ) : null}

      {empty && !error ? (
        <section className="mt-10 rounded-[28px] bg-white px-7 py-8 ring-1 ring-black/[0.04]">
          <h2 className="text-[1.35rem] font-semibold tracking-tight">
            Connect this laptop
          </h2>
          <ConnectLaptopSteps />
        </section>
      ) : null}

      {status?.notes?.length ? (
        <ul className="mt-6 space-y-1 text-[13px] text-muted">
          {status.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}

      {status && status.by_project && status.by_project.length > 0 ? (
        <section className="mt-10">
          <h2 className="text-[1.2rem] font-semibold">By project</h2>
          <ul className="mt-4 divide-y divide-black/[0.04] rounded-[24px] bg-white ring-1 ring-black/[0.04]">
            {status.by_project.map((row) => (
              <li
                key={row.project}
                className="flex items-center justify-between px-6 py-3 text-[15px]"
              >
                <span>{row.project}</span>
                <span className="text-muted">
                  {money(row.cost_usd)} · {row.entries}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {status && status.by_model && status.by_model.length > 0 ? (
        <section className="mt-8">
          <h2 className="text-[1.2rem] font-semibold">By model</h2>
          <ul className="mt-4 divide-y divide-black/[0.04] rounded-[24px] bg-white ring-1 ring-black/[0.04]">
            {status.by_model.slice(0, 8).map((row) => (
              <li
                key={row.model}
                className="flex items-center justify-between px-6 py-3 text-[15px]"
              >
                <span>{row.model}</span>
                <span className="text-muted">{money(row.cost_usd)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {plan === "free" && status && status.month_entries > 0 && !status.invoice_grade ? (
        <p className="mt-10 text-[13px] text-muted">
          <Link href="/pricing" className="text-grape transition hover:text-grape-ink">
            Paste a vendor bill on Pro to upgrade this Estimate to Billed.
          </Link>
        </p>
      ) : null}
    </AppShell>
  );
}
