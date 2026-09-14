"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function BillingSuccessPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/app");
  }, [router]);
  return (
    <div className="flex min-h-svh items-center justify-center text-[15px] text-muted">
      Taking you to your ledger…
    </div>
  );
}
