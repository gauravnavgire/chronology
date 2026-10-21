Smith case
├── 1950
│   └── Smith born (2 Mar 1950) [2 sources: p1 · witness.txt; row 1 · police-log.csv]
├── Smith marries [low confidence] (1970s, between 1975 and 1979) [p7 · witness.txt]
├── 1990
│   └── Smith tweets [low confidence] [p6 · witness.txt]
├── 1998
│   ├── Report filed (11 Jun 1998) [row 42 · police-log.csv]
│   ├── ⚠ Smith meets Jones (12 Jun 1998 14:02) [3 sources: p3 · witness.txt; row 41 · police-log.csv; §2 · newspaper.html]
│   ├── Phone call (15 Jun 1998) [p4 · witness.txt]
│   └── Follow-up visit [derived date] (19 Jun 1998) — date derived: +7 days from 'Smith meets Jones' [row 43 · police-log.csv]
├── 2001
│   └── Smith dies (10 May 2001) [p2 · witness.txt]
└── 2003
    └── Letter signed by Smith [p5 · witness.txt]

Consistency report:
- ERROR [anachronism] 'Smith tweets' (1990) is before Mar 2006, the earliest it could be: Twitter launched March 2006
- ERROR [order] 'Report filed' (11 Jun 1998) should be after 'Smith meets Jones' (12 Jun 1998 14:02) but is entirely before it
- ERROR [offset] 'Phone call' (15 Jun 1998) is stated, but +2 days from 'Smith meets Jones' (12 Jun 1998 14:02) gives 14 Jun 1998
- WARNING [conflict] 'Smith meets Jones' - sources disagree: p3 · witness.txt: 12 Jun 1998 14:02; row 41 · police-log.csv: 12 Jun 1998 14:10; §2 · newspaper.html: 13 Jun 1998
- WARNING [lifespan] 'Letter signed by Smith' (2003) involves Smith after 'Smith dies' (10 May 2001) (posthumous or legacy?)
- INFO [legend] ⚠ marks events whose sources disagree on the date.
