import Link from "next/link";

export function Install() {
  return (
    <section
      id="cost-tracking"
      className="mx-auto w-full max-w-6xl scroll-mt-24 px-6 pb-20 sm:px-8"
    >
      <div className="rounded-[32px] bg-white px-8 py-14 shadow-[0_8px_40px_rgba(76,29,149,0.06)] ring-1 ring-black/[0.03] sm:px-12 lg:px-14 lg:py-16">
        <p className="text-[12px] font-semibold tracking-[0.18em] text-grape uppercase">
          Cost tracking
        </p>
        <h2 className="mt-3 max-w-xl text-[2.15rem] font-bold tracking-[-0.035em] text-ink sm:text-[2.5rem]">
          Know what each project costs.
        </h2>
        <p className="mt-4 max-w-md text-[16px] leading-relaxed text-muted">
          Attribute Claude Code + Cursor spend per project. Local ledger first —
          invoice-grade when you need it.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
          <Link
            href="/signup"
            className="inline-flex items-center rounded-full bg-grape px-8 py-3.5 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep"
          >
            Start tracking
            <span aria-hidden className="ml-1.5">
              →
            </span>
          </Link>
          <Link
            href="/pricing"
            className="text-[15px] font-medium text-muted transition hover:text-ink"
          >
            Pricing
            <span aria-hidden className="ml-1">
              →
            </span>
          </Link>
        </div>
      </div>
    </section>
  );
}
