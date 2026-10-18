import { Check, CircleCheck, CirclePause, Clock, Link2, ShieldAlert, TriangleAlert } from "lucide-react";

import { CHANNEL, DecisionChip, DocSlip, SecurityTag } from "~/components/badges";
import { type FieldView, fieldChecks, type JevAnswer } from "~/lib/detail";
import { formatMoney } from "~/lib/format";
import type { RuleResult, StepName, TraceStep } from "~/lib/trace";
import { splitCodePoint } from "~/lib/try";

/*
 * The step panel on Probar: what each finished step found, with the run's real data. Document
 * text (hidden lines, quotes, instructions) is shown as quotation in ak-slip, never as interface.
 */

/** alinka/api/views.py FIELD_LABELS_ES. */
const FIELD_ES: Record<string, string> = {
  doc_type: "Tipo de documento",
  beneficiary_name: "Beneficiario",
  beneficiary_tax_id: "Identificación tributaria",
  invoice_number: "Número de factura",
  fiscal_id: "Identificador fiscal",
  issue_date: "Fecha de emisión",
  due_date: "Fecha de vencimiento",
  service_period: "Periodo del servicio",
  currency: "Moneda",
  subtotal: "Subtotal",
  tax_total: "Impuestos",
  total: "Total a pagar",
  amount_in_words: "Monto en letras",
  bank_account: "Cuenta impresa (no se usa para pagar)",
  service_text: "Concepto",
  buyer_name: "Comprador",
  buyer_tax_id: "Identificación del comprador",
};

const OUTCOME = {
  pass: { cls: "ak-rule--pasa", icon: CircleCheck, word: "pasa" },
  hold: { cls: "ak-rule--retiene", icon: CirclePause, word: "frena" },
  escalate: { cls: "ak-rule--escala", icon: Clock, word: "escala" },
} as const;

const decimal = (x: number) => x.toFixed(2).replace(".", ",");

function Checks({ items }: { items: { label: string; ok: boolean }[] }) {
  return (
    <ul className="ak-checks">
      {items.map((c) => (
        <li key={c.label} className={c.ok ? "ok" : "warn"}>
          {c.ok ? <Check aria-hidden className="ak-icon" /> : <TriangleAlert aria-hidden className="ak-icon" />}
          {c.label}
        </li>
      ))}
    </ul>
  );
}

function Hidden({ data }: { data: Record<string, any> }) {
  const hidden: string[] = data.hidden_content ?? [];
  const controls: string[] = data.unicode_controls ?? [];
  const instructions: string[] = data.instructions ?? [];
  if (!hidden.length && !controls.length && !instructions.length && !data.html_text_mismatch)
    return <p className="ak-muted m-0">No había nada oculto: la IA recibe el documento tal como se ve.</p>;
  return (
    <>
      {(hidden.length > 0 || controls.length > 0) && (
        <DocSlip caption="Lo que se descartó antes de la lectura">
          {hidden.map((h, k) => (
            <span key={`h${k}`}>
              <del>{h}</del>
              {"\n"}
            </span>
          ))}
          {controls.map((c, k) => {
            const [cp, rest] = splitCodePoint(c);
            return (
              <span key={`c${k}`}>
                {cp && <span className="ak-hidden-char">{cp}</span>}
                {cp ? ` ${rest}` : rest}
                {"\n"}
              </span>
            );
          })}
        </DocSlip>
      )}
      {instructions.length > 0 && (
        <DocSlip caption="Instrucciones dirigidas a un sistema (no se siguen)">
          {instructions.map((t, k) => (
            <span key={k}>
              <del>{t}</del>
              {"\n"}
            </span>
          ))}
        </DocSlip>
      )}
      {data.html_text_mismatch && <p className="m-0">El HTML del correo dice algo distinto a su texto plano.</p>}
    </>
  );
}

