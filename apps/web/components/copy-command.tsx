"use client";

import { useState } from "react";

export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-[#17141F] px-5 py-4 text-left sm:flex-row sm:items-center sm:justify-between">
      <code className="overflow-x-auto font-mono text-[13px] leading-relaxed text-violet-100 sm:text-[14px]">
        {command}
      </code>
      <button
        type="button"
        onClick={onCopy}
        className="shrink-0 self-start rounded-full bg-white/10 px-3.5 py-1.5 text-[12px] font-semibold text-white transition hover:bg-white/16 sm:self-auto"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
