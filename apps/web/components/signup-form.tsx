"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  isBillingNotWired,
  isPaidPlan,
  startCheckout,
} from "@/lib/saas-billing";
import {
  isOtpNotWired,
  requestEmailOtp,
  verifyEmailOtp,
} from "@/lib/saas-otp";
import { saveSession } from "@/lib/saas-session";
import { Mascot } from "./mark";

type Step = "email" | "code" | "done";

function messageOf(error: unknown): string {
  if (isOtpNotWired(error)) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Something went wrong";
}

export function SignupForm() {
  const searchParams = useSearchParams();
  const requestedPlan = searchParams.get("plan");
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stub, setStub] = useState(false);

  async function onRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const result = await requestEmailOtp(email);
      setEmail(result.email);
      setStub(result.mocked);
      setStep("code");
    } catch (caught) {
      if (isOtpNotWired(caught)) {
        setStub(true);
        setStep("code");
        return;
      }
      setError(messageOf(caught));
    } finally {
      setPending(false);
    }
  }

  async function onVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (stub && !code.trim()) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      const session = await verifyEmailOtp(email, code);
      saveSession(session);
      setStub(false);
      if (isPaidPlan(requestedPlan)) {
        try {
          const checkout = await startCheckout(
            requestedPlan,
            session.accessToken,
          );
          window.location.assign(checkout.url);
          return;
        } catch (billing) {
          if (!isBillingNotWired(billing)) {
            setError(
              billing instanceof Error ? billing.message : "Checkout failed",
            );
          }
        }
      }
      setStep("done");
    } catch (caught) {
      if (isOtpNotWired(caught)) {
        setStub(true);
        setError(null);
        return;
      }
      setError(messageOf(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="relative mx-auto w-full max-w-[440px]">
      <div
        className="mascot-bob pointer-events-none absolute -top-10 right-6 z-10 h-[72px] w-[66px] sm:-top-12 sm:right-8 sm:h-[80px] sm:w-[72px]"
        aria-hidden
      >
        <Mascot className="h-full w-full drop-shadow-sm" />
      </div>
      <div className="rounded-[28px] bg-white px-6 py-8 shadow-[0_8px_30px_rgba(76,29,149,0.07),0_28px_80px_rgba(76,29,149,0.08)] ring-1 ring-black/[0.03] sm:px-8 sm:py-10">
        {step === "email" ? (
          <form onSubmit={onRequest} className="space-y-5">
            <label className="block">
              <span className="sr-only">Email</span>
              <input
                type="email"
                name="email"
                autoComplete="email"
                inputMode="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-full border border-black/[0.06] bg-mist/70 px-5 py-3.5 text-[15px] text-ink outline-none transition placeholder:text-muted/70 focus:border-grape/40 focus:ring-4 focus:ring-grape/15"
              />
            </label>
            <button
              type="submit"
              disabled={pending}
              className="flex w-full items-center justify-center rounded-full bg-grape py-3.5 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep disabled:cursor-wait disabled:opacity-70"
            >
              {pending ? "Sending…" : "Continue"}
            </button>
          </form>
        ) : null}

        {step === "code" ? (
          <form onSubmit={onVerify} className="space-y-5">
            <p className="text-[15px] text-muted">
              {stub ? "Enter a code." : `We sent a code to ${email}.`}
            </p>
            <label className="block">
              <span className="sr-only">One-time code</span>
              <input
                type="text"
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                spellCheck={false}
                required={!stub}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="••••••"
                className="w-full rounded-full border border-black/[0.06] bg-mist/70 px-5 py-3.5 text-center text-[18px] tracking-[0.35em] text-ink outline-none transition placeholder:tracking-[0.35em] placeholder:text-muted/50 focus:border-grape/40 focus:ring-4 focus:ring-grape/15"
              />
            </label>
            <button
              type="submit"
              disabled={pending}
              className="flex w-full items-center justify-center rounded-full bg-grape py-3.5 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep disabled:cursor-wait disabled:opacity-70"
            >
              {pending ? "Checking…" : "Verify"}
            </button>
            <button
              type="button"
              onClick={() => {
                setStep("email");
                setCode("");
                setError(null);
                setStub(false);
              }}
              className="mx-auto block text-[13px] font-medium text-muted transition hover:text-ink"
            >
              Use a different email
            </button>
          </form>
        ) : null}

        {step === "done" ? (
          <div className="py-4 text-center">
            <p className="text-[1.35rem] font-semibold tracking-tight text-ink">
              You’re in.
            </p>
            <p className="mt-2 text-[15px] text-muted">
              Local ledger stays on your machine.
            </p>
            <Link
              href="/#install"
              className="mt-6 inline-flex items-center rounded-full bg-lavender px-6 py-3 text-[15px] font-semibold text-grape transition hover:bg-violet-100"
            >
              Install the CLI
              <span aria-hidden className="ml-1.5">
                →
              </span>
            </Link>
          </div>
        ) : null}

        {stub && step !== "done" ? (
          <p
            role="status"
            className="mt-5 rounded-2xl bg-mist/80 px-4 py-3 text-center text-[13px] leading-relaxed text-muted"
          >
            Coming soon — API not wired
          </p>
        ) : null}

        {error ? (
          <p role="alert" className="mt-4 text-center text-[13px] text-grape-ink">
            {error}
          </p>
        ) : null}

        {step !== "done" ? (
          <p className="mt-6 text-center text-[13px] text-muted">
            Local ledger stays on your machine
          </p>
        ) : null}
      </div>
    </div>
  );
}
