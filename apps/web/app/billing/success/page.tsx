import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/page-shell";

export const metadata: Metadata = {
  title: "You’re in — Ardoise",
  description: "Subscription checkout completed.",
};

export default function BillingSuccessPage() {
  return (
    <PageShell>
      <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-6 pb-20 pt-4 sm:px-8 lg:pt-2">
        <div className="max-w-xl">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem] lg:text-[4.15rem]">
            You’re <span className="text-grape">in</span>.
          </h1>
          <p className="mt-6 max-w-md text-[17px] leading-relaxed text-muted sm:text-[18px]">
            Local ledger stays on your machine.
          </p>
          <Link
            href="/#install"
            className="mt-8 inline-flex items-center rounded-full bg-grape px-8 py-3.5 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep"
          >
            Install the CLI
            <span aria-hidden className="ml-1.5">
              →
            </span>
          </Link>
        </div>
      </section>
    </PageShell>
  );
}
