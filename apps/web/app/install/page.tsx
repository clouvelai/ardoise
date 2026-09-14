import type { Metadata } from "next";
import { Install } from "@/components/install";
import { PageShell } from "@/components/page-shell";
import { RequireSession } from "@/components/require-session";

export const metadata: Metadata = {
  title: "Install — Ardoise",
  description: "Pin the CLI. Local ledger on your machine.",
};

export default function InstallPage() {
  return (
    <PageShell>
      <RequireSession>
        <section className="mx-auto w-full max-w-6xl px-6 pb-4 pt-4 sm:px-8 lg:pt-2">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-[-0.045em] text-ink sm:text-[3.6rem] lg:text-[4.15rem]">
            You’re <span className="text-grape">in</span>.
          </h1>
          <p className="mt-6 max-w-md text-[17px] leading-relaxed text-muted sm:text-[18px]">
            Local ledger stays on your machine.
          </p>
        </section>
        <Install />
      </RequireSession>
    </PageShell>
  );
}
