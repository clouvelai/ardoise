import Link from "next/link";
import { LedgerCard } from "./ledger-card";

export function Hero() {
  return (
    <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-6 pb-10 pt-4 sm:px-8 lg:pt-2">
      <div className="grid items-center gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:gap-16">
        <div className="max-w-xl">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem] lg:text-[4.15rem]">
            Know where
            <br />
            every <span className="text-grape">token</span> went.
          </h1>
          <p className="mt-6 max-w-md text-[17px] leading-relaxed text-muted sm:text-[18px]">
            Turn Claude Code and Cursor usage into a local ledger.
            Nothing leaves the machine.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/signup"
              className="inline-flex items-center rounded-full bg-grape px-8 py-3.5 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep"
            >
              Start for free
              <span aria-hidden className="ml-1.5">
                →
              </span>
            </Link>
            <a
              href="#install"
              className="inline-flex items-center rounded-full bg-white px-6 py-3.5 text-[15px] font-semibold text-ink shadow-[0_1px_2px_rgba(23,20,31,0.06)] ring-1 ring-black/5 transition hover:bg-mist"
            >
              Install
            </a>
          </div>
          <p className="mt-4 text-[13px] text-muted">
            No credit card required.
          </p>
        </div>
        <LedgerCard />
      </div>
    </section>
  );
}
