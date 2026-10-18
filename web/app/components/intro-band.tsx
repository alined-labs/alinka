import { ArrowRight, BookOpen } from "lucide-react";
import { Link } from "react-router";

import { useMotionOK } from "~/lib/motion";
import { useView } from "~/lib/view";

/**
 * The way in for a first visit: what Alinka does in one sentence (Lane A's copy, A11) and where
 * to start. Probar always runs in the sandbox; Cómo funciona keeps the view, like the nav. It sits on the Tablero, away from the canonical/sandbox switch in the header.
 */
export function IntroBand() {
  const motion = useMotionOK();
  const [view] = useView();
  return (
    <section
      aria-label="Qué es Alinka"
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-xl border border-line bg-surface px-4 py-3 max-md:px-3 max-md:py-2"
    >
      <p className="m-0 max-w-prose text-ink max-md:text-small">Alinka paga facturas sin dejar que un modelo de IA mueva el dinero.</p>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Link to="/probar" className="ak-btn ak-btn--secondary ak-btn--sm" viewTransition={motion}>
          Pruébalo con una factura
          <ArrowRight aria-hidden className="ak-icon" />
        </Link>
        <Link to={{ pathname: "/como-funciona", search: view === "canonical" ? "?vista=canonica" : "" }} className="ak-btn ak-btn--ghost ak-btn--sm" viewTransition={motion}>
          <BookOpen aria-hidden className="ak-icon" />
          Cómo funciona
        </Link>
      </div>
    </section>
  );
}
