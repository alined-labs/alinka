// The Alinka wordmark. Stroke follows currentColor, so it takes --ink in both themes.
export function AlinkaLogo({ className, title = "alinka" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="-3 -2 131 48" role="img" aria-label={title} className={className}>
      <title>{title}</title>
      <g fill="none" stroke="currentColor" strokeWidth={5} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="23" r="9" />
        <path d="M21 14 V32" />
        <path d="M3 41 H122" />
        <path d="M32 4 V32" />
        <path d="M42 14 V32" />
        <circle cx="42" cy="5.6" r="3" fill="currentColor" stroke="none" />
        <path d="M52 14 V32 M52 23 A9 9 0 0 1 70 23 V32" />
        <path d="M81 4 V32 M93 14 L81 26 M85.6 21.6 L94 32" />
        <circle cx="113" cy="23" r="9" />
        <path d="M122 14 V32" />
      </g>
    </svg>
  );
}
