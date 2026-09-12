import { CopyCommand } from "./copy-command";

export function Install() {
  return (
    <section
      id="install"
      className="mx-auto w-full max-w-6xl scroll-mt-24 px-6 pb-20 sm:px-8"
    >
      <div className="grid items-center gap-10 rounded-[32px] bg-white px-8 py-12 shadow-[0_8px_40px_rgba(76,29,149,0.06)] ring-1 ring-black/[0.03] lg:grid-cols-[1fr_1.1fr] lg:px-14 lg:py-16">
        <div>
          <p className="text-[12px] font-semibold tracking-[0.18em] text-grape uppercase">
            Phase 1
          </p>
          <h2 className="mt-3 text-[2.15rem] font-bold tracking-[-0.035em] text-ink sm:text-[2.5rem]">
            Install on this machine.
          </h2>
          <p className="mt-4 max-w-md text-[16px] leading-relaxed text-muted">
            Shared hooks land in Claude and Cursor settings. No plugin
            marketplace. Then backfill what is already on disk.
          </p>
        </div>
        <div className="space-y-3">
          <CopyCommand command="./install.sh --no-plugin-manager" />
          <CopyCommand command="bin/ardoise status --json" />
          <CopyCommand command="bin/ardoise statement 2026-09" />
        </div>
      </div>
    </section>
  );
}
