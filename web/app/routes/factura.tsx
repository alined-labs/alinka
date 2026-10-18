import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CircleAlert,
  CircleCheck,
  FileCheck,
  Gavel,
  Inbox,
  Landmark,
  Link2,
  ScanText,
  ShieldAlert,
  UserCheck,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { api, unwrap, type View } from "~/api/client";
import { ApprovalDialog } from "~/components/approval-dialog";
import { CHANNEL, DecisionChip, DocSlip, MarkedQuote, ReasonText, RuleChip, SecurityTag } from "~/components/badges";
import { Amount, BeneficiaryName } from "~/components/invoice-card";
import { PageViewer } from "~/components/page-viewer";
import { STATE_LABEL } from "~/lib/board";
import { type Detail, fieldChecks, type FieldView, orderRules, type RuleView } from "~/lib/detail";
import { formatDateTime, formatMoney, formatUsd } from "~/lib/format";
import { useView } from "~/lib/view";

import type { Route } from "./+types/factura";

export function meta({ params }: Route.MetaArgs) {
  return [{ title: `${params.invoiceId} · Alinka` }];
}

const NEVER_APPROVABLE = ["R01", "R12"];

export const detailKey = (view: View, id: string) => ["invoice", view, id] as const;

export default function Factura() {
  const { invoiceId = "" } = useParams();
  const [view] = useView();
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: detailKey(view, invoiceId),
    queryFn: () => unwrap(api.GET("/api/invoices/{invoice_id}", { params: { path: { invoice_id: invoiceId }, query: { view } } })),
  });
  const back = { pathname: "/", search: view === "canonical" ? "?vista=canonica" : "" };

  return (
    <div className="space-y-4">
      <Link to={back} className="ak-btn ak-btn--ghost ak-btn--sm">
        <ArrowLeft aria-hidden className="ak-icon" />
        Volver al tablero
      </Link>
      {detail.isPending && (
        <div className="ak-skel" aria-label="Cargando la factura">
          <span />
          <span />
          <span />
          <span />
        </div>
      )}
      {detail.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudo cargar la factura {invoiceId}: {detail.error.message}
        </p>
      )}
      {detail.data && (
        <DetailView
          detail={detail.data}
          view={view}
          onChange={(d) => qc.setQueryData(detailKey(view, invoiceId), d)}
        />
      )}
    </div>
  );
}

