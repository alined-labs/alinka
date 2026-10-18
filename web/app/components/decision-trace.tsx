import { EyeOff, FileCheck, Gavel, Inbox, Link2, ListChecks, ScanText } from "lucide-react";
import type { ReactNode } from "react";

import { CHANNEL, DecisionChip, DocSlip, MarkedQuote, ReasonText, RuleChip } from "~/components/badges";
import type { StepName, TraceStep } from "~/lib/trace";
import { type Call, formatMs, hasData, type StepData } from "~/lib/trace-data";

/*
 * "Cómo se decidió": the seven stored steps of an invoice as an ak-timeline. Each step opens
 * onto the data it used. Text from the document is always shown as document text (ak-slip).
 * Inside a step there are no li elements: the kit styles every li of .ak-timeline as an item.
 */

const ICON: Record<StepName, typeof Inbox> = {
  received: Inbox,
  sanitize: EyeOff,
  read: ScanText,
  verify: FileCheck,
  rules: ListChecks,
  decide: Gavel,
  record: Link2,
};

const OUTCOME = { pass: "PAY", hold: "HOLD", escalate: "ESCALATE" } as const;
const CONFIDENCE = { high: "alta", medium: "media", low: "baja" } as const;
const ROLE = { reader: "Lectura", checker: "Segunda lectura", jev: "JEV" } as const;

const yesNo = (v: boolean | null) => (v === null ? "no aplica" : v ? "sí" : "no");
const decimal = (n: number, d = 2) => n.toFixed(d).replace(".", ",");

/** The steps as timeline items, to sit in the Detalle's ak-timeline before the human decision. */
export function TraceItems({ steps, label }: { steps: TraceStep[]; label: (field: string) => string }) {
  return steps.map((s) => {
    const Icon = ICON[s.step];
    return (
      <li key={s.step} data-step={s.step} data-status={s.status}>
        <Icon aria-hidden className="ak-icon" />
        <div className="grid min-w-0 gap-1">
          <span className="ak-row flex-wrap">
            <strong>{s.title_es}</strong>
            {s.status === "flagged" && <span className="ak-rule ak-rule--escala">revisar</span>}
            {s.status === "error" && <span className="ak-rule ak-rule--retiene">error</span>}
            {s.step === "decide" && hasData(s) && <DecisionChip decision={(s.data as StepData["decide"]).decision} />}
          </span>
          <small>
            {s.summary_es}
            {formatMs(s.ms) && ` · ${formatMs(s.ms)}`}
          </small>
          {hasData(s) && (
            <details>
              <summary className="cursor-pointer text-small text-ink-muted">Ver los datos</summary>
              <div className="mt-2 grid gap-3 text-small">{body(s, label)}</div>
            </details>
          )}
        </div>
      </li>
    );
  });
}

function body(s: TraceStep, label: (field: string) => string): ReactNode {
  if (!hasData(s)) return null;
  switch (s.step) {
    case "received":
      return <Received d={s.data as StepData["received"]} />;
    case "sanitize":
      return <Sanitize d={s.data as StepData["sanitize"]} />;
    case "read":
      return <Read d={s.data as StepData["read"]} label={label} />;
    case "verify":
      return <Verify d={s.data as StepData["verify"]} label={label} />;
    case "rules":
      return <Rules d={s.data as StepData["rules"]} />;
    case "decide":
      return <ReasonText text={(s.data as StepData["decide"]).reason_es} className="ak-muted m-0" />;
    case "record": {
      const d = s.data as StepData["record"];
      return (
        <Pairs
          rows={[
            ["Registro", `n.º ${d.seq}`],
            ["Hash", <Hash key="h" value={d.hash8} />],
            ["Hash anterior", <Hash key="p" value={d.prev_hash8} />],
          ]}
        />
      );
    }
  }
}

