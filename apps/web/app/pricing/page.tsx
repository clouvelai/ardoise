import type { Metadata } from "next";
import { PageShell } from "@/components/page-shell";
import { PricingGrid } from "@/components/pricing-grid";

export const metadata: Metadata = {
  title: "Pricing — Ardoise",
  description:
    "Free local CLI. Team $39/mo. Business $149/mo. Account first, card later.",
};

export default function PricingPage() {
  return (
    <PageShell>
      <section className="mx-auto w-full max-w-6xl flex-1 px-6 pb-20 pt-8 sm:px-8 sm:pt-14">
        <div className="max-w-xl">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem]">
            Pricing.
          </h1>
          <p className="mt-5 text-[17px] text-muted sm:text-[18px]">
            Account first. Card later.
          </p>
        </div>
        <div className="mt-14">
          <PricingGrid />
        </div>
      </section>
    </PageShell>
  );
}
