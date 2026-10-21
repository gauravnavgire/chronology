# CHRONOLOGY: the full guide

The README covers installation and the basics. This guide covers every
feature. Commands assume you are in the repository root.

## Why use this skill instead of just asking Claude?

For a short text with a few clear dates, asking Claude directly works just as
well. The skill is for the cases where a direct request tends to go wrong or
comes out differently each time.

## Features

### Checking the material

- **Consistency checks.** A report lists where the material contradicts
  itself, from most to least serious:
  - ranges that end before they start
  - "after X" statements that are certainly false
  - "3 days after X" statements that don't match the stated date
  - events involving someone before their birth or after their death
  - anachronisms (e.g. a tweet dated 1990), checked against limits recorded
    with their reason
  - schedule slips: planned vs. actual dates

  Contradictions are reported, never silently "fixed".
- **Merging several sources.** Witness statements, logs, emails and articles
  become one chronology. Events with the same `id` are merged, the number of
  corroborating sources is shown ("3 sources: p3 · witness.txt; row 41 ·
  police-log.csv; ..."), and sources that disagree are marked ⚠, with each
  source's date listed.
- **Date windows.** Every date is a window of possible instants, from earliest
  to latest ("late 1970s" → 1975–1979; "c. 753 BCE" → 754–752 BCE).
  Corroborating sources narrow the window. Events whose order the source
  doesn't actually establish are marked ≈ instead of being shown with false
  certainty. Relative dates ("a week after the meeting") are derived, or
  checked, by the script.
- **Self-check against the source.** Every event carries the source's exact
  words. `--verify letters.txt` re-reads the source and catches:
  - quotes that aren't there (misreadings or invented details)
  - misquotes ("pay rates" where the source says "piece-rates")
  - wrong page citations
  - dates contradicted by their own quote ("the quote mentions 1888 but the
    event is dated 1887")

  Problems lower the event's confidence, and the summary says how much was
  checked: "Verified 3 of 5 quotes word for word".
- **Confidence scores.** Every event is rated high, medium or low with
  reasons, e.g. "date precise to the day; backed by 2 sources" or
  "approximate (c.); the source hedges ('reportedly')". Weak events are
  marked, and `--min-confidence high` keeps only the solid ones.

### Calendars

Write dates the way the source does, and the script converts them exactly,
keeping the original wording:

| Calendar | Example | Shown as |
|---|---|---|
| Julian (Old Style) | `julian:1616-04-23` | 23 Apr 1616 (Julian) (= 3 May 1616) |
| Islamic (Hijri) | `hijri:1445-ramadan` | Ramadan 1445 AH (= 11 Mar 2024 – 9 Apr 2024) |
| Hebrew | `hebrew:5784-adar2-14` | 14 Adar II 5784 AM (= 24 Mar 2024) |
| Japanese eras | `japanese:Showa 20-08-15` | Shōwa 20-08-15 (= 15 Aug 1945) |
| Hindu panchang | `panchang:VS 2081 Chaitra shukla 9` | VS 2081 Chaitra Shukla 9 (Navami) (= 17 Apr 2024) |
| Regnal years | `regnal:Elizabeth II:3` | year 3 of Elizabeth II (= 6 Feb 1954 – 5 Feb 1955) |
| Fiscal years | `fy:2024-Q2` | FY2024 Q2 (= 1 Jan 2024 – 31 Mar 2024) |

- **Why it matters:** Shakespeare and Cervantes both "died on 23 April 1616",
  yet they died 11 days apart, because one date is Julian and the other
  Gregorian. Calendar-aware sorting gets this right.
- **Hindu panchang dates** are computed astronomically from the positions of
  the Sun and Moon. That covers the tithi at local sunrise, amanta or
  purnimanta months, adhika (leap) months, Vikram Samvat and Shaka years, and
  Gujarati Kartikadi years. The results match published timings to within
  minutes, and reproduce historical records:
  - Shivaji's coronation, Shaka 1596 Jyeshtha shukla 13 = 16 Jun 1674
    Gregorian, i.e. the conventional 6 June Old Style
  - Gandhi's birth, Bhadrapada vad 12, a tithi that began on 2 Oct 1869
- **Uncertainty is built in.** Moon-sighting for Hijri dates, days that begin
  at sunset, and ±1 day between almanacs are built into the date windows and
  noted in the report. Chinese lunisolar dates are flagged with the reason,
  never guessed.

### Seeing the shape of the timeline

- **Gaps and density.** A histogram of events per period, with runs of empty
  periods collapsed ("2973 empty days"). It lists the **largest certain gaps**
  ("25 years: after 'Smith born' → before 'Smith marries'") and the **busiest
  periods**.
- **Parallel tracks (lanes).** Swimlanes per person, theme, source or any
  field. In lanes by source, each column shows that source's own date, so
  disagreements line up side by side.
- **Story time vs. telling order.** For novels, memoirs, films and testimony:
  the `telling` layout labels `↩ flashback 24 years`, `↪ flash-forward`,
  `↩ flashback continues` and `→ resumes`, and reports linearity, e.g.
  "62% of steps move forward in story time".
- **Interactive HTML.** One self-contained page (no internet needed, light
  and dark themes, fits phone screens) with:
  - live zoom from millennium to minute
  - timeline, lanes and as-told views
  - search, filters and a confidence filter
  - a clickable density strip
  - expandable event cards with every source and the date it gives
  - a side panel where clicking an issue or a gap highlights the events
    involved

### Asking questions

- `--how-long A B`: "about 27 years (at least 25, at most 30)"
- `--as-of 1998-06-13`: what had certainly or possibly happened by then, and
  who was alive or active
- `--before X`, `--after X`, `--from`, `--to`
- `--entity`, `--tag`, `--source`, `--search`

### Working with data and other tools

- **Tables and databases.** CSV, TSV and SQLite go straight in. The date,
  title and id columns are detected. Day-first and month-first dates are told
  apart where the data allows, and flagged as ambiguous where it doesn't.
  Epoch seconds and milliseconds, Excel serials and time-zone offsets are
  handled. SQLite is opened read-only. `--collapse` turns 40 identical log
  lines into one "×40" event.
- **Exports.** `-l ics` writes an RFC 5545 calendar file for Google, Outlook or
  Apple Calendar. `-l gantt` writes a Mermaid Gantt chart. `-l timelinejs` and
  `-l vis` write JSON for those timeline libraries.
- **Presets.** `--preset incident | legal | biography | history | project |
  story` sets granularity, layout, lanes and gap analysis in one word. With
  `project`, planned dates are checked against actual ones.
- **Incremental re-runs.** `--state work/state.json` remembers the last run.
  The next run reports new events, moved dates, new corroboration, new or
  resolved issues, and extraction progress per source.

### Quality

- **Test suite.** `python -m unittest discover -s tests` (run from
  `chronology/`) runs 45 checks against known answers:
  - calendar math across BCE
  - Julian, Hebrew, Hijri, Japanese and panchang conversions, checked
    against published dates
  - the consistency checks, telling order, questions and presets
  - tables, including that SQLite stays read-only
  - export formats and the self-check
- **Skill evaluation kit.** `eval/` runs real Claude sessions on 14 realistic
  documents with answer keys, and scores triggering, step-following, recall,
  precision, date accuracy and self-check use. See `eval/README.md`.

## Further advantages over asking directly

1. **The same result every time.** Granularity names, layouts, date labels,
   uncertainty markers and the Undated and Notes sections are fixed.
2. **No invented precision.** A date known only as "July 1969" is never put
   on a specific day.
3. **Nothing silently dropped.** Undated items are listed; disagreeing
   sources are kept; any sampling is disclosed.
4. **Sorting done by code, not by the model:**
   - BCE dates and the absence of a year 0
   - strict century counting (the 19th century is 1801–1900)
   - ISO weeks
   - time zones
   - ties between events, least precise first
5. **Handles large inputs.** Long sources are processed in chunks, carrying
   the last known date across chunks.
6. **Extract once, view many ways.** Switching layout or granularity re-runs
   the script on the saved events, without re-reading the source.
7. **Sources stay checkable.** Every event carries a locator and a quote.
8. **Short prompts.** "Chronology of this PDF by century as a tree" is enough.

**Limits:** Claude still does the reading, so a date it misses or misreads is
still wrong. The self-check catches misquotes and invented events, not missed
ones. Without code execution, Claude applies the rules by hand and the
code-backed guarantees are lost.

## Example prompts

- "Create a chronology of this PDF at **year** granularity as a **tree**."
- "Chronological **table** of these incident logs, down to the **second**."
- "Here are a witness statement, the police log and two news articles. Build **one
  timeline** and tell me **where they disagree**."
- "Does the timeline in this manuscript **add up**? Just give me the **contradictions**."
- "These letters use **Old Style** dates and the diary uses **Hijri** dates. Put everything on one timeline."
- "Convert the **Samvat** dates in our family record and put the events in order."
- "Map the **flashbacks** in this novel: what order is the story **told** in versus what **happened**?"
- "I've added chapters 8–12 to my notes. **Update** the chronology and tell me **what changed**."
- "Which milestones in these status reports **slipped**, and by how much?"
- "**How long** was it between the first symptoms and the diagnosis?"
- "Here's our **orders.csv**: give me a monthly timeline of returns and cancellations."
- "Export the project milestones as a **calendar file** and a **Gantt chart**."
- "Make me an **interactive** timeline of this book that I can **zoom** and **search**."
- "Build the timeline from this report and **double-check every date against the text**."

## Command-line tour

```bash
cd chronology
python scripts/chronology.py examples/apollo11-events.json -g day -l tree

# merge three sources and show the consistency report
cd examples/multi-source
python ../../scripts/chronology.py witness.json police-log.json newspaper.json -g day -l table
python ../../scripts/chronology.py witness.json police-log.json newspaper.json -l lanes --tracks source
python ../../scripts/chronology.py witness.json police-log.json newspaper.json -g year -l density
python ../../scripts/chronology.py witness.json police-log.json newspaper.json -l html -o chronology.html
cd ../..

# tables, exports, questions, tests
python scripts/chronology.py examples/tables/orders.csv -g month -l table
python scripts/chronology.py examples/apollo11-events.json -l ics -o apollo11.ics
python scripts/chronology.py examples/multi-source/*.json --how-long born died --answer-only
python -m unittest discover -s tests
```

## Repository layout

```
chronology/            the skill (this folder is what gets installed / zipped)
├── SKILL.md           entry point: rules, 6-step workflow, reference map
├── references/        loaded only when needed (options, extraction, schema, checks, …)
├── scripts/           chronology.py: deterministic engine, standard library only
├── tests/             45 unit tests
└── examples/          worked inputs and outputs for every feature
eval/                  evaluation kit: real Claude sessions scored against answer keys
docs/                  this guide, the project site, screenshots
```
