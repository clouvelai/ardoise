const steps = [
  {
    title: "Capture",
    body: "Hooks and logs flow into a local SQLite ledger—no prompts, no credentials.",
  },
  {
    title: "Attribute",
    body: "Every token maps to a project via git remote. See where spend actually went.",
  },
  {
    title: "Statement",
    body: "Month-ready MD, HTML, and CSV. Local first; invoice-grade when you need it.",
  },
];

const features = [
  "Claude Code + Cursor",
  "SQLite on your machine",
  "Project-level attribution",
  "Privacy by default",
];

const proofPlaceholders = [
  "Acme Labs",
  "Northwind AI",
  "Helix Studio",
  "Orbit Systems",
  "Cedar Works",
  "Prism Co",
];

export default function Home() {
  return (
    <div className="flex min-h-full flex-col bg-gradient-to-b from-purple-50 to-white text-neutral-900">
      {/* Nav */}
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600 text-sm font-bold text-white">
            A
          </span>
          <span className="text-lg font-semibold tracking-tight">ardoise</span>
        </div>
        <nav className="flex items-center gap-6 text-sm text-neutral-600">
          <a href="#how" className="hidden hover:text-neutral-900 sm:inline">
            How it works
          </a>
          <a href="#early-access" className="hidden hover:text-neutral-900 sm:inline">
            Early access
          </a>
          <a
            href="#early-access"
            className="rounded-full border border-neutral-900/15 bg-white px-4 py-2 font-medium text-neutral-900 shadow-sm transition hover:border-neutral-900/30"
          >
            Get early access →
          </a>
        </nav>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="mx-auto grid w-full max-w-6xl items-center gap-12 px-6 pb-20 pt-10 md:grid-cols-2 md:gap-16 md:pb-28 md:pt-16">
          <div className="max-w-xl">
            <h1 className="text-4xl font-bold tracking-tight text-neutral-900 sm:text-5xl md:text-[3.25rem] md:leading-[1.1]">
              Attribute every AI dollar{" "}
              <span className="text-violet-600">to a project.</span>
            </h1>
            <p className="mt-5 max-w-md text-lg leading-relaxed text-neutral-500">
              Ardoise is a local spend ledger for Claude Code and Cursor.
              Capture usage first—invoice-grade statements when you&apos;re ready.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <a
                id="early-access"
                href="mailto:hello@ardoise.ai?subject=Early%20access"
                className="inline-flex items-center rounded-full bg-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-600/25 transition hover:bg-violet-700"
              >
                Get early access →
              </a>
              <a
                href="#how"
                className="text-sm font-medium text-neutral-600 hover:text-neutral-900"
              >
                See how it works
              </a>
            </div>
            <p className="mt-4 text-sm text-neutral-400">
              Local-first · Python stdlib core · Nothing leaves your machine
            </p>
          </div>

          {/* Floating card */}
          <div className="relative mx-auto w-full max-w-md md:mx-0 md:justify-self-end">
            <div className="absolute -right-3 -top-3 z-10 rounded-full bg-violet-100 px-3 py-1 text-xs font-medium text-violet-700 shadow-sm">
              live ledger
            </div>
            <div className="rounded-2xl border border-violet-100/80 bg-white p-6 shadow-2xl shadow-violet-200/40">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-neutral-400">
                    This month
                  </p>
                  <p className="mt-1 text-2xl font-bold tracking-tight">$184.62</p>
                </div>
                <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700">
                  3 projects
                </span>
              </div>
              <div className="space-y-3">
                {[
                  { name: "clouvelai/ardoise", amount: "$92.40", pct: "50%" },
                  { name: "acme/agent-runtime", amount: "$61.18", pct: "33%" },
                  { name: "personal/notes", amount: "$31.04", pct: "17%" },
                ].map((row) => (
                  <div key={row.name}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className="truncate font-medium text-neutral-700">
                        {row.name}
                      </span>
                      <span className="ml-3 shrink-0 text-neutral-500">
                        {row.amount}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-violet-50">
                      <div
                        className="h-full rounded-full bg-violet-500"
                        style={{ width: row.pct }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-5 rounded-xl border border-dashed border-violet-200 bg-violet-50/50 px-4 py-3 text-center text-sm text-violet-700">
                Statement ready · Sep 2026
              </div>
            </div>
          </div>
        </section>

        {/* 3-step */}
        <section id="how" className="mx-auto w-full max-w-6xl px-6 py-16 md:py-20">
          <p className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400">
            How it works
          </p>
          <h2 className="mt-3 text-center text-2xl font-bold tracking-tight sm:text-3xl">
            Capture → Attribute → Statement
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-3">
            {steps.map((step, i) => (
              <div key={step.title} className="text-center sm:text-left">
                <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-violet-100 text-sm font-bold text-violet-700 sm:mx-0">
                  {i + 1}
                </div>
                <h3 className="mt-4 text-lg font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-neutral-500">
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Tiny feature strip */}
        <section className="border-y border-violet-100/80 bg-white/60">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-10 gap-y-3 px-6 py-6 text-sm font-medium text-neutral-600">
            {features.map((f) => (
              <span key={f} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-violet-500" />
                {f}
              </span>
            ))}
          </div>
        </section>

        {/* Social proof placeholders */}
        <section className="mx-auto w-full max-w-6xl px-6 py-16 md:py-20">
          <p className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400">
            Built for teams who ship with AI
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-x-10 gap-y-4 opacity-40 grayscale">
            {proofPlaceholders.map((name) => (
              <span
                key={name}
                className="text-sm font-semibold tracking-wide text-neutral-700 sm:text-base"
              >
                {name}
              </span>
            ))}
          </div>
        </section>

        {/* Final CTA */}
        <section className="mx-auto w-full max-w-3xl px-6 pb-24 pt-4 text-center">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Know where your AI budget goes.
          </h2>
          <p className="mx-auto mt-4 max-w-md text-neutral-500">
            Early access opens soon. Local ledger today—sharable statements when
            you need them.
          </p>
          <a
            href="mailto:hello@ardoise.ai?subject=Early%20access"
            className="mt-8 inline-flex items-center rounded-full bg-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-600/25 transition hover:bg-violet-700"
          >
            Get early access →
          </a>
        </section>
      </main>

      <footer className="border-t border-violet-100/80 py-8 text-center text-sm text-neutral-400">
        © {new Date().getFullYear()} Ardoise · Local AI spend ledger
      </footer>
    </div>
  );
}
