"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { billingMessage, isPaidPlan, startCheckout, type PaidPlan } from "@/lib/saas-billing";
import { COPY, isSessionRequired } from "@/lib/saas-errors";
import { clearSession, getSession } from "@/lib/saas-session";

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
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const className = featured ? featuredClass : quietClass;

  if (!plan || !isPaidPlan(plan)) {
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }

  async function onPay() {
    if (!plan) {
      return;
    }
    const paidPlan = plan;
    setError(null);
    setStatus(null);
    const session = getSession();
    if (!session) {
      router.push("/signup?next=/pricing");
      return;
    }
    setPending(true);
    try {
      const checkout = await startCheckout(paidPlan, session.accessToken);
      window.location.assign(checkout.url);
    } catch (caught) {
      if (isSessionRequired(caught)) {
        clearSession();
        router.push("/signup?next=/pricing");
        return;
      }
      const message = billingMessage(caught);
      if (message === COPY.notWired) {
        setStatus(COPY.notWired);
        return;
      }
      setError(message);
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <button type="button" className={className} disabled={pending} onClick={onPay}>
        {pending ? "Continuing…" : children}
      </button>
      {status ? (
        <p
          role="status"
          className="mt-3 text-center text-[13px] leading-relaxed text-muted"
        >
          {status}
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
