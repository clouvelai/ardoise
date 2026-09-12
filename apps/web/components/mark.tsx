export function SlateMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 28 28"
      className={className}
      aria-hidden
      fill="none"
    >
      <rect width="28" height="28" rx="8" fill="#17141F" />
      <path
        d="M7.5 19c2.9-5.8 10.1-5.8 13 0"
        stroke="#C4B5FD"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M9.5 12.25h9"
        stroke="#7C3AED"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Mascot({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 80 88"
      className={className}
      aria-hidden
      fill="none"
    >
      <ellipse cx="40" cy="84" rx="16" ry="3.2" fill="#5B21B6" opacity="0.12" />
      <path
        d="M18 48c0-14 10.5-24 24.5-24 9.2 0 17.2 5.2 21 13.2 2.6-1.4 6.6-1.2 8.8 1.6 2.4 3.1.6 7.4-2.8 8.8 1.8 3.4 2.4 7.4 1.4 11.4C67.2 73 55 80 41.2 80 26 80 18 68.6 18 56.2V48Z"
        fill="#6D28D9"
      />
      <path
        d="M28 62c2.4 8.6 12.8 13.2 22.4 8.4 6.4-3.2 9.6-9.4 8.6-15.6"
        fill="#7C3AED"
      />
      <ellipse cx="36" cy="58" rx="11" ry="13" fill="#EDE9FE" />
      <circle cx="44" cy="34" r="13" fill="#5B21B6" />
      <path d="M55.5 35.5 66 32.2l-8.2 10.4-2.3-7.1Z" fill="#F59E0B" />
      <circle cx="47.2" cy="32.2" r="4.1" fill="white" />
      <circle cx="48.3" cy="32.4" r="2.05" fill="#17141F" />
      <circle cx="49.1" cy="31.5" r="0.7" fill="white" />
      <path
        d="M40 17c1.2-6.4 5.6-9.4 8.8-8.6 1.4.4 2.2 2.2 1.4 4.2"
        stroke="#5B21B6"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <path
        d="M47 15.5c1.6-5.2 5.8-7.2 8.4-5.8 1.6.8 1.8 3.2.6 5.4"
        stroke="#6D28D9"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M26 72.5c2.2 3.4 1.4 6.2-1.2 7.2"
        stroke="#4C1D95"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M33 74c1.6 3.6.6 6.4-2 7.4"
        stroke="#4C1D95"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function FileGlyph({
  kind,
}: {
  kind: "claude" | "cursor";
}) {
  const stroke = kind === "claude" ? "#C2410C" : "#2563EB";
  const fill = kind === "claude" ? "#FFF7ED" : "#EFF6FF";
  return (
    <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
      <rect width="32" height="32" rx="8" fill={fill} />
      <path
        d="M11 9.5h7.2L21 13.2V22a1.5 1.5 0 0 1-1.5 1.5h-8.5A1.5 1.5 0 0 1 9.5 22V11A1.5 1.5 0 0 1 11 9.5Z"
        stroke={stroke}
        strokeWidth="1.5"
        fill="white"
      />
      <path d="M18 9.6V13h3.2" stroke={stroke} strokeWidth="1.5" />
    </svg>
  );
}
