import { CircleCheck, Clock, FileText, Image, Inbox, Mail, MessageSquare, OctagonX, ShieldAlert } from "lucide-react";

import type { Card } from "~/api/client";
import { type CardState, STATE_LABEL } from "~/lib/board";

const CHANNEL = {
  email: { icon: Mail, label: "Correo" },
  pdf: { icon: FileText, label: "PDF" },
  image: { icon: Image, label: "Imagen" },
  chat: { icon: MessageSquare, label: "Chat" },
} as const satisfies Record<Card["channel"], { icon: unknown; label: string }>;

export function ChannelIcon({ channel, withLabel = false }: { channel: Card["channel"]; withLabel?: boolean }) {
  const { icon: Icon, label } = CHANNEL[channel];
  return (
    <span className="inline-flex items-center gap-1 text-muted" title={`Canal: ${label}`}>
      <Icon aria-hidden size={16} />
      <span className={withLabel ? "text-xs" : "sr-only"}>{withLabel ? label : `Canal: ${label}`}</span>
    </span>
  );
}

export const STATE_STYLE: Record<CardState, { icon: typeof Inbox; text: string; bg: string; border: string }> = {
  inbox: { icon: Inbox, text: "text-inbox", bg: "bg-inbox-bg", border: "border-inbox" },
  PAY: { icon: CircleCheck, text: "text-pay", bg: "bg-pay-bg", border: "border-pay" },
  HOLD: { icon: OctagonX, text: "text-hold", bg: "bg-hold-bg", border: "border-hold" },
  ESCALATE: { icon: Clock, text: "text-escalate", bg: "bg-escalate-bg", border: "border-escalate" },
};

/** The decision as icon plus word, so colour is never the only signal. */
export function StateBadge({ state }: { state: CardState }) {
  const s = STATE_STYLE[state];
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-xs font-medium ${s.text} ${s.bg}`}>
      <Icon aria-hidden size={14} />
      {STATE_LABEL[state]}
    </span>
  );
}

/** A security alert has its own icon and outline. */
export function AlertBadge({ rules }: { rules: readonly string[] }) {
  if (rules.length === 0) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-pill border-2 border-alert bg-alert-bg px-2 py-0.5 text-xs font-semibold text-alert">
      <ShieldAlert aria-hidden size={14} />
      Alerta de seguridad <span className="font-mono">{rules.join(", ")}</span>
    </span>
  );
}

/**
 * "Texto del documento": text that came from a document. React escapes it; the style marks it
 * as a quotation so it never reads as part of the interface.
 */
export function DocText({ children, label = "Texto del documento" }: { children: string; label?: string }) {
  return (
    <q className="doc-text inline-block" aria-label={`${label}: ${children}`}>
      {children}
    </q>
  );
}
