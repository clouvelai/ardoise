"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { SlateMark } from "@/components/mark";
import { StatementWorkspace } from "@/components/statement-view";
import {
  BILLED_STATEMENT_FIXTURE,
  EMPTY_STATEMENT_FIXTURE,
  ESTIMATE_STATEMENT_FIXTURE,
} from "@/lib/statement-fixtures";

function fixtureFor(state: string) {
  if (state === "billed") {
    return BILLED_STATEMENT_FIXTURE;
  }
  if (state === "estimate") {
    return ESTIMATE_STATEMENT_FIXTURE;
  }
  return EMPTY_STATEMENT_FIXTURE;
}

function StatementPreviewInner() {
  const params = useSearchParams();
  const state = params.get("state") || "empty";
  const [pasted, setPasted] = useState(false);
  const fixture = useMemo(
    () => (pasted ? BILLED_STATEMENT_FIXTURE : fixtureFor(state)),
    [pasted, state],
  );
  const [copied, setCopied] = useState(false);
  const [month, setMonth] = useState(fixture.month);
  const canPasteBill =
    params.get("plan") === "pro" || state === "billed" || pasted ? true : false;

  useEffect(() => {
    setPasted(false);
  }, [state]);

  return (
    <div className="flex min-h-svh flex-col">
      <header className="print-hide mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 sm:px-8">
        <Link href="/app" className="flex items-center gap-2.5 text-ink">
          <SlateMark className="h-7 w-7" />
          <span className="text-[17px] font-semibold tracking-tight">ardoise</span>
        </Link>
        <nav className="flex items-center gap-4 sm:gap-6">
          <span className="text-[15px] font-medium text-ink/70">Ledger</span>
          <span className="text-[15px] font-semibold text-ink">Statement</span>
          <span className="text-[15px] font-medium text-ink/70">Settings</span>
        </nav>
      </header>
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 pb-16 sm:px-8">
        <StatementWorkspace
          month={month}
          onMonthChange={setMonth}
          data={fixture}
          copied={copied}
          canPasteBill={canPasteBill}
          onCopy={() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          }}
          onPrint={() => window.print()}
          onPasteVendorTotal={() => {
            setPasted(true);
          }}
        />
      </main>
    </div>
  );
}

export default function StatementPreviewPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-svh items-center justify-center text-[15px] text-muted">
          Loading…
        </div>
      }
    >
      <StatementPreviewInner />
    </Suspense>
  );
}
