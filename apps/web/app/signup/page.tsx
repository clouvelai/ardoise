import type { Metadata } from "next";
import { Suspense } from "react";
import { PageShell } from "@/components/page-shell";
import { SignupForm } from "@/components/signup-form";

export const metadata: Metadata = {
  title: "Start for free — Ardoise",
  description: "Create an Ardoise account with email. No credit card required.",
};

export default function SignupPage() {
  return (
    <PageShell>
      <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-6 pb-20 pt-4 sm:px-8 lg:pt-2">
        <div className="grid items-center gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:gap-16">
          <div className="max-w-xl">
            <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem] lg:text-[4.15rem]">
              Start for <span className="text-grape">free</span>.
            </h1>
            <p className="mt-6 max-w-md text-[17px] leading-relaxed text-muted sm:text-[18px]">
              No credit card required.
            </p>
          </div>
          <Suspense
            fallback={
              <div className="mx-auto h-64 w-full max-w-[440px] animate-pulse rounded-[28px] bg-white/80 ring-1 ring-black/[0.03]" />
            }
          >
            <SignupForm />
          </Suspense>
        </div>
      </section>
    </PageShell>
  );
}
