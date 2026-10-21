# Without code execution

Read this when the script can't be run. Apply the same rules by hand, and say
that results were produced without the script.

- **Sort** by start date. Within the same instant, the coarser date comes
  first ("1969" before "1969-07-20"), then source order.
- **Bucket** each event into its period at the requested granularity. Events
  finer than the granularity roll up into that period, with their exact time
  in parentheses. Events *coarser* than the granularity stay at their own
  level, labelled "date known only to <level>". Never fake precision.
- **Group levels** (tree/bullets): from the top level down to the
  granularity, e.g. `year > month > day` (see `granularity.md`).
- **Windows and ≈:** treat each date as its earliest–latest window. Mark an
  event ≈ when its window overlaps the window of the event above it.
- **Merging and ⚠:** combine events that share an id. If their windows don't
  overlap, show the majority date, mark the event ⚠, and list each source's date.
- **Checks:** go through every check in `checks.md`.
- **Gaps:** a gap is certain only between the latest possible date of
  everything before and the earliest possible date of the next event.
- **Lanes:** a markdown table, with one row per period and one column per
  lane. An event appears in every lane it belongs to.
- **Calendars:** convert Julian dates with the century-dependent offset
  (10 days for 1582–1700, 11 for 1700–1800, 12 for 1800–1900, 13 for
  1900–2100). For other calendars, say the exact conversion needs the script.
- **Telling:** list events in reading order, give each its chronological
  position, and label backward and forward jumps.
- **Confidence:** use the factors in `event-schema.md` qualitatively (high,
  medium or low, with a reason).
- **Self-check:** re-open at least 5–10 cited passages, and say how many.
- **Not feasible by hand:** HTML, `.ics`, exact non-Julian calendar
  conversion (Hindu panchang dates need the Sun and Moon positions), and
  large tables. Offer text layouts (`density`, `lanes`)
  instead, and say these need code execution.
