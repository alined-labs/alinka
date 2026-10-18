import { Link } from "react-router";

import type { Card } from "~/api/client";
import { amountParts, formatDay, formatUsd } from "~/lib/format";
import { invoiceTransitionName, useMotionOK } from "~/lib/motion";
import { useView } from "~/lib/view";

import { CHANNEL, ChannelIcon, DecisionChip, DocSlip, ReasonText, RuleChip, SecurityTag } from "./badges";

/** The beneficiary on the list, or the name as printed (document text) when it matches none. */
export function BeneficiaryName({ card, inline = true }: { card: Card; inline?: boolean }) {
  if (card.beneficiary_id) return <span>{card.beneficiary_name}</span>;
  if (card.beneficiary_name)
    return (
      <DocSlip caption="Nombre en el documento" inline={inline}>
        {card.beneficiary_name}
      </DocSlip>
    );
  return <span className="ak-muted">Beneficiario no identificado</span>;
}

export function Amount({ minor, currency }: { minor: number | null | undefined; currency: string | null | undefined }) {
  const parts = amountParts(minor, currency);
  if (!parts) return <span className="ak-muted">—</span>;
  return (
    <>
      {parts.number}
      <small>{parts.currency}</small>
    </>
  );
}

export function InvoiceCard({ card, moved = false }: { card: Card; moved?: boolean }) {
  const decided = card.state !== "inbox";
  const [view] = useView();
  const motion = useMotionOK();
  return (
    <li className="grid">
      <Link
        to={{ pathname: `/facturas/${encodeURIComponent(card.invoice_id)}`, search: view === "canonical" ? "?vista=canonica" : "" }}
        className={`ak-card ${moved ? "ak-moved" : ""}`}
        style={{ viewTransitionName: invoiceTransitionName(card.invoice_id), viewTransitionClass: "card" }}
        viewTransition={motion}
        aria-label={`Factura ${card.invoice_id}: ${card.beneficiary_name ?? "beneficiario no identificado"}`}
      >
      <div className="ak-card__top">
        <span className="ak-card__who min-w-0">
          <BeneficiaryName card={card} />
        </span>
        <span className="ak-card__amount">
          <Amount minor={card.amount_minor} currency={card.currency} />
        </span>
      </div>
      <p className="ak-card__meta">
        <ChannelIcon channel={card.channel} />
        <span>
          {card.invoice_id} · {CHANNEL[card.channel].label} · {formatDay(card.received_at)}
        </span>
        {card.currency !== "USD" && card.usd_minor != null && (
          <span>· ≈ {formatUsd(card.usd_minor)}</span>
        )}
      </p>
      {card.reason_es && <ReasonText text={card.reason_es} className="ak-card__reason" />}
      {(decided || card.alerts.length > 0) && (
        <div className="ak-card__tags">
          <SecurityTag rules={card.alerts} />
          {decided && <DecisionChip decision={card.state as Exclude<Card["state"], "inbox">} />}
          {card.determining_rule && (
            <RuleChip
              rule={card.determining_rule}
              name={card.determining_rule_es}
              decision={card.state === "inbox" ? undefined : card.state}
            />
          )}
          {card.technical_error && <span className="ak-rule ak-rule--escala">error técnico</span>}
        </div>
      )}
      {card.approver && <p className="ak-note">Decidida por {card.approver}</p>}
      </Link>
    </li>
  );
}
