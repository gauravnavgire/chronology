```mermaid
gantt
    title Website relaunch
    dateFormat YYYY-MM-DD
    axisFormat %Y-%m-%d
    section Management
    Project kickoff :milestone, t1, 2025-01-06, 0d
    Public launch :milestone, t2, 2025-05-02, 0d
    section Design
    Designs signed off :milestone, t3, 2025-02-14, 0d
    section Content
    Content migration finished :t4, 2025-03-01, 2025-04-01
    section Backend
    New API live in staging :milestone, t5, 2025-03-21, 0d
    section Frontend
    Front end feature-complete :milestone, t6, 2025-04-04, 0d
    section QA
    QA sign-off :milestone, t7, 2025-04-18, 0d
```

Consistency report:
- WARNING [schedule] 'Designs signed off' (14 Feb 2025) happened after its planned date (7 Feb 2025): late by 7 days
- WARNING [schedule] 'Content migration finished' (Mar 2025) happened after its planned date (28 Feb 2025): late by up to 1.1 months
- WARNING [schedule] 'Front end feature-complete' (4 Apr 2025) happened after its planned date (21 Mar 2025): late by 14 days
- WARNING [schedule] 'Public launch' (2 May 2025) happened after its planned date (11 Apr 2025): late by 21 days
- INFO [schedule] 'New API live in staging' (21 Mar 2025) happened before its planned date (28 Mar 2025): early by 7 days
- INFO [order] 1 event(s) marked ≈ could have happened before the event listed just above them (their possible date ranges overlap).
