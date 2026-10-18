# Evaluation report

Source: gold facts from data/labels. Rules 2026-10-18.1, as of 2026-10-17. 150 invoices; generated 2026-10-18T08:24:58+00:00.

## Headline

- **Improper approvals: 0 of 62** (one-sided 95% Clopper–Pearson upper bound 4.7%).
- Autonomy: 127 of 150 decided without a person (85%), next to a ceiling of 127 (85%).
- The month: 23 of 30 autonomous, ceiling 23 of 30.
- Decision accuracy 99.3%; escalation precision 100.0%; security-alert recall on attacks — (n=0), overall — (n=0).
- Rule accuracy: determining rule among the gold rules 96.8%, all gold rules fired 100.0% (n=62).
- verifier_risk_max picked from the data: — (default 0.7; not measured on gold facts, whose risk is 0).
- Latency p50 — ms, p95 — ms; cost per invoice — USD.

## Decisions (rows gold, columns ours)

| gold \ ours | PAY | HOLD | ESCALATE |
| --- | --- | --- | --- |
| PAY | 87 | 1 | 0 |
| HOLD | 0 | 39 | 0 |
| ESCALATE | 0 | 0 | 23 |

## Risk–coverage

| threshold | coverage (JEV on) | error | improper | coverage (JEV off) | error |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 0.8467 | 0.0079 | 0 | — | — |
| 0.1 | 0.8467 | 0.0079 | 0 | — | — |
| 0.15 | 0.8467 | 0.0079 | 0 | — | — |
| 0.2 | 0.8467 | 0.0079 | 0 | — | — |
| 0.25 | 0.8467 | 0.0079 | 0 | — | — |
| 0.3 | 0.8467 | 0.0079 | 0 | — | — |
| 0.35 | 0.8467 | 0.0079 | 0 | — | — |
| 0.4 | 0.8467 | 0.0079 | 0 | — | — |
| 0.45 | 0.8467 | 0.0079 | 0 | — | — |
| 0.5 | 0.8467 | 0.0079 | 0 | — | — |
| 0.55 | 0.8467 | 0.0079 | 0 | — | — |
| 0.6 | 0.8467 | 0.0079 | 0 | — | — |
| 0.65 | 0.8467 | 0.0079 | 0 | — | — |
| 0.7 | 0.8467 | 0.0079 | 0 | — | — |
| 0.75 | 0.8467 | 0.0079 | 0 | — | — |
| 0.8 | 0.8467 | 0.0079 | 0 | — | — |
| 0.85 | 0.8467 | 0.0079 | 0 | — | — |
| 0.9 | 0.8467 | 0.0079 | 0 | — | — |
| 0.95 | 0.8467 | 0.0079 | 0 | — | — |
| 1.0 | 0.8467 | 0.0079 | 0 | — | — |

JEV off: no data/runs/<run>-nojev recorded; JEV-off curve not drawn

## Disagreements (1)

See `evals/disagreements.csv`.
