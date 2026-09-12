const items = [
  {
    title: "Local first",
    body: "The ledger lives at ~/.ardoise/ledger.db. Phase 1 never opens a port or calls a network.",
  },
  {
    title: "Deduped",
    body: "Streaming rows share message.id and requestId. Ardoise keeps the highest output_tokens.",
  },
  {
    title: "Statements",
    body: "One month becomes Markdown, HTML, and CSV. Project is the git remote owner/repo.",
  },
];

export function Features() {
  return (
    <section className="mx-auto w-full max-w-6xl px-6 py-20 sm:px-8 sm:py-24">
      <div className="grid gap-12 md:grid-cols-3 md:gap-10">
        {items.map((item) => (
          <div key={item.title} className="max-w-sm">
            <h2 className="text-[1.65rem] font-semibold tracking-tight text-ink">
              {item.title}
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              {item.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
