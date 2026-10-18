import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, RotateCcw, Save, UserPlus } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { api, type Board, type Schemas, unwrap } from "~/api/client";
import { DocSlip } from "~/components/badges";
import { diffBoards, impactSentence } from "~/lib/board";
import { formatMoney, parseMajor } from "~/lib/format";
import { useView } from "~/lib/view";

import { boardKey } from "./tablero";

export function meta() {
  return [{ title: "Reglas · Alinka" }];
}

type RulesOut = Schemas["RulesOut"];
type RulesIn = Schemas["RulesIn"];
type Key = keyof RulesIn & keyof Schemas["RulesConfig"];

/** One sentence per editable rule; each [box] is a value the finance lead may change. */
const SENTENCES: { id: string; parts: (string | { key: Key; short?: boolean; label: string })[] }[] = [
  {
    id: "R05",
    parts: ["Frenar cualquier pago de más de", { key: "per_payment_cap_usd", label: "Tope por pago en USD" }, "USD"],
  },
  {
    id: "R06",
    parts: [
      "Escalar si el monto supera",
      { key: "approval_threshold_usd", label: "Umbral de aprobación en USD" },
      "USD o queda a menos del",
      { key: "approval_band_pct", short: true, label: "Banda bajo el umbral, en porcentaje" },
      "% por debajo",
    ],
  },
  {
    id: "R07",
    parts: ["Frenar si los pagos del mes superan", { key: "monthly_cap_usd", label: "Tope mensual en USD" }, "USD"],
  },
  {
    id: "R09",
    parts: [
      "Escalar si la fecha de pago venció hace más de",
      { key: "due_grace_days", short: true, label: "Días de gracia" },
      "días",
    ],
  },
];

const KEYS = SENTENCES.flatMap((s) => s.parts.flatMap((p) => (typeof p === "string" ? [] : [p.key])));

function useRules() {
  const [view] = useView();
  return {
    view,
    query: useQuery({
      queryKey: ["rules", view],
      queryFn: () => unwrap(api.GET("/api/rules", { params: { query: { view } } })),
    }),
  };
}

/** After a re-decision: put the new board in the cache and refresh everything that depends on it. */
function useRedecided() {
  const qc = useQueryClient();
  return (board: Board) => {
    qc.setQueryData(boardKey("sandbox"), board);
    void qc.invalidateQueries({ queryKey: ["rules", "sandbox"] });
    void qc.invalidateQueries({ queryKey: ["invoice", "sandbox"] });
    void qc.invalidateQueries({ queryKey: ["log", "sandbox"] });
  };
}

export default function Reglas() {
  const { view, query } = useRules();
  const qc = useQueryClient();
  const [impact, setImpact] = useState<string | null>(null);
  const redecided = useRedecided();
  const before = () => qc.getQueryData<Board>(boardKey("sandbox"));

  const reset = useMutation({
    mutationFn: async () => ({ before: before(), board: await unwrap(api.POST("/api/sandbox/reset")) }),
    onSuccess: ({ before, board }) => {
      redecided(board);
      setImpact(before ? `Sandbox restablecido. ${impactSentence(diffBoards(before, board))}` : "Sandbox restablecido.");
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="ak-h1">Reglas</h1>
        {view === "sandbox" && (
          <button type="button" className="ak-btn ak-btn--secondary" onClick={() => reset.mutate()} disabled={reset.isPending}>
            <RotateCcw aria-hidden className="ak-icon" />
            Restablecer sandbox
          </button>
        )}
      </div>
      {view === "canonical" && (
        <p className="ak-banner ak-banner--demo">
          Estas son las reglas de la ejecución canónica, de solo lectura. Para cambiarlas, pasa a «Mi sandbox».
        </p>
      )}
      {reset.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudo restablecer el sandbox: {reset.error.message}
        </p>
      )}
      {impact && (
        <p className="ak-impact" role="status">
          <ArrowRightLeft aria-hidden className="ak-icon" />
          {impact}
        </p>
      )}
      {query.isPending && (
        <div className="ak-skel" aria-label="Cargando las reglas">
          <span />
          <span />
        </div>
      )}
      {query.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudieron cargar las reglas: {query.error.message}
        </p>
      )}
      {query.data && (
        <>
          <RulesForm data={query.data} readOnly={view === "canonical"} before={before} onImpact={setImpact} />
          <Beneficiaries data={query.data} />
          {view === "sandbox" && <AddBeneficiary data={query.data} before={before} onImpact={setImpact} />}
        </>
      )}
    </div>
  );
}

