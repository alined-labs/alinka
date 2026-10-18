-- Alinka schema (PLAN section 6). Applied in file order by `python -m alinka.db migrate`.

CREATE TABLE sessions (
    id          text PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('canonical', 'sandbox')),
    run_name    text,                                -- data/runs/<name> the inputs come from
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz                          -- sandboxes: 24 hours after creation
);
CREATE INDEX sessions_expires_at ON sessions (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE rule_versions (
    id          bigserial PRIMARY KEY,
    session_id  text NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    rules_yaml  text NOT NULL,
    hash        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rule_versions_session ON rule_versions (session_id, id DESC);

CREATE TABLE sandbox_beneficiaries (
    session_id      text NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    beneficiary_id  text NOT NULL,
    beneficiary     jsonb NOT NULL,                  -- alinka.types.Beneficiary
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, beneficiary_id)
);

CREATE TABLE decisions (
    session_id  text NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    seq         integer NOT NULL CHECK (seq > 0),
    record_id   text NOT NULL UNIQUE,
    prev_hash   text NOT NULL,
    hash        text NOT NULL,
    canonical   bytea NOT NULL,                      -- RFC 8785 bytes of the record without hash
    decision    text NOT NULL CHECK (decision IN ('PAY', 'HOLD', 'ESCALATE')),
    invoice_id  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX decisions_invoice ON decisions (session_id, invoice_id, seq DESC);

CREATE TABLE ledger (
    id                   bigserial PRIMARY KEY,
    session_id           text NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    invoice_id           text NOT NULL,
    beneficiary_id       text,
    invoice_number_norm  text,
    doc_sha256           text NOT NULL,
    fiscal_id            text,
    amount_minor         bigint NOT NULL,
    currency             text NOT NULL,
    usd_minor            bigint NOT NULL,
    cost_center          text,
    period_start         date,
    period_end           date,
    status               text NOT NULL CHECK (status IN ('paid', 'approved', 'pending', 'rejected')),
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ledger_number_unique UNIQUE (session_id, beneficiary_id, invoice_number_norm),
    CONSTRAINT ledger_document_unique UNIQUE (session_id, doc_sha256)
);
CREATE INDEX ledger_session ON ledger (session_id, created_at);

CREATE TABLE responses (
    key           text PRIMARY KEY,
    model         text NOT NULL,
    request_hash  text NOT NULL,
    response      jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
INSERT INTO settings (key, value) VALUES ('live_uploads', 'false'), ('jev_mode', '"replay"');
