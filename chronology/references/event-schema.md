# Event schema

The input file for `scripts/chronology.py` is either a bare JSON array of
events or an object with an `events` array plus optional metadata:

```json
{
  "title": "Apollo 11 Mission",
  "source_document": "apollo11-notes.md",
  "events": [
    {
      "date": "1969-07-20T20:17:40Z",
      "end": null,
      "title": "Eagle lands in the Sea of Tranquility",
      "details": "Armstrong: \"The Eagle has landed.\"",
      "source": "para 4",
      "approximate": false,
      "derived": false,
      "precision": null,
      "tags": ["landing"]
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `date` (alias `start`) | yes (may be `null`) | Point or start of the event. See the formats below. `null` means undated. |
| `end` | no | End of a range or duration. |
| `title` (alias `event`) | yes | Short factual headline. |
| `details` (alias `context`) | no | Associated content: who, what, where, why, quotes. |
| `source` | no | Locator: page, chapter, paragraph, URL, row id. |
| `approximate` | no | `true` for circa / around / estimated dates. Rendered as "c.". |
| `derived` | no | `true` when the date was computed from a relative expression. |
| `precision` | no | Declare a precision *coarser* than the string implies, e.g. `"date":"1969","precision":"decade"`. |
| `tags` | no | Free-form labels, used for filtering and the CSV output. |
| `id` | no* | Stable identifier. **Events with the same `id` are the same event**, even across files. Merged events keep every source. *Required for `after`, `before`, `offset` and merging. |
| `earliest` / `latest` | no | Explicit window of possible dates, e.g. "late 1970s" → `"date":"1970s","earliest":"1975","latest":"1979"`. If only these are given, `date` defaults to `earliest`. |
| `after` / `before` | no | Id or list of ids this event must come after or before ("after the meeting"). Checked against the date windows. |
| `offset` | no | `{"from": "<id>", "by": "3d", "anchor": "start"\|"end"}` for "3 days after X". If `date` is null, the date is **derived** from it. If `date` is given, it is **checked** against it. Units: `s, min, h, d, w, mo, y` (negative = before). |
| `entities` | no | People, organisations or objects involved. Used by lifespan checks. |
| `lifespan` | no | Marks this event as an entity's boundary: `{"entity": "Smith", "boundary": "start"\|"end"}` (birth/death, founding/closure). |
| `not_before` / `not_after` | no | Date limits from world knowledge (anachronism checks), e.g. `"not_before":"2006-03"`. |
| `reason` | no | Why `not_before` / `not_after` apply, e.g. "Twitter launched March 2006". |
| `hedged` | no | `true` when the source hedges ("reportedly", "probably", "I think"). Lowers confidence |
| `certainty` (alias `reliability`) | no | `low` / `medium` / `high`: how reliable the source is for this fact. `low` caps confidence at low and `medium` caps it at medium |
| `quote` | recommended | The source's exact words for this event and its date, up to about 25 words. Checked by `--verify`, and it raises or lowers confidence |
| `planned` (alias `due`) | no | When the event was planned or due. The script reports late or early delivery (`schedule` issues) |

Any other fields are kept and passed through unchanged in the `json` layout.

## Other calendars

Write `<calendar>:<date as in the source>` in any date field (`date`, `end`,
`earliest`, `latest`, `not_before`, `not_after`). Alternatively, set
`"calendar": "julian"` on the event to apply one calendar to all its date
fields. The output shows both forms, e.g. `23 Apr 1616 (Julian) (= 3 May 1616)`,
and the event is placed by its Gregorian window.

| Prefix | Format | Example | Notes |
|---|---|---|---|
| `julian:` (`os:`) | `Y[-M[-D]]`, negative = BCE | `julian:1616-04-23`, `julian:-44-03-15` | Old Style. Years are taken to start on 1 Jan; if the source uses a 25 March year start, adjust the year first |
| `hijri:` (`islamic:`, `ah:`) | `Y[-M[-D]]`, month number or name | `hijri:1445-09-01`, `hijri:1445-ramadan` | Tabular (arithmetical) calendar. The window is widened by 1–2 days for moon-sighting differences |
| `hebrew:` (`jewish:`, `am:`) | `Y[-M[-D]]`, Nisan = 1 … Tishrei = 7, or names | `hebrew:5785-tishrei-01`, `hebrew:5784-adar2-14` | Leap-year months: `adar1`/`adar i` and `adar2`. The day begins at sunset (noted in the report) |
| `japanese:` | `Era Y[-M[-D]]`, rōmaji, kanji or initial | `japanese:Showa 20-08-15`, `japanese:令和元年-05-01`, `japanese:H31` | Meiji 6 (1873) onward, when Japan adopted Gregorian months |
| `regnal:` | `Name:N` | `regnal:Elizabeth II:3` | Needs `"reigns": {"Elizabeth II": "1952-02-06"}` (accession day) in the file metadata |
| `fy:` (`fiscal:`) | `Y` or `Y-Qn` | `fy:2024`, `fy:2024-Q2` | Uses `"fiscal_year": {"start": "10-01", "label": "end"}` from the metadata. `label: end` means FY2024 ends in 2024. The default is calendar years |
| `panchang:` (`panchangam:`, `hindu:`, `tithi:`) | `[amanta\|purnimanta] [kartikadi] VS\|Shaka YEAR [adhika] MASA [shukla\|krishna] [TITHI]` | `panchang:VS 2081 Chaitra shukla 9`, `panchang:Shaka 1596 Jyeshtha sudi 13`, `panchang:VS 2080 adhika Shravana` | Hindu lunisolar calendar, computed astronomically (see below). Optional `"panchang": {"location", "scheme", "year_start"}` metadata |
| `gregorian:` | as usual | `gregorian:1752-09-14` | Explicit, e.g. when the event sets `"calendar"` |
| `chinese:` | — | — | Not supported: lunisolar dates need astronomical tables. Convert by hand and keep the original in `details`. The event is listed as undated, with the reason |

### Hindu panchang (`panchang:`)

Dates are computed the *drik* (astronomical) way that most modern panchangs
use. They are not looked up in a table.

- **tithi**: the 12° step of the Moon–Sun elongation current at **local
  sunrise**. Shukla 1–15 (15 = Purnima), Krishna 1–15 (15 = Amavasya).
- **masa**: amanta months begin at a new moon, and are named from the
  sidereal sign (Lahiri ayanamsa) the Sun is in at that new moon. A month
  with no solar ingress is **adhika** (leap) and takes the next month's
  name.
- **year**: Vikram Samvat = Gregorian + 57 and Shaka = Gregorian − 78, both
  starting at Chaitra shukla 1. Add `kartikadi` for Gujarati years, which
  start at Kartika shukla 1.
- **purnimanta** (North Indian): months end at the full moon, so its krishna
  paksha falls in the previous amanta month. The year number still changes
  at Chaitra shukla 1, so `purnimanta VS 2080 Chaitra krishna 1` is 26 Mar 2024.

| Part | Accepted words |
|---|---|
| Era | `VS`, `Vikram`, `Vikram Samvat`, `Samvat`; `Shaka`, `Saka` |
| Masa | Chaitra, Vaishakha (Baisakh), Jyeshtha (Jeth), Ashadha, Shravana (Sawan), Bhadrapada (Bhado), Ashvina (Ashwin, Aswayuja), Kartika, Margashirsha (Agrahayana), Pausha (Pushya), Magha, Phalguna; prefix `adhika` (or `nija` for the regular month) |
| Paksha | `shukla` / `sudi` / `sud` / `bright`; `krishna` / `vadi` / `vad` / `badi` / `bahula` / `dark` |
| Tithi | 1–15, or names: Pratipada … Chaturdashi, `purnima`, `amavasya` |

Metadata (file level): `"panchang": {"location": "delhi" | "ujjain" | "mumbai" |
"chennai" | "kolkata" | "bengaluru" | "hyderabad" | "varanasi" | "pune" |
"ahmedabad" | "kathmandu" | {"lat": …, "lon": …, "tz": 5.5}, "scheme":
"amanta" | "purnimanta", "year_start": "chaitra" | "kartika"}`. The default is
New Delhi, amanta, Chaitra.

**Output.** For a tithi date the label gives the civil day on which the
tithi was current at sunrise, **and when the tithi actually ran**, e.g.
`[at sunrise on 3 Oct 1869; tithi ran 2 Oct 1869 09:47 to 3 Oct 1869 06:52, UTC+5:30]`.
Events recorded by the tithi current *at that moment* (births, deaths,
battles) can fall on the day the tithi began, so the window covers both
days, plus ±1 day for almanacs that differ. Kshaya (skipped) and vriddhi
(repeated) tithis are labelled.

**Accuracy.** Checked against published timings, all within a few minutes:

- new moons
- Delhi sunrise
- Ugadi, Ram Navami and Holi for 2023–2025, including Navami and Purnima start and end times
- the adhika months of 2020, 2023 and 2026

Historically it reproduces Shivaji's coronation (Jyeshtha shukla 13, Shaka
1596 = 16 Jun 1674 Gregorian, i.e. the conventional 6 June Old Style) and
Gandhi's birth (Bhadrapada vad 12, Gujarati VS 1925, a tithi that began on
2 Oct 1869).

Expect ±1 day against almanacs that use Surya Siddhanta rules, another
ayanamsa, or another location. Accuracy degrades well before 1500 CE.
**Festivals** often follow other rules (Diwali at pradosh, Janmashtami at
midnight): Ashvina Amavasya 2023 was current at sunrise on 13 Nov, but Diwali
was 12 Nov. For a festival, use the festival's published date as `date`, and
keep the panchang wording in `details`. Solar calendars (Tamil, Malayalam,
Bengali and so on) are not supported. Convert those by hand.

A converted date covers its full Gregorian window. A Hijri month, for
example, spans parts of two Gregorian months, so at `day` granularity it is
grouped by the finest Gregorian period that contains it.

## Telling order and incremental extraction

| Field | Where | Meaning |
|---|---|---|
| `told` | event | Position in the source's narrative (a number). If absent, the order of events in the file is used, so extract in reading order. Drives `-l telling` and the html "As told" view |
| `extracted_through` | file metadata | How far this source has been extracted, e.g. `"p. 120"`, `"ch. 7"` or `"row 5000"`. It is saved in the state file and reported as progress |

## Self-check (`--verify`)

`--verify SOURCE.txt` looks for each event's `quote` in the source text. It
ignores case, curly vs. straight quotes, dashes, extra whitespace, and words
hyphenated across line breaks. Each event's `source_document` is matched to
a `--verify` file by file name; if only one file is given, it is used for
everything.

| Check | Result |
|---|---|
| Quote found word for word | counted as verified (confidence +5) |
| 85–98% of the quote matches, in order | WARNING showing what the source actually says (confidence −5) |
| Not found | ERROR, event marked `[quote not found in source]` (confidence −30) |
| Source has page breaks (`\f`) and `source` cites `p. N` | WARNING if the quote is on another page |
| Quote names a year or month the event's date can't be in | WARNING (confidence −20) |

Derived dates and other-calendar dates skip the date check, because their
wording legitimately differs. "may" and "march" (and three-letter month
abbreviations) count as months only when a number is next to them.

## Confidence

Each event gets a score from 5 to 100, and a level: **high** (75 or more),
**medium** (50–74) or **low** (under 50). The table, CSV, JSON and HTML show
the level and the reasons. Other layouts mark only `[low confidence]` events.

| Factor | Effect |
|---|---|
| Date precision | second/minute 90 · hour 88 · day 85 · week 75 · month 70 · quarter 65 · year 60 · decade 45 · century 35 · millennium 25 |
| Approximate (`c.`) | −15 |
| Derived from a relative statement | −10 |
| Calendar conversion with uncertainty | −5 |
| `hedged` | −20 |
| Each extra corroborating source | +10 (max +20) |
| Sources disagree (⚠) | −25 |
| Involved in an ERROR / WARNING | −20 / −10 |
| Quote verified / approximate / not found | +5 / −5 / −30 |
| Own quote contradicts the date | −20 |
| `certainty: low` / `medium` | caps the score at 45 / 70 |

The score shows how well-supported the date is in the material. It is not a
probability that the event happened.

## Date windows

The script turns every date into a window of possible instants:

| Input | Window |
|---|---|
| `1969-07-20T20:17:40` | that second |
| `1969-07` | 1 Jul – 31 Jul 1969 |
| `C19` | 1 Jan 1801 – 31 Dec 1900 |
| `1969` + `"approximate": true` | 1968 – 1970 (one neighbouring period on each side) |
| `1970s` + `earliest:"1975"`, `latest:"1979"` | 1975 – 1979 |
| Same `id` in several sources that agree | The overlap of their windows (corroboration narrows it) |

Windows decide which orderings are certain. An event whose window overlaps the
window of the event listed just above it is marked **≈** (the order between
them is not established by the source).

## Several sources

Write one events file per source document and set `source_document` in each.
Give the same `id` to events that describe the same happening, and pass all
the files to the script together:

```bash
python scripts/chronology.py witness.json police-log.json newspaper.json -g day -l table
```

- Sources that agree are combined: "2 sources: p1 · witness.txt; row 1 · police-log.csv".
- Sources that give non-overlapping dates are marked **⚠** and reported as a
  conflict, with each source's date. The date shown is the one most sources
  agree with, then the most precise one.
- `--auto-merge` also merges id-less events with identical titles (after
  lowercasing and removing punctuation). Prefer explicit ids, because
  deciding that two descriptions are the same event is a judgement call.

## Accepted date formats

| Format | Example | Precision |
|---|---|---|
| ISO year | `1969`, `-44` (44 BCE) | year |
| Era suffix | `753 BC`, `44 BCE`, `79 AD` | year |
| ISO month | `1969-07` | month |
| ISO date | `1969-07-20` | day |
| ISO date-time | `1969-07-20T20`, `1969-07-20T20:17`, `1969-07-20T20:17:40` | hour / minute / second |
| With zone | `...T20:17:40Z`, `...T15:17-05:00` | converted to UTC |
| Quarter | `1969-Q3` | quarter |
| ISO week | `1969-W29` | week |
| Decade | `1960s`, `40s BCE` | decade |
| Century | `C19` / `19C` (19th c.), `-C1` / `1C BCE` | century |
| Millennium | `M2`, `-M1` | millennium |

Rules:

- Years are **historical**. There is no year 0, and `-1` is 1 BCE.
- Centuries are counted strictly: the 19th century is 1801-1900. Decades
  follow common usage: the 1960s are 1960-1969.
- Dates in **other calendars** are written as they appear in the source,
  with a calendar prefix (see below). The script converts them. Don't
  convert them by hand, except for the Chinese calendar.
- Convert Unix epoch values (seconds or ms) and Excel serial dates to ISO.
- Don't mix local wall-clock times from different zones without offsets.
  Either add offsets, or state the assumed zone in the notes.
