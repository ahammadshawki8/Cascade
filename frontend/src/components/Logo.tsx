interface LogoProps {
  /** Height of the mark in px. The wordmark scales from this. */
  size?: number;
  /** Render the wordmark alongside the mark. */
  wordmark?: boolean;
  className?: string;
}

/**
 * Cascade brand mark.
 *
 * Three descending pills — a cascade, and also the mechanism: a change at the
 * top propagating down a dependency chain. Opacity falls off with each step so
 * the descent reads as propagation rather than as decoration.
 *
 * Monochrome by design. It inherits `currentColor`, so one component serves the
 * dark app chrome, the docs header, and any light surface without a variant.
 * The favicon at `app/icon.svg` is the same geometry with the accent hard-coded,
 * because a file the browser fetches directly cannot inherit anything.
 */
export function Logo({ size = 24, wordmark = false, className }: LogoProps) {
  const mark = (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      fill="none"
      aria-hidden={wordmark ? "true" : undefined}
      role={wordmark ? undefined : "img"}
      aria-label={wordmark ? undefined : "Cascade"}
      style={{ flexShrink: 0, display: "block" }}
    >
      <rect x="4" y="6" width="17" height="5" rx="2.5" fill="currentColor" />
      <rect
        x="7.5"
        y="13.5"
        width="17"
        height="5"
        rx="2.5"
        fill="currentColor"
        opacity="0.72"
      />
      <rect
        x="11"
        y="21"
        width="17"
        height="5"
        rx="2.5"
        fill="currentColor"
        opacity="0.44"
      />
    </svg>
  );

  if (!wordmark) {
    return className ? <span className={className}>{mark}</span> : mark;
  }

  return (
    <span
      className={className}
      style={{ display: "inline-flex", alignItems: "center", gap: size * 0.4 }}
    >
      {mark}
      <span
        style={{
          fontSize: size * 0.62,
          fontWeight: 600,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          lineHeight: 1,
        }}
      >
        Cascade
      </span>
    </span>
  );
}
