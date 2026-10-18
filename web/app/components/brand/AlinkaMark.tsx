// The Alinka mark (the "a" on its baseline). Stroke follows currentColor.
export function AlinkaMark({ className, title = "alinka" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="-7 4.5 46 46" role="img" aria-label={title} className={className}>
      <title>{title}</title>
      <g fill="none" stroke="currentColor" strokeWidth={5} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="23" r="9" />
        <path d="M21 14 V32" />
        <path d="M3 41 H29" />
      </g>
    </svg>
  );
}
