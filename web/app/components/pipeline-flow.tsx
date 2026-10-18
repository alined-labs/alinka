import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";

import { STATE_LABEL } from "~/lib/board";
import {
  DEMO_TRACE,
  type Flow,
  flowFromSteps,
  STAGES,
  type StageId,
  type StageState,
  STATE_WORD,
  stageSummary,
  type TraceStep,
} from "~/lib/trace";
import "~/styles/pipeline.css";

/*
 * The pipeline as an SVG: eight stages, connectors that carry the document, the 16 rule cells,
 * the decision stamp and the hash chain. "demo" plays DEMO_TRACE (scroll-driven where the browser
 * has view timelines, else autoplay once in view); "live" draws the step events it is given.
 * Under reduced motion it is static. The ordered list under it is the readable version.
 */

const REDUCE = "(prefers-reduced-motion: reduce)";
const NARROW = "(max-width: 640px)";
const DEMO_TICK_MS = 600;

function useMedia(query: string, server: boolean): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia?.(query);
      mq?.addEventListener("change", onChange);
      return () => mq?.removeEventListener("change", onChange);
    },
    () => window.matchMedia?.(query).matches ?? server,
    () => server,
  );
}

const scrollDriven = () => typeof CSS !== "undefined" && CSS.supports?.("animation-timeline: view()") === true;

const STAMP: Record<string, string> = { PAY: "Pagada", HOLD: "Frenada", ESCALATE: "Pendiente" };
const DECISION_CLASS: Record<string, string> = { PAY: "pagada", HOLD: "retenida", ESCALATE: "pendiente" };

type Geo = { x: number; y: number; w: number; h: number };

function geometry(vertical: boolean) {
  const at = (i: number): Geo => (vertical ? { x: 56, y: 44 + i * 84, w: 92, h: 64 } : { x: 60 + i * 120, y: 76, w: 92, h: 68 });
  return vertical ? { at, width: 320, height: 44 + 7 * 84 + 44 } : { at, width: 960, height: 176 };
}

function Glyph({ state, x, y }: { state: StageState; x: number; y: number }) {
  if (state === "done") return <path className="pf-glyph" d={`M${x - 9} ${y} l6 6 l12 -13`} />;
  if (state === "flagged")
    return (
      <g className="pf-glyph">
        <path d={`M${x} ${y - 11} v13`} />
        <circle cx={x} cy={y + 9} r={1.6} className="pf-dot" />
      </g>
    );
  if (state === "error") return <path className="pf-glyph" d={`M${x - 8} ${y - 8} l16 16 M${x + 8} ${y - 8} l-16 16`} />;
  if (state === "running")
    return (
      <g className="pf-running">
        {[-10, 0, 10].map((dx, k) => (
          <circle key={dx} cx={x + dx} cy={y} r={3} style={{ animationDelay: `${k * 160}ms` }} />
        ))}
      </g>
    );
  return null;
}

function RuleCells({ flow, g }: { flow: Flow; g: Geo }) {
  const size = 11;
  const gap = 3;
  const x0 = g.x - (4 * size + 3 * gap) / 2;
  const y0 = g.y - (4 * size + 3 * gap) / 2;
  return (
    <g>
      {Array.from({ length: 16 }, (_, j) => {
        const r = flow.rules[j];
        const cls = r ? `pf-cell pf-cell--${r.outcome}${r.security ? " pf-cell--sec" : ""}` : "pf-cell";
        return (
          <rect
            key={j}
            className={cls}
            x={x0 + (j % 4) * (size + gap)}
            y={y0 + Math.floor(j / 4) * (size + gap)}
            width={size}
            height={size}
            rx={2}
            style={{ "--j": j } as React.CSSProperties}
          >
            {r && <title>{`${r.rule} ${r.name_es}: ${r.sentence_es}`}</title>}
          </rect>
        );
      })}
    </g>
  );
}

