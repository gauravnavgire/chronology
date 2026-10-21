## Smith case

| # | When | Exact date | Event | Confidence | Details | Source |
|---|---|---|---|---|---|---|
| 1 | 2 Mar 1950 | 2 Mar 1950 | Smith born | high |  | 2 sources: p1 · witness.txt; row 1 · police-log.csv |
| 2 | 1970s | 1970s, between 1975 and 1979 | Smith marries [low confidence] | low |  | p7 · witness.txt |
| 3 | 1990 | 1990 | Smith tweets [low confidence] | low |  | p6 · witness.txt |
| 4 | 11 Jun 1998 | 11 Jun 1998 | Report filed | medium |  | row 42 · police-log.csv |
| 5 | 12 Jun 1998 | 12 Jun 1998 14:02 | ⚠ Smith meets Jones | medium |  | 3 sources: p3 · witness.txt; row 41 · police-log.csv; §2 · newspaper.html |
| 6 | 15 Jun 1998 | 15 Jun 1998 | Phone call | medium |  | p4 · witness.txt |
| 7 | 19 Jun 1998 | 19 Jun 1998 | Follow-up visit [derived date] | high | date derived: +7 days from 'Smith meets Jones' | row 43 · police-log.csv |
| 8 | 10 May 2001 | 10 May 2001 | Smith dies | high |  | p2 · witness.txt |
| 9 | 2003 | 2003 | Letter signed by Smith | medium |  | p5 · witness.txt |

Consistency report:
- ERROR [anachronism] 'Smith tweets' (1990) is before Mar 2006, the earliest it could be: Twitter launched March 2006
- ERROR [order] 'Report filed' (11 Jun 1998) should be after 'Smith meets Jones' (12 Jun 1998 14:02) but is entirely before it
- ERROR [offset] 'Phone call' (15 Jun 1998) is stated, but +2 days from 'Smith meets Jones' (12 Jun 1998 14:02) gives 14 Jun 1998
- WARNING [conflict] 'Smith meets Jones' - sources disagree: p3 · witness.txt: 12 Jun 1998 14:02; row 41 · police-log.csv: 12 Jun 1998 14:10; §2 · newspaper.html: 13 Jun 1998
- WARNING [lifespan] 'Letter signed by Smith' (2003) involves Smith after 'Smith dies' (10 May 2001) (posthumous or legacy?)
- INFO [legend] ⚠ marks events whose sources disagree on the date.