function DetailView({ detail, view, onChange }: { detail: Detail; view: View; onChange: (d: Detail) => void }) {
  const { card, record } = detail;
  const [active, setActive] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const jev = record?.facts.verification?.jev ?? [];
  const { fired, passed } = orderRules(detail.rules, card.alerts);
  const alertRules = fired.filter((r) => card.alerts.includes(r.rule));
  const blocked = [...card.alerts, card.determining_rule].some((r) => r && NEVER_APPROVABLE.includes(r));
  const canAct = view === "sandbox" && card.state === "ESCALATE" && !card.approver;

  const focusField = (f: FieldView | null) => {
    setActive(f?.name ?? null);
    const first = f?.boxes[0];
    if (first && !f.boxes.some((b) => b.page === page)) setPage(first.page);
  };

  return (
    <article className="ak-detail overflow-hidden rounded-xl border border-line" aria-labelledby="detalle-titulo">
      <div className="ak-detail__data">
        <header className="ak-detail__head">
          <p className="ak-card__meta">
            {card.invoice_id} · {CHANNEL[card.channel].label} · recibida el {formatDateTime(card.received_at)}
          </p>
          <h1 id="detalle-titulo" className="ak-h1">
            <BeneficiaryName card={card} inline={false} />
          </h1>
          <p className="ak-detail__amount">
            <Amount minor={card.amount_minor} currency={card.currency} />
          </p>
          {card.currency !== "USD" && card.usd_minor != null && (
            <p className="ak-note">
              ≈ {formatUsd(card.usd_minor)}
              {record?.facts.computed?.fx &&
                ` · tasa ${record.facts.computed.fx.rate} (${record.facts.computed.fx.source}, ${record.facts.computed.fx.date})`}
            </p>
          )}
          <div className="ak-card__tags">
            <SecurityTag rules={card.alerts} />
            {card.state === "inbox" ? (
              <span className="ak-rule">{STATE_LABEL.inbox}</span>
            ) : (
              <DecisionChip decision={card.state} />
            )}
            {card.determining_rule && card.state !== "inbox" && (
              <RuleChip rule={card.determining_rule} name={card.determining_rule_es} decision={card.state} />
            )}
          </div>
        </header>

        {alertRules.map((r) => (
          <section key={r.rule} className="ak-sec-box" aria-label={`Alerta de seguridad ${r.rule}`}>
            <ShieldAlert aria-hidden className="ak-icon" />
            <strong>
              Alerta de seguridad ({r.rule}) · {r.name_es}
            </strong>
            <div className="col-start-2">
              <ReasonText as="span" text={sentence(r)} className="block text-small text-ink-muted" />
            </div>
            {NEVER_APPROVABLE.includes(r.rule) && <p>Esta alerta no puede aprobarse.</p>}
          </section>
        ))}
        <HiddenContent detail={detail} />

        {/* When the decision comes from a security alert, its box above already says why. */}
        {card.reason_es && !alertRules.some((r) => r.rule === card.determining_rule) && (
          <ReasonText text={card.reason_es} className="text-lead" />
        )}

        <Payment detail={detail} view={view} />

        {canAct && (
          <section aria-label="Decisión humana" className="ak-stack">
            {blocked ? (
              <p className="ak-banner ak-banner--error">
                Sin botón de aprobar: las reglas R01 (beneficiario autorizado) y R12 (cuenta bancaria) no se pueden aprobar.
                {card.determining_rule === "R01" && " Si el beneficiario es legítimo, agrégalo en Reglas y la factura se vuelve a decidir."}
              </p>
            ) : null}
            <div className="ak-row">
              {card.approvable && !blocked && <ApprovalDialog invoiceId={card.invoice_id} action="approve" onDone={onChange} />}
              <ApprovalDialog invoiceId={card.invoice_id} action="reject" onDone={onChange} />
            </div>
          </section>
        )}
        {view === "canonical" && card.state === "ESCALATE" && (
          <p className="ak-note">Las aprobaciones solo existen en tu sandbox.</p>
        )}

        <section aria-labelledby="campos" className="ak-stack">
          <h2 id="campos" className="ak-h2">
            Lo que leyó la IA
          </h2>
          <dl className="ak-fields">
            {detail.fields.map((f) => (
              <FieldRow key={f.name} field={f} checks={fieldChecks(f, jev)} active={active === f.name} onFocus={focusField} />
            ))}
          </dl>
        </section>

        {record && (
          <section aria-labelledby="reglas" className="ak-stack">
            <h2 id="reglas" className="ak-h2">
              Reglas
            </h2>
            <ul className="ak-stack" aria-label="Reglas que se activaron">
              {fired.map((r) => (
                <RuleRow key={r.rule} rule={r} decision={card.state === "inbox" ? undefined : card.state} />
              ))}
            </ul>
            {passed.length > 0 && (
              <details>
                <summary className="cursor-pointer text-small text-ink-muted">
                  {passed.length} reglas se cumplieron
                </summary>
                <ul className="ak-stack mt-3">
                  {passed.map((r) => (
                    <RuleRow key={r.rule} rule={r} />
                  ))}
                </ul>
              </details>
            )}
          </section>
        )}

        <Timeline detail={detail} />
      </div>

      <div className="ak-detail__doc">
        <PageViewer
          pages={detail.pages}
          page={page}
          onPageChange={setPage}
          boxes={detail.fields.flatMap((f) => f.boxes.map((b, i) => ({ ...b, key: `${f.name}-${i}`, active: active === f.name })))}
          label={`la factura ${detail.card.invoice_id}`}
        />
      </div>
    </article>
  );
}

