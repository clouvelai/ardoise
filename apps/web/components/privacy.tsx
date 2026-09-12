export function Privacy() {
  return (
    <section
      id="privacy"
      className="mx-auto w-full max-w-3xl scroll-mt-24 px-6 pb-20 text-center sm:px-8"
    >
      <h2 className="text-[1.8rem] font-semibold tracking-tight text-ink">
        Prompts stay off the slate.
      </h2>
      <p className="mt-4 text-[16px] leading-relaxed text-muted">
        Capture scrubs message bodies, tool I/O, and credentials before enqueue
        or insert. The ledger keeps model, tokens, timestamps, ids, and
        owner/repo — never prompts, never keys.
      </p>
    </section>
  );
}
