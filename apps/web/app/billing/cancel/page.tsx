import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/page-shell";

export const metadata: Metadata = {
  title: "Checkout canceled — Ardoise",
  description: "No charge. Your free account is still here.",
};

export default function BillingCancelPage() {
  return (
    <PageShell>
      <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-6 pb-20 pt-4 sm:px-8 lg:pt-2">
        <div className="max-w-xl">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem] lg:text-[4.15rem]">
            No charge.
          </h1>
          <p className="mt-6 max-w-md text-[17px] leading-relaxed text-muted sm:text-[18px]">
            Your free account is still here. Card later.
          </p>
          <Link
            href="/pricing"
            className="mt-8 inline-flex items-center rounded-full bg-lavender px-8 py-3.5 text-[15px] font-semibold text-grape transition hover:bg-violet-100"
          >
            Back to pricing
            <span aria-hidden className="ml-1.5">
              →
            </span>
          </Link>
        </div>
      </section>
    </PageShell>
  );
}
