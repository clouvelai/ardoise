"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { getSession } from "@/lib/saas-session";

export function RequireSession({
  children,
  next = "/install",
}: {
  children: ReactNode;
  next?: "/install" | "/pricing";
}) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getSession()) {
      router.replace(`/signup?next=${next}`);
      return;
    }
    setReady(true);
  }, [next, router]);

  if (!ready) {
    return (
      <div
        className="mx-auto h-48 w-full max-w-3xl animate-pulse rounded-[28px] bg-white/80 ring-1 ring-black/[0.03]"
        aria-hidden
      />
    );
  }

  return children;
}
