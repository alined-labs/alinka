import { Dialog } from "@base-ui/react/dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useId, useState } from "react";

import { api, unwrap } from "~/api/client";
import type { Detail } from "~/lib/detail";

type Action = "approve" | "reject";

const COPY: Record<Action, { trigger: string; title: string; confirm: string; className: string }> = {
  approve: { trigger: "Aprobar", title: "Aprobar el pago", confirm: "Aprobar", className: "ak-btn ak-btn--primary" },
  reject: { trigger: "Rechazar", title: "Rechazar la factura", confirm: "Rechazar", className: "ak-btn ak-btn--secondary" },
};

/** Approve or reject an escalation by name. The API re-checks the caps and refuses R01 and R12. */
export function ApprovalDialog({ invoiceId, action, onDone }: { invoiceId: string; action: Action; onDone: (d: Detail) => void }) {
  const [open, setOpen] = useState(false);
  const [approver, setApprover] = useState("");
  const [note, setNote] = useState("");
  const nameId = useId();
  const noteId = useId();
  const qc = useQueryClient();
  const copy = COPY[action];

  const mutation = useMutation({
    mutationFn: () => {
      const body = { approver: approver.trim(), note: note.trim() || null };
      const params = { path: { invoice_id: invoiceId } };
      return unwrap(
        action === "approve"
          ? api.POST("/api/invoices/{invoice_id}/approve", { params, body })
          : api.POST("/api/invoices/{invoice_id}/reject", { params, body }),
      );
    },
    onSuccess: (detail) => {
      onDone(detail);
      void qc.invalidateQueries({ queryKey: ["board"] });
      void qc.invalidateQueries({ queryKey: ["log"] });
      setOpen(false);
    },
  });

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) mutation.reset();
      }}
    >
      <Dialog.Trigger className={copy.className}>
        {action === "approve" ? <Check aria-hidden className="ak-icon" /> : <X aria-hidden className="ak-icon" />}
        {copy.trigger}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className="ak-backdrop" />
        <Dialog.Popup className="ak-dialog">
          <Dialog.Title className="ak-h2">{copy.title}</Dialog.Title>
          <Dialog.Description className="ak-muted">
            Factura {invoiceId}. Tu nombre queda en el registro junto a la decisión.
          </Dialog.Description>
          <form
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (approver.trim()) mutation.mutate();
            }}
          >
            <label htmlFor={nameId} className="grid gap-1 text-small text-ink-muted">
              Nombre de quien {action === "approve" ? "aprueba" : "rechaza"}
              <input
                id={nameId}
                className="ak-input ak-input--text"
                value={approver}
                onChange={(e) => setApprover(e.target.value)}
                maxLength={120}
                required
                autoComplete="name"
              />
            </label>
            <label htmlFor={noteId} className="grid gap-1 text-small text-ink-muted">
              Nota (opcional)
              <input
                id={noteId}
                className="ak-input ak-input--text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={500}
              />
            </label>
            {mutation.isError && (
              <p role="alert" className="ak-banner ak-banner--error">
                {mutation.error.message}
              </p>
            )}
            <div className="ak-row justify-end">
              <Dialog.Close className="ak-btn ak-btn--ghost">Cancelar</Dialog.Close>
              <button type="submit" className={copy.className} disabled={!approver.trim() || mutation.isPending}>
                {copy.confirm}
              </button>
            </div>
          </form>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
