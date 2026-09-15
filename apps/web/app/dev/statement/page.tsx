"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { SlateMark } from "@/components/mark";
import { StatementWorkspace } from "@/components/statement-view";
import { csvFilename } from "@/lib/statement-chrome";
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
  const fixture = useMemo(() => fixtureFor(state), [state]);
  const [copied, setCopied] = useState(false);
  const [month, setMonth] = useState(fixture.month);
  const canPasteBill =
    params.get("plan") === "pro" || state === "billed" ? true : false;

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
          onDownloadCsv={() => {
            if (!fixture.csv) {
              return;
            }
            const blob = new Blob([fixture.csv], { type: "text/csv;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = csvFilename(month);
            link.rel = "noopener";
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
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
