---
name: chronology
description: Builds a chronology from any text (notes, PDFs, books, articles, DB data) at a chosen granularity and layout; merges sources, flags conflicts and timeline contradictions.
dependencies: python>=3.9 (standard library only; optional)
license: MIT
---

# CHRONOLOGY

Turn unstructured or semi-structured material into an ordered chronology.
Find every time reference, resolve it to the **finest granularity the source
supports**, attach the content that belongs to that moment, then order and
group the events at the **granularity the user asked for** and render them in
the **layout the user asked for**. A bundled script does the sorting, the
date maths, the checks and the rendering deterministically.

## Rules that always apply

- **Never fake precision.** A date known only to the month stays a month.
  Vague dates are windows, not points.
- **Never drop anything silently.** Undated items are listed, and sampled or
  skipped parts are disclosed.
- **Never invent.** Every event rests on the source's own words (`quote`),
  and those words are checked against the source before presenting.
- **Report contradictions; don't fix them.** Changing a date to make the
  story consistent is never acceptable.
- **Merge conservatively.** Only merge events that clearly describe the same
  happening, never just because their dates match.

## When to use

The user supplies (or points to) material and wants it "in order", "as a
timeline", "chronologically", "what happened when", or names a granularity or
layout. Inputs range from a paragraph to a whole book: notes, PDFs, e-books,
articles, blogs, transcripts, logs, chat exports, CSV/TSV, SQLite and query
results. Also use it to reconcile **several sources**, to check whether a
timeline **adds up**, for **flashbacks** in a narrative, for **schedules
that slipped**, and for questions like "how long between X and Y?".

## Workflow

### 1. Read the request

Get the **granularity** (millennium … second; default: the finest level most
events share) and the **layout** (default `timeline`). If the user describes
the job rather than settings ("incident timeline", "project schedule", "the
plot of this novel"), use a **preset**. For anything else (filters,
questions, confidence, lanes, state, exports), see
[references/options.md](references/options.md). If a choice is ambiguous and
matters a lot, ask once. Otherwise pick the default and say so.

### 2. Ingest the source

- **Text / Markdown:** use it as is.
- **PDF:** extract it page by page, and save the text as `.txt` with a form
  feed (`\f`) between pages (`pdftotext` does this). The self-check uses it.
- **E-books / DOCX / HTML:** convert to text, keeping chapter and heading
  names as locators.
- **CSV / TSV / SQLite:** don't extract by hand. Pass the file to the script
  ([references/tables.md](references/tables.md)) and confirm the `INFO [table]`
  lines (date column, day/month order, unreadable rows). Save Excel sheets
  as CSV first, and convert JSON records to CSV or to the events schema.
- **Large inputs:** work in chunks (chapters, or about 20–40 pages). Carry the
  running anchor date across chunks, and add every chunk's events to one file.

### 3. Extract events at the finest grain

Create one event per temporal expression, written in reading order. See
[references/extraction.md](references/extraction.md) for patterns, the fields
the checks need, several sources, and continuing earlier work. The
essentials:

1. **Absolute** `1969-07-20T20:17:40Z`. **Partial:** keep only what is known
   (`1969-07`, `1960s`, `C19`, `-44-03-15` for 44 BCE).
2. **Relative** ("two days later"): resolve against the nearest anchor, and
   set `"derived": true` with the reasoning, or record an `offset`.
3. **Approximate** ("circa", "late 1800s"): `"approximate": true`, or an
   `earliest` / `latest` window.
4. **Other calendars:** keep the source's date with a prefix (`julian:`,
   `hijri:`, `hebrew:`, `japanese:`, `panchang:`, `regnal:`, `fy:`). The
   script converts it. For Hindu tithi dates, see the panchang notes in
   `event-schema.md` (amanta/purnimanta, Kartikadi years, festivals).
5. **No usable date:** keep the item with `"date": null`.
6. **Quote every event:** the source's exact words for it, in `quote`
   (up to about 25 words, copied, not paraphrased).
7. **Several sources:** one events file per document. The same happening
   gets the same `id` in each.

