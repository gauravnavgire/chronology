## Smith case — by source

| When | witness.txt | police-log.csv | newspaper.html |
|---|---|---|---|
| 2 Mar 1950 | Smith born | Smith born (1950) |  |
| 1970s | Smith marries [low confidence] |  |  |
| 1990 | Smith tweets [low confidence] |  |  |
| 11 Jun 1998 |  | Report filed |  |
| 12 Jun 1998 | ⚠ Smith meets Jones (12 Jun 1998 14:02) | ⚠ Smith meets Jones (12 Jun 1998 14:10) | ⚠ Smith meets Jones (13 Jun 1998) |
| 15 Jun 1998 | Phone call |  |  |
| 19 Jun 1998 |  | Follow-up visit [derived date] |  |
| 10 May 2001 | Smith dies |  |  |
| 2003 | Letter signed by Smith |  |  |

Consistency report:
- ERROR [anachronism] 'Smith tweets' (1990) is before Mar 2006, the earliest it could be: Twitter launched March 2006
- ERROR [order] 'Report filed' (11 Jun 1998) should be after 'Smith meets Jones' (12 Jun 1998 14:02) but is entirely before it
- ERROR [offset] 'Phone call' (15 Jun 1998) is stated, but +2 days from 'Smith meets Jones' (12 Jun 1998 14:02) gives 14 Jun 1998
- WARNING [conflict] 'Smith meets Jones' - sources disagree: p3 · witness.txt: 12 Jun 1998 14:02; row 41 · police-log.csv: 12 Jun 1998 14:10; §2 · newspaper.html: 13 Jun 1998
- WARNING [lifespan] 'Letter signed by Smith' (2003) involves Smith after 'Smith dies' (10 May 2001) (posthumous or legacy?)
- INFO [legend] ⚠ marks events whose sources disagree on the date.
