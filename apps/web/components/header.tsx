import { SlateMark } from "./mark";

const nav = [
  { href: "https://github.com/clouvelai/ardoise", label: "GitHub" },
  { href: "#privacy", label: "Privacy" },
];

export function Header() {
  return (
    <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 sm:px-8">
      <a href="#top" className="flex items-center gap-2.5 text-ink">
        <SlateMark className="h-7 w-7" />
        <span className="text-[17px] font-semibold tracking-tight">
          ardoise
        </span>
      </a>
      <nav className="flex items-center gap-6 sm:gap-8">
        {nav.map((item) => (
          <a
            key={item.href}
            href={item.href}
            className="hidden text-[15px] font-medium text-ink/80 transition hover:text-ink sm:inline"
            {...(item.href.startsWith("http")
              ? { target: "_blank", rel: "noreferrer" }
              : {})}
          >
            {item.label}
          </a>
        ))}
        <a
          href="#install"
          className="rounded-full bg-white px-5 py-2 text-[15px] font-semibold text-ink shadow-[0_1px_2px_rgba(23,20,31,0.06)] ring-1 ring-black/5 transition hover:bg-mist"
        >
          Get started
          <span aria-hidden className="ml-1.5">
            →
          </span>
        </a>
      </nav>
    </header>
  );
}