function RulesForm({
  data,
  readOnly,
  before,
  onImpact,
}: {
  data: RulesOut;
  readOnly: boolean;
  before: () => Board | undefined;
  onImpact: (s: string) => void;
}) {
  const initial = () => Object.fromEntries(KEYS.map((k) => [k, String(data.rules[k])])) as Record<Key, string>;
  const [values, setValues] = useState(initial);
  useEffect(() => setValues(initial()), [data.rules_hash]);
  const redecided = useRedecided();
  const formId = useId();

  // Accept "5,5" as well as "5.5": Spanish uses the comma as the decimal mark.
  const num = (k: Key) => Number(values[k].trim().replace(",", "."));
  const changed = KEYS.filter((k) => num(k) !== data.rules[k]);
  const invalid = KEYS.filter((k) => {
    const v = num(k);
    const b = data.bounds[k];
    return values[k].trim() === "" || !Number.isFinite(v) || (b !== undefined && (v < b.min || v > b.max));
  });

  const save = useMutation({
    mutationFn: async () => {
      const body: RulesIn = Object.fromEntries(changed.map((k) => [k, num(k)]));
      return { before: before(), saved: await unwrap(api.PUT("/api/rules", { body })) };
    },
    onSuccess: ({ before, saved }) => {
      redecided(saved.board);
      onImpact(before ? impactSentence(diffBoards(before, saved.board)) : "Reglas guardadas; el sandbox se volvió a decidir.");
    },
  });

  return (
    <section aria-labelledby={`${formId}-h`} className="ak-stack">
      <h2 id={`${formId}-h`} className="ak-h2">
        Límites
      </h2>
      <form
        className="ak-stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (changed.length > 0 && invalid.length === 0) save.mutate();
        }}
      >
        {SENTENCES.map((s) => (
          <p key={s.id} className="ak-sentence">
            <span className="ak-sentence__id">{s.id}</span>
            {s.parts.map((p, i) => {
              if (typeof p === "string") return <span key={i}>{p}</span>;
              const b = data.bounds[p.key];
              const bad = invalid.includes(p.key);
              return (
                <input
                  key={i}
                  className={`ak-input ${p.short ? "ak-input--short" : ""}`}
                  type="text"
                  inputMode="decimal"
                  name={p.key}
                  aria-label={p.label}
                  aria-invalid={bad || undefined}
                  title={b ? `Entre ${b.min} y ${b.max}` : undefined}
                  value={values[p.key]}
                  disabled={readOnly}
                  onChange={(e) => setValues((v) => ({ ...v, [p.key]: e.target.value }))}
                />
              );
            })}
          </p>
        ))}
        {invalid.length > 0 && (
          <p role="alert" className="ak-banner ak-banner--error">
            Revisa los valores: {invalid.map((k) => {
              const b = data.bounds[k];
              return b ? `${k} debe estar entre ${b.min} y ${b.max}` : k;
            }).join("; ")}.
          </p>
        )}
        {save.isError && (
          <p role="alert" className="ak-banner ak-banner--error">
            No se guardaron las reglas: {save.error.message}
          </p>
        )}
        {!readOnly && (
          <div className="ak-row">
            <button type="submit" className="ak-btn ak-btn--primary" disabled={changed.length === 0 || invalid.length > 0 || save.isPending}>
              <Save aria-hidden className="ak-icon" />
              Guardar y volver a decidir
            </button>
            {changed.length > 0 && (
              <button type="button" className="ak-btn ak-btn--ghost" onClick={() => setValues(initial())}>
                Descartar cambios
              </button>
            )}
            <span className="ak-note">Versión {data.rules.version} · al {data.rules.as_of}</span>
          </div>
        )}
      </form>
    </section>
  );
}

