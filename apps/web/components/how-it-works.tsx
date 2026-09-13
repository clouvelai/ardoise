"use client";

import {
  useWorkflowView,
  WorkflowCard,
  type WorkflowStep,
} from "./workflow-card";

const STEPS: {
  id: WorkflowStep;
  title: string;
  body: string;
}[] = [
  {
    id: "capture",
    title: "Capture usage",
    body: "Hooks from Claude Code + Cursor. Prompts never land in the ledger.",
  },
  {
    id: "ledger",
    title: "Ledger by project",
    body: "Deduped tokens → $ on this machine, per git remote.",
  },
  {
    id: "invoice",
    title: "Invoice when ready",
    body: "One month becomes MD / HTML / CSV. Invoice-grade later.",
  },
];

export function HowItWorks() {
  const { view, select } = useWorkflowView();

  return (
    <section
      id="how-it-works"
      aria-labelledby="how-it-works-heading"
      className="mx-auto w-full max-w-6xl scroll-mt-24 px-6 py-20 sm:px-8 sm:py-28"
    >
      <h2
        id="how-it-works-heading"
        className="text-center text-[2.35rem] font-bold leading-[1.08] tracking-[-0.04em] text-ink sm:text-[3rem] lg:text-[3.35rem]"
      >
        Ardoise makes spend{" "}
        <span className="text-grape">attributable</span>.
      </h2>

      <div className="mt-14 grid gap-16 lg:mt-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:items-start lg:gap-20">
        <ol className="space-y-12 lg:mt-[7.5rem] lg:space-y-14">
          {STEPS.map((item) => {
            const active = view === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => select(item.id)}
                  aria-current={active ? "step" : undefined}
                  className="group flex w-full gap-5 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-grape/35 focus-visible:ring-offset-4 focus-visible:ring-offset-mist"
                >
                  <span
                    aria-hidden
                    className={`w-[3px] shrink-0 self-stretch rounded-full transition-colors ${
                      active ? "bg-grape" : "bg-transparent"
                    }`}
                  />
                  <span className="min-w-0">
                    <span
                      className={`block text-[1.7rem] font-semibold tracking-tight transition-colors sm:text-[1.85rem] ${
                        active ? "text-ink" : "text-ink/35 group-hover:text-ink/55"
                      }`}
                    >
                      {item.title}
                    </span>
                    <span
                      className={`mt-2 block max-w-sm text-[15px] leading-relaxed transition-colors ${
                        active ? "text-muted" : "text-muted/45 group-hover:text-muted/70"
                      }`}
                    >
                      {item.body}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        <div className="pt-20 lg:pt-[7.25rem]">
          <WorkflowCard
            view={view}
            className="relative mx-auto w-full max-w-[440px]"
          />
        </div>
      </div>
    </section>
  );
}
