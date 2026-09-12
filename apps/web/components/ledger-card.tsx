import { FileGlyph, Mascot } from "./mark";

const rows = [
  { kind: "claude" as const, name: "session.jsonl", meta: "Claude Code · Anthropic T0" },
  { kind: "cursor" as const, name: "chat.jsonl", meta: "Cursor · usage-shaped" },
];

export function LedgerCard() {
  return (
    <div className="relative mx-auto w-full max-w-[440px]">
      <div
        className="mascot-bob pointer-events-none absolute -top-10 right-6 z-10 h-[72px] w-[66px] sm:-top-12 sm:right-8 sm:h-[80px] sm:w-[72px]"
        aria-hidden
      >
        <Mascot className="h-full w-full drop-shadow-sm" />
      </div>
      <div className="rounded-[28px] bg-white px-6 py-7 shadow-[0_8px_30px_rgba(76,29,149,0.07),0_28px_80px_rgba(76,29,149,0.08)] ring-1 ring-black/[0.03] sm:px-8 sm:py-8">
        <div className="space-y-2.5">
          {rows.map((row) => (
            <div
              key={row.name}
              className="flex items-center gap-3 rounded-2xl border border-black/[0.04] bg-mist/70 px-3.5 py-3"
            >
              <FileGlyph kind={row.kind} />
              <div className="min-w-0">
                <p className="truncate text-[14px] font-medium text-ink">
                  {row.name}
                </p>
                <p className="truncate text-[12px] text-muted">{row.meta}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-5 rounded-2xl border border-dashed border-violet-200/90 bg-mist/50 px-5 py-8 text-center">
          <p className="text-[15px] font-medium text-ink/70">
            ~/.ardoise/ledger.db
          </p>
          <p className="mt-1 text-[13px] text-muted">
            Prompts, bodies, and keys are stripped
          </p>
        </div>

        <a
          href="#install"
          className="mt-5 flex w-full items-center justify-center rounded-full bg-lavender py-3.5 text-[15px] font-semibold text-grape-deep transition hover:bg-violet-100"
        >
          Write statement
        </a>
      </div>
    </div>
  );
}