function Stamp({ flow, g }: { flow: Flow; g: Geo }) {
  if (!flow.decision) return <Glyph state={flow.states.decide} x={g.x} y={g.y} />;
  return (
    <g transform={`rotate(-6 ${g.x} ${g.y})`}>
      <g className={`pf-stamp pf-stamp--${DECISION_CLASS[flow.decision]}`}>
        <rect x={g.x - 41} y={g.y - 13} width={82} height={26} rx={4} />
        <text x={g.x} y={g.y + 4.5} textAnchor="middle">
          {STAMP[flow.decision]}
        </text>
      </g>
    </g>
  );
}

function Chain({ flow, g }: { flow: Flow; g: Geo }) {
  const w = 15;
  const step = 19;
  const x0 = g.x - (4 * step - 4) / 2;
  return (
    <g>
      {[0, 1, 2, 3].map((k) => {
        const isNew = k === 3;
        if (isNew && !flow.record) return null;
        return (
          <rect
            key={k}
            className={isNew ? "pf-link pf-link--new" : "pf-link"}
            x={x0 + k * step}
            y={g.y - 5}
            width={w}
            height={10}
            rx={5}
          />
        );
      })}
      {flow.states.record === "running" && <Glyph state="running" x={g.x} y={g.y + 18} />}
    </g>
  );
}

function Diagram({ flow, vertical, titleId, descId }: { flow: Flow; vertical: boolean; titleId: string; descId: string }) {
  const { at, width, height } = geometry(vertical);
  const cur = flow.current ? STAGES.findIndex((s) => s.id === flow.current) : -1;
  const doc = cur >= 0 ? at(cur) : null;
  const desc = STAGES.map((s) => `${s.title}: ${STATE_WORD[flow.states[s.id]]}.`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="pf-svg" role="img" aria-labelledby={`${titleId} ${descId}`}>
      <title id={titleId}>Recorrido de la factura por Alinka</title>
      <desc id={descId}>{desc}</desc>
      {STAGES.slice(1).map((s, k) => {
        const a = at(k);
        const b = at(k + 1);
        const next = flow.states[s.id];
        const cls = next === "idle" ? "pf-conn" : next === "running" ? "pf-conn is-flowing" : "pf-conn is-done";
        const d = vertical ? `M${a.x} ${a.y + a.h / 2} V${b.y - b.h / 2}` : `M${a.x + a.w / 2} ${a.y} H${b.x - b.w / 2}`;
        return <path key={s.id} className={cls} d={d} style={{ "--i": k + 1 } as React.CSSProperties} />;
      })}
      {STAGES.map((s, i) => {
        const g = at(i);
        const state = flow.states[s.id];
        const words = s.title.split(" ");
        const lines = s.title.length > 12 && !vertical ? [words.slice(0, -1).join(" "), words.at(-1)!] : [s.title];
        return (
          <g key={s.id} className={`pf-stage is-${state} pf-stage--${s.id}`} style={{ "--i": i } as React.CSSProperties}>
            <rect className="pf-node" x={g.x - g.w / 2} y={g.y - g.h / 2} width={g.w} height={g.h} rx={10} />
            {s.id === "rules" ? (
              <RuleCells flow={flow} g={g} />
            ) : s.id === "decide" ? (
              <Stamp flow={flow} g={g} />
            ) : s.id === "record" ? (
              <Chain flow={flow} g={g} />
            ) : (
              <Glyph state={state} x={g.x} y={g.y} />
            )}
            {vertical ? (
              <text className="pf-label" x={g.x + g.w / 2 + 16} y={g.y - 2}>
                <tspan>{s.title}</tspan>
                <tspan className="pf-state" x={g.x + g.w / 2 + 16} dy={18}>
                  {STATE_WORD[state]}
                </tspan>
              </text>
            ) : (
              <text className="pf-label" x={g.x} y={g.y + g.h / 2 + 20} textAnchor="middle">
                {lines.map((l, k) => (
                  <tspan key={l} x={g.x} dy={k === 0 ? 0 : 16}>
                    {l}
                  </tspan>
                ))}
              </text>
            )}
          </g>
        );
      })}
      {doc && (
        <g
          className="pf-doc"
          style={{ transform: vertical ? `translate(${doc.x + doc.w / 2 - 4}px, ${doc.y - 30}px)` : `translate(${doc.x + doc.w / 2 - 8}px, ${doc.y - doc.h / 2 - 22}px)` }}
          aria-hidden
        >
          <path d="M0 0 h10 l5 5 v14 h-15 z" />
          <path d="M3 9 h9 M3 13 h9" />
        </g>
      )}
    </svg>
  );
}

