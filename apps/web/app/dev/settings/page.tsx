"use client";

import Link from "next/link";
import { useState } from "react";
import { SlateMark } from "@/components/mark";
import { SettingsWorkspace } from "@/components/settings-view";

const PREVIEW_TOKEN = "ard_preview_once";

export default function SettingsMintPreviewPage() {
  const [token, setToken] = useState<string | null>(null);

  return (
    <div className="flex min-h-svh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 sm:px-8">
        <Link href="/app" className="flex items-center gap-2.5 text-ink">
          <SlateMark className="h-7 w-7" />
          <span className="text-[17px] font-semibold tracking-tight">ardoise</span>
        </Link>
        <nav className="flex items-center gap-4 sm:gap-6">
          <span className="text-[15px] font-medium text-ink/70">Ledger</span>
          <span className="text-[15px] font-medium text-ink/70">Statement</span>
          <span className="text-[15px] font-semibold text-ink">Settings</span>
        </nav>
      </header>
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 pb-16 sm:px-8">
        <SettingsWorkspace
          plan="free"
          token={token}
          pending={false}
          onMint={() => setToken(PREVIEW_TOKEN)}
        />
      </main>
    </div>
  );
}