function Beneficiaries({ data }: { data: RulesOut }) {
  return (
    <section aria-labelledby="lista" className="ak-stack">
      <h2 id="lista" className="ak-h2">
        Lista de beneficiarios
      </h2>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="ak-log">
          <caption className="ak-sr">Beneficiarios autorizados y sus contratos</caption>
          <thead>
            <tr>
              <th scope="col">Beneficiario</th>
              <th scope="col">País y moneda</th>
              <th scope="col">Cuenta registrada</th>
              <th scope="col">Contrato</th>
              <th scope="col">Tarifa</th>
            </tr>
          </thead>
          <tbody>
            {data.beneficiaries.map((b) => (
              <tr key={b.id}>
                <td>
                  <span className="font-semibold">{b.name}</span>
                  <span className="ak-note">
                    {b.id} · {b.tax_id}
                    {b.added_in_sandbox && " · agregado en tu sandbox"}
                  </span>
                </td>
                <td>
                  {b.country} · {b.currency}
                </td>
                <td>{b.account_masked}</td>
                <td>
                  {b.contract_id} · {b.cost_center}
                </td>
                <td className="whitespace-nowrap">
                  {formatMoney(b.rate_minor, b.currency)}
                  <span className="ak-note">{FREQUENCY[b.frequency] ?? b.frequency}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const FREQUENCY: Record<string, string> = {
  monthly: "mensual",
  biweekly: "quincenal",
  weekly: "semanal",
  per_delivery: "por entrega",
};

const COUNTRY_BY_CURRENCY: Record<string, string> = { COP: "CO", MXN: "MX", BRL: "BR", USD: "US" };

type Draft = {
  name: string;
  tax_id: string;
  country: string;
  currency: string;
  account_on_file: string;
  scope_es: string;
  rate: string;
  tolerance_pct: string;
  frequency: "monthly" | "biweekly" | "weekly" | "per_delivery";
  valid_from: string;
  valid_to: string;
  cost_center: string;
  doc_types: string[];
};

const DOC_TYPES: { value: string; label: string }[] = [
  { value: "factura", label: "Factura" },
  { value: "cuenta_de_cobro", label: "Cuenta de cobro" },
  { value: "invoice", label: "Invoice" },
];

function emptyDraft(data: RulesOut): Draft {
  const from = data.rules.as_of;
  const to = `${Number(from.slice(0, 4)) + 1}${from.slice(4)}`;
  return {
    name: "",
    tax_id: "DEMO-",
    country: "",
    currency: "",
    account_on_file: "",
    scope_es: "",
    rate: "",
    tolerance_pct: "5",
    frequency: "monthly",
    valid_from: from,
    valid_to: to,
    cost_center: data.beneficiaries[0]?.cost_center ?? "",
    doc_types: ["factura", "cuenta_de_cobro"],
  };
}

/** Invoices held by R01: the way out is to add their beneficiary here. */
function usePendingR01() {
  return useQuery({
    queryKey: ["board", "sandbox"],
    queryFn: () => unwrap(api.GET("/api/board", { params: { query: { view: "sandbox" } } })),
    select: (b: Board) => b.columns.flatMap((c) => c.cards).filter((c) => c.determining_rule === "R01"),
  });
}

function AddBeneficiary({
  data,
  before,
  onImpact,
}: {
  data: RulesOut;
  before: () => Board | undefined;
  onImpact: (s: string) => void;
}) {
  const [draft, setDraft] = useState(() => emptyDraft(data));
  const [source, setSource] = useState<{ id: string; name: string } | null>(null);
  const pending = usePendingR01();
  const redecided = useRedecided();
  const ids = useId();
  const costCenters = [...new Set(data.beneficiaries.map((b) => b.cost_center))].sort();
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }));

  const prefill = async (invoiceId: string) => {
    if (!invoiceId) return;
    const detail = await unwrap(
      api.GET("/api/invoices/{invoice_id}", { params: { path: { invoice_id: invoiceId }, query: { view: "sandbox" } } }),
    );
    const field = (name: string) => detail.fields.find((f) => f.name === name)?.value ?? "";
    const currency = detail.card.currency ?? "";
    setSource({ id: invoiceId, name: detail.card.beneficiary_name ?? "" });
    setDraft((d) => ({
      ...d,
      name: field("beneficiary_name"),
      tax_id: field("beneficiary_tax_id") || d.tax_id,
      currency,
      country: COUNTRY_BY_CURRENCY[currency] ?? d.country,
      rate: detail.card.amount_minor != null && currency ? formatMoney(detail.card.amount_minor, currency).split(" ")[0]! : d.rate,
      scope_es: field("service_text"),
      // The payout account is never copied from a document: a person types the one on file.
      account_on_file: "",
    }));
  };

  const rateMinor = draft.currency ? parseMajor(draft.rate, draft.currency) : null;
  const scope = draft.scope_es.split(",").map((s) => s.trim()).filter(Boolean);
  const problems = [
    draft.name.trim().length < 2 && "el nombre",
    !/^DEMO-[A-Za-z0-9.\-]{1,40}$/.test(draft.tax_id) && "la identificación (DEMO-…)",
    !/^[A-Z]{2}$/.test(draft.country) && "el país (dos letras)",
    !/^[A-Z]{3}$/.test(draft.currency) && "la moneda (tres letras)",
    draft.account_on_file.trim().length < 4 && "la cuenta registrada",
    scope.length === 0 && "el alcance del contrato",
    (rateMinor === null || rateMinor <= 0) && "la tarifa",
    draft.doc_types.length === 0 && "un tipo de documento",
  ].filter(Boolean) as string[];

  const add = useMutation({
    mutationFn: async () => {
      const body: Schemas["BeneficiaryIn"] = {
        name: draft.name.trim(),
        tax_id: draft.tax_id.trim(),
        country: draft.country,
        currency: draft.currency,
        account_on_file: draft.account_on_file.trim(),
        doc_types: draft.doc_types as Schemas["BeneficiaryIn"]["doc_types"],
        contract: {
          scope_es: scope,
          scope_en: [],
          rate_minor: rateMinor ?? 0,
          tolerance_pct: Number(draft.tolerance_pct),
          frequency: draft.frequency,
          valid_from: draft.valid_from,
          valid_to: draft.valid_to,
          cost_center: draft.cost_center,
        },
      };
      return { before: before(), added: await unwrap(api.POST("/api/beneficiaries", { body })) };
    },
    onSuccess: ({ before, added }) => {
      redecided(added.board);
      onImpact(
        `${added.beneficiary.name} quedó en la lista (${added.beneficiary.id}). ${
          before ? impactSentence(diffBoards(before, added.board)) : ""
        }`,
      );
      setDraft(emptyDraft(data));
      setSource(null);
    },
  });

  const input = (k: keyof Draft, label: string, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="grid gap-1 text-small text-ink-muted" htmlFor={`${ids}-${k}`}>
      {label}
      <input id={`${ids}-${k}`} className="ak-input ak-input--text" value={draft[k] as string} onChange={set(k)} {...extra} />
    </label>
  );

  return (
    <section aria-labelledby={`${ids}-h`} className="ak-stack">
      <h2 id={`${ids}-h`} className="ak-h2">
        Añadir beneficiario
      </h2>
      <form
        className="ak-sentence"
        onSubmit={(e) => {
          e.preventDefault();
          if (problems.length === 0) add.mutate();
        }}
      >
        <div className="grid w-full gap-4">
        {(pending.data?.length ?? 0) > 0 && (
          <label className="grid gap-1 text-small text-ink-muted" htmlFor={`${ids}-from`}>
            Partir de una factura pendiente por beneficiario no autorizado (R01)
            <select id={`${ids}-from`} className="ak-input ak-input--text" defaultValue="" onChange={(e) => void prefill(e.target.value)}>
              <option value="">Elegir factura…</option>
              {pending.data?.map((c) => (
                <option key={c.invoice_id} value={c.invoice_id}>
                  {c.invoice_id} · {formatMoney(c.amount_minor, c.currency)}
                </option>
              ))}
            </select>
          </label>
        )}
        {source && (
          <DocSlip caption={`Datos tomados de ${source.id}: revísalos antes de guardar`} inline>
            {source.name}
          </DocSlip>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          {input("name", "Nombre")}
          {input("tax_id", "Identificación tributaria")}
          {input("country", "País (ISO, dos letras)", { maxLength: 2 })}
          {input("currency", "Moneda (ISO, tres letras)", { maxLength: 3 })}
          {input("account_on_file", "Cuenta registrada (la escribe una persona, nunca se copia del documento)")}
          {input("scope_es", "Alcance del contrato (palabras separadas por comas)")}
          {input("rate", `Tarifa por periodo${draft.currency ? ` en ${draft.currency}` : ""}`, { inputMode: "decimal" })}
          {input("tolerance_pct", "Tolerancia (%)", { type: "number", min: 0, max: 50, step: "any" })}
          <label className="grid gap-1 text-small text-ink-muted" htmlFor={`${ids}-frequency`}>
            Frecuencia
            <select id={`${ids}-frequency`} className="ak-input ak-input--text" value={draft.frequency} onChange={set("frequency")}>
              {Object.entries(FREQUENCY).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-small text-ink-muted" htmlFor={`${ids}-cost_center`}>
            Centro de costo
            <select id={`${ids}-cost_center`} className="ak-input ak-input--text" value={draft.cost_center} onChange={set("cost_center")}>
              {costCenters.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          {input("valid_from", "Contrato desde", { type: "date" })}
          {input("valid_to", "Contrato hasta", { type: "date" })}
        </div>
        <fieldset className="ak-row">
          <legend className="mb-1 text-small text-ink-muted">Documentos que puede enviar</legend>
          {DOC_TYPES.map((t) => (
            <label key={t.value} className="ak-row mr-4 text-small">
              <input
                type="checkbox"
                name="doc_types"
                value={t.value}
                checked={draft.doc_types.includes(t.value)}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    doc_types: e.target.checked ? [...d.doc_types, t.value] : d.doc_types.filter((x) => x !== t.value),
                  }))
                }
              />
              {t.label}
            </label>
          ))}
        </fieldset>
        {problems.length > 0 && <p className="ak-note">Falta o no es válido: {problems.join(", ")}.</p>}
        {add.isError && (
          <p role="alert" className="ak-banner ak-banner--error">
            No se agregó el beneficiario: {add.error.message}
          </p>
        )}
        <div className="ak-row">
          <button type="submit" className="ak-btn ak-btn--primary" disabled={problems.length > 0 || add.isPending}>
            <UserPlus aria-hidden className="ak-icon" />
            Añadir y volver a decidir
          </button>
        </div>
        </div>
      </form>
    </section>
  );
}
