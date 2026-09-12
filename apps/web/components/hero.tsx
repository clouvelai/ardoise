import { LedgerCard } from "./ledger-card";

export function Hero() {
  return (
    <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-6 pb-10 pt-4 sm:px-8 lg:pt-2">
      <div className="grid items-center gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:gap-16">
        <div className="max-w-xl">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem] lg:text-[4.15rem]">
            The private way
            <br />
            to see <span className="text-grape">spend</span>.
          </h1>
          <p className="mt-6 max-w-md text-[17px] leading-relaxed text-muted sm:text-[18px]">
            Turn Claude Code and Cursor usage into a local ledger.
            Nothing leaves the machine.
          </p>
          <a
            href="#install"
            className="mt-8 inline-flex items-center rounded-full bg-grape-deep px-8 py-3.5 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(91,33,182,0.28)] transition hover:bg-grape-ink"
          >
            Install for free
            <span aria-hidden className="ml-1.5">
              →
            </span>
          </a>
          <p className="mt-4 text-[13px] text-muted">
            Python 3 · stdlib only · MIT
          </p>
        </div>
        <LedgerCard />
      </div>
    </section>
  );
}