/** A rule's sentence as the API words it, capitalised for a line of its own. */
function sentence(r: RuleView) {
  const s = r.reason_es || r.name_es;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function RuleRow({ rule, decision }: { rule: RuleView; decision?: "PAY" | "HOLD" | "ESCALATE" }) {
  const tone = rule.outcome === "pass" ? "PAY" : rule.outcome === "hold" ? "HOLD" : (decision ?? "ESCALATE");
  return (
    <li className="grid gap-1.5">
      <span className="ak-row">
        <RuleChip rule={rule.rule} name={rule.name_es} decision={tone === "PAY" ? "PAY" : tone === "HOLD" ? "HOLD" : "ESCALATE"} />
        {rule.outcome === "pass" && <CircleCheck aria-label="Se cumple" className="ak-icon ak-c-pagada" />}
      </span>
      <ReasonText text={sentence(rule)} className="text-small text-ink-muted" />
    </li>
  );
}

function FieldRow({
  field,
  checks,
  active,
  onFocus,
}: {
  field: FieldView;
  checks: { label: string; ok: boolean }[];
  active: boolean;
  onFocus: (f: FieldView | null) => void;
}) {
  const located = field.boxes.length > 0;
  return (
    <div
      className={`ak-field ${active ? "bg-desk" : ""}`}
      onMouseEnter={() => onFocus(field)}
      onMouseLeave={() => onFocus(null)}
      onFocus={() => onFocus(field)}
      onBlur={() => onFocus(null)}
      tabIndex={located ? 0 : undefined}
      aria-label={located ? `${field.label_es}: marcar en la página` : undefined}
    >
      <dt>
        {field.label_es}
        {field.critical && <span className="ak-note">Crítico</span>}
      </dt>
      <dd>
        <span className="ak-field__value">{field.value ?? <span className="ak-muted">No consta</span>}</span>
        {field.quote && (
          <DocSlip inline>
            <MarkedQuote quote={field.quote} value={field.value} />
          </DocSlip>
        )}
        <ul className="ak-checks">
          {checks.map((c) => (
            <li key={c.label} className={c.ok ? "ok" : "warn"}>
              {c.ok ? <CircleCheck aria-hidden className="ak-icon" /> : <CircleAlert aria-hidden className="ak-icon" />}
              {c.label}
            </li>
          ))}
        </ul>
      </dd>
    </div>
  );
}

/**
 * What would be paid, always to the account on file in the beneficiary list. The API sends
 * `payment` for a paid invoice; for one held or escalated, the account comes from the same
 * list (GET /api/rules), so an alert shows which account a payment could ever go to.
 */
function Payment({ detail, view }: { detail: Detail; view: View }) {
  const { card } = detail;
  const listed = card.beneficiary_id ?? null;
  const rules = useQuery({
    queryKey: ["rules", view],
    queryFn: () => unwrap(api.GET("/api/rules", { params: { query: { view } } })),
    enabled: !detail.payment && listed !== null && card.state !== "inbox",
  });
  const onFile = rules.data?.beneficiaries.find((b) => b.id === listed);
  const p = detail.payment
    ? detail.payment
    : onFile && card.amount_minor != null && card.currency && card.usd_minor != null
      ? {
          beneficiary_id: onFile.id,
          beneficiary_name: onFile.name,
          account_masked: onFile.account_masked,
          amount_minor: card.amount_minor,
          currency: card.currency,
          usd_minor: card.usd_minor,
        }
      : null;
  if (!p) return null;
  const title =
    card.state === "PAY" ? "Pago" : card.state === "HOLD" ? "No se pagará; la cuenta registrada es esta" : "Si se aprobara, se pagaría así";
  return (
    <section aria-labelledby="pago" className="ak-stack">
      <h2 id="pago" className="ak-h2">
        {title}
      </h2>
      <div className="ak-account">
        <Landmark aria-hidden className="ak-icon" />
        <div>
          <p className="ak-account__num">
            {formatMoney(p.amount_minor, p.currency)} a {p.beneficiary_name}
          </p>
          <p>{p.account_masked}</p>
          <p className="ak-account__src">
            Cuenta registrada en la Lista de beneficiarios ({p.beneficiary_id}), nunca la del documento · ≈{" "}
            {formatUsd(p.usd_minor)}
          </p>
        </div>
      </div>
    </section>
  );
}

/** Hidden content the code found and dropped before the AI read the document. */
function HiddenContent({ detail }: { detail: Detail }) {
  const flags = detail.record?.facts.flags;
  if (!flags) return null;
  const hidden = [...flags.hidden_content, ...flags.unicode_controls];
  const instructions = [...flags.instructions, ...flags.reader_instructions];
  if (hidden.length === 0 && instructions.length === 0 && !flags.html_text_mismatch) return null;
  return (
    <div className="ak-stack">
      {hidden.length > 0 && (
        <DocSlip caption="Contenido oculto que se descartó antes de leer">
          {hidden.map((h, i) => (
            <span key={i} className="block">
              <del>{h}</del>
            </span>
          ))}
        </DocSlip>
      )}
      {instructions.length > 0 && (
        <DocSlip caption="Instrucciones encontradas en el documento (no se siguieron)">
          {instructions.map((h, i) => (
            <span key={i} className="block">
              <del>{h}</del>
            </span>
          ))}
        </DocSlip>
      )}
      {flags.html_text_mismatch && (
        <p className="ak-note">El HTML del correo dice algo distinto a su texto plano.</p>
      )}
    </div>
  );
}

function Timeline({ detail }: { detail: Detail }) {
  const { card, record } = detail;
  const facts = record?.facts;
  const reader = facts?.calls.filter((c) => c.role === "reader") ?? [];
  const grounded = detail.fields.filter((f) => f.grounded).length;
  return (
    <section aria-labelledby="historia" className="ak-stack">
      <h2 id="historia" className="ak-h2">
        Historia
      </h2>
      <ol className="ak-timeline">
        <li>
          <Inbox aria-hidden className="ak-icon" />
          <div>
            <strong>Recibida por {CHANNEL[card.channel].label.toLowerCase()}</strong>
            <time dateTime={card.received_at}>{formatDateTime(card.received_at)}</time>
          </div>
        </li>
        {facts && (
          <li>
            <ScanText aria-hidden className="ak-icon" />
            <div>
              <strong>Leída por la IA</strong>
              <small>
                {facts.source.pages} {facts.source.pages === 1 ? "página" : "páginas"} · {grounded} de {detail.fields.length}{" "}
                datos con cita en la página{reader[0] ? ` · ${reader[0].model}` : ""}
              </small>
            </div>
          </li>
        )}
        {facts?.verification && (
          <li>
            <FileCheck aria-hidden className="ak-icon" />
            <div>
              <strong>Verificada en código</strong>
              <small>
                Riesgo {facts.verification.risk.toFixed(2).replace(".", ",")}
                {facts.verification.disagreements.length > 0 &&
                  ` · lecturas distintas en ${facts.verification.disagreements.length} campos`}
                {facts.verification.jev.length > 0 && " · JEV consultado"}
              </small>
            </div>
          </li>
        )}
        {record && (
          <li>
            <Gavel aria-hidden className="ak-icon" />
            <div>
              <strong>
                Decidida: {STATE_LABEL[record.decision]}
                {record.determining_rule ? ` (${record.determining_rule})` : ""}
              </strong>
              <time dateTime={record.created_at}>{formatDateTime(record.created_at)}</time>
              <small>
                Registro n.º {record.seq} de la cadena ·{" "}
                <span className="ak-hash">
                  <Link2 aria-hidden className="ak-icon" />
                  {record.hash.slice(0, 12)}
                </span>
              </small>
            </div>
          </li>
        )}
        {record?.human && (
          <li>
            <UserCheck aria-hidden className="ak-icon" />
            <div>
              <strong>
                {record.human.action === "approve" ? "Aprobada" : "Rechazada"} por {record.human.approver}
              </strong>
              <time dateTime={record.human.at}>{formatDateTime(record.human.at)}</time>
              {record.human.note && <small>{record.human.note}</small>}
            </div>
          </li>
        )}
      </ol>
    </section>
  );
}
