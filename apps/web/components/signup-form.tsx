"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { COPY, isNetworkError, safeNextPath } from "@/lib/saas-errors";
import { isOtpNotWired, otpMessage, requestEmailOtp, verifyEmailOtp } from "@/lib/saas-otp";
import { getSession, saveSession } from "@/lib/saas-session";
import { Install } from "./install";
import { Mascot } from "./mark";

type Step = "email" | "code" | "done";

const fieldClass =
  "w-full rounded-full border border-black/[0.06] bg-mist/70 px-5 py-3.5 text-[15px] text-ink outline-none transition placeholder:text-muted/70 focus:border-grape/40 focus:ring-4 focus:ring-grape/15 disabled:opacity-70";
const primaryClass =
  "flex w-full items-center justify-center rounded-full bg-grape py-3.5 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(124,92,255,0.28)] transition hover:bg-grape-deep disabled:cursor-wait disabled:opacity-70";

export function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = safeNextPath(searchParams.get("next"));
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (nextPath && getSession()) {
      router.replace(nextPath);
    }
  }, [nextPath, router]);

  async function onRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setStatus(null);
    try {
      const result = await requestEmailOtp(email);
      setEmail(result.email);
      setStep("code");
      setStatus(result.mocked ? COPY.notWired : null);
    } catch (caught) {
      if (isOtpNotWired(caught)) {
        setStatus(COPY.notWired);
        return;
      }
      setError(otpMessage(caught));
    } finally {
      setPending(false);
    }
  }

  async function onVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const session = await verifyEmailOtp(email, code);
      saveSession(session);
      if (nextPath) {
        router.replace(nextPath);
        return;
      }
      setStep("done");
      setStatus(null);
    } catch (caught) {
      if (isOtpNotWired(caught)) {
        setStatus(COPY.notWired);
        return;
      }
      setError(otpMessage(caught));
    } finally {
      setPending(false);
    }
  }

  async function onResend() {
    setPending(true);
    setError(null);
    try {
      await requestEmailOtp(email);
      setStatus("Sent again.");
    } catch (caught) {
      if (isOtpNotWired(caught) || isNetworkError(caught)) {
        setStatus(otpMessage(caught));
        return;
      }
      setError(otpMessage(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <div
      className={`relative mx-auto w-full ${step === "done" ? "max-w-3xl" : "max-w-[440px]"}`}
    >
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
                disabled={pending}
                className={fieldClass}
              />
            </label>
            <button type="submit" disabled={pending} className={primaryClass}>
              {pending ? "Sending…" : "Continue"}
            </button>
          </form>
        ) : null}

        {step === "code" ? (
          <form onSubmit={onVerify} className="space-y-5">
            <p className="text-[15px] text-muted">
              We sent a code to {email}.
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
                required
                maxLength={8}
                value={code}
                onChange={(event) =>
                  setCode(event.target.value.replace(/\s/g, ""))
                }
                placeholder="••••••"
                disabled={pending}
                className={`${fieldClass} text-center text-[18px] tracking-[0.35em] placeholder:tracking-[0.35em] placeholder:text-muted/50`}
              />
            </label>
            <button type="submit" disabled={pending} className={primaryClass}>
              {pending ? "Checking…" : "Verify"}
            </button>
            <div className="flex items-center justify-center gap-4 text-[13px] font-medium">
              <button
                type="button"
                disabled={pending}
                onClick={() => {
                  setStep("email");
                  setCode("");
                  setError(null);
                  setStatus(null);
                }}
                className="text-muted transition hover:text-ink"
              >
                Use a different email
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={onResend}
                className="text-muted transition hover:text-ink"
              >
                Resend
              </button>
            </div>
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
              href="/pricing"
              className="mt-6 inline-block text-[13px] font-medium text-muted transition hover:text-ink"
            >
              See pricing
            </Link>
          </div>
        ) : null}

        {status && step !== "done" ? (
          <p
            role="status"
            className="mt-5 rounded-2xl bg-mist/80 px-4 py-3 text-center text-[13px] leading-relaxed text-muted"
          >
            {status}
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
      {step === "done" ? <Install className="mt-8 w-full" /> : null}
    </div>
  );
}