function Fields({ read, verify, onActive }: { read: TraceStep; verify?: TraceStep; onActive: (name: string | null) => void }) {
  const fields = Object.entries((read.data.fields ?? {}) as Record<string, { value: string | null; quote: string | null; confidence: string }>).filter(
    ([, f]) => f.value != null,
  );
  const checked = verify?.data.fields as Record<string, { grounded: boolean; agreed: boolean | null }> | undefined;
  const jev = (verify?.data.jev ?? []) as JevAnswer[];
  return (
    <dl className="ak-fields">
      {fields.map(([name, f]) => {
        const c = checked?.[name];
        return (
          <div
            key={name}
            className="ak-field"
            onMouseEnter={() => onActive(name)}
            onMouseLeave={() => onActive(null)}
            onFocus={() => onActive(name)}
            onBlur={() => onActive(null)}
            tabIndex={c ? 0 : undefined}
          >
            <dt>{FIELD_ES[name] ?? name}</dt>
            <dd>
              <span className="ak-field__value [overflow-wrap:anywhere]">{f.value}</span>
              {f.quote && (
                <figure className="ak-slip ak-slip--inline">
                  <figcaption className="ak-sr">Cita del documento</figcaption>
                  <blockquote>
                    <mark>{f.quote}</mark>
                  </blockquote>
                </figure>
              )}
              {c && <Checks items={fieldChecks({ name, grounded: c.grounded, agreed: c.agreed } as FieldView, jev)} />}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function VerifySummary({ data }: { data: Record<string, any> }) {
  const items: { label: string; ok: boolean }[] = [];
  if (data.amount_in_regex != null)
    items.push({ label: data.amount_in_regex ? "Monto en letras coincide" : "Monto en letras no coincide", ok: data.amount_in_regex });
  if (data.totals_reconcile != null)
    items.push({ label: data.totals_reconcile ? "Los totales cuadran" : "Los totales no cuadran", ok: data.totals_reconcile });
  const risk = Number(data.risk ?? 0);
  const max = Number(data.risk_max ?? 1);
  items.push({ label: `Riesgo de la lectura ${decimal(risk)} (máximo ${decimal(max)})`, ok: risk <= max });
  const ungrounded: string[] = [...(data.ungrounded ?? []), ...(data.disagreements ?? [])];
  return (
    <>
      <Checks items={items} />
      {ungrounded.length > 0 && (
        <p className="ak-muted m-0">Con dudas: {[...new Set(ungrounded)].map((n) => FIELD_ES[n] ?? n).join(", ")}.</p>
      )}
    </>
  );
}

function Rules({ results }: { results: RuleResult[] }) {
  return (
    <ul className="grid gap-2 p-0 m-0 list-none">
      {results.map((r) => {
        const o = OUTCOME[r.outcome];
        const Icon = o.icon;
        return (
          <li key={r.rule} className="grid gap-1">
            <span className="ak-row">
              <span className={`ak-rule ${o.cls}`}>
                <Icon aria-hidden className="ak-icon" />
                <b>{r.rule}</b>
                {r.name_es}
                <span className="ak-sr"> {o.word}</span>
              </span>
              {r.security && r.outcome !== "pass" && <SecurityTag rules={[r.rule]} />}
            </span>
            <span className="ak-muted text-small">{r.sentence_es.charAt(0).toUpperCase() + r.sentence_es.slice(1)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Decision({ data }: { data: Record<string, any> }) {
  const p = data.payment as { beneficiary_name: string; account_masked: string; amount_minor: number; currency: string } | null;
  return (
    <>
      {(data.alerts ?? []).length > 0 && (
        <div className="ak-sec-box">
          <ShieldAlert aria-hidden className="ak-icon" />
          <strong>Alerta de seguridad ({(data.alerts as string[]).join(", ")})</strong>
          <p>Nadie puede pagar esta factura sin revisar la alerta.</p>
        </div>
      )}
      <span>
        <DecisionChip decision={data.decision} />
      </span>
      <p className="m-0">{data.reason_es}</p>
      {p && (
        <p className="ak-muted m-0">
          Pago a {p.beneficiary_name} por {formatMoney(p.amount_minor, p.currency)}, a la cuenta {p.account_masked} de la lista de
          beneficiarios.
        </p>
      )}
    </>
  );
}

const ORDER: StepName[] = ["received", "sanitize", "read", "verify", "rules", "decide", "record"];

export function TrySteps({ steps, onActiveField }: { steps: readonly TraceStep[]; onActiveField: (name: string | null) => void }) {
  const last: Partial<Record<StepName, TraceStep>> = {};
  for (const s of steps) last[s.step] = s;
  const done = (n: StepName) => (last[n] && last[n]!.status !== "running" ? last[n] : undefined);
  const read = done("read");
  return (
    <ol className="ak-stack m-0 list-none p-0">
      {ORDER.map((name) => {
        const s = done(name);
        if (!s) return null;
        const d = s.data;
        return (
          <li key={name} className="ak-stack border-b border-line pb-4">
            <h3 className="ak-h2 text-title">{s.title_es}</h3>
            <p className="m-0">
              {s.summary_es}
              {s.ms != null && <span className="ak-muted"> · {s.ms.toLocaleString("es-CO")} ms</span>}
            </p>
            {name === "received" && (
              <p className="ak-muted m-0">
                {d.filename} · {CHANNEL[d.channel as keyof typeof CHANNEL]?.label ?? d.channel} · {d.pages}{" "}
                {d.pages === 1 ? "página" : "páginas"} · huella <span className="ak-hash">{d.sha8}</span>
              </p>
            )}
            {name === "sanitize" && <Hidden data={d} />}
            {name === "read" && (
              <>
                {d.error && (
                  <div className="ak-banner ak-banner--error m-0 grid gap-1">
                    <span>La IA no pudo leer el documento. La factura pasa a una persona (R10).</span>
                    <span className="ak-note [overflow-wrap:anywhere]">Detalle técnico: {d.error}</span>
                  </div>
                )}
                {(d.instructions_seen ?? []).length > 0 && (
                  <DocSlip caption="La IA vio estas instrucciones y no las siguió">{(d.instructions_seen as string[]).join("\n")}</DocSlip>
                )}
                <Fields read={s} verify={done("verify")} onActive={onActiveField} />
              </>
            )}
            {name === "verify" && read && <VerifySummary data={d} />}
            {name === "rules" && <Rules results={d.results ?? []} />}
            {name === "decide" && <Decision data={d} />}
            {name === "record" && (
              <p className="m-0">
                Registro n.º {d.seq}:{" "}
                <span className="ak-hash">
                  <Link2 aria-hidden className="ak-icon" />
                  {d.hash8}
                </span>{" "}
                encadenado a{" "}
                <span className="ak-hash">
                  <Link2 aria-hidden className="ak-icon" />
                  {d.prev_hash8}
                </span>
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
