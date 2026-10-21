Chronology — events per minute

3 Jun 2025 14:00 │██ 1
                 ┊ 5 empty minutes (3 Jun 2025 14:01 – 3 Jun 2025 14:05)
3 Jun 2025 14:06 │██████████████ 7
3 Jun 2025 14:07 │████████████████████████████████████████ 20
3 Jun 2025 14:08 │██████████████████████████ 13
3 Jun 2025 14:09 │██ 1
                 ┊ 11 empty minutes (3 Jun 2025 14:10 – 3 Jun 2025 14:20)
3 Jun 2025 14:21 │████ 2
3 Jun 2025 14:22 │██████ 3
3 Jun 2025 14:23 │██████ 3
3 Jun 2025 14:24 │██████ 3
3 Jun 2025 14:25 │████ 2
3 Jun 2025 14:26 │
3 Jun 2025 14:27 │██ 1

Largest gaps (periods in which no event can have happened):
- 13 minutes: after 'page sent to on-call' (3 Jun 2025 14:09:02) → before 'rollback to v2.13 started' (3 Jun 2025 14:21:37)
- 6.5 minutes: after 'deploy v2.14 started' (3 Jun 2025 14:00:11) → before 'upstream timeout calling payments' (3 Jun 2025 14:06:40)
- 1.7 minutes: after 'health check failed' (3 Jun 2025 14:25:20) → before 'error rate back to baseline' (3 Jun 2025 14:27:05)
- 24 seconds: after 'upstream timeout calling payments' (3 Jun 2025 14:08:37) → before 'page sent to on-call' (3 Jun 2025 14:09:02)
- 19 seconds: after 'health check failed' (3 Jun 2025 14:21:40) → before 'health check failed' (3 Jun 2025 14:22:00)

Busiest periods (by minute):
- 3 Jun 2025 14:07: 20 events (36% of events placed at this level)
- 3 Jun 2025 14:08: 13 events (23% of events placed at this level)
- 3 Jun 2025 14:06: 7 events (12% of events placed at this level)
- 3 Jun 2025 14:22: 3 events (5% of events placed at this level)
- 3 Jun 2025 14:23: 3 events (5% of events placed at this level)

Consistency report:
- INFO [table] app-log.csv: dates from column 'ts'
- INFO [table] app-log.csv: event titles from column 'message'
