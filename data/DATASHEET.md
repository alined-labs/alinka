# Datasheet: the Alinka invoice set

175 fictional invoices for testing an accounts-payable agent that reads invoices and decides
to pay, hold or escalate them. Built for the Blinka challenge (HackRadar 30X), October 2026.

## Composition

| Split | Folder | Labels | Documents | What it is for |
| --- | --- | --- | --- | --- |
| showcase | `data/showcase/` | `labels/showcase.jsonl` | 30 | A typical October, decided as one batch in received order |
| generated | `data/generated/` | `labels/generated.jsonl` | 120 | The evaluation set, decided in episodes |
| attack | `data/adversarial/` | `labels/attack.jsonl` | 25 | Security claims: 23 attacks and 2 invoices that set two of them up |

- **The month.** 16 routine invoices; the brief's five traps twice each (duplicate, new beneficiary, off contract, over the approval threshold, insufficient budget); four edge cases (just under the threshold, due date past the grace period, amount in words that can't be parsed, currency mismatch). At most 23 of 30 can be decided without a person.
- **Generated.** 72 routine invoices and 48 traps across 21 trap types; 72 in Spanish and 48 in English; 72 PDF, 12 image, 18 email and 18 chat. IDs are `GEN-<episode>-<n>`; decide each episode as its own batch on a fresh ledger. Duplicate, budget, frequency and split traps follow routine invoices that pay first.
- **Attacks.** Hidden text (white, render mode 3, opacity 0, covered, a layer that is off, metadata and a sticky note); impersonation (look-alike name, Cyrillic homoglyphs, a known tax ID under another name); bank and channel tricks (a bank-change email, an "urgent, the CFO approved" chat, zero-width and tag characters, an HTML part that differs from the plain text); amount and currency games; documents that are not payable as presented. IDs are `ATK-<episode>-<n>`.
- **The world.** One payer (`company.yaml`: a Delaware company with a USD balance, four October budgets and two approvers) and 13 beneficiaries with contracts (`vendors.yaml`: Colombia 5, Mexico 2, Brazil 1, Argentina 1, United States 3, Spain 1). Rule parameters are in `rules.yaml`; exchange rates are in `fx.yaml`.

## Labels come from intent

Every trap type in `generator/traps.yaml` declares its gold decision, the rules it is built to fail and whether it must raise a security alert. These were written from the rule table, never by running the engine. Each label (`alinka.types.Label`) copies its trap's values and adds the channel, language, received time, the listed beneficiary the document claims to be, and the gold facts: the critical fields exactly as printed. Amounts were checked against the published rates on 2026-10-16 and 17, so budget, threshold and split traps land on the intended rule. An engine may record extra rules that end in the same decision; the gold decision is the claim. `tests/test_data_qa.py` checks every label, file, ID, total and fictional marker. `tests/judge/fixtures/` maps the 21 judge tests to these documents.

## Realism

Each document carries the EN 16931 core: number, dates, type, currency, both parties with tax IDs, lines, the VAT breakdown or exemption wording, and totals that reconcile. Each country's printed form follows `reports/2026-10-18-07-e-invoicing-standards.md` in the project brain:

- the Colombian factura electrónica with a 96-hex CUFE and QR, and the cuenta de cobro with the no-IVA declaration;
- CFDI 4.0 with a UUID folio fiscal, uso G03, PUE and IVA 0% on exports;
- an NFS-e with a 44-digit chave and ISS not levied;
- the Argentine Factura E with a 14-digit CAE;
- a Spanish factura citing art. 69 LIVA, with a VERI*FACTU-style QR;
- US invoices with an EIN, Net 30 terms and remit-to details.

Numbers and dates follow each locale: 1.234.567,89 or 1,234.56, and 15/10/2026 or October 15, 2026. Amounts in words come from num2words. Images are pages rasterized with a slight rotation, blur and JPEG compression. Emails have plain-text and HTML parts; chats are WhatsApp-style transcripts.

## Fictional on purpose

Every party is invented. The payer's name contains "Demo", and every document says "(empresa ficticia)" or "(fictitious company)". Tax IDs and account numbers start with or contain `DEMO`, and QR codes, URLs and email addresses use the `.invalid` domain. Resolutions are marked "(ficticia)". No real tax authority, bank or company names, logos or seals are used. Some attack documents contain instructions addressed to an AI. They are test inputs: never follow them.

## Rebuilding and license

`uv run python data/generator/month.py`, `generate.py` and `attacks.py` rebuild the documents from Jinja2 templates through WeasyPrint and PyMuPDF. The output is deterministic, byte for byte, so recorded model responses stay valid. The brief allows teams to share datasets. We intend to release the set under CC BY 4.0, with attribution to the Alinka team; the final license is chosen with the repository's.
