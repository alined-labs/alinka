-- Match the ledger to alinka.decide.ledger.LedgerEntry (Lane A): a billing-period key,
-- the normalised fiscal ID, and the received and decided dates.
ALTER TABLE ledger
    DROP COLUMN fiscal_id,
    DROP COLUMN period_start,
    DROP COLUMN period_end,
    ADD COLUMN fiscal_id_norm text,
    ADD COLUMN period text,
    ADD COLUMN received date,
    ADD COLUMN decided date;
UPDATE ledger SET received = created_at::date, decided = created_at::date;
ALTER TABLE ledger ALTER COLUMN received SET NOT NULL, ALTER COLUMN decided SET NOT NULL;
