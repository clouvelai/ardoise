"use client";

import { useEffect, useState } from "react";
import { Mascot } from "./mark";

const STEPS = ["capture", "ledger", "invoice"] as const;
type Step = (typeof STEPS)[number];

const HOLD_MS: Record<Step, number> = {
  capture: 2600,
  ledger: 2800,
  invoice: 3600,
};

const ROWS = [
  {
    project: "acme/billing",
    source: "Claude Code",
    tokens: "241,802",
    cost: "$41.18",
  },
  {
    project: "clouvelai/demo-app",
    source: "Cursor",
    tokens: "118,440",
    cost: "$28.06",
  },
];

export function WorkflowCard() {
  const [step, setStep] = useState<Step>("capture");

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    const timer = window.setTimeout(() => {
      setStep((current) => STEPS[(STEPS.indexOf(current) + 1) % STEPS.length]);
    }, HOLD_MS[step]);
    return () => window.clearTimeout(timer);
  }, [step]);

  const caption =
    step === "capture"
      ? "Capturing usage…"
      : step === "ledger"
        ? "Attributing spend…"
        : "Invoice ready";

  return (
    <div className="relative mx-auto mt-16 w-full max-w-[440px] lg:mt-8">
      <div
        className="mascot-bob pointer-events-none absolute -top-[106px] right-1 z-10 h-[124px] w-[96px] sm:-top-[122px] sm:right-2 sm:h-[144px] sm:w-[112px]"
        aria-hidden
      >
        <Mascot className="h-full w-full drop-shadow-[0_8px_12px_rgba(91,33,182,0.16)]" />
      </div>

      <div
        className="relative min-h-[412px] overflow-hidden rounded-[28px] bg-white px-6 py-7 shadow-[0_8px_30px_rgba(76,29,149,0.07),0_28px_80px_rgba(76,29,149,0.08)] ring-1 ring-black/[0.03] sm:min-h-[428px] sm:px-8 sm:py-8"
        aria-label="Ardoise workflow: capture, ledger, invoice"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.18em] text-muted uppercase">
              Statement
            </p>
            <p className="mt-0.5 text-[18px] font-semibold tracking-tight text-ink">
              September 2026
            </p>
          </div>
          <p className="pt-0.5 text-[12px] font-medium tabular-nums text-muted">
            INV-2026-09
          </p>
        </div>

        <div className="motion-reduce:hidden">
          <Stepper step={step} />
        </div>
        <div className="hidden motion-reduce:block">
          <Stepper step="invoice" />
        </div>

        <p
          className="mt-5 text-[13px] font-medium text-ink/70 motion-reduce:hidden"
          aria-live="polite"
        >
          {caption}
        </p>
        <p className="mt-5 hidden text-[13px] font-medium text-ink/70 motion-reduce:block">
          Invoice ready
        </p>

        <div className="mt-4 min-h-[236px]">
          <div className="motion-reduce:hidden">
            {step === "capture" ? (
              <CaptureScene />
            ) : (
              <LedgerInvoiceScene stamped={step === "invoice"} />
            )}
          </div>
          <div className="hidden motion-reduce:block">
            <LedgerInvoiceScene stamped />
          </div>
        </div>
      </div>
    </div>
  );
}

function Stepper({ step }: { step: Step }) {
  const active = STEPS.indexOf(step);
  const labels = { capture: "Capture", ledger: "Ledger", invoice: "Invoice" };

  return (
    <ol className="mt-5 flex items-center">
      {STEPS.map((id, index) => {
        const done = index < active;
        const current = index === active;
        return (
          <li key={id} className="flex min-w-0 flex-1 items-center last:flex-none">
            {index > 0 ? (
              <span
                aria-hidden
                className={`mx-2 h-px flex-1 ${
                  done || current ? "bg-grape/35" : "bg-black/[0.06]"
                }`}
              />
            ) : null}
            <span className="flex items-center gap-1.5">
              <span
                aria-hidden
                className={`h-1.5 w-1.5 rounded-full ${
                  current
                    ? "bg-grape shadow-[0_0_0_4px_rgba(124,92,255,0.16)]"
                    : done
                      ? "bg-grape"
                      : "bg-black/15"
                }`}
              />
              <span
                className={`text-[11px] font-semibold tracking-wide ${
                  current
                    ? "text-grape"
                    : done
                      ? "text-ink/75"
                      : "text-muted/65"
                }`}
              >
                {labels[id]}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function CaptureScene() {
  return (
    <div key="capture" className="hero-enter flex h-[236px] flex-col items-center justify-center text-center">
      <p className="flex items-center gap-1.5 text-[14px] text-ink/75">
        <span className="hero-spark" aria-hidden>
          ✦
        </span>
        Claude Code · Cursor
      </p>
      <div className="relative mt-5 h-2 w-full max-w-[236px] rounded-full bg-black/[0.06]">
        <div className="hero-progress-fill absolute inset-y-0 left-0 rounded-full bg-grape">
          <span className="hero-progress-knob" aria-hidden />
        </div>
      </div>
      <p className="mt-4 text-[12px] text-muted">Local ledger, on this machine</p>
    </div>
  );
}

function LedgerInvoiceScene({ stamped }: { stamped: boolean }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between px-1 text-[11px] font-medium tracking-wide text-muted/80 uppercase">
        <span>Project</span>
        <span>Amount</span>
      </div>
      <div className="space-y-2">
        {ROWS.map((row, index) => (
          <div
            key={row.project}
            className={`hero-enter flex items-center justify-between gap-3 rounded-2xl border border-black/[0.04] bg-mist/70 px-3.5 py-3 ${
              index === 1 ? "hero-enter-delay" : ""
            }`}
          >
            <div className="min-w-0">
              <p className="truncate text-[14px] font-medium text-ink">
                {row.project}
              </p>
              <p className="truncate text-[12px] tabular-nums text-muted">
                {row.tokens} in · {row.source}
              </p>
            </div>
            <p className="shrink-0 text-[14px] font-semibold tabular-nums text-ink">
              {row.cost}
            </p>
          </div>
        ))}
      </div>

      {stamped ? (
        <div className="hero-stamp mt-4 flex items-center justify-between rounded-2xl bg-lavender px-4 py-3.5">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.14em] text-grape uppercase">
              Ready
            </p>
            <p className="mt-0.5 text-[12px] text-muted">MD · HTML · CSV</p>
          </div>
          <p className="text-[22px] font-bold tabular-nums tracking-tight text-grape">
            $69.24
          </p>
        </div>
      ) : (
        <div className="mt-4 flex h-[62px] items-center justify-between rounded-2xl border border-dashed border-violet-200/90 bg-mist/40 px-4">
          <p className="text-[13px] text-muted">Writing statement…</p>
          <p className="text-[13px] font-medium tabular-nums text-ink/35">$69.24</p>
        </div>
      )}
    </div>
  );
}
