import Link from "next/link";

export function Footer() {
  return (
    <footer className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-4 px-6 py-10 text-[13px] text-muted sm:flex-row sm:px-8">
      <p>© 2026 clouvelai · MIT</p>
      <div className="flex items-center gap-6">
        <a
          href="https://github.com/clouvelai/ardoise"
          className="transition hover:text-ink"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>
        <Link href="/pricing" className="transition hover:text-ink">
          Pricing
        </Link>
        <Link href="/#privacy" className="transition hover:text-ink">
          Privacy
        </Link>
        <a
          href="https://github.com/clouvelai/ardoise#install"
          className="transition hover:text-ink"
          target="_blank"
          rel="noreferrer"
        >
          Install
        </a>
      </div>
    </footer>
  );
}
