## Chronology

| # | When | Exact date | Event | Confidence | Details | Source |
|---|---|---|---|---|---|---|
| 1 | 3 Feb 2024 | 3 Feb 2024 | Desk lamp | high | amount: 24.99; status: shipped | order_id=A-1001 |
| 2 | 14 Feb 2024 | 14 Feb 2024 | Office chair | high | amount: 189.00; status: shipped | order_id=A-1002 |
| 3 | 14 Feb 2024 | 14 Feb 2024 | ≈ Monitor arm | high | amount: 59.50; status: returned | order_id=A-1003 |
| 4 | 29 Feb 2024 | 29 Feb 2024 | Standing desk | high | amount: 420.00; status: shipped | order_id=A-1004 |
| 5 | 5 Mar 2024 | 5 Mar 2024 | Cable tray | high | amount: 15.00; status: shipped | order_id=A-1005 |
| 6 | 25 Mar 2024 | 25 Mar 2024 | Desk mat | high | amount: 19.99; status: cancelled | order_id=A-1006 |
| 7 | 2 Apr 2024 | 2 Apr 2024 | Webcam | high | amount: 79.00; status: shipped | order_id=A-1008 |

Undated / unresolved:
- Footrest

Consistency report:
- INFO [table] orders.csv: dates from column 'order_date'
- INFO [table] orders.csv: 1 row(s) have a value in 'order_date' that is not a readable date; they are listed as undated
- INFO [table] orders.csv: event titles from column 'item'
- INFO [order] 1 event(s) marked ≈ could have happened before the event listed just above them (their possible date ranges overlap).
