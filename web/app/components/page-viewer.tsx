import { Dialog } from "@base-ui/react/dialog";
import { ChevronLeft, ChevronRight, Maximize2, Minus, Plus, X } from "lucide-react";
import { type PointerEvent as ReactPointerEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

import { boxStyle } from "~/lib/detail";

/*
 * A document page with its evidence boxes, and a full-screen viewer to read it closely.
 * Boxes are 0..1 of the page and placed with percentages, so they stay on their text at
 * every zoom. Shared with Probar (Lane B): keep the props generic.
 */

export type ViewerPage = { n: number; url: string; width: number; height: number };
export type ViewerBox = { key: string; page: number; x0: number; y0: number; x1: number; y1: number; active?: boolean };

export const ZOOM_MIN = 1;
export const ZOOM_MAX = 4;
const ZOOM_STEPS = [1, 1.5, 2, 3, 4];

export const clampZoom = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

/** The next step up or down from any zoom, pinch-made ones included. */
export function stepZoom(z: number, dir: 1 | -1) {
  const next = dir > 0 ? ZOOM_STEPS.find((s) => s > z + 1e-6) : [...ZOOM_STEPS].reverse().find((s) => s < z - 1e-6);
  return next ?? (dir > 0 ? ZOOM_MAX : ZOOM_MIN);
}

/** The page image at 1, 2 or 3 times its size, whichever keeps the text sharp on this screen. */
export function imageScale(displayWidth: number, naturalWidth: number, dpr: number): 1 | 2 | 3 {
  const need = (displayWidth * dpr) / Math.max(1, naturalWidth);
  return need <= 1 ? 1 : need <= 2 ? 2 : 3;
}

export function scaledUrl(url: string, scale: 1 | 2 | 3) {
  if (scale === 1) return url;
  const [path, query = ""] = url.split("?", 2);
  const params = new URLSearchParams(query);
  params.set("scale", String(scale));
  return `${path}?${params}`;
}

type Props = {
  pages: ViewerPage[];
  page: number;
  onPageChange: (n: number) => void;
  boxes: ViewerBox[];
  /** Names the document in alt text and labels, for example "la factura OCT-14". */
  label: string;
};

export function PageViewer({ pages, page, onPageChange, boxes, label }: Props) {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const current = pages.find((p) => p.n === page) ?? pages[0];
  if (!current) return <p className="ak-muted">Sin imágenes de página.</p>;
  const total = pages.length;
  const own = boxes.filter((b) => b.page === current.n);
  const alt = `Página ${current.n} de ${label}`;

  return (
    <section aria-label="Documento original">
      <div className="ak-doctools">
        <span>
          Página {current.n} de {total} · imagen del documento recibido
        </span>
        <span className="ak-row">
          <PageNav current={current.n} total={total} onPageChange={onPageChange} />
          <button type="button" className="ak-btn ak-btn--ghost ak-btn--sm" onClick={() => setOpen(true)}>
            <Maximize2 aria-hidden className="ak-icon" />
            Ampliar
          </button>
        </span>
      </div>
      {failed[current.n] ? (
        <p className="ak-banner ak-banner--demo">La imagen de esta página no está disponible.</p>
      ) : (
        <figure className="ak-page">
          <img
            src={current.url}
            width={current.width}
            height={current.height}
            alt={alt}
            onError={() => setFailed((f) => ({ ...f, [current.n]: true }))}
          />
          {own.map((b) => (
            <span key={b.key} className={`ak-box ${b.active ? "is-active" : ""}`} style={boxStyle(b)} aria-hidden />
          ))}
          <button
            type="button"
            className="absolute inset-0 cursor-zoom-in rounded-[inherit]"
            onClick={() => setOpen(true)}
            aria-label={`Ampliar la página ${current.n}`}
          />
        </figure>
      )}
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Backdrop className="ak-backdrop" />
          <Dialog.Popup className="fixed inset-0 grid grid-rows-[auto_1fr] bg-desk text-ink">
            {open && (
              <Viewer
                page={current}
                total={total}
                onPageChange={onPageChange}
                boxes={own}
                alt={alt}
                title={`Documento original de ${label}`}
              />
            )}
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}

function PageNav({ current, total, onPageChange, size = "sm" }: { current: number; total: number; onPageChange: (n: number) => void; size?: "sm" | "md" }) {
  if (total <= 1) return null;
  const cls = `ak-btn ak-btn--ghost ${size === "sm" ? "ak-btn--sm" : ""}`;
  return (
    <span className="ak-row">
      <button type="button" className={cls} onClick={() => onPageChange(current - 1)} disabled={current <= 1} aria-label="Página anterior">
        <ChevronLeft aria-hidden className="ak-icon" />
      </button>
      <button type="button" className={cls} onClick={() => onPageChange(current + 1)} disabled={current >= total} aria-label="Página siguiente">
        <ChevronRight aria-hidden className="ak-icon" />
      </button>
    </span>
  );
}

type Anchor = { fx: number; fy: number; ax: number; ay: number };

function Viewer({
  page,
  total,
  onPageChange,
  boxes,
  alt,
  title,
}: {
  page: ViewerPage;
  total: number;
  onPageChange: (n: number) => void;
  boxes: ViewerBox[];
  alt: string;
  title: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [sharp, setSharp] = useState<string | null>(null);
  const anchor = useRef<Anchor | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ dist: number; zoom: number } | null>(null);

  // Fit-to-width follows the window.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () => setFit(el.clientWidth - 32);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const width = fit * zoom;
  const height = (width * page.height) / Math.max(1, page.width);

  /** Zoom keeping the point under (ax, ay), in scroller coordinates, still. */
  const zoomTo = (next: number, at?: { ax: number; ay: number }) => {
    const el = scroller.current;
    const z = clampZoom(next);
    if (!el || z === zoom) return;
    const ax = at?.ax ?? el.clientWidth / 2;
    const ay = at?.ay ?? el.clientHeight / 2;
    anchor.current = { fx: (el.scrollLeft + ax) / Math.max(1, el.scrollWidth), fy: (el.scrollTop + ay) / Math.max(1, el.scrollHeight), ax, ay };
    setZoom(z);
  };

  useLayoutEffect(() => {
    const el = scroller.current;
    const a = anchor.current;
    if (!el || !a) return;
    el.scrollLeft = a.fx * el.scrollWidth - a.ax;
    el.scrollTop = a.fy * el.scrollHeight - a.ay;
    anchor.current = null;
  }, [zoom]);

  // A sharper image once the zoom settles; the base image stays underneath until it loads.
  const scale = imageScale(width, page.width, typeof window === "undefined" ? 1 : window.devicePixelRatio || 1);
  const want = scaledUrl(page.url, scale);
  useEffect(() => setSharp(null), [page.url]);

  // Ctrl + wheel (and trackpad pinch) zooms; a plain wheel scrolls, which pans.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomTo(zoom * Math.exp(-e.deltaY / 200), { ax: e.clientX - r.left, ay: e.clientY - r.top });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  // + - 0 work wherever focus is inside the viewer; Base UI handles Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "+" || e.key === "=") zoomTo(stepZoom(zoom, 1));
      else if (e.key === "-" || e.key === "_") zoomTo(stepZoom(zoom, -1));
      else if (e.key === "0") zoomTo(1);
      else return;
      e.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  const local = (e: { clientX: number; clientY: number }) => {
    const r = scroller.current!.getBoundingClientRect();
    return { ax: e.clientX - r.left, ay: e.clientY - r.top };
  };

  const onPointerDown = (e: ReactPointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()] as [{ x: number; y: number }, { x: number; y: number }];
      pinch.current = { dist: Math.hypot(a.x - b.x, a.y - b.y), zoom };
    }
  };

  const onPointerMove = (e: ReactPointerEvent) => {
    const prev = pointers.current.get(e.pointerId);
    const el = scroller.current;
    if (!prev || !el) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 1) {
      el.scrollLeft -= e.clientX - prev.x;
      el.scrollTop -= e.clientY - prev.y;
    } else if (pointers.current.size === 2 && pinch.current) {
      const [a, b] = [...pointers.current.values()] as [{ x: number; y: number }, { x: number; y: number }];
      const mid = local({ clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 });
      zoomTo((pinch.current.zoom * Math.hypot(a.x - b.x, a.y - b.y)) / Math.max(1, pinch.current.dist), mid);
    }
  };

  const onPointerUp = (e: ReactPointerEvent) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2">
        <Dialog.Title className="m-0 text-small font-semibold">
          {title} · página {page.n} de {total}
        </Dialog.Title>
        <Dialog.Description className="ak-sr">
          Arrastra o desplázate para mover la página. Teclas: más y menos para acercar o alejar, 0 para ajustar al ancho, Esc para cerrar.
        </Dialog.Description>
        <div className="ak-row flex-wrap">
          <PageNav current={page.n} total={total} onPageChange={onPageChange} size="md" />
          <button type="button" className="ak-btn ak-btn--ghost" onClick={() => zoomTo(stepZoom(zoom, -1))} disabled={zoom <= ZOOM_MIN} aria-label="Alejar">
            <Minus aria-hidden className="ak-icon" />
          </button>
          <button type="button" className="ak-btn ak-btn--ghost min-w-20 font-mono" onClick={() => zoomTo(1)} aria-label={`Ajustar al ancho (ahora ${Math.round(zoom * 100)}%)`}>
            {Math.round(zoom * 100)}%
          </button>
          <button type="button" className="ak-btn ak-btn--ghost" onClick={() => zoomTo(stepZoom(zoom, 1))} disabled={zoom >= ZOOM_MAX} aria-label="Acercar">
            <Plus aria-hidden className="ak-icon" />
          </button>
          <Dialog.Close className="ak-btn ak-btn--secondary">
            <X aria-hidden className="ak-icon" />
            Cerrar
          </Dialog.Close>
        </div>
      </div>
      <div
        ref={scroller}
        className="overflow-auto p-4 select-none touch-none cursor-grab active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        tabIndex={0}
        role="group"
        aria-label={`Página ${page.n}, al ${Math.round(zoom * 100)}% del ancho`}
      >
        {fit > 0 && (
          <div className="ak-page mx-auto" style={{ width, height }}>
            <img src={page.url} alt={alt} width={page.width} height={page.height} draggable={false} className="h-full" />
            {want !== page.url && (
              <img
                key={want}
                src={want}
                alt=""
                aria-hidden
                draggable={false}
                className={`absolute inset-0 h-full ${sharp === want ? "" : "invisible"}`}
                onLoad={() => setSharp(want)}
                onError={() => setSharp(null)}
              />
            )}
            {boxes.map((b) => (
              <span key={b.key} className={`ak-box ${b.active ? "is-active" : ""}`} style={boxStyle(b)} aria-hidden />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
