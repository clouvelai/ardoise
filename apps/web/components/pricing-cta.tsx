"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { isBillingNotWired, startCheckout, type PaidPlan } from "@/lib/saas-billing";
import { getSession } from "@/lib/saas-session";

const featuredClass =
  "mt-8 flex w-full items-center justify-center rounded-full bg-grape py-3 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep disabled:cursor-wait disabled:opacity-70";
const quietClass =
  "mt-8 flex w-full items-center justify-center rounded-full bg-lavender py-3 text-[15px] font-semibold text-grape transition hover:bg-violet-100 disabled:cursor-wait disabled:opacity-70";

export function PricingCta({
  plan,
  featured,
  href,
  children,
}: {
  plan?: PaidPlan;
  featured: boolean;
  href: string;
  children: ReactNode;
}) {
  const [pending, setPending] = useState(false);
  const [stub, setStub] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const className = featured ? featuredClass : quietClass;

  if (!plan) {
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }

  async function onPay() {
    setError(null);
    const session = getSession();
    if (!session) {
      window.location.assign(`/signup?plan=${plan}`);
      return;
    }
    setPending(true);
    try {
      const checkout = await startCheckout(plan, session.accessToken);
      window.location.assign(checkout.url);
    } catch (caught) {
      if (isBillingNotWired(caught)) {
        setStub(true);
        return;
      }
      setError(caught instanceof Error ? caught.message : "Checkout failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <button type="button" className={className} disabled={pending} onClick={onPay}>
        {pending ? "Continuing…" : children}
      </button>
      {stub ? (
        <p
          role="status"
          className="mt-3 text-center text-[13px] leading-relaxed text-muted"
        >
          Coming soon — API not wired
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-center text-[13px] text-grape-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
}
