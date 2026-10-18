import type { Card } from "~/api/client";
import { formatMoney, formatUsd } from "~/lib/format";

import { AlertBadge, ChannelIcon, DocText, STATE_STYLE, StateBadge } from "./badges";

/** The beneficiary on the list, or the name as printed (document text) when it matches none. */
export function BeneficiaryName({ card }: { card: Card }) {
  if (card.beneficiary_id) return <span>{card.beneficiary_name}</span>;
  if (card.beneficiary_name) return <DocText label="Nombre en el documento">{card.beneficiary_name}</DocText>;
  return <span className="text-muted">Beneficiario no identificado</span>;
}

export function InvoiceCard({ card }: { card: Card }) {
  const alerted = card.alerts.length > 0;
  return (
    <li
      className={`rounded-md border bg-surface p-3 shadow-card ${alerted ? "border-2 border-alert" : "border-border"}`}
      aria-label={`Factura ${card.invoice_id}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-2 font-mono text-sm font-semibold">
          <ChannelIcon channel={card.channel} />
          {card.invoice_id}
        </span>
        <StateBadge state={card.state} />
      </div>
      <p className="mt-1 text-sm">
        <BeneficiaryName card={card} />
      </p>
      <p className="mt-1 text-sm font-medium">
        {formatMoney(card.amount_minor, card.currency)}
        {card.currency !== "USD" && card.usd_minor != null && (
          <span className="ml-2 text-xs font-normal text-muted">≈ {formatUsd(card.usd_minor)}</span>
        )}
      </p>
      {(alerted || card.technical_error) && (
        <p className="mt-2 flex flex-wrap gap-1">
          <AlertBadge rules={card.alerts} />
          {card.technical_error && (
            <span className={`rounded-pill px-2 py-0.5 text-xs ${STATE_STYLE.ESCALATE.bg} ${STATE_STYLE.ESCALATE.text}`}>
              error técnico
            </span>
          )}
        </p>
      )}
      {card.reason_es && <p className="mt-2 text-sm text-muted">{card.reason_es}</p>}
      {card.approver && <p className="mt-1 text-xs text-muted">Decidida por {card.approver}</p>}
    </li>
  );
}
