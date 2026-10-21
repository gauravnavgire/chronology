# Consistency report and self-check

Read this before presenting a chronology: what each issue means, how to
self-check quotes against the source, and what to do about each finding.

## The consistency report

It lists issues most serious first.

| Severity | Kind | Meaning |
|---|---|---|
| ERROR | range | An event ends before it starts |
| ERROR | order | An event stated to be after (or before) another is certainly not |
| ERROR | offset | "N units after X" doesn't match the stated date (units under a day allow one unit of slack) |
| ERROR | lifespan | An event involves an entity before it began |
| ERROR | anachronism | An event is earlier than `not_before` (or later than `not_after`) |
| ERROR | verify | A quote is not in the source text |
| WARNING | conflict | Sources give dates that can't both be true (⚠) |
| WARNING | lifespan | An event involves an entity after it ended (posthumous?) |
| WARNING | schedule | Happened after its `planned` / `due` date |
| WARNING | verify | Misquote, wrong page, or a quote that contradicts the event's date |
| WARNING | reference / offset | Unknown id, or an offset that can't be parsed |
| INFO | order | How many events are ≈ (order not established) |
| INFO | schedule | Happened before its planned date |
| INFO | calendar / table / verify | Conversion caveats, how a table was read, the verification summary |

**Before reporting an ERROR,** re-read the cited passage to confirm the
problem is in the source and not in your extraction. Fix extraction mistakes
and re-run. Explain each remaining issue in one plain sentence. Never "fix" a
real contradiction in the source by changing a date: report it.

## Self-check (required before presenting)

Each event's `quote` holds the source's exact words. Check them against the
source text:

```bash
python scripts/chronology.py events.json --verify source.txt --report-only
# several sources: --verify a.txt --verify b.txt  (matched to source_document)
# very large sources: --verify-sample 50  (a fixed, repeatable sample)
```

For PDFs, verify against the extracted `.txt` that has form feeds between
pages, so page citations are checked too.

| Result | What to do |
|---|---|
| `ERROR [verify] … quote not found` | Re-read the cited passage. Fix the event, or remove it if the source doesn't support it. Never present it as it is |
| `WARNING … only approximately (NN%)` | Copy the source's real wording (shown in the message) into `quote`, and check the event still holds |
| `WARNING … quote is on page X, but cited as p. N` | Correct `source` |
| `WARNING … the quote mentions 1888 but the event is dated 1887` | Re-read: the date or the quote is wrong. If the source really is inconsistent, keep it and say so |
| `INFO … N event source(s) have no quote` | Add quotes where you can; these events are unchecked |

Re-run until only real source problems remain. Then report the summary line,
e.g. "Verified 41 of 42 quotes word for word". The matching rules and the
effect on confidence are in `event-schema.md`.

**Without code execution:** re-open at least 5–10 cited passages by hand,
including every event you are less sure of, and say how many you checked.
