import Image from "next/image";

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
    <Image
      src="/mascot-cub.png"
      alt=""
      width={400}
      height={512}
      priority
      draggable={false}
      aria-hidden
      className={`object-contain object-bottom ${className ?? ""}`}
    />
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
