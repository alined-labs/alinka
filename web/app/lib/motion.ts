import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { flushSync } from "react-dom";

/*
 * View transitions, only where the browser has them and the visitor has not asked for
 * reduced motion. Otherwise every update simply applies at once.
 */

const REDUCE = "(prefers-reduced-motion: reduce)";

const supported = () => typeof document !== "undefined" && typeof document.startViewTransition === "function";
export const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia?.(REDUCE).matches === true;

export const canTransition = () => supported() && !prefersReducedMotion();

/** Re-renders when the reduced-motion preference changes; false while prerendering. */
export function useMotionOK(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia?.(REDUCE);
      mq?.addEventListener("change", onChange);
      return () => mq?.removeEventListener("change", onChange);
    },
    canTransition,
    () => false,
  );
}

let running = false;
let queued: (() => void) | null = null;

/**
 * Runs a state update inside a view transition, flushed synchronously so the new frame is captured.
 * Updates that arrive while one is animating wait for it and only the last runs, so a fast run
 * replay never cuts a morph short.
 */
export function withTransition(update: () => void) {
  if (!canTransition()) return update();
  if (running) {
    queued = update;
    return;
  }
  running = true;
  const t = document.startViewTransition(() => flushSync(update));
  // A skipped or aborted transition rejects these; the update itself has still been applied.
  t.ready.catch(() => undefined);
  t.updateCallbackDone.catch(() => undefined);
  t.finished
    .catch(() => undefined)
    .then(() => {
      running = false;
      const next = queued;
      queued = null;
      if (next) withTransition(next);
    });
}

/**
 * The value on screen. A new value whose key differs from the shown one arrives inside a view
 * transition; one with the same key (a refetch with nothing new) replaces it silently.
 */
export function useTransitionedValue<T>(value: T, key: (v: T) => string): T {
  const [shown, setShown] = useState(value);
  const shownRef = useRef(shown);
  shownRef.current = shown;
  const keyRef = useRef(key);
  keyRef.current = key;
  useEffect(() => {
    const prev = shownRef.current;
    if (prev === value) return;
    if (prev == null || value == null || keyRef.current(prev) === keyRef.current(value)) setShown(value);
    else withTransition(() => setShown(value));
  }, [value]);
  return shown;
}

/**
 * A view-transition-name for an invoice: "inv-" and its id, with every character that is not a
 * letter, digit or hyphen written as _<hex>_, so two different ids never share a name.
 */
export function invoiceTransitionName(id: string): string {
  return `inv-${id.replace(/[^A-Za-z0-9-]/g, (c) => `_${c.codePointAt(0)!.toString(16)}_`)}`;
}
