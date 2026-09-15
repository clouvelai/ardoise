import type { Metadata } from "next";
import { PageShell } from "@/components/page-shell";
import { PricingGrid } from "@/components/pricing-grid";

export const metadata: Metadata = {
  title: "Pricing — Ardoise",
  description:
    "Free local CLI. Pro $20/mo. Team $49/mo. Account first, card later.",
};

export default function PricingPage() {
  return (
    <PageShell>
      <section className="mx-auto w-full max-w-6xl flex-1 px-6 pb-20 pt-4 sm:px-8 lg:pt-2">
        <div className="max-w-xl">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem] lg:text-[4.15rem]">
            Pricing.
          </h1>
          <p className="mt-6 max-w-lg text-[17px] leading-relaxed text-muted sm:text-[18px]">
            Free on disk forever. Pro pastes a vendor bill for Billed truth —
            not a prettier statement.
          </p>
        </div>
        <div className="mt-14">
          <PricingGrid />
        </div>
      </section>
    </PageShell>
  );
}
