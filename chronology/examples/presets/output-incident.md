## Checkout outage, 3 June 2025

| # | When | Exact date | Event | Confidence | Details | Source |
|---|---|---|---|---|---|---|
| 1 | 3 Jun 2025 14:02:11 | 3 Jun 2025 14:02:11 | Deploy of payments v2.14 starts | high |  | line 12 |
| 2 | 3 Jun 2025 14:05:00 | 3 Jun 2025 14:05:00 | Database connection pool exhausted | medium | Engineer: 'probably started around 14:05' | line 31 |
| 3 | 3 Jun 2025 14:06:40 | 3 Jun 2025 14:06:40 | 5xx rate on /checkout rises above 20% | high |  | line 19 |
| 4 | 3 Jun 2025 14:09:02 | 3 Jun 2025 14:09:02 | On-call paged | high |  | line 23 |
| 5 | 3 Jun 2025 14:21:37 | 3 Jun 2025 14:21:37 | Rollback to v2.13 started | high |  | line 44 |
| 6 | 3 Jun 2025 14:27:05 | 3 Jun 2025 14:27:05 | Error rate back to baseline | high |  | line 52 |
| 7 | 3 Jun 2025 14:40 | 3 Jun 2025 14:40 | All-clear posted | high |  | line 60 |

Largest gaps (periods in which no event can have happened):
- 13 minutes: after 'Error rate back to baseline' (3 Jun 2025 14:27:05) → before 'All-clear posted' (3 Jun 2025 14:40)
- 13 minutes: after 'On-call paged' (3 Jun 2025 14:09:02) → before 'Rollback to v2.13 started' (3 Jun 2025 14:21:37)
- 5.5 minutes: after 'Rollback to v2.13 started' (3 Jun 2025 14:21:37) → before 'Error rate back to baseline' (3 Jun 2025 14:27:05)
- 2.8 minutes: after 'Deploy of payments v2.14 starts' (3 Jun 2025 14:02:11) → before 'Database connection pool exhausted' (3 Jun 2025 14:05:00)
- 2.4 minutes: after '5xx rate on /checkout rises above 20%' (3 Jun 2025 14:06:40) → before 'On-call paged' (3 Jun 2025 14:09:02)

Busiest periods (by second):
- None: no second has more than one event.

Consistency report:
- No problems found.
