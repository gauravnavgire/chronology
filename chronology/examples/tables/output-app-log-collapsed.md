## Chronology

| # | When | Exact date | Event | Confidence | Details | Source |
|---|---|---|---|---|---|---|
| 1 | 3 Jun 2025 14:00 | 3 Jun 2025 14:00:11 | deploy v2.14 started | high | level: INFO | row 1 |
| 2 | 3 Jun 2025 14:06 | 3 Jun 2025 14:06:40 – 3 Jun 2025 14:06:58 | upstream timeout calling payments (×7) | high | 7 occurrences; first 3 Jun 2025 14:06:40, last 3 Jun 2025 14:06:58; e.g. level: ERROR | row 2 … row 8 |
| 3 | 3 Jun 2025 14:07 | 3 Jun 2025 14:07:01 – 3 Jun 2025 14:07:58 | upstream timeout calling payments (×20) | high | 20 occurrences; first 3 Jun 2025 14:07:01, last 3 Jun 2025 14:07:58; e.g. level: ERROR | row 9 … row 28 |
| 4 | 3 Jun 2025 14:08 | 3 Jun 2025 14:08:01 – 3 Jun 2025 14:08:37 | upstream timeout calling payments (×13) | high | 13 occurrences; first 3 Jun 2025 14:08:01, last 3 Jun 2025 14:08:37; e.g. level: ERROR | row 29 … row 41 |
| 5 | 3 Jun 2025 14:09 | 3 Jun 2025 14:09:02 | page sent to on-call | high | level: WARN | row 42 |
| 6 | 3 Jun 2025 14:21 | 3 Jun 2025 14:21:37 | rollback to v2.13 started | high | level: INFO | row 55 |
| 7 | 3 Jun 2025 14:21 | 3 Jun 2025 14:21:40 | health check failed | high | level: INFO | row 43 |
| 8 | 3 Jun 2025 14:22 | 3 Jun 2025 14:22:00 – 3 Jun 2025 14:22:40 | health check failed (×3) | high | 3 occurrences; first 3 Jun 2025 14:22:00, last 3 Jun 2025 14:22:40; e.g. level: INFO | row 44 … row 46 |
| 9 | 3 Jun 2025 14:23 | 3 Jun 2025 14:23:00 – 3 Jun 2025 14:23:40 | health check failed (×3) | high | 3 occurrences; first 3 Jun 2025 14:23:00, last 3 Jun 2025 14:23:40; e.g. level: INFO | row 47 … row 49 |
| 10 | 3 Jun 2025 14:24 | 3 Jun 2025 14:24:00 – 3 Jun 2025 14:24:40 | health check failed (×3) | high | 3 occurrences; first 3 Jun 2025 14:24:00, last 3 Jun 2025 14:24:40; e.g. level: INFO | row 50 … row 52 |
| 11 | 3 Jun 2025 14:25 | 3 Jun 2025 14:25:00 – 3 Jun 2025 14:25:20 | health check failed (×2) | high | 2 occurrences; first 3 Jun 2025 14:25:00, last 3 Jun 2025 14:25:20; e.g. level: INFO | row 53 … row 54 |
| 12 | 3 Jun 2025 14:27 | 3 Jun 2025 14:27:05 | error rate back to baseline | high | level: INFO | row 56 |

Consistency report:
- INFO [table] app-log.csv: dates from column 'ts'
- INFO [table] app-log.csv: event titles from column 'message'
