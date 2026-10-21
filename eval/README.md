# Evaluating the CHRONOLOGY skill inside Claude

The skill's script has its own unit tests (`chronology/tests`). This kit tests
the **skill**: whether Claude picks it up, follows its workflow, extracts the
right events with the right dates, and self-checks before answering. It runs
real, headless Claude Code sessions and scores them against answer keys.

```
eval/
├── build_cases.py        writes cases/ and trigger_probes.json (the source of truth)
├── cases/NN-name/        inputs/ (what Claude sees) + gold.json (prompt + answer key)
├── trigger_probes.json   12 short prompts: 6 should trigger the skill, 6 should not
├── run_eval.py           runs `claude -p` per case/probe, then scores and reports
├── score.py              scoring (also re-scores existing runs)
├── selftest_scorer.py    proves the scorer works, using fabricated runs (no cost)
└── runs/<batch>/         transcripts, Claude's files, score.json per run, report.md
```

## The cases

| Case | Tests |
|---|---|
| 01 news, relative dates | Dateline anchoring ("on Tuesday", "the previous evening"), vague "last autumn" |
| 02 email time zones | Hour precision, IST/PDT to UTC |
| 03 witnesses + dispatch CSV | Merging sources, a time conflict (23:30 vs 23:52) |
| 04 diary | Vague dates without fake precision, the undated page kept |
| 05 story | Telling order vs. story order (flashbacks, flash-forward) |
| 06 incident log CSV + notes | Table input (epoch seconds), hedged "probably around 14:05" |
| 07 status reports | Planned vs. actual: who slipped and by how much |
| 08 Old Style letters | Julian dates and the 25 March year start ("1 January 1731" = 12 Jan 1732 Gregorian) |
| 09 family record (bahi) | Hindu panchang dates, purnimanta, adhika month |
| 10 bio | Contradictions: Instagram in 2003, a mentor calling after his death |
| 11 symptom notes | A "how long between" question with honest bounds |
| 12 company history (~3,300 words) | Recall at length: 31 dated events plus a relative one |
| 13 recipe | No dates at all: must not invent any |
| 14 conference notes | Producing the HTML page and an `.ics` file |

All documents were written for this kit, so every event is known exactly.
Case 09's gold dates come from the skill's own panchang code, which was
validated separately against published timings. That case measures whether
Claude writes panchang dates for the script, not the conversion itself.

## What is scored

| Metric | How |
|---|---|
| Triggered | A `Skill` tool call naming `chronology` |
| Step-following | `chronology.py` run; `--verify` run; references opened; layout and granularity as asked |
| Recall / precision | Claude's events (re-loaded from the exact files it passed to the script) matched to gold by keywords plus overlapping date windows. Unmatched extracted events are listed for manual review, because the gold may be incomplete |
| Date accuracy | Matched events whose date window agrees with the gold window |
| Fake precision | A vague gold date ("late spring") given a precise, non-approximate date |
| Issues, undated, quotes | Expected consistency issues raised; undated items kept; share of events with a `quote` |
| Answer patterns | Required statements in the reply (e.g. "launch late by 21 days") |

## Running

```bash
python eval/selftest_scorer.py                     # check the scorer (free)
python eval/run_eval.py --all --dry-run            # prepare folders, send nothing
python eval/run_eval.py --cases 01,03 --budget 1   # a small pilot
python eval/run_eval.py --all                      # everything
python eval/score.py --report eval/runs/<batch>    # re-build a report
```

Each run uses `--max-budget-usd` (default $2 per run), `--permission-mode
dontAsk` with a fixed tool list, no MCP servers, and project settings only.
The current skill is copied into each run folder as a project skill. If the
same skill is also installed on the account (e.g. synced from claude.ai), it
may be offered too: `score.json` records which skill name was invoked.

## Limits

- **The data is synthetic.** It is realistic but written for the test, and
  the same author wrote the skill, the documents and the answer keys. Add
  real documents with independently made answer keys for a stronger result.
- **Matching is automatic.** It can miss a correct event phrased very
  differently from the gold keywords. Check the "unmatched extracted" lists.
- **Single runs.** Claude's behaviour varies between runs. Repeat a batch to
  see the spread before drawing firm conclusions.
