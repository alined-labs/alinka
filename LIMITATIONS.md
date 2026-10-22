# Limitations

Alinka is a hackathon prototype for the Blinka challenge. What it does not do:

- **The public demo replays recordings.** The site answers from responses recorded from the API: every visitor shares the same recorded sandbox, Probar's samples always give the same results in any order, and nothing that writes (rules, beneficiaries, approvals, uploads) is accepted. A sample run in Probar does not appear on the recorded board.
- **Synthetic data only.** All 175 documents, the payer (Ceiba Demo Labs, Inc.), the 13 beneficiaries, their contracts and accounts are fictional. Tax IDs start with `DEMO`, URLs use `.invalid`, and no real authority, bank or company appears. Numbers measured on this set say how the system behaves on these traps, not on a real supplier base.
- **No integration.** There is no connection to Blinka, a bank, an ERP or a tax authority. The balance, budgets and beneficiary list are YAML files; the "payment" is a preview of what would be sent to the account on file.
- **No money moves.** Pagada means "the rules allow this payment"; nothing is paid.
- **US-only processing.** The payer is a Delaware company paying in USD equivalents; FX comes from four official rates (TRM, Banxico FIX, PTAX, ECB) recorded in `data/fx.yaml` for one as-of date. Tax withholding, e-invoice validation (UBL, CII, CFDI XML) and local compliance are out of scope.
- **Recorded reading.** The board, the evaluation and Probar's samples replay recorded model responses (`cache/responses/`, `data/runs/`); only the steps after the reading run live. Against the FastAPI service, uploads in Probar are read live only while an administrator switches them on (off by default), within their limits: PDF, PNG or JPG, 4 MB, 3 pages, 5 per 10 minutes and 30 a day per client IP, 200 a day in total. Files and results are deleted with the sandbox after 24 hours.
- **Probar runs are serial.** At most 2 runs at once on the server and 1 per visitor; sample runs are limited to 60 an hour per client IP. Running the same sample twice makes the second a duplicate under R03, and a sample can collide with the month's invoices once "Ejecutar agente" has run in the same sandbox.
- **Demo sandboxes, no login.** Each visitor gets a 24-hour sandbox through a cookie; approvals ask for a name but nobody is authenticated. Saving rules or adding a beneficiary re-decides the sandbox from scratch, which also clears its earlier approvals.
- **Images read least well.** Field accuracy on photographed or scanned images is 87.6% against 99.8% on PDFs (`evals/report.json`); weak readings escalate under R10 rather than pay.
- **Page images** are rendered from the source documents; emails and chats show the page built in code from their visible text, not the original client's rendering.
