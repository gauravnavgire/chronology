# Extracting temporal data and context

## Temporal expressions to look for

| Kind | Examples | Encode as |
|---|---|---|
| Full timestamp | `2024-03-10 01:30:05 -05:00`, `10/03/2024 1:30pm` | ISO with offset if known |
| Date | `20 July 1969`, `July 20th, 1969`, `20/07/69` | `1969-07-20` (check the locale for dd/mm vs mm/dd) |
| Month / year | `July 1969`, `in 1969` | `1969-07`, `1969` |
| Fiscal / regnal | `FY2023 Q2`, `in the third year of Elizabeth II` | `fy:2023-Q2`, `regnal:Elizabeth II:3` (+ `fiscal_year` / `reigns` metadata) |
| Other calendars | `23 April 1616 O.S.`, `1 Ramadan 1445`, `15 Nisan 5784`, `昭和20年8月15日`, `Samvat 1925 Bhadrapada vad 12` | `julian:1616-04-23`, `hijri:1445-09-01`, `hebrew:5784-nisan-15`, `japanese:Showa 20-08-15`, `panchang:VS 1925 Bhadrapada krishna 12` (add `kartikadi` for Gujarati years, `purnimanta` for North Indian month naming, if the source uses them). Keep the source's own date and let the script convert it. Watch for Old Style/New Style dual dates (`11/22 Feb 1732`): use the side the source asserts, or both as `earliest`/`latest` |
| Era / BCE | `44 BC`, `753 BCE`, `AD 79` | `-44`, `-753`, `79` |
| Decade / century | `the sixties`, `late 1800s`, `the 5th century` | `1960s`, `1880s` + approximate, `C5` |
| Time of day | `that evening`, `at dawn`, `around 3 pm` | Hour precision + approximate |
| Relative | `two days later`, `the next morning`, `a decade after the war` | Resolve against the anchor; `derived: true` |
| Named period | `the Renaissance`, `WWII`, `the Great Depression` | Standard range + approximate |
| Durations | `for three weeks`, `between 1939 and 1945` | `date` + `end` |
| Data fields | `created_at`, `ts`, `1689849460` (epoch), `25404` (Excel serial) | ISO |
| Ordinal sequence only | `first`, `then`, `finally` (no dates) | Keep source order with `date: null`, or a synthetic relative order (see below) |

## Anchors for relative expressions

Keep a stack of anchors while reading:

1. The most recent explicit date in the same paragraph or section.
2. Otherwise the section, chapter, or document date (from the byline, the
   publication date, the log header, or the email "Sent:" line).
3. Otherwise no anchor. Record the event as undated and quote the relative
   phrase in `details`.

Always write how a derived date was computed, e.g. *"'three days later' after
16 Jul 1969 launch"*.

## Material with sequence but no dates

Recipes, procedures, and story plots often have order but no dates. Say this
to the user, and offer either:
- a **sequence-only chronology** (step 1, 2, 3...), or
- relative times when durations are given (T+0, T+15 min, ...). Encode these
  as times on an arbitrary reference day and label the output "relative time".

## Associating context

For each event, capture:

- **title**: about 4-12 words, factual, past tense: who did what.
- **details**: the surrounding sentence(s) that explain it (actors, place,
  cause, effect, figures, quotes). Use the detail level the user asked for.
- **source**: the most specific locator available (page, chapter §, para,
  timestamp in a transcript, table + primary key).
- **tags** (optional): people, places, themes. They help with filtering.

When one sentence has several dated facts, split it into several events.
When several sentences describe one moment, merge them into one event.

## Source-specific tips

- **PDF**: keep a page → text map. Watch headers and footers for dates
  (e.g. a report date) and do not treat them as events.
- **Books**: chapter titles often carry the period ("Chapter 3: 1914-1918").
  Use them as anchors.
- **Articles and blogs**: the publish date is the anchor for words like
  "yesterday" and "last week".
- **Logs**: each line is usually an event. If the log is a CSV, pass it to the
  script with `--collapse`. Otherwise fold repeated identical lines into one
  event with a count, e.g. "×37".
- **Database data / CSV**: pass the file to the script (see `tables.md`).
  Decide which timestamp column the user means (created, updated, event
  time). If it's unclear, ask, then set `--date-col`. For large tables use
  `--collapse` or `-l density` rather than listing every row, unless the user
  asks for every row.

## Fields the checks and features need

Record these as you extract. Field formats are in `event-schema.md`.

| Situation in the source | Record |
|---|---|
| Any event | `quote`: its exact words, up to about 25 words, copied, not paraphrased (checked by `--verify`) |
| Vague date ("late 1970s") | `earliest` / `latest` (1975 / 1979) rather than a single point |
| "after the meeting", "three days later" | An `id` on the referenced event, plus `after` / `before` / `offset`. With `"date": null` plus `offset`, the script derives the date. With both, it checks them |
| People or organisations involved | `entities` (these also drive lanes and the html "Who" filter) |
| Births, deaths, foundings, closures | `lifespan`: `{"entity": …, "boundary": "start" \| "end"}` |
| Something with a well-known first date (a technology, an institution, a law) | `not_before` + `reason`. This is the only place outside knowledge enters, and it is always shown with its reason |
| "reportedly", "probably", "I think", "allegedly" | `"hedged": true` |
| Weak source (hearsay, a later rumour, an unreliable witness) | `"certainty": "low"` or `"medium"`, with the reason in `details` |
| Planned, scheduled or due dates | `"planned": "<date>"` (or `"due"`) on the actual event |
| Dates in another calendar | The source's own date with a prefix: `julian:`, `hijri:`, `hebrew:`, `japanese:`, `panchang:`, `regnal:`, `fy:`. Regnal and fiscal dates need `reigns` / `fiscal_year` metadata. Convert Chinese lunisolar dates by hand and keep the original in `details` |

## Several sources

Write **one events file per document**, with `source_document` set. Give the
**same `id`** to events in different files that describe the same happening.
The script merges them, counts the corroborating sources, and marks ⚠ (with
each source's date) when they disagree. Deciding that two descriptions match
is a judgement call, so be conservative. Never merge two events just because
their dates match. `--auto-merge` also merges identical titles without ids.

## Reading order

Write events in the order the source tells them, or set `told` (a number).
This drives the `telling` layout (flashbacks, flash-forwards), so keep it
accurate for narratives: novels, memoirs, films and interviews.

## Continuing earlier work

Keep the events files and a state file in a working folder (for example
`chronology-work/`). Record `extracted_through` (e.g. `"p. 120"`) in each
file's metadata. When the user adds material or returns to a long source,
extract only the new part, append it to that source's file (or add a file),
and run with `--state chronology-work/state.json`. The output then says what
changed.

## Integrity

- Do not invent dates. Partial is better than precise and wrong.
- Use outside knowledge only to map well-known named periods (marked
  approximate) and for `not_before` / `not_after` limits (with a `reason`).
- When sources disagree, give the events the same `id` and keep each
  source's own date. Never pick one silently.
