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
        stroke="#7C5CFF"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Mascot({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 200 220"
      preserveAspectRatio="xMidYMax meet"
      className={className}
      aria-hidden
      fill="none"
    >
      <path
        d="M62 150c-22 8-38 28-28 46 3 5 11 4 13-2 4-12 10-20 22-26"
        fill="#8B6CE8"
      />
      <ellipse cx="32" cy="190" rx="14" ry="12" fill="#A78BFA" />
      <ellipse cx="26" cy="186" rx="6" ry="5" fill="#C4B5FD" />

      <ellipse cx="70" cy="184" rx="28" ry="24" fill="#8B6CE8" />
      <ellipse cx="130" cy="184" rx="28" ry="24" fill="#8B6CE8" />
      <ellipse cx="100" cy="168" rx="50" ry="40" fill="#A78BFA" />
      <ellipse cx="100" cy="176" rx="32" ry="28" fill="#F4F0FC" />

      <ellipse cx="80" cy="206" rx="18" ry="13" fill="#C4B5FD" />
      <ellipse cx="120" cy="206" rx="18" ry="13" fill="#C4B5FD" />
      <ellipse cx="80" cy="208" rx="12" ry="8" fill="#F8F4FF" />
      <ellipse cx="120" cy="208" rx="12" ry="8" fill="#F8F4FF" />
      <ellipse cx="80" cy="210" rx="4.4" ry="3.2" fill="#E8A878" />
      <ellipse cx="120" cy="210" rx="4.4" ry="3.2" fill="#E8A878" />
      <ellipse cx="72" cy="205" rx="2.2" ry="2.6" fill="#E8A878" />
      <ellipse cx="80" cy="203" rx="2.2" ry="2.6" fill="#E8A878" />
      <ellipse cx="88" cy="205" rx="2.2" ry="2.6" fill="#E8A878" />
      <ellipse cx="112" cy="205" rx="2.2" ry="2.6" fill="#E8A878" />
      <ellipse cx="120" cy="203" rx="2.2" ry="2.6" fill="#E8A878" />
      <ellipse cx="128" cy="205" rx="2.2" ry="2.6" fill="#E8A878" />

      <circle cx="52" cy="86" r="30" fill="#8B6CE8" />
      <circle cx="148" cy="86" r="30" fill="#8B6CE8" />
      <circle cx="64" cy="52" r="26" fill="#9D7EF0" />
      <circle cx="136" cy="52" r="26" fill="#9D7EF0" />
      <circle cx="100" cy="42" r="28" fill="#A78BFA" />
      <circle cx="38" cy="108" r="20" fill="#9D7EF0" />
      <circle cx="162" cy="108" r="20" fill="#9D7EF0" />
      <circle cx="56" cy="128" r="16" fill="#B8A0F8" />
      <circle cx="144" cy="128" r="16" fill="#B8A0F8" />
      <circle cx="100" cy="34" r="10" fill="#C4B5FD" />

      <ellipse cx="62" cy="40" rx="16" ry="18" fill="#A78BFA" />
      <ellipse cx="138" cy="40" rx="16" ry="18" fill="#A78BFA" />
      <ellipse cx="62" cy="43" rx="8.5" ry="10" fill="#F3C4C8" />
      <ellipse cx="138" cy="43" rx="8.5" ry="10" fill="#F3C4C8" />

      <circle cx="100" cy="92" r="46" fill="#C4B5FD" />
      <ellipse cx="100" cy="102" rx="34" ry="30" fill="#F8F4FF" />

      <ellipse cx="70" cy="108" rx="11" ry="7" fill="#F4C4D0" opacity="0.75" />
      <ellipse cx="130" cy="108" rx="11" ry="7" fill="#F4C4D0" opacity="0.75" />

      <ellipse cx="82" cy="90" rx="8.5" ry="10.5" fill="#1F1633" />
      <ellipse cx="118" cy="90" rx="8.5" ry="10.5" fill="#1F1633" />
      <circle cx="79" cy="86" r="3" fill="white" />
      <circle cx="115" cy="86" r="3" fill="white" />
      <circle cx="85" cy="94" r="1.3" fill="white" opacity="0.75" />
      <circle cx="121" cy="94" r="1.3" fill="white" opacity="0.75" />

      <ellipse cx="100" cy="112" rx="5.6" ry="4.2" fill="#E8A070" />
      <path
        d="M100 116.2v3.2"
        stroke="#D48960"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path
        d="M88 124c4 4.6 8 6.4 12 6.4s8-1.8 12-6.4"
        stroke="#5B21B6"
        strokeWidth="2.2"
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
