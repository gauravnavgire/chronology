# Evaluation results

These results come from real, headless Claude Code sessions (`claude -p`,
model `claude-opus-5-5`), run with [`run_eval.py`](run_eval.py) and scored
automatically by [`score.py`](score.py) against hand-made answer keys. The
cases are described in [README.md](README.md).

## Extraction quality (batch `full-2`, 14 cases, October 2026)

Measured on the 11 cases where the skill was used and the answer key has
dated events:

| Metric | Result |
|---|---|
| Gold events found (recall) | **98 of 99** (99.0%). The one miss is an optional event |
| Must-have events found | **100%** in every case |
| Extracted events that match a gold event (precision) | **98 of 106** (92.5%) |
| Matched events with the exact date | **97 of 98** (99.0%) |
| Vague dates given false precision | **0** |
| Events carrying a source quote | **100%** |

About the rough edges:

- **The 8 "unmatched" events are mostly real events that the answer keys
  don't list**, such as the dates of the status reports themselves (case 07)
  and a reply email (case 02). The score treats them as wrong, so precision
  is if anything understated.
- **The one inexact date is arguably right.** In the diary, "Around
  Christmas we became engaged. The following winter… we married in the
  February" could mean February 1953 or 1954. Claude gave a window covering
  both. The answer key assumed 1953.

### Behaviour checks

| Case | Expected behaviour | Result |
|---|---|---|
| 01 news article | Resolve "on Tuesday" and "the previous evening" from the dateline | ✓ derived dates |
| 03 witnesses + log | Merge accounts; report the 23:30 vs 23:52 conflict | ✓ merged, conflict reported |
| 04 diary | Keep vague dates as windows; keep the undated page | ✓ |
| 05 story | Identify the flashback (1975) and the flash-forward (2012) | ✓ both |
| 06 incident CSV | Read epoch timestamps; mark "probably around 14:05" as hedged | ✓ both |
| 07 status reports | Planned vs. actual: launch 21 days late, design 7 days late, API early | ✓ all three |
| 08 Old Style letters | Convert Julian dates (including the 25 March year start) | ✓ |
| 09 family record | Write Samvat dates for the panchang converter, purnimanta reckoning | ✓ |
| 13 recipe (no dates) | Invent no dates | ✓ |

## Triggering (batch `trigger-3`, current v1.0.1 description)

12 short prompts: 6 that should use the skill, and 6 unrelated ones that
shouldn't.

| Description | Should trigger, did | Shouldn't trigger, did |
|---|---|---|
| v1.0.0 | 2 of 6 | 0 of 6 |
| v1.0.1 (current) | **4 of 6** | **0 of 6** |

The prompts still missed are short and given inline, such as "put these
three events in order: …". Claude answered those directly and correctly.
In the 14-case batch (v1.0.0 description), the skill was used in 12 of 14
cases. The two misses were short questions that Claude also answered
correctly on its own.

## Known limitations of this evaluation

- **Synthetic documents.** The test documents were written for this
  evaluation by the skill's author, who also wrote the answer keys. They are
  realistic but not independent. Contributions of real documents with
  independently made answer keys are very welcome.
- **One run per prompt.** Claude's behaviour varies between runs, so treat
  the triggering figures as indicative rather than precise rates.
- **Script runs blocked by the test harness.** The test sessions ran with a
  narrow command allow-list, which refused some of Claude's compound shell
  commands in 7 of 14 cases. This affects the "ran the script / self-check"
  counts (Claude *attempted* the self-check in 11 of 14 cases; 6 ran).
  Extraction quality is not affected: it is scored from the event files
  Claude wrote.
- **Automatic matching.** Events are matched to the answer key by keywords
  plus overlapping dates. The unmatched lists were reviewed by hand.

Total cost of the 14-case batch: about $3.34 of Claude usage.
