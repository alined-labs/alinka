# Evaluation report

Source: gold facts from data/labels. Rules 2026-10-18.1, as of 2026-10-17. 175 invoices; generated 2026-10-18T08:43:09+00:00.

## Headline

- **Improper approvals: 0 of 85** (one-sided 95% Clopper–Pearson upper bound 3.5%).
- Autonomy: 137 of 175 decided without a person (78%), next to a ceiling of 137 (78%).
- The month: 23 of 30 autonomous, ceiling 23 of 30.
- Decision accuracy 99.4%; escalation precision 100.0%; security-alert recall on attacks 100.0% (n=13), overall 100.0% (n=13).
- Rule accuracy: determining rule among the gold rules 97.7%, all gold rules fired 100.0% (n=85).
- verifier_risk_max picked from the data: — (default 0.7; not measured on gold facts, whose risk is 0).
- Latency p50 — ms, p95 — ms; cost per invoice — USD.

## Decisions (rows gold, columns ours)

| gold \ ours | PAY | HOLD | ESCALATE |
| --- | --- | --- | --- |
| PAY | 89 | 1 | 0 |
| HOLD | 0 | 47 | 0 |
| ESCALATE | 0 | 0 | 38 |

## Risk–coverage

| threshold | coverage (JEV on) | error | improper | coverage (JEV off) | error |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 0.7829 | 0.0073 | 0 | — | — |
| 0.1 | 0.7829 | 0.0073 | 0 | — | — |
| 0.15 | 0.7829 | 0.0073 | 0 | — | — |
| 0.2 | 0.7829 | 0.0073 | 0 | — | — |
| 0.25 | 0.7829 | 0.0073 | 0 | — | — |
| 0.3 | 0.7829 | 0.0073 | 0 | — | — |
| 0.35 | 0.7829 | 0.0073 | 0 | — | — |
| 0.4 | 0.7829 | 0.0073 | 0 | — | — |
| 0.45 | 0.7829 | 0.0073 | 0 | — | — |
| 0.5 | 0.7829 | 0.0073 | 0 | — | — |
| 0.55 | 0.7829 | 0.0073 | 0 | — | — |
| 0.6 | 0.7829 | 0.0073 | 0 | — | — |
| 0.65 | 0.7829 | 0.0073 | 0 | — | — |
| 0.7 | 0.7829 | 0.0073 | 0 | — | — |
| 0.75 | 0.7829 | 0.0073 | 0 | — | — |
| 0.8 | 0.7829 | 0.0073 | 0 | — | — |
| 0.85 | 0.7829 | 0.0073 | 0 | — | — |
| 0.9 | 0.7829 | 0.0073 | 0 | — | — |
| 0.95 | 0.7829 | 0.0073 | 0 | — | — |
| 1.0 | 0.7829 | 0.0073 | 0 | — | — |

JEV off: no data/runs/<run>-nojev recorded; JEV-off curve not drawn

## Disagreements (1)

See `evals/disagreements.csv`.
