-- Probar uploads: the uploaded file stays with its sandbox (and goes with it after 24 h),
-- and every accepted upload is logged by client IP for the quotas.
ALTER TABLE try_invoices
    ADD COLUMN document  bytea,                      -- uploads only; samples live in data/
    ADD COLUMN filename  text;

CREATE TABLE upload_log (
    id          bigserial PRIMARY KEY,
    client_ip   text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX upload_log_ip ON upload_log (client_ip, created_at);
CREATE INDEX upload_log_created ON upload_log (created_at);
