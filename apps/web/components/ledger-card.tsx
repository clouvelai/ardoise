import { Mascot } from "./mark";

const rows = [
  { project: "acme/billing", tokensIn: "241,802", cost: "$41.18" },
  { project: "clouvelai/demo-app", tokensIn: "118,440", cost: "$28.06" },
];

export function LedgerCard() {
  return (
    <div className="relative mx-auto mt-10 w-full max-w-[440px] lg:mt-6">
      <div
        className="mascot-bob pointer-events-none absolute -top-[84px] right-3 z-10 h-[92px] w-[84px] sm:-top-[100px] sm:right-4 sm:h-[108px] sm:w-[98px]"
        aria-hidden
      >
        <Mascot className="h-full w-full drop-shadow-[0_6px_10px_rgba(91,33,182,0.18)]" />
      </div>
      <div className="rounded-[28px] bg-white px-6 py-7 shadow-[0_8px_30px_rgba(76,29,149,0.07),0_28px_80px_rgba(76,29,149,0.08)] ring-1 ring-black/[0.03] sm:px-8 sm:py-8">
        <p className="mb-3 text-[12px] font-medium text-muted">
          $ ardoise status
        </p>
        <div className="space-y-2.5">
          {rows.map((row) => (
            <div
              key={row.project}
              className="flex items-center justify-between gap-3 rounded-2xl border border-black/[0.04] bg-mist/70 px-3.5 py-3"
            >
              <div className="min-w-0">
                <p className="truncate text-[14px] font-medium text-ink">
                  {row.project}
                </p>
                <p className="truncate text-[12px] tabular-nums text-muted">
                  {row.tokensIn} in
                </p>
              </div>
              <p className="shrink-0 text-[14px] font-semibold tabular-nums text-ink">
                {row.cost}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-5 rounded-2xl border border-dashed border-violet-200/90 bg-mist/50 px-5 py-6 text-center">
          <p className="text-[15px] font-medium text-ink/70">
            statement 2026-09
          </p>
          <p className="mt-1 text-[13px] text-muted">MD · HTML · CSV</p>
        </div>

        <a
          href="#install"
          className="mt-5 flex w-full items-center justify-center rounded-full bg-lavender py-3.5 text-[15px] font-semibold text-grape transition hover:bg-violet-100"
        >
          Write statement
        </a>
      </div>
    </div>
  );
}
