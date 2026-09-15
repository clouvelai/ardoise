import Link from "next/link";

/** Shared next-step list for empty Ledger and empty Statement. */
export function ConnectLaptopSteps() {
  return (
    <>
      <ol className="mt-4 list-decimal space-y-2 pl-5 text-[15px] text-muted">
        <li>
          Install the CLI from{" "}
          <Link href="/app/settings" className="text-ink underline">
            Settings
          </Link>
        </li>
        <li>
          <code className="text-[13px] text-ink/80">ardoise backfill</code> then{" "}
          <code className="text-[13px] text-ink/80">ardoise login</code>
        </li>
        <li>
          <code className="text-[13px] text-ink/80">ardoise sync</code>
        </li>
      </ol>
      <p className="mt-4 text-[13px] text-muted">
        Claude Code JSONL usually meters on first backfill. Cursor Individual
        often stays $0 until a usage-shaped hook or Team Admin key lands.
      </p>
    </>
  );
}
