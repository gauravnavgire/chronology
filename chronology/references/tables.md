# Tables: CSV, TSV and SQLite

Structured data doesn't need extraction by hand. Pass the file straight to the
script, and each row becomes an event:

```bash
python scripts/chronology.py orders.csv -g month -l table
python scripts/chronology.py app-log.csv -g minute -l table --collapse --tag-col service
python scripts/chronology.py support.db --table tickets --end-col closed_at --entity-col agent
python scripts/chronology.py support.db --sql "SELECT * FROM tickets WHERE priority = 'high'"
```

Table files can be mixed with JSON event files in one run, e.g. a support
database plus events extracted from emails. Merging by `id` still applies.

## What the script detects

| Column role | How it is chosen | Override |
|---|---|---|
| **Date** | Name hints (`date`, `time`, `*_at`, `created`, `ts`, …) plus at least 80% of values readable as dates | `--date-col` |
| End | Only when asked | `--end-col` |
| **Title** | A column named `title`/`name`/`subject`/`message`/`description`/…, else the most varied text column. `status`/`type`-like columns are a last resort | `--title-col` |
| Source locator | An id column (`id`, `*_id`, `uuid`, …) → `order_id=A-1001`, else `row N` | — |
| Entities / tags | Only when asked; values may be separated by `;` `,` or `\|` | `--entity-col`, `--tag-col` |
| Details | Every other non-empty column, as `name: value` | — |

Every choice is reported as `INFO [table]` in the consistency report, so you
can say which column was used and offer the alternatives.

## Date formats in cells

- ISO and anything the event schema accepts (`2024-03-10 01:30:05+01:00`, `1969`, `C19` …).
- `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY/MM/DD`, with `.` or `-` separators and optional `HH:MM[:SS] [am/pm]`.
- Month names: `20 Jul 1969`, `July 20, 1969`, `Jul 1969`.
- Numbers, **only in columns whose name looks like a date**: epoch seconds,
  epoch milliseconds, Excel serial days (with a time fraction), and plain years.

**Day-first vs. month-first:** the script looks for values that settle it
(25/03 can only be day-first). If none do, it reads day-first and reports the
ambiguity. Ask the user, or follow the data's locale, then pass `--dayfirst`
or `--monthfirst`. A requested order that the data contradicts is ignored,
and that is reported too.

Two-digit years are read as 1950–2049, and this is reported. Unreadable cells
make the row undated, and the count is reported.

## Big tables

- `--collapse` folds repeats (same title, tags and entities in the same period
  at the granularity) into one event: `upstream timeout calling payments (×40)`,
  with the count and the first and last time.
- `-l density` gives counts per period plus the largest gaps and the busiest periods.
- Filters (`--from`, `--to`, `--tag`, `--search`, `--entity`) and `--sql`
  narrow the rows before you lay them out.
- Above 2,000 events the script suggests these on stderr.

## Safety

SQLite files are opened **read-only**. A `--sql` statement that tries to
write is refused with an error, and one that returns no rows is rejected.
Excel workbooks aren't read directly: save the sheet as CSV first.
