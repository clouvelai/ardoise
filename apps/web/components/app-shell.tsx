"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { SlateMark } from "./mark";
import { clearSession, getSession } from "@/lib/saas-session";

const links = [
  { href: "/app", label: "Ledger" },
  { href: "/app/statement", label: "Statement" },
  { href: "/app/settings", label: "Settings" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    const session = getSession();
    if (!session) {
      router.replace("/signup?next=/app");
      return;
    }
    setEmail(session.email);
  }, [router]);

  if (!email) {
    return (
      <div className="flex min-h-svh items-center justify-center text-[15px] text-muted">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 sm:px-8">
        <Link href="/app" className="flex items-center gap-2.5 text-ink">
          <SlateMark className="h-7 w-7" />
          <span className="text-[17px] font-semibold tracking-tight">ardoise</span>
        </Link>
        <nav className="flex items-center gap-4 sm:gap-6">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={
                pathname === link.href
                  ? "text-[15px] font-semibold text-ink"
                  : "text-[15px] font-medium text-ink/70 transition hover:text-ink"
              }
            >
              {link.label}
            </Link>
          ))}
          <button
            type="button"
            className="text-[15px] font-medium text-ink/70 transition hover:text-ink"
            onClick={() => {
              clearSession();
              router.push("/");
            }}
          >
            Sign out
          </button>
        </nav>
      </header>
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 pb-16 sm:px-8">
        {children}
      </main>
    </div>
  );
}
