import { PricingCta } from "./pricing-cta";
import type { PaidPlan } from "@/lib/saas-billing";

/**
 * Locked amounts: Free $0 · Pro $20/mo · Team $49/mo.
 * Checkout posts plan=pro | team (never business).
 */
const tiers: {
  name: string;
  tagline: string;
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
    tagline: "Local CLI forever",
    price: "$0",
    period: "",
    items: [
      "Ledger on disk",
      "Status, statement, export",
      "No card",
    ],
    cta: "Start for free",
    href: "/signup",
    featured: false,
  },
  {
    name: "Pro",
    tagline: "Solo SaaS companion",
    price: "$20",
    period: "/mo",
    badge: "Most popular",
    items: [
      "Invoice-grade statements",
      "Cloud sync",
      "Account first, card later",
    ],
    cta: "Get Pro",
    href: "/signup?next=/pricing",
    featured: true,
    plan: "pro",
  },
  {
    name: "Team",
    tagline: "The org ledger",
    price: "$49",
    period: "/mo",
    items: [
      "Multi-seat roster + seat filters",
      "Shared org rollup across projects",
      "Agent/skill attribution for the team",
      "Shared invoice exports for finance",
      "Invite seats without sharing a login",
    ],
    cta: "Get Team",
    href: "/signup?next=/pricing",
    featured: false,
    plan: "team",
  },
];

function Check() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="mt-0.5 h-4 w-4 shrink-0 text-grape"
    >
      <path
        d="M3.2 8.2 6.3 11.3 12.8 4.7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function PricingGrid() {
  return (
    <div className="grid gap-5 lg:grid-cols-3 lg:items-stretch lg:gap-6">
      {tiers.map((tier) => (
        <article
          key={tier.name}
          className={
            tier.featured
              ? "relative flex flex-col rounded-[28px] bg-white px-7 py-8 shadow-[0_8px_30px_rgba(76,29,149,0.07),0_28px_80px_rgba(76,29,149,0.08)] ring-2 ring-grape/25"
              : "relative flex flex-col rounded-[28px] bg-white/80 px-7 py-8 ring-1 ring-black/[0.04]"
          }
        >
          {tier.featured ? (
            <p className="absolute -top-3 left-7 rounded-full bg-grape px-3 py-1 text-[11px] font-semibold tracking-wide text-white">
              {tier.badge}
            </p>
          ) : null}
          <p className="text-[15px] font-semibold text-ink">{tier.name}</p>
          <p className="mt-1 text-[14px] leading-relaxed text-muted">
            {tier.tagline}
          </p>
          <p className="mt-5 flex items-baseline gap-1">
            <span className="text-[2.35rem] font-bold tracking-[-0.04em] text-ink">
              {tier.price}
            </span>
            {tier.period ? (
              <span className="text-[15px] text-muted">{tier.period}</span>
            ) : (
              <span className="text-[15px] text-muted">no card</span>
            )}
          </p>
          <ul className="mt-6 flex-1 space-y-2.5 text-[15px] text-muted">
            {tier.items.map((item) => (
              <li key={item} className="flex items-start gap-2.5">
                <Check />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <div className="mt-auto">
            <PricingCta plan={tier.plan} featured={tier.featured} href={tier.href}>
              {tier.cta}
              <span aria-hidden className="ml-1.5">
                →
              </span>
            </PricingCta>
          </div>
        </article>
      ))}
    </div>
  );
}