function Pairs({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-muted">{k}</dt>
          <dd className="m-0 min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Hash({ value }: { value: string }) {
  return (
    <span className="ak-hash">
      <Link2 aria-hidden className="ak-icon" />
      {value}
    </span>
  );
}

function Received({ d }: { d: StepData["received"] }) {
  const channel = CHANNEL[d.channel as keyof typeof CHANNEL]?.label ?? d.channel;
  return (
    <Pairs
      rows={[
        ["Factura", d.invoice_id],
        ["Canal", channel],
        ["Archivo", d.filename],
        ["Páginas", String(d.pages)],
        ["Idioma", d.language === "es" ? "español" : d.language === "en" ? "inglés" : "sin detectar"],
        ["Huella", <span key="s" className="font-mono">{d.sha8}</span>],
      ]}
    />
  );
}

/** What was hidden is document text: shown in a slip, never followed. */
function Found({ title, items, caption }: { title: string; items: string[]; caption: string }) {
  if (items.length === 0) return null;
  return (
    <div className="grid gap-1">
      <strong>{title}</strong>
      {items.map((t, i) => (
        <DocSlip key={i} caption={caption}>
          {t}
        </DocSlip>
      ))}
    </div>
  );
}

function Sanitize({ d }: { d: StepData["sanitize"] }) {
  const none = !d.hidden_content.length && !d.unicode_controls.length && !d.instructions.length && !d.html_text_mismatch;
  if (none) return <p className="ak-muted m-0">No había texto oculto, caracteres invisibles ni instrucciones.</p>;
  return (
    <>
      <Found title="Texto oculto, descartado antes de la lectura" items={d.hidden_content} caption="Texto oculto en el documento" />
      <Found title="Caracteres invisibles" items={d.unicode_controls} caption="Caracteres en el documento" />
      <Found title="Instrucciones dentro del documento, no seguidas" items={d.instructions} caption="Instrucción en el documento" />
      {d.html_text_mismatch && <p className="m-0">El HTML del correo dice algo distinto a su texto plano.</p>}
    </>
  );
}

function Calls({ calls }: { calls: Call[] }) {
  if (calls.length === 0) return null;
  return (
    <div className="grid gap-1">
      {calls.map((c, i) => (
        <div key={i} className="ak-note">
          {ROLE[c.role]}: {c.model} · {c.cached ? "grabada" : "en vivo"} · {formatMs(c.latency_ms)} · {decimal(c.cost_usd, 4)} USD
        </div>
      ))}
    </div>
  );
}

function Read({ d, label }: { d: StepData["read"]; label: (field: string) => string }) {
  return (
    <>
      <p className="m-0">
        {d.mode === "replay" ? "Lectura grabada" : "Lectura en vivo"}, sin herramientas y sin ver las reglas ni la lista de beneficiarios.
      </p>
      <Calls calls={d.calls} />
      {d.error && <p className="ak-banner ak-banner--error m-0">{d.error}</p>}
      <Found title="Instrucciones que la IA vio y no siguió" items={d.instructions_seen} caption="Instrucción en el documento" />
      <div className="grid gap-2">
        {Object.entries(d.fields).map(([name, f]) => (
          <div key={name} className="grid gap-1">
            <span>
              <strong>{label(name)}</strong> · confianza {CONFIDENCE[f.confidence]}
            </span>
            {f.quote ? (
              <DocSlip caption="Cita en el documento">
                <MarkedQuote quote={f.quote} value={f.value} />
              </DocSlip>
            ) : (
              <span className="ak-muted">{f.value ?? "sin valor"} · sin cita</span>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function Verify({ d, label }: { d: StepData["verify"]; label: (field: string) => string }) {
  const fields = Object.entries(d.fields);
  const grounded = fields.filter(([, f]) => f.grounded).length;
  return (
    <>
      <Pairs
        rows={[
          ["Citas en la página", `${grounded} de ${fields.length}`],
          ["Sin cita", d.ungrounded.length ? d.ungrounded.map(label).join(", ") : "ninguno"],
          ["Lecturas distintas", d.disagreements.length ? d.disagreements.map(label).join(", ") : "ninguna"],
          ["Monto en letras igual al total", yesNo(d.amount_in_regex)],
          ["Los totales cuadran", yesNo(d.totals_reconcile)],
          ["Riesgo", `${decimal(d.risk)} de un máximo de ${decimal(d.risk_max)}`],
        ]}
      />
      <Calls calls={d.calls} />
      {d.jev.length > 0 && (
        <div className="grid gap-1">
          {d.jev.map((j) => (
            <span key={j.question} className="ak-note">
              {jevLabel(j.question, label)}: <span className="font-mono">{jevAnswer(j.answer)}</span> · probabilidad{" "}
              {decimal(j.probability)}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

/** J1a and J1b read the total twice on their own; J2.<field> asks whether a field was misread. */
function jevLabel(q: string, label: (field: string) => string) {
  if (q === "J1a" || q === "J1b") return `JEV, total leído por separado (${q.slice(2)})`;
  if (q.startsWith("J2.")) return `JEV, ¿${label(q.slice(3)).toLowerCase()} mal leído?`;
  return `JEV ${q}`;
}
const jevAnswer = (a: string) => (a === "yes" ? "sí" : a === "no" ? "no" : a);

function Rules({ d }: { d: StepData["rules"] }) {
  return (
    <div className="grid gap-2">
      {d.results.map((r) => (
        <div key={r.rule} className="grid justify-items-start gap-1">
          <RuleChip rule={r.rule} name={r.name_es} decision={OUTCOME[r.outcome]} />
          <ReasonText text={r.sentence_es} className="ak-muted m-0" as="span" />
        </div>
      ))}
    </div>
  );
}
