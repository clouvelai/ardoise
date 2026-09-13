import { PricingCta } from "./pricing-cta";
import type { PaidPlan } from "@/lib/saas-billing";

const tiers: {
  name: string;
  price: string;
  period: string;
  items: readonly string[];
  cta: string;
  href: string;
  featured: boolean;
  badge?: string;
  plan?: PaidPlan;
}[] = [
  {
    name: "Free",
    price: "$0",
    period: "",
    items: ["Local CLI", "One seat", "Export"],
    cta: "Start for free",
    href: "/signup",
    featured: false,
  },
  {
    name: "Pro",
    price: "$20",
    period: "/mo",
    badge: "Most popular",
    items: ["Invoice-grade statements", "Cloud sync", "One seat"],
    cta: "Get Pro",
    href: "/signup?next=/pricing",
    featured: true,
    plan: "pro",
  },
  {
    name: "Team",
    price: "$49",
    period: "/mo",
    items: ["Multi-seat", "Shared reports", "Org rollup"],
    cta: "Get Team",
    href: "/signup?next=/pricing",
    featured: false,
    plan: "team",
  },
];

export function PricingGrid() {
  return (
    <div>
      <div className="grid gap-5 lg:grid-cols-3 lg:gap-6">
        {tiers.map((tier) => (
          <article
            key={tier.name}
            className={
              tier.featured
                ? "relative rounded-[28px] bg-white px-7 py-8 shadow-[0_8px_30px_rgba(76,29,149,0.07),0_28px_80px_rgba(76,29,149,0.08)] ring-2 ring-grape/25"
                : "relative rounded-[28px] bg-white/80 px-7 py-8 ring-1 ring-black/[0.04]"
            }
          >
            {tier.featured ? (
              <p className="absolute -top-3 left-7 rounded-full bg-grape px-3 py-1 text-[11px] font-semibold tracking-wide text-white">
                {tier.badge}
              </p>
            ) : null}
            <p className="text-[15px] font-semibold text-ink">{tier.name}</p>
            <p className="mt-4 flex items-baseline gap-1">
              <span className="text-[2.35rem] font-bold tracking-[-0.04em] text-ink">
                {tier.price}
              </span>
              {tier.period ? (
                <span className="text-[15px] text-muted">{tier.period}</span>
              ) : (
                <span className="text-[15px] text-muted">no card</span>
              )}
            </p>
            <ul className="mt-6 space-y-2.5 text-[15px] text-muted">
              {tier.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <PricingCta plan={tier.plan} featured={tier.featured} href={tier.href}>
              {tier.cta}
              <span aria-hidden className="ml-1.5">
                →
              </span>
            </PricingCta>
          </article>
        ))}
      </div>
    </div>
  );
}
