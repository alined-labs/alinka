# Evaluation report

Source: recorded run data/runs/all-jev-on (JEV off: data/runs/all-jev-off). Rules 2026-10-18.1, as of 2026-10-17. 175 invoices; generated 2026-10-18T09:38:15+00:00.

## Headline

- **Improper approvals: 0 of 85** (one-sided 95% Clopper–Pearson upper bound 3.5%).
- Autonomy: 124 of 175 decided without a person (71%; 124 of them as gold), next to a ceiling of 137 (78%).
- The month: 23 of 30 autonomous (23 as gold), ceiling 23 of 30.
- Decision accuracy 92.6%; escalation precision 74.5%; security-alert recall on attacks 100.0% (n=13), overall 100.0% (n=13).
- Rule accuracy: determining rule among the gold rules 95.3%, all gold rules fired 100.0% (n=85).
- verifier_risk_max picked from the data: 0.9 with JEV on, 0.7 with JEV off (default 0.7; the pick decides 1 more invoice(s) autonomously than the default).
- Latency p50 11440 ms, p95 16379 ms; cost per invoice 0.02348 USD.

## Decisions (rows gold, columns ours)

| gold \ ours | PAY | HOLD | ESCALATE |
| --- | --- | --- | --- |
| PAY | 77 | 0 | 13 |
| HOLD | 0 | 47 | 0 |
| ESCALATE | 0 | 0 | 38 |

## Risk–coverage

| threshold | coverage (JEV on) | error | improper | coverage (JEV off) | error |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 0.6686 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.1 | 0.68 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.15 | 0.6857 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.2 | 0.6971 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.25 | 0.6971 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.3 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.35 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.4 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.45 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.5 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.55 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.6 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.65 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.7 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.75 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.8 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.85 | 0.7086 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.9 | 0.7143 | 0.0 | 0 | 0.7143 | 0.0 |
| 0.95 | 0.7143 | 0.0 | 0 | 0.7143 | 0.0 |
| 1.0 | 0.7143 | 0.0 | 0 | 0.7143 | 0.0 |

## Disagreements (13)

See `evals/disagreements.csv`.
