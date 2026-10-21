# Changelog

## v1.0.1: triggers more reliably

- **Skill description** now also names when to use the skill: checking whether
  dates add up, finding the time between events, and Old Style or Samvat
  dates. In testing with headless Claude Code, the skill was used for 4 of 6
  prompts that should trigger it (previously 2 of 6), and for none of 6
  unrelated prompts. Each prompt ran once, so treat these as indicative.
- **Evaluation kit** fixes from the first full run:
  - support for PowerShell
  - follows script paths stored in variables
  - counts refused commands separately
  - stops a batch when the usage limit is hit
  - two answer-key keywords corrected

## v1.0.0: first public release

- **Skill:** a six-step workflow (read the request, ingest, extract, run the
  script, self-check, present), with eight reference files loaded on demand.
- **Engine:** granularities from millennium to second; date windows with ≈
  order certainty; merging several sources with ⚠ conflicts; consistency
  checks (ranges, order, offsets, lifespans, anachronisms, schedule slips);
  confidence scores.
- **Calendars:** Julian, Hijri, Hebrew, Japanese eras, regnal and fiscal
  years, and the Hindu panchang (drik method; amanta and purnimanta, adhika
  months, VS and Shaka, Kartikadi years).
- **Layouts:** tree, timeline, table, bullets, Mermaid, CSV, JSON, density,
  lanes, telling order, and interactive HTML. Exports: iCalendar, Mermaid
  Gantt, TimelineJS, vis-timeline.
- **Inputs:** event JSON, plus CSV, TSV and SQLite read directly.
- **Questions:** `--how-long`, `--as-of`, `--before`/`--after`, ranges,
  filters. Presets for incident, legal, biography, history, project and
  story work.
- **Self-check:** `--verify` looks up every event's quote in the source.
- **Quality:** 45 unit tests, and an evaluation kit that runs real Claude
  sessions on 14 test documents.