The `title` is a short factual statement, `details` gives the context in the
source's own wording, and `source` is the most specific locator. Write the
events as JSON following [references/event-schema.md](references/event-schema.md).

### 4. Run the script

```bash
python scripts/chronology.py events.json [more.json …] -g <granularity> -l <layout> [-o out]
```

Common additions: `--preset NAME`, `--tracks entities`, `--gaps`,
`--how-long A B`, `--as-of DATE`, `--min-confidence high`, `--collapse`,
`--state chronology-work/state.json`. The full list is in
[references/options.md](references/options.md). Layouts and exports are in
[references/layouts.md](references/layouts.md). Bucketing rules are in
[references/granularity.md](references/granularity.md).

Without code execution, follow [references/manual-mode.md](references/manual-mode.md).
In a new environment, `python -m unittest discover -s tests` confirms the
script works.

### 5. Self-check before presenting (required)

```bash
python scripts/chronology.py events.json --verify source.txt --report-only
```

Fix every `ERROR [verify]` (a quote not in the source) and every misquote,
wrong page or date contradiction that comes from your extraction, then re-run.
Re-read the cited passage before reporting any ERROR as a problem in the
source. What each finding means and what to do is in
[references/checks.md](references/checks.md).

### 6. Present

1. **Header:** source, event count, the granularity and layout (and preset),
   and the date span. If the user asked a question, answer it first, keeping
   the script's bounds and uncertainty.
2. **The chronology** in the requested layout. Put `tree` and `timeline` in a
   code block. For `html` and the exports, give the file path.
3. **Undated / unresolved** items, with the reason.
4. **Consistency report**, most serious first, one plain sentence per issue
   (meanings in `checks.md`), and the verification summary ("Verified 41 of
   42 quotes word for word").
5. **Changes since last run**, when a state file was used.
6. **Notes:** derived or approximate dates, assumptions (time zone,
   calendar), and sampled or skipped parts.

For many events at a coarse granularity, summarise each period in 1–3
sentences if the user wants a summary. Mention a notable gap or burst in the
header when it bears on the question. Close with one line of follow-ups: a
different granularity or layout, lanes by person or source, the interactive
HTML page, a calendar file, or filters.

## Reference map

| Open | When |
|---|---|
| [references/options.md](references/options.md) | Presets, filters, questions, confidence, lanes, state files, exports, the full command line |
| [references/extraction.md](references/extraction.md) | Extracting: date patterns, anchors, fields the checks need, several sources, reading order, continuing work |
| [references/event-schema.md](references/event-schema.md) | Writing the events JSON: fields, date and calendar formats, windows, confidence scoring, self-check rules |
| [references/checks.md](references/checks.md) | Before presenting: issue meanings, the self-check procedure |
| [references/layouts.md](references/layouts.md) | Choosing or describing a layout or export |
| [references/granularity.md](references/granularity.md) | How events are bucketed, grouped and labelled; ≈ order certainty |
| [references/tables.md](references/tables.md) | CSV / TSV / SQLite inputs |
| [references/manual-mode.md](references/manual-mode.md) | No code execution available |
| [examples/README.md](examples/README.md) | Worked inputs and outputs for every feature |

## Example

**Prompt:** "Make a chronology of these Apollo notes, granularity day, as a tree."

```
Apollo 11 Mission
├── 1961
│   └── May
│       └── 25 May
│           └── Kennedy commits to a Moon landing — Address to Congress [para 1]
└── 1969
    └── Jul
        ├── Worldwide TV audience of ~600 million (c. Jul 1969) [para 8]
        ├── 16 Jul
        │   └── Saturn V launches from LC-39A (16 Jul 1969 13:32) [para 2]
        └── 20 Jul
            └── Eagle lands in the Sea of Tranquility (20 Jul 1969 20:17:40) [para 4]
```

With several sources, the same run also reports where the sources disagree,
for example:

```
- WARNING [conflict] 'Smith meets Jones' - sources disagree: p3 · witness.txt: 12 Jun 1998 14:02; row 41 · police-log.csv: 12 Jun 1998 14:10; §2 · newspaper.html: 13 Jun 1998
```
