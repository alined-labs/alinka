-- Probar: invoices a visitor runs in their sandbox (samples now, uploads later). The facts
-- are stored here so the board and the invoice routes serve them like the run's inputs;
-- they go when the sandbox goes.
CREATE TABLE try_invoices (
    session_id  text NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    invoice_id  text NOT NULL,
    sample_id   text,                                -- the dataset invoice it copies, if any
    facts       jsonb NOT NULL,                      -- alinka.types.InvoiceFacts
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, invoice_id)
);
