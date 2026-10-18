# Evaluation report

Source: recorded run data/runs/all-jev-on (JEV off: data/runs/all-jev-off). Rules 2026-10-18.1, as of 2026-10-17. 175 invoices; generated 2026-10-18T09:07:01+00:00.

## Headline

- **Improper approvals: 0 of 85** (one-sided 95% Clopper–Pearson upper bound 3.5%).
- Autonomy: 126 of 175 decided without a person (72%; 124 of them as gold), next to a ceiling of 137 (78%).
- The month: 24 of 30 autonomous (23 as gold), ceiling 23 of 30.
- Decision accuracy 91.4%; escalation precision 73.5%; security-alert recall on attacks 100.0% (n=13), overall 100.0% (n=13).
- Rule accuracy: determining rule among the gold rules 92.9%, all gold rules fired 100.0% (n=85).
- verifier_risk_max picked from the data: 0.9 with JEV on, 0.7 with JEV off (default 0.7; the pick decides 1 more invoice(s) autonomously than the default).
- Latency p50 11440 ms, p95 16379 ms; cost per invoice 0.02348 USD.

## Decisions (rows gold, columns ours)

| gold \ ours | PAY | HOLD | ESCALATE |
| --- | --- | --- | --- |
| PAY | 77 | 0 | 13 |
| HOLD | 0 | 47 | 0 |
| ESCALATE | 0 | 2 | 36 |

## Risk–coverage

| threshold | coverage (JEV on) | error | improper | coverage (JEV off) | error |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 0.68 | 0.0168 | 0 | 0.7257 | 0.0157 |
| 0.1 | 0.6914 | 0.0165 | 0 | 0.7257 | 0.0157 |
| 0.15 | 0.6971 | 0.0164 | 0 | 0.7257 | 0.0157 |
| 0.2 | 0.7086 | 0.0161 | 0 | 0.7257 | 0.0157 |
| 0.25 | 0.7086 | 0.0161 | 0 | 0.7257 | 0.0157 |
| 0.3 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.35 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.4 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.45 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.5 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.55 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.6 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.65 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.7 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.75 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.8 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.85 | 0.72 | 0.0159 | 0 | 0.7257 | 0.0157 |
| 0.9 | 0.7257 | 0.0157 | 0 | 0.7257 | 0.0157 |
| 0.95 | 0.7257 | 0.0157 | 0 | 0.7257 | 0.0157 |
| 1.0 | 0.7257 | 0.0157 | 0 | 0.7257 | 0.0157 |

## Disagreements (15)

See `evals/disagreements.csv`.
