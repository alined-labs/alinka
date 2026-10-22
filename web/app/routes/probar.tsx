import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Play, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { ChannelIcon, CHANNEL } from "~/components/badges";
import { PageViewer, type ViewerPage } from "~/components/page-viewer";
import { PipelineFlow } from "~/components/pipeline-flow";
import { TrySteps } from "~/components/try-steps";
import { FROZEN } from "~/lib/frozen";
import { useMotionOK } from "~/lib/motion";
import { seo } from "~/lib/seo";
import type { DoneEvent, TraceStep } from "~/lib/trace";
import {
  HOLD_MS,
  KIND_ES,
  paced,
  pageUrl,
  type RunInput,
  type Sample,
  samplesQuery,
  startTry,
  subscribe,
  TRY_MOCK,
  TryError,
  type UploadLimits,
} from "~/lib/try";
import { BOARD_PATH } from "~/lib/view";
import "~/styles/probar.css";

export function meta() {
  return seo({
    path: "/probar",
    title: "Probar",
    description:
      "Elige una factura ficticia y mira a Alinka trabajar paso a paso: lo que estaba oculto, lo que la IA leyó con sus citas, las 16 reglas y la decisión.",
  });
}

type Run = {
  label: string;
  sample: Sample | null;
  steps: TraceStep[];
  done: DoneEvent | null;
  error: string | null;
  finished: boolean;
};

