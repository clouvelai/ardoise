const marks = [
  "Claude Code",
  "Cursor",
  "SQLite",
  "Python 3",
  "stdlib only",
];

export function Trust() {
  return (
    <section
      aria-label="What stays local"
      className="mx-auto w-full max-w-6xl px-6 pb-10 pt-4 sm:px-8 sm:pb-14"
    >
      <p className="text-center text-[11px] font-semibold tracking-[0.22em] text-muted/80 uppercase">
        Nothing leaves the machine
      </p>
      <ul className="mt-5 flex flex-wrap items-center justify-center gap-x-10 gap-y-3 text-[15px] font-semibold tracking-tight text-ink/35 sm:gap-x-14 sm:text-[17px]">
        {marks.map((name) => (
          <li key={name}>{name}</li>
        ))}
      </ul>
    </section>
  );
}
