# Granularity rules

## Levels (coarse → fine)

`millennium > century > decade > year > quarter > month > week > day > hour > minute > second`

Synonyms are accepted: centuries, yrs, mins, secs, hr, "date" (= day), and so on.

## What "granularity" controls

The granularity is the **smallest period used to group and label events**.
Events are always *ordered* by their full precision, so two events on the
same day keep their hour/minute order even at `day` granularity.

| Event precision vs. granularity | Treatment |
|---|---|
| Finer (e.g. a 20:17:40 event at `day`) | Rolled up into its day. The exact time is shown in parentheses unless `--no-exact` is set. |
| Equal | Placed in its period. |
| Coarser (e.g. "July 1969" at `day`) | Stays at its own level (the July node), comes before the finer events of July, and is labelled "date known only to month". Never assign a fake day. |

## Group levels for `tree`, `bullets` and `json`

The hierarchy runs from a **top** level down to the granularity, using
this chain:

`millennium > century > decade > year > month > day > hour > minute > second`

- `quarter` granularity uses `... year > quarter`.
- `week` granularity uses `... year > week` (ISO weeks; CE dates only).
- `millennium` and `decade` appear only when chosen as the top level or the granularity.
- **Auto top**: if the granularity is year or coarser, the top is the
  granularity itself (a flat list of periods). Otherwise the top is
  `century` when the data spans more than 500 years, and `year` when it
  doesn't.
- Override with `--top <level>` or with an explicit `--levels year,day,minute`
  (levels can be skipped).

Pick the top that keeps the tree readable:

| Data spans | Requested granularity | Suggested levels |
|---|---|---|
| Hours (incident log) | second/minute | `--levels hour,minute` |
| Days to weeks | hour | `--levels day,hour` |
| Months to years | day | `year > month > day` (auto) |
| Centuries | year | `--top century` → `century > year` |
| Millennia | century | `--top millennium` |

## Labels

| Level | Full label | Short label (under its parent) |
|---|---|---|
| millennium | 2nd millennium, 1st millennium BCE | — |
| century | 19th century, 1st century BCE | — |
| decade | 1960s, 40s BCE | — |
| year | 1969, 44 BCE | — |
| quarter | Q3 1969 | Q3 |
| month | Jul 1969 | Jul |
| week | 1969-W29 | W29 |
| day | 20 Jul 1969 | 20 Jul |
| hour | 20 Jul 1969 20:00 | 20:00 |
| minute | 20 Jul 1969 20:17 | 20:17 |
| second | 20 Jul 1969 20:17:40 | 20:17:40 |

## Ranges

A range sorts by its start. It is labelled `start – end` at the requested
granularity, e.g. `24 Jul 1969 – 10 Aug 1969`. In tree layouts it sits
under the period that holds its start.

## Order certainty (≈)

Sorting uses each event's best date. The script then compares each event's
window of possible dates with the window of the event listed just above it. If
the windows overlap, the source does not establish which came first, and the
event is marked **≈**. Typical causes are mixed precision ("July 1969" next to
"16 Jul 1969"), approximate dates, and simultaneous timestamps. Mention ≈
events in the notes when the order matters to the user's question.

## Approximate and derived dates

- Approximate dates get the prefix `c.`, both in the group label and in the
  event label.
- Derived (relative-resolved) dates get the suffix `[derived date]`. Explain
  the derivation in `details`.
