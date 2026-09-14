import {
  INSTALL_ONE_LINER,
  INSTALL_RELEASE_URL,
  INSTALL_SHA256,
  INSTALL_TAG,
  INSTALL_VERIFY,
} from "@/lib/install";

export function Install() {
  return (
    <section
      id="install"
      aria-labelledby="install-heading"
      className="mx-auto w-full max-w-3xl scroll-mt-24 px-6 pb-16 sm:px-8"
    >
      <h2
        id="install-heading"
        className="text-[11px] font-semibold tracking-[0.22em] text-muted/80 uppercase"
      >
        Install
      </h2>
      <p className="mt-3 text-[13px] leading-relaxed text-muted">
        Pin{" "}
        <a
          href={INSTALL_RELEASE_URL}
          className="underline decoration-black/10 underline-offset-2 transition hover:text-ink"
          target="_blank"
          rel="noreferrer"
        >
          {INSTALL_TAG}
        </a>
        . No API keys.
      </p>
      <pre className="mt-4 overflow-x-auto whitespace-pre-wrap break-all rounded-xl bg-white/60 px-4 py-3 text-[12px] leading-relaxed text-ink/75 ring-1 ring-black/[0.04]">
        <code>{INSTALL_ONE_LINER}</code>
      </pre>
      <p className="mt-3 break-all font-mono text-[11px] leading-relaxed text-muted/80">
        SHA-256 {INSTALL_SHA256}
      </p>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-all rounded-xl bg-white/40 px-4 py-3 text-[11px] leading-relaxed text-ink/60 ring-1 ring-black/[0.03]">
        <code>{INSTALL_VERIFY}</code>
      </pre>
      <ol className="mt-5 list-decimal space-y-1 pl-5 text-[13px] text-muted">
        <li>
          <code className="text-[12px] text-ink/70">ardoise backfill</code>
        </li>
        <li>
          <code className="text-[12px] text-ink/70">ardoise status</code>
        </li>
        <li>Open Claude Code or Cursor once</li>
      </ol>
    </section>
  );
}