/** Starts a run and follows its events, showing each one at least HOLD_MS so a replay stays readable. */
function useRun() {
  const [run, setRun] = useState<Run | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const inbox = useRef<{ steps: TraceStep[]; end: { done?: DoneEvent; error?: string } | null }>({ steps: [], end: null });
  const stop = useRef<() => void>(() => {});

  useEffect(() => {
    if (!run || run.finished) return;
    let shown = run.steps.length;
    let last = 0;
    const t = setInterval(() => {
      const now = performance.now();
      const next = paced(inbox.current.steps.length, shown, last, now);
      if (next !== shown) {
        shown = next;
        last = now;
        const steps = inbox.current.steps.slice(0, shown);
        setRun((r) => (r ? { ...r, steps } : r));
      } else if (shown === inbox.current.steps.length && inbox.current.end && now - last >= HOLD_MS) {
        const end = inbox.current.end;
        setRun((r) => (r ? { ...r, done: end.done ?? null, error: end.error ?? null, finished: true } : r));
      }
    }, 50);
    return () => clearInterval(t);
  }, [run?.finished, run?.label]);

  useEffect(() => () => stop.current(), []);

  const start = useCallback(async (input: RunInput, label: string, sample: Sample | null) => {
    stop.current();
    setStartError(null);
    setStarting(true);
    try {
      const job = await startTry(input);
      inbox.current = { steps: [], end: null };
      setRun({ label: `${label} · ${job.job_id}`, sample, steps: [], done: null, error: null, finished: false });
      stop.current = subscribe(job.events_url, {
        step: (s) => inbox.current.steps.push(s),
        done: (d) => (inbox.current.end = { done: d }),
        error: (m) => (inbox.current.end = { error: m }),
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "No se pudo iniciar la ejecución.";
      const retry = e instanceof TryError && e.retryAfter ? ` Intenta de nuevo en ${e.retryAfter} s.` : "";
      setStartError(msg + retry);
    } finally {
      setStarting(false);
    }
  }, []);

  return { run, start, starting, startError };
}

function SampleCard({ sample, busy, onRun }: { sample: Sample; busy: boolean; onRun: () => void }) {
  return (
    <li className="ak-card grid-rows-[auto_auto_auto_1fr_auto]">
      {sample.preview_url ? (
        <img src={sample.preview_url} alt="" loading="lazy" className="probar-thumb" width={300} height={388} />
      ) : (
        <div className="probar-thumb probar-thumb--none" aria-hidden>
          <ChannelIcon channel={sample.channel} />
        </div>
      )}
      <div className="ak-card__top">
        <span className="ak-card__who">{sample.title_es}</span>
        <span className={`probar-kind probar-kind--${sample.kind}`}>{KIND_ES[sample.kind]}</span>
      </div>
      <p className="ak-card__meta m-0">
        <ChannelIcon channel={sample.channel} />
        {CHANNEL[sample.channel].label} · {sample.pages} {sample.pages === 1 ? "página" : "páginas"}
      </p>
      <p className="ak-card__reason">{sample.hint_es}</p>
      <button type="button" className="ak-btn ak-btn--secondary ak-btn--sm justify-self-start" disabled={busy} onClick={onRun}>
        <Play aria-hidden className="ak-icon" />
        Probar esta factura
      </button>
    </li>
  );
}

function Dropzone({ limits, busy, onFile }: { limits: UploadLimits; busy: boolean; onFile: (f: File) => void }) {
  const [over, setOver] = useState(false);
  const accept = limits.types.map((t) => (t === "jpg" ? ".jpg,.jpeg" : `.${t}`)).join(",");
  return (
    <label
      className={`ak-drop${over ? " is-over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files[0];
        if (f && !busy) onFile(f);
      }}
    >
      <Upload aria-hidden className="ak-icon" />
      <strong>Sube tu propia factura</strong>
      <span>Sube solo facturas ficticias.</span>
      <span>
        {limits.types.map((t) => t.toUpperCase()).join(", ")} · hasta {limits.max_mb} MB y {limits.max_pages} páginas ·{" "}
        {limits.per_10_min} cada 10 minutos y {limits.per_day} al día · se borran a las {limits.keep_hours} horas
      </span>
      <input
        type="file"
        className="ak-sr"
        accept={accept}
        disabled={busy}
        onChange={(e) => {
          const f = e.currentTarget.files?.[0];
          e.currentTarget.value = "";
          if (f) onFile(f);
        }}
      />
    </label>
  );
}

const useSamples = () => useQuery(samplesQuery);

/** The run's page images; their size comes from the image itself once it loads. */
function usePages(run: Run | null): ViewerPage[] {
  const received = run?.steps.find((s) => s.step === "received" && s.status !== "running")?.data;
  const [sizes, setSizes] = useState<Record<string, [number, number]>>({});
  const urls: string[] = [];
  if (received) {
    for (let n = 1; n <= Math.max(1, Number(received.pages) || 1); n++) {
      // The mock has no sandbox pages: it shows the canonical sample's, when there is one.
      if (TRY_MOCK) {
        if (run?.sample?.preview_url) urls.push(run.sample.preview_url.replace("/pages/1", `/pages/${n}`));
      } else urls.push(pageUrl(received.invoice_id, n));
    }
  }
  const key = urls.join(" ");
  useEffect(() => {
    for (const u of urls) {
      if (sizes[u]) continue;
      const img = new Image();
      img.onload = () => setSizes((s) => ({ ...s, [u]: [img.naturalWidth, img.naturalHeight] }));
      img.src = u;
    }
  }, [key]);
  return urls.map((url, i) => ({ n: i + 1, url, width: sizes[url]?.[0] ?? 1275, height: sizes[url]?.[1] ?? 1650 }));
}

export default function Probar() {
  const samples = useSamples();
  const { run, start, starting, startError } = useRun();
  const [page, setPage] = useState(1);
  const [active, setActive] = useState<string | null>(null);
  const motion = useMotionOK();
  const runRef = useRef<HTMLElement>(null);
  const pages = usePages(run);
  const busy = starting || (run != null && !run.finished);

  const verify = run?.steps.find((s) => s.step === "verify" && s.status !== "running");
  const boxes = Object.entries((verify?.data.fields ?? {}) as Record<string, { boxes: { page: number; x0: number; y0: number; x1: number; y1: number }[] }>).flatMap(
    ([name, f]) => f.boxes.map((b, i) => ({ ...b, key: `${name}-${i}`, active: active === name })),
  );
  const read = run?.steps.find((s) => s.step === "read" && s.status !== "running");
  const mode = read?.data.mode as "replay" | "live" | undefined;

  const launch = (input: RunInput, label: string, sample: Sample | null) => {
    setPage(1);
    void start(input, label, sample);
  };

  // A new run scrolls into view once its section exists.
  useEffect(() => {
    if (run?.label) runRef.current?.scrollIntoView({ behavior: motion ? "smooth" : "auto", block: "start" });
  }, [run?.label]);

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="ak-h1">Probar</h1>
        <p className="ak-muted max-w-3xl">
          Elige una factura de muestra y mira a Alinka trabajar: lo que estaba oculto, lo que la IA leyó con la cita de cada dato,
          lo que comprobó el código, las 16 reglas y la decisión que queda en el registro. Todas las facturas son ficticias.
        </p>
      </header>

      <section aria-labelledby="muestras" className="ak-stack">
        <h2 id="muestras" className="ak-h2">
          Facturas de muestra
        </h2>
        {samples.isPending && (
          <div className="ak-skel" aria-label="Cargando muestras">
            <span />
            <span />
          </div>
        )}
        {samples.isError && (
          <p className="ak-banner ak-banner--error" role="alert">
            {samples.error.message}
          </p>
        )}
        {samples.data && (
          <ul className="probar-gallery m-0 list-none p-0">
            {samples.data.samples.map((s) => (
              <SampleCard key={s.id} sample={s} busy={busy} onRun={() => launch({ sampleId: s.id }, s.title_es, s)} />
            ))}
          </ul>
        )}
        {samples.data?.live_uploads && (
          <Dropzone limits={samples.data.upload_limits} busy={busy} onFile={(f) => launch({ file: f }, f.name, null)} />
        )}
        {startError && (
          <p className="ak-banner ak-banner--error" role="alert">
            {startError}
          </p>
        )}
      </section>

      {run && (
        <section ref={runRef} aria-labelledby="ejecucion" className="ak-stack scroll-mt-4">
          <div className="ak-row ak-between">
            <h2 id="ejecucion" className="ak-h2">
              {run.sample?.title_es ?? "Tu factura"}
            </h2>
            {mode && <span className="ak-rule">{mode === "live" ? "Lectura en vivo" : "Lectura grabada"}</span>}
          </div>
          <PipelineFlow mode="live" steps={run.steps} />
          {run.error && (
            <p className="ak-banner ak-banner--error" role="alert">
              {run.error}
            </p>
          )}
          {run.done && (
            <p className="ak-row" role="status">
              {/* The frozen demo's board is a recording, so a sample's new card never reaches it. */}
              {!FROZEN && (
                <Link to={{ pathname: BOARD_PATH, search: "" }} className="ak-btn ak-btn--secondary" viewTransition={motion}>
                  Ver en el tablero
                </Link>
              )}
              <Link to={run.done.href} className="ak-btn ak-btn--primary" viewTransition={motion}>
                Ver el detalle
                <ArrowRight aria-hidden className="ak-icon" />
              </Link>
            </p>
          )}
          <div className="probar-run">
            <div className="min-w-0">
              <TrySteps steps={run.steps} onActiveField={setActive} />
            </div>
            <div className="ak-detail__doc min-w-0">
              {pages.length > 0 ? (
                <PageViewer pages={pages} page={page} onPageChange={setPage} boxes={boxes} label={run.sample?.title_es ?? "tu factura"} />
              ) : (
                <p className="ak-muted">
                  {run.steps.some((x) => x.step === "received" && x.status !== "running")
                    ? "La imagen de la página no está disponible."
                    : "La imagen de la página aparece cuando llega el documento."}
                </p>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
