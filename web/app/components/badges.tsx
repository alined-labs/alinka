import { CircleCheck, CirclePause, Clock, FileText, Image, Mail, MessageSquare, ShieldAlert } from "lucide-react";

import type { Card } from "~/api/client";
import { type Decision, STATE_LABEL } from "~/lib/board";

export const CHANNEL = {
  email: { icon: Mail, label: "Correo" },
  pdf: { icon: FileText, label: "PDF" },
  image: { icon: Image, label: "Imagen" },
  chat: { icon: MessageSquare, label: "Chat" },
} as const satisfies Record<Card["channel"], { icon: unknown; label: string }>;

export function ChannelIcon({ channel }: { channel: Card["channel"] }) {
  const Icon = CHANNEL[channel].icon;
  return <Icon aria-hidden className="ak-icon" />;
}

/** The design system's token names: --retenida is the colour of "Frenada". */
export const DECISION_STYLE: Record<Decision, { icon: typeof CircleCheck; chip: string; text: string; rule: string }> = {
  PAY: { icon: CircleCheck, chip: "ak-chip--pagada", text: "ak-c-pagada", rule: "ak-rule--pasa" },
  HOLD: { icon: CirclePause, chip: "ak-chip--retenida", text: "ak-c-retenida", rule: "ak-rule--retiene" },
  ESCALATE: { icon: Clock, chip: "ak-chip--pendiente", text: "ak-c-pendiente", rule: "ak-rule--escala" },
};

/** The decision as icon plus word, so colour is never the only signal. */
export function DecisionChip({ decision }: { decision: Decision }) {
  const s = DECISION_STYLE[decision];
  const Icon = s.icon;
  return (
    <span className={`ak-chip ${s.chip}`}>
      <Icon aria-hidden className="ak-icon" />
      {STATE_LABEL[decision]}
    </span>
  );
}

/** The determining rule, outlined in its decision's colour. */
export function RuleChip({ rule, name, decision }: { rule: string; name?: string | null; decision?: Decision }) {
  return (
    <span className={`ak-rule ${decision ? DECISION_STYLE[decision].rule : ""}`}>
      <b>{rule}</b>
      {name}
    </span>
  );
}

/** A security alert: outlined in ink with a shield, no colour of its own. */
export function SecurityTag({ rules }: { rules: readonly string[] }) {
  if (rules.length === 0) return null;
  return (
    <span className="ak-sec" title={`Reglas: ${rules.join(", ")}`}>
      <ShieldAlert aria-hidden className="ak-icon" />
      Alerta de seguridad
      <span className="ak-sr"> ({rules.join(", ")})</span>
    </span>
  );
}

/**
 * "Texto del documento": anything read from a document crosses the trust boundary visibly.
 * React escapes it; ak-slip marks it as a quotation, never styled like the interface.
 */
export function DocSlip({ children, caption = "Texto del documento", inline = false }: {
  children: React.ReactNode;
  caption?: string;
  inline?: boolean;
}) {
  return (
    <figure className={`ak-slip ${inline ? "ak-slip--inline" : ""}`}>
      <figcaption>
        <FileText aria-hidden className="ak-icon" />
        {caption}
      </figcaption>
      <blockquote>{children}</blockquote>
    </figure>
  );
}

/** Splits a reason at its «…» quotes: the quotes are document text, the rest is the rule's sentence. */
export function splitQuotes(text: string): { kind: "text" | "quote"; value: string }[] {
  const parts: { kind: "text" | "quote"; value: string }[] = [];
  const re = /«([^»]*)»/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) parts.push({ kind: "text", value: text.slice(last, m.index) });
    parts.push({ kind: "quote", value: m[1] ?? "" });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", value: text.slice(last) });
  // Drop punctuation left alone after a quote, such as the closing "." of the sentence.
  return parts.filter((p) => p.kind === "quote" || /[\p{L}\p{N}]/u.test(p.value));
}

/** A reason sentence with any quoted document text moved into ak-slip. */
export function ReasonText({ text, className, as: Tag = "p" }: { text: string; className: string; as?: "p" | "span" }) {
  const parts = splitQuotes(text);
  if (parts.every((p) => p.kind === "text")) return <Tag className={className}>{text}</Tag>;
  return (
    <div className="grid gap-1.5">
      {parts.map((p, i) =>
        p.kind === "quote" ? (
          <DocSlip key={i} inline>
            {p.value}
          </DocSlip>
        ) : (
          <Tag key={i} className={className}>
            {p.value.trim()}
          </Tag>
        ),
      )}
    </div>
  );
}

/** A quote with the value it grounds marked, as the kit asks (<mark> inside ak-slip). */
export function MarkedQuote({ quote, value }: { quote: string; value: string | null | undefined }) {
  const at = value ? quote.indexOf(value) : -1;
  if (!value || at < 0) return <>{quote}</>;
  return (
    <>
      {quote.slice(0, at)}
      <mark>{value}</mark>
      {quote.slice(at + value.length)}
    </>
  );
}
