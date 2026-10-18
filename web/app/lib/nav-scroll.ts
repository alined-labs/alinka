import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";

/** Which edges of a sideways-scrolling row still hide links: "start", "end", both or none. */
export function fadeEdges(scrollLeft: number, scrollWidth: number, clientWidth: number): string | undefined {
  if (scrollWidth - clientWidth < 1) return undefined;
  const edges = [scrollLeft > 1 && "start", scrollLeft + clientWidth < scrollWidth - 1 && "end"].filter(Boolean);
  return edges.length ? edges.join(" ") : undefined;
}

/**
 * The header nav scrolls sideways on narrow screens: keep the current page's link in view and
 * report which edges hide more links, so they can fade.
 */
export function useNavScroll<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const { pathname } = useLocation();
  const [fade, setFade] = useState<string | undefined>();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setFade(fadeEdges(el.scrollLeft, el.scrollWidth, el.clientWidth));
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, []);

  useEffect(() => {
    const el = ref.current;
    const active = el?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!el || !active || el.scrollWidth <= el.clientWidth) return;
    // Scroll the nav only, never the page.
    const a = active.getBoundingClientRect();
    const n = el.getBoundingClientRect();
    if (a.left < n.left) el.scrollLeft -= n.left - a.left + 8;
    else if (a.right > n.right) el.scrollLeft += a.right - n.right + 8;
  }, [pathname]);

  return { ref, fade };
}
