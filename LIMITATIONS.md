# Limitations

Alinka is a hackathon prototype for the Blinka challenge. What it does not do:

- **Synthetic data only.** All 175 documents, the payer (Ceiba Demo Labs, Inc.), the 13 beneficiaries, their contracts and accounts are fictional. Tax IDs start with `DEMO`, URLs use `.invalid`, and no real authority, bank or company appears. Numbers measured on this set say how the system behaves on these traps, not on a real supplier base.
- **No integration.** There is no connection to Blinka, a bank, an ERP or a tax authority. The balance, budgets and beneficiary list are YAML files; the "payment" is a preview of what would be sent to the account on file.
- **No money moves.** Pagada means "the rules allow this payment"; nothing is paid.
- **US-only processing.** The payer is a Delaware company paying in USD equivalents; FX comes from four official rates (TRM, Banxico FIX, PTAX, ECB) recorded in `data/fx.yaml` for one as-of date. Tax withholding, e-invoice validation (UBL, CII, CFDI XML) and local compliance are out of scope.
- **Recorded reading.** The API and the evaluation replay recorded model responses (`cache/responses/`, `data/runs/`). Live reading of uploaded documents is switched off.
- **Demo sandboxes, no login.** Each visitor gets a 24-hour sandbox through a cookie; approvals ask for a name but nobody is authenticated. Saving rules or adding a beneficiary re-decides the sandbox from scratch, which also clears its earlier approvals.
- **Images read least well.** Field accuracy on photographed or scanned images is 87.6% against 99.8% on PDFs (`evals/report.json`); weak readings escalate under R10 rather than pay.
- **Page images** are rendered from the source documents; emails and chats without a page show a placeholder.
