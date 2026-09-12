import Link from "next/link";
import { ENTERPRISE_MAILTO } from "@/lib/saas-otp";

const tiers = [
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
    name: "Team",
    price: "$39",
    period: "/mo",
    badge: "Most teams",
    items: ["Cloud sync", "Multi-seat", "Shared reports"],
    cta: "Start for free",
    href: "/signup",
    featured: true,
  },
  {
    name: "Business",
    price: "$149",
    period: "/mo",
    items: ["Invoice-grade statements", "Audit trail"],
    cta: "Get started",
    href: "/signup",
    featured: false,
  },
] as const;

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
            <Link
              href={tier.href}
              className={
                tier.featured
                  ? "mt-8 flex w-full items-center justify-center rounded-full bg-grape py-3 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep"
                  : "mt-8 flex w-full items-center justify-center rounded-full bg-lavender py-3 text-[15px] font-semibold text-grape transition hover:bg-violet-100"
              }
            >
              {tier.cta}
              <span aria-hidden className="ml-1.5">
                →
              </span>
            </Link>
          </article>
        ))}
      </div>

      <a
        href={ENTERPRISE_MAILTO}
        className="mt-6 flex items-center justify-between gap-6 rounded-[28px] bg-white/70 px-7 py-5 ring-1 ring-black/[0.04] transition hover:bg-white"
      >
        <span className="text-[15px] font-semibold text-ink">
          Enterprise
          <span className="ml-3 font-medium text-muted">Custom</span>
        </span>
        <span className="text-[15px] font-semibold text-grape">
          Talk to us
          <span aria-hidden className="ml-1.5">
            →
          </span>
        </span>
      </a>
    </div>
  );
}
