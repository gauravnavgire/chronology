# Options: request parameters, presets and command line

Read this when the request goes beyond "granularity + layout": presets,
filters, questions, confidence, lanes, state files, exports or tables.

## Request parameters

Parse these from the prompt. Use the default when the user doesn't say.

| Parameter | Accepted values (synonyms are fine) | Default |
|---|---|---|
| **granularity** | millennium, century, decade, year, quarter, month, week, day, hour, minute, second | Finest level that most events share (often `day` or `year`) |
| **layout** | `tree`, `timeline`, `table`, `bullets`, `mermaid`, `csv`, `json`, `density`, `lanes`, `html`, `telling`; exports `ics`, `gantt`, `timelinejs`, `vis` (see `layouts.md`) | `timeline` |
| order | oldest-first / newest-first | oldest-first |
| scope / filter | date range, people, topics, tags, sources, text | everything |
| detail | `brief` (title only), `standard` (title + one line), `full` (title + all context) | `standard` |
| grouping top | coarsest grouping level for tree/bullets ("by century, then year") | auto |
| citations | source locators (page, section, row id) | on |
| sources | one document, or several to merge | as given |
| checks | consistency report and ≈ / ⚠ marks; "checks only" prints just the report | on |
| tracks | lanes for `lanes` / `html`: `entities` (who), `tags` (themes), `source`, or any field | auto |
| gaps | largest gaps and busiest periods added to any layout | off (always in `density`, `html`) |
| preset | a kind of job (table below) | none |
| confidence | all, medium+ or high only | all; low-confidence events marked |
| question | how long between X and Y; as of a date; before/after an event; a date range | none |
| updates | "what changed since last time" → state file | off; on when continuing earlier work |
| verify | self-check quotes against the source text | always, before presenting (`checks.md`) |

If the granularity or layout is ambiguous *and* the choice changes the result
a lot, ask once. Otherwise use the default and say which one you used.

## Presets

Use one when the user describes the job rather than the settings.
Explicit settings always override a preset.

| Preset (aliases) | Granularity | Layout | Also |
|---|---|---|---|
| `incident` (outage, postmortem, logs) | second | table | lanes by tags (service), gaps on |
| `legal` (case, litigation, investigation) | day | table | lanes by source |
| `biography` (life, memoir) | year | tree, grouped by decade | lanes by entities |
| `history` | year | tree, grouped by century | gaps on |
| `project` (schedule, plan) | week | lanes by tags (workstream) | gaps on; planned vs. actual dates |
| `story` (novel, narrative, fiction) | year | telling | lanes by entities |

## Command line

```bash
python scripts/chronology.py INPUT [INPUT ...] [options]
```

INPUT is an events JSON file, or a table (`.csv`, `.tsv`, `.db`/`.sqlite`; see
`tables.md`). Several inputs are merged into one chronology.

| Group | Options |
|---|---|
| Shape | `-g/--granularity G` · `-l/--layout L` · `-t/--title T` · `--top LEVEL` · `--levels a,b,c` · `--reverse` · `--no-exact` · `-o FILE` |
| Presets | `--preset NAME` |
| Merging & checks | `--auto-merge` · `--report-only` · `--no-checks` · `--collapse` |
| Lanes & gaps | `--tracks FIELD` · `--lanes A,B` · `--gaps` |
| Confidence | `--min-confidence low\|medium\|high` |
| Questions | `--how-long A B` · `--as-of D` · `--before EVENT` · `--after EVENT` · `--from D` · `--to D` · `--answer-only` |
| Filters | `--entity X` · `--tag X` · `--source DOC` · `--search TEXT` (each repeatable) |
| Re-runs | `--state FILE` · `--since FILE` · `--save-state FILE` |
| Self-check | `--verify SOURCE.txt` (repeatable) · `--verify-sample N` |
| Tables | `--date-col` · `--end-col` · `--title-col` · `--entity-col` · `--tag-col` · `--dayfirst` / `--monthfirst` · `--sql "SELECT …"` · `--table T` |

### Notes on behaviour

- **Questions:** EVENT is an id, or a title fragment that matches exactly one
  event. If it's ambiguous, the script lists the candidates. DATE accepts
  calendar prefixes (`julian:1616-04-23`). The answer appears at the top of
  the output, and the chronology is narrowed to the matching events. Events
  that only *possibly* match are marked, e.g. `[may not have happened yet]`.
  Checks always run on the full data. `--answer-only` prints just the answer.
- **Confidence:** a column in `table`/`csv`, a field in `json`, a badge and
  filter in `html`. Other layouts mark only `[low confidence]`. The scoring is
  in `event-schema.md`.
- **Re-runs:** `--state FILE` compares with the run saved in FILE (if there is
  one) and then saves this run there. `--since` and `--save-state` do only one
  of the two. Changed events are marked `[new]` / `[date was …]`.
- **HTML:** always write it to a file (`-o chronology.html`). Tell the user the
  path, and that it opens in any browser with no internet needed.
- **Exports:** `ics` imports into Google Calendar, Outlook or Apple Calendar.
  Day-or-coarser dates become all-day events spanning their period, and times
  are UTC. `gantt` is Mermaid, with milestones and bars, one section per lane.
  `timelinejs` and `vis` are JSON for those libraries. `ics`, `gantt` and
  `vis` need years 1–9999 (BCE events are left out and counted on stderr);
  TimelineJS keeps BCE.
- **Machine formats** (`csv`, `json`, `html`, `ics`, `timelinejs`, `vis`) carry
  no report text. The report, changes and answers go to stderr, or into the
  JSON / HTML.
- **Big inputs:** above 2,000 events the script suggests `--collapse`,
  `-l density` or filters.

## Verify the script itself

In a new environment, or if results look surprising, run this from the skill
folder:

```bash
python -m unittest discover -s tests
```

All tests should pass. They check calendar math, conversions, checks,
questions, tables, exports and the self-check against known answers.