export function PipelineFlow(props: { mode: "demo" } | { mode: "live"; steps: readonly TraceStep[] }) {
  const reduced = useMedia(REDUCE, true);
  const vertical = useMedia(NARROW, false);
  const titleId = useId();
  const descId = useId();
  const ref = useRef<HTMLElement>(null);
  const [scroll, setScroll] = useState(false);
  const [shown, setShown] = useState(DEMO_TRACE.length);
  const [play, setPlay] = useState(0);
  const demo = props.mode === "demo";
  const animated = demo && !reduced && !scroll;

  useEffect(() => setScroll(demo && !reduced && scrollDriven()), [demo, reduced]);

  // Autoplay: start from nothing once the figure is in view, one event per tick, then hold.
  useEffect(() => {
    if (!animated || !ref.current) return;
    setShown(0);
    let timer: ReturnType<typeof setInterval> | undefined;
    const io = new IntersectionObserver(([e]) => {
      if (!e?.isIntersecting || timer) return;
      timer = setInterval(() => setShown((n) => (n >= DEMO_TRACE.length ? n : n + 1)), DEMO_TICK_MS);
      io.disconnect();
    }, { threshold: 0.4 });
    io.observe(ref.current);
    return () => {
      io.disconnect();
      clearInterval(timer);
    };
  }, [animated, play]);

  const steps = props.mode === "live" ? props.steps : DEMO_TRACE.slice(0, animated ? shown : DEMO_TRACE.length);
  const flow = flowFromSteps(steps);
  const current = flow.current ? STAGES.find((s) => s.id === flow.current) : undefined;

  return (
    <figure ref={ref} className={`pf${scroll ? " pf--scroll" : ""}`}>
      <Diagram flow={flow} vertical={vertical} titleId={titleId} descId={descId} />
      <figcaption className="ak-row ak-between">
        <span className="ak-muted" aria-live={props.mode === "live" ? "polite" : undefined}>
          {current ? `${current.title}: ${STATE_WORD[flow.states[current.id]]}` : "Esperando la factura"}
          {flow.decision && ` · ${STATE_LABEL[flow.decision]}`}
        </span>
        {animated && shown >= DEMO_TRACE.length && (
          <button type="button" className="ak-btn ak-btn--secondary ak-btn--sm" onClick={() => setPlay((p) => p + 1)}>
            Repetir
          </button>
        )}
      </figcaption>
      <ol className="pf-list">
        {STAGES.map((s: { id: StageId; title: string }) => {
          const state = flow.states[s.id];
          const step = s.id === "boundary" ? undefined : flow.steps[s.id];
          return (
            <li key={s.id} className={`is-${state}`} aria-current={flow.current === s.id ? "step" : undefined}>
              <span>
                <strong>{s.title}</strong> <span className="ak-muted">· {STATE_WORD[state]}</span>
                {step?.ms != null && <span className="ak-muted"> · {step.ms.toLocaleString("es-CO")} ms</span>}
              </span>
              {stageSummary(flow, s.id) && <p>{stageSummary(flow, s.id)}</p>}
            </li>
          );
        })}
      </ol>
    </figure>
  );
}
