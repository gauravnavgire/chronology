#!/usr/bin/env python3
"""
chronology.py - sort, bucket and render extracted events as a chronology.

Standard library only (Python 3.8+). Claude extracts events from the source
material into a JSON file (schema in references/event-schema.md); this script
does the deterministic part: date normalisation, ordering, grouping at the
requested granularity, and rendering in the requested layout. It also:

  * treats every date as a window of possible instants (earliest..latest),
    so it can tell which orderings are certain and which are not (≈);
  * merges several event files into one chronology, combining events that
    share an `id`, counting corroborating sources and flagging conflicts (⚠);
  * runs consistency checks (impossible ranges, broken before/after or
    "N days after" statements, lifespans, anachronisms) and prints a report;
  * converts Julian, Hijri, Hebrew, Japanese-era, Hindu panchang (tithi,
    computed from Sun/Moon positions), regnal and fiscal dates
    ("julian:1616-04-23") to Gregorian windows, keeping the original wording;
  * compares telling order with story order (flashbacks, flash-forwards);
  * remembers each run in a state file and reports what changed since;
  * scores each event's confidence (high/medium/low, with reasons);
  * offers presets (incident, legal, biography, history, project, story),
    including planned-vs-actual checks;
  * answers questions: --how-long, --as-of, --before/--after, --from/--to,
    and filters by entity, tag, source or text;
  * reads CSV / TSV / SQLite directly (date column detection, --collapse);
  * exports iCalendar (.ics), Mermaid Gantt, TimelineJS and vis-timeline;
  * self-checks: --verify SOURCE.txt looks up each event's `quote` in the
    source (word for word, page citation, and whether it supports the date).

Tests: python -m unittest discover -s tests   (from the skill folder)

Usage:
    python chronology.py events.json --granularity day --layout tree
    python chronology.py events.json -g century -l table --title "Rome"
    python chronology.py events.json -g minute -l timeline --levels day,hour,minute
    python chronology.py events.json -g month -l mermaid -o out.md
    python chronology.py a.json b.json c.json -g day -l table   # merge sources
    python chronology.py events.json --report-only              # checks only
    python chronology.py events.json -l telling                 # as told vs. as happened
    python chronology.py *.json -l table --state work/state.json  # what changed
    python chronology.py events.json --preset project           # schedule view
    python chronology.py events.json --how-long born died --answer-only

Layouts: tree, timeline, table, bullets, mermaid, csv, json, density, lanes,
         html, telling, ics, gantt, timelinejs, vis
Granularities: millennium, century, decade, year, quarter, month, week,
               day, hour, minute, second
"""

import argparse
import csv
import datetime as dt
import difflib
import io
import json
import math
import re
import sys

# --------------------------------------------------------------------------
# Granularity model
# --------------------------------------------------------------------------

RANK = {
    "millennium": 0, "century": 1, "decade": 2, "year": 3, "quarter": 4,
    "month": 5, "week": 6, "day": 7, "hour": 8, "minute": 9, "second": 10,
}
ALIASES = {
    "millennia": "millennium", "centuries": "century", "decades": "decade",
    "years": "year", "yr": "year", "quarters": "quarter", "q": "quarter",
    "months": "month", "weeks": "week", "days": "day", "date": "day",
    "hours": "hour", "hr": "hour", "minutes": "minute", "min": "minute",
    "mins": "minute", "seconds": "second", "sec": "second", "secs": "second",
    "s": "second",
}
BASE_CHAIN = ["millennium", "century", "decade", "year", "month", "day",
              "hour", "minute", "second"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def norm_level(name):
    name = name.strip().lower()
    name = ALIASES.get(name, name)
    if name not in RANK:
        raise ValueError("unknown granularity '%s' (use one of: %s)"
                         % (name, ", ".join(RANK)))
    return name


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "%d%s" % (n, suf)


# --------------------------------------------------------------------------
# Date parsing
# --------------------------------------------------------------------------
# Years are *historical*: negative = BCE, there is no year 0 (-1 = 1 BCE).

ISO_RE = re.compile(
    r"^(?P<y>[+-]?\d{1,6})"
    r"(?:-(?P<mo>\d{1,2})"
    r"(?:-(?P<d>\d{1,2})"
    r"(?:[T ](?P<h>\d{1,2})"
    r"(?::(?P<mi>\d{2})"
    r"(?::(?P<s>\d{2})(?:\.\d+)?)?)?)?)?)?"
    r"\s*(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)
QUARTER_RE = re.compile(r"^(?P<y>[+-]?\d{1,6})-?Q(?P<q>[1-4])$", re.I)
WEEK_RE = re.compile(r"^(?P<y>\d{4})-?W(?P<w>\d{1,2})$", re.I)
DECADE_RE = re.compile(r"^(?P<y>\d{1,5}0)s(?P<bce>\s*(?:BCE?|B\.C\.E?\.?))?$", re.I)
CENTURY_RE = re.compile(r"^(?P<neg>-)?C(?P<n>\d{1,3})$|^(?P<n2>\d{1,3})C(?P<bce>\s*BCE?)?$", re.I)
MILLENNIUM_RE = re.compile(r"^(?P<neg>-)?M(?P<n>\d{1,2})$", re.I)
ERA_RE = re.compile(r"^(?P<y>\d{1,6})\s*(?P<era>BCE?|B\.C\.E?\.?|CE|AD|A\.D\.)$", re.I)


class DateParts(object):
    """A (possibly partial) point in time with an explicit precision."""

    __slots__ = ("year", "month", "day", "hour", "minute", "second",
                 "precision", "quarter", "week")

    def __init__(self, year, month=None, day=None, hour=None, minute=None,
                 second=None, precision=None, quarter=None, week=None):
        self.year, self.month, self.day = year, month, day
        self.hour, self.minute, self.second = hour, minute, second
        self.quarter, self.week = quarter, week
        if precision is None:
            precision = "year"
            for lvl, val in (("month", month), ("day", day), ("hour", hour),
                             ("minute", minute), ("second", second)):
                if val is None:
                    break
                precision = lvl
        self.precision = precision
        if self.quarter is None and month is not None:
            self.quarter = (month - 1) // 3 + 1

    @property
    def astro(self):
        """Astronomical year (1 BCE = 0) for arithmetic ordering."""
        return self.year + 1 if self.year < 0 else self.year

    def sort_key(self):
        # Missing components sort as -1 so a coarse date precedes finer
        # dates inside the same period ("1969" before "1969-07-20").
        def v(x):
            return -1 if x is None else x
        month = self.month
        if month is None and self.quarter is not None and self.precision == "quarter":
            month = (self.quarter - 1) * 3 + 1
        return (self.astro, v(month), v(self.day), v(self.hour),
                v(self.minute), v(self.second))


def parse_date(raw):
    """Parse a date string into DateParts. Returns None for empty input."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return DateParts(int(raw))
    s = str(raw).strip()
    if not s:
        return None

    m = MILLENNIUM_RE.match(s)
    if m:
        n = int(m.group("n"))
        y = -((n - 1) * 1000 + 1000) if m.group("neg") else (n - 1) * 1000 + 1
        return DateParts(y, precision="millennium")
    m = CENTURY_RE.match(s)
    if m:
        n = int(m.group("n") or m.group("n2"))
        bce = bool(m.group("neg") or m.group("bce"))
        y = -(n * 100) if bce else (n - 1) * 100 + 1
        return DateParts(y, precision="century")
    m = DECADE_RE.match(s)
    if m:
        y = int(m.group("y"))
        if m.group("bce"):
            y = -(y + 9) if y else -9
        return DateParts(y, precision="decade")
    m = ERA_RE.match(s)
    if m:
        y = int(m.group("y"))
        return DateParts(-y if m.group("era").upper().startswith("B") else y)
    m = QUARTER_RE.match(s)
    if m:
        return DateParts(int(m.group("y")), precision="quarter",
                         quarter=int(m.group("q")))
    m = WEEK_RE.match(s)
    if m:
        d = dt.date.fromisocalendar(int(m.group("y")), int(m.group("w")), 1)
        return DateParts(d.year, d.month, d.day, precision="week",
                         week=(int(m.group("y")), int(m.group("w"))))
    m = ISO_RE.match(s)
    if not m:
        raise ValueError("unrecognised date '%s'" % s)
    g = m.groupdict()
    y = int(g["y"])
    if y == 0:
        raise ValueError("year 0 does not exist in historical numbering "
                         "(use -1 for 1 BCE): '%s'" % s)
    parts = [y] + [int(g[k]) if g[k] is not None else None
                   for k in ("mo", "d", "h", "mi", "s")]
    mo, d, h, mi, sec = parts[1:]
    if mo is not None and not 1 <= mo <= 12:
        raise ValueError("month %d out of range in '%s'" % (mo, s))
    if d is not None:
        a = _hist_to_astro(y)
        dim = days_from_civil(a + (mo == 12), mo % 12 + 1, 1) - days_from_civil(a, mo, 1)
        if not 1 <= d <= dim:
            raise ValueError("day %d out of range in '%s'" % (d, s))
    if (h is not None and h > 23) or (mi is not None and mi > 59) or \
            (sec is not None and sec > 59):
        raise ValueError("time out of range in '%s'" % s)
    dp = DateParts(*parts)
    if g["tz"] and dp.hour is not None and 1 <= y <= 9999:
        dp = _to_utc(dp, g["tz"])
    return dp


def _to_utc(dp, tz):
    tz = tz.replace(":", "")
    if tz.upper() == "Z":
        return dp
    sign = 1 if tz[0] == "+" else -1
    offset = dt.timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
    t = dt.datetime(dp.year, dp.month, dp.day, dp.hour, dp.minute or 0,
                    dp.second or 0) - sign * offset
    return DateParts(t.year, t.month, t.day, t.hour,
                     t.minute if dp.minute is not None else None,
                     t.second if dp.second is not None else None,
                     precision=dp.precision)


# --------------------------------------------------------------------------
# Buckets and labels
# --------------------------------------------------------------------------

def can_bucket(dp, level):
    if RANK[dp.precision] < RANK[level]:
        return False
    if level == "week":
        return dp.precision == "week" or (dp.day is not None and 1 <= dp.year <= 9999)
    if level == "month" and dp.precision == "week":
        return True
    return True


def _era_split(y):
    return ("", y) if y > 0 else (" BCE", -y)


def bucket(dp, level, short=False):
    """Return (sort_key, label) of the period at `level` containing dp."""
    y = dp.year
    era, ay = _era_split(y)
    if level == "millennium":
        n = (ay - 1) // 1000 + 1
        return ((1 if y > 0 else -1, n if y > 0 else -n),
                "%s millennium%s" % (ordinal(n), era))
    if level == "century":
        n = (ay - 1) // 100 + 1
        return ((1 if y > 0 else -1, n if y > 0 else -n),
                "%s century%s" % (ordinal(n), era))
    if level == "decade":
        d = ay // 10 * 10
        return ((1 if y > 0 else -1, d if y > 0 else -d), "%ds%s" % (d, era))
    yl = "%d%s" % (ay, era)
    if level == "year":
        return ((dp.astro,), yl)
    if level == "quarter":
        return ((dp.astro, dp.quarter),
                "Q%d" % dp.quarter if short else "Q%d %s" % (dp.quarter, yl))
    if level == "week":
        if dp.week is None:
            iy, iw, _ = dt.date(dp.year, dp.month, dp.day).isocalendar()
        else:
            iy, iw = dp.week
        return ((iy, iw), "W%02d" % iw if short else "%d-W%02d" % (iy, iw))
    mon = MONTHS[dp.month - 1]
    if level == "month":
        return ((dp.astro, dp.month), mon if short else "%s %s" % (mon, yl))
    dl = "%d %s %s" % (dp.day, mon, yl)
    if level == "day":
        return ((dp.astro, dp.month, dp.day),
                "%d %s" % (dp.day, mon) if short else dl)
    key = (dp.astro, dp.month, dp.day, dp.hour)
    if level == "hour":
        t = "%02d:00" % dp.hour
        return (key, t if short else "%s %s" % (dl, t))
    key += (dp.minute,)
    if level == "minute":
        t = "%02d:%02d" % (dp.hour, dp.minute)
        return (key, t if short else "%s %s" % (dl, t))
    key += (dp.second,)
    t = "%02d:%02d:%02d" % (dp.hour, dp.minute, dp.second)
    return (key, t if short else "%s %s" % (dl, t))


def exact_label(dp):
    """Full label at the date's own precision."""
    return bucket(dp, dp.precision if dp.precision != "week" else "week")[1]


# --------------------------------------------------------------------------
# Intervals: every date is a window [earliest, latest] in seconds
# --------------------------------------------------------------------------
# Proleptic Gregorian calendar on astronomical years, so BCE works too.

DAY = 86400
UNIT_SECONDS = {
    "second": 1, "minute": 60, "hour": 3600, "day": DAY, "week": 7 * DAY,
    "month": 2629746, "quarter": 3 * 2629746, "year": 31556952,
    "decade": 10 * 31556952, "century": 100 * 31556952,
    "millennium": 1000 * 31556952,
}


def days_from_civil(y, m, d):
    """Days since 1970-01-01 for astronomical year y (H. Hinnant)."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * ((m + 9) % 12) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return yoe + era * 400 + (m <= 2), m, d


def _month_start(a, m):
    a, m0 = divmod(a * 12 + m - 1, 12)
    return days_from_civil(a, m0 + 1, 1) * DAY


def _hist_to_astro(y):
    return y + 1 if y < 0 else y


def _span_years(y, level):
    """First and last historical year of the decade/century/millennium of y."""
    if level == "decade":
        d = abs(y) // 10 * 10
        return (max(d, 1), d + 9) if y > 0 else (-(d + 9), -max(d, 1))
    size = 1000 if level == "millennium" else 100
    n = (abs(y) - 1) // size + 1
    return ((n - 1) * size + 1, n * size) if y > 0 else (-(n * size), -((n - 1) * size + 1))


def period_bounds(dp):
    """(earliest, latest) second covered by dp at its precision."""
    p = dp.precision
    if p in ("millennium", "century", "decade"):
        first, last = _span_years(dp.year, p)
        return (_month_start(_hist_to_astro(first), 1),
                _month_start(_hist_to_astro(last) + 1, 1) - 1)
    a = dp.astro
    if p == "year":
        return (_month_start(a, 1), _month_start(a + 1, 1) - 1)
    if p == "quarter":
        m0 = (dp.quarter - 1) * 3 + 1
        return (_month_start(a, m0), _month_start(a, m0 + 3) - 1)
    if p == "month":
        return (_month_start(a, dp.month), _month_start(a, dp.month + 1) - 1)
    days = days_from_civil(a, dp.month, dp.day)
    if p == "week":
        days -= (days + 3) % 7  # back to Monday
        return (days * DAY, (days + 7) * DAY - 1)
    lo = days * DAY + (dp.hour or 0) * 3600 + (dp.minute or 0) * 60 + (dp.second or 0)
    return (lo, lo + UNIT_SECONDS[p] - 1)


def from_seconds(sec, precision):
    """DateParts for the instant `sec`, truncated to `precision`."""
    days, rem = divmod(sec, DAY)
    a, m, d = civil_from_days(days)
    h, rem = divmod(rem, 3600)
    mi, s = divmod(rem, 60)
    r = RANK[precision]
    return DateParts(a if a > 0 else a - 1,
                     m if r >= RANK["quarter"] else None,
                     d if r >= RANK["week"] else None,
                     h if r >= RANK["hour"] else None,
                     mi if r >= RANK["minute"] else None,
                     s if r >= RANK["second"] else None,
                     precision=precision)


OFFSET_RE = re.compile(r"^\s*([+-]?\d+)\s*([a-z]+)\s*$", re.I)
OFFSET_UNITS = {
    "s": "second", "sec": "second", "secs": "second", "second": "second",
    "seconds": "second", "min": "minute", "mins": "minute", "minute": "minute",
    "minutes": "minute", "h": "hour", "hr": "hour", "hrs": "hour",
    "hour": "hour", "hours": "hour", "d": "day", "day": "day", "days": "day",
    "w": "week", "wk": "week", "week": "week", "weeks": "week",
    "mo": "month", "month": "month", "months": "month", "y": "year",
    "yr": "year", "yrs": "year", "year": "year", "years": "year",
}


def parse_offset(text):
    m = OFFSET_RE.match(str(text))
    if not m or m.group(2).lower() not in OFFSET_UNITS:
        raise ValueError("unrecognised offset '%s' (e.g. 3d, -2h, 1y, 15min)" % text)
    n, unit = int(m.group(1)), OFFSET_UNITS[m.group(2).lower()]
    if unit == "week":  # "a week later" lands on a day, not an ISO week
        n, unit = n * 7, "day"
    return n, unit


def offset_text(n, unit):
    return "%+d %s%s" % (n, unit, "" if abs(n) == 1 else "s")


def shift(dp, n, unit):
    """dp moved by n units. Result precision is the coarser of the two."""
    p = dp.precision if RANK[dp.precision] < RANK[unit] else unit
    if unit in ("year", "month"):
        months = dp.astro * 12 + (dp.month or 1) - 1 + (n * 12 if unit == "year" else n)
        a, m0 = divmod(months, 12)
        dim = (_month_start(a, m0 + 2) - _month_start(a, m0 + 1)) // DAY
        sec = (days_from_civil(a, m0 + 1, min(dp.day or 1, dim)) * DAY
               + (dp.hour or 0) * 3600 + (dp.minute or 0) * 60 + (dp.second or 0))
    else:
        sec = period_bounds(dp)[0] + n * UNIT_SECONDS[unit]
    return from_seconds(sec, p)


# --------------------------------------------------------------------------
# Other calendars
# --------------------------------------------------------------------------
# A date written as "<calendar>:<value>" (or with an event-level "calendar"
# field) is converted to a window of proleptic Gregorian days. The original
# wording is kept for display. Algorithms for the Hebrew calendar follow
# Reingold & Dershowitz, "Calendrical Calculations"; RD 1 = 1 Jan 1 CE.

RD_UNIX = 719163  # RD of 1970-01-01
CALENDAR_RE = re.compile(r"^\s*([a-z_]+)\s*:\s*(.+)$", re.I)
CALENDAR_ALIASES = {
    "julian": "julian", "os": "julian", "old_style": "julian",
    "hijri": "hijri", "islamic": "hijri", "ah": "hijri",
    "hebrew": "hebrew", "jewish": "hebrew", "am": "hebrew",
    "japanese": "japanese", "nengo": "japanese", "wareki": "japanese",
    "regnal": "regnal", "reign": "regnal",
    "fy": "fiscal", "fiscal": "fiscal",
    "gregorian": "gregorian", "ns": "gregorian", "new_style": "gregorian",
    "chinese": "chinese", "lunar": "chinese",
    "panchang": "panchang", "panchangam": "panchang", "panchanga": "panchang",
    "hindu": "panchang", "tithi": "panchang",
}
YMD_RE = re.compile(r"^([+-]?\d{1,6})(?:-(\d{1,2}|[a-z][a-z0-9 '\-]*?))?(?:-(\d{1,2}))?$", re.I)


def _ymd(text, months=None):
    """Split 'Y[-M[-D]]'; M may be a month name looked up in `months`."""
    m = YMD_RE.match(text.strip())
    if not m:
        raise ValueError("expected YEAR[-MONTH[-DAY]], got '%s'" % text)
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    if mo is not None and not mo.isdigit():
        key = re.sub(r"[^a-z0-9]", "", mo.lower())
        if not months or key not in months:
            raise ValueError("unknown month name '%s'" % mo)
        mo = months[key]
    return y, (int(mo) if mo is not None else None), (int(d) if d else None)


def _span(first_day, next_first_day):
    """Seconds window from a first day (unix days) to the day before next."""
    return first_day * DAY, next_first_day * DAY - 1


# Julian ----------------------------------------------------------------

def julian_days(y, m, d):
    """Unix days for a Julian-calendar date (historical year, no year 0)."""
    a = _hist_to_astro(y)
    k = (14 - m) // 12
    yy, mm = a + 4800 - k, m + 12 * k - 3
    jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - 32083
    return jdn - 2440588


def julian_window(text):
    y, m, d = _ymd(text)
    if d:
        first = julian_days(y, m, d)
        return _span(first, first + 1), "%d %s %s (Julian)" % (d, MONTHS[m - 1], _yl(y))
    if m:
        nxt = (y, m + 1) if m < 12 else (y + 1 if y != -1 else 1, 1)
        return (_span(julian_days(y, m, 1), julian_days(nxt[0], nxt[1], 1)),
                "%s %s (Julian)" % (MONTHS[m - 1], _yl(y)))
    ny = y + 1 if y != -1 else 1
    return _span(julian_days(y, 1, 1), julian_days(ny, 1, 1)), "%s (Julian)" % _yl(y)


def _yl(y):
    return "%d BCE" % -y if y < 0 else "%d" % y


# Islamic (tabular / arithmetical) ----------------------------------------

HIJRI_MONTHS = ["Muharram", "Safar", "Rabi I", "Rabi II", "Jumada I", "Jumada II",
                "Rajab", "Shaban", "Ramadan", "Shawwal", "Dhu al-Qadah", "Dhu al-Hijjah"]
HIJRI_LOOKUP = {re.sub(r"[^a-z0-9]", "", n.lower()): i + 1 for i, n in enumerate(HIJRI_MONTHS)}
HIJRI_LOOKUP.update({"rabiulawwal": 3, "rabialawwal": 3, "rabi1": 3, "rabiulakhir": 4,
                     "rabialthani": 4, "rabi2": 4, "jumadaalula": 5, "jumada1": 5,
                     "jumadaalakhirah": 6, "jumada2": 6, "shaaban": 8, "ramadhan": 9,
                     "dhulqadah": 11, "dhulqidah": 11, "dhulhijjah": 12, "zulhijjah": 12})


def hijri_days(y, m, d):
    """Unix days for a date in the tabular Islamic calendar (civil epoch)."""
    jdn = d + (59 * (m - 1) + 1) // 2 + (y - 1) * 354 + (3 + 11 * y) // 30 + 1948439
    return jdn - 2440588


def hijri_window(text):
    y, m, d = _ymd(text, HIJRI_LOOKUP)
    if d:
        first, nxt, label = hijri_days(y, m, d), hijri_days(y, m, d) + 1, \
            "%d %s %d AH" % (d, HIJRI_MONTHS[m - 1], y)
    elif m:
        first = hijri_days(y, m, 1)
        nxt = hijri_days(y, m + 1, 1) if m < 12 else hijri_days(y + 1, 1, 1)
        label = "%s %d AH" % (HIJRI_MONTHS[m - 1], y)
    else:
        first, nxt, label = hijri_days(y, 1, 1), hijri_days(y + 1, 1, 1), "%d AH" % y
    # Observed (moon-sighting) dates can differ from the tabular calendar
    # by a day or two either way, and the day begins at sunset.
    return _span(first - 2, nxt + 1), label, (first, nxt)


# Hebrew -------------------------------------------------------------------

HEBREW_EPOCH = -1373427  # RD of 1 Tishrei AM 1
HEBREW_MONTHS = {1: "Nisan", 2: "Iyyar", 3: "Sivan", 4: "Tammuz", 5: "Av", 6: "Elul",
                 7: "Tishrei", 8: "Heshvan", 9: "Kislev", 10: "Tevet", 11: "Shevat",
                 12: "Adar", 13: "Adar II"}
HEBREW_LOOKUP = {"nisan": 1, "iyar": 2, "iyyar": 2, "sivan": 3, "tammuz": 4, "tamuz": 4,
                 "av": 5, "ab": 5, "elul": 6, "tishrei": 7, "tishri": 7, "heshvan": 8,
                 "cheshvan": 8, "marheshvan": 8, "kislev": 9, "tevet": 10, "teves": 10,
                 "shevat": 11, "shvat": 11, "adar": 12, "adari": 12, "adar1": 12,
                 "adarii": 13, "adar2": 13, "veadar": 13}


def _heb_leap(y):
    return (7 * y + 1) % 19 < 7


def _heb_elapsed(y):
    months = (235 * y - 234) // 19
    parts = 12084 + 13753 * months
    days = 29 * months + parts // 25920
    return days + 1 if (3 * (days + 1)) % 7 < 3 else days


def _heb_new_year(y):
    ny0, ny1, ny2 = _heb_elapsed(y - 1), _heb_elapsed(y), _heb_elapsed(y + 1)
    corr = 2 if ny2 - ny1 == 356 else (1 if ny1 - ny0 == 382 else 0)
    return HEBREW_EPOCH + ny1 + corr


def _heb_month_len(m, y):
    year_len = _heb_new_year(y + 1) - _heb_new_year(y)
    if (m in (2, 4, 6, 10, 13) or (m == 12 and not _heb_leap(y))
            or (m == 8 and year_len not in (355, 385))
            or (m == 9 and year_len in (353, 383))):
        return 29
    return 30


def hebrew_days(y, m, d):
    """Unix days for a Hebrew date (month numbering: Nisan = 1, Tishrei = 7)."""
    last = 13 if _heb_leap(y) else 12
    if not 1 <= m <= last:
        raise ValueError("Hebrew year %d has no month %d" % (y, m))
    rd = _heb_new_year(y) + d - 1
    if m < 7:
        rd += sum(_heb_month_len(mm, y) for mm in range(7, last + 1))
        rd += sum(_heb_month_len(mm, y) for mm in range(1, m))
    else:
        rd += sum(_heb_month_len(mm, y) for mm in range(7, m))
    return rd - RD_UNIX


def hebrew_window(text):
    y, m, d = _ymd(text, HEBREW_LOOKUP)
    name = "Adar I" if m == 12 and _heb_leap(y) else HEBREW_MONTHS.get(m)
    if d:
        first = hebrew_days(y, m, d)
        nxt, label = first + 1, "%d %s %d AM" % (d, name, y)
    elif m:
        first = hebrew_days(y, m, 1)
        nxt, label = first + _heb_month_len(m, y), "%s %d AM" % (name, y)
    else:
        first = _heb_new_year(y) - RD_UNIX
        nxt, label = _heb_new_year(y + 1) - RD_UNIX, "%d AM" % y
    # The Hebrew day begins at sunset on the previous civil day; the window
    # uses the civil day on which most of it falls (noted in the report).
    return _span(first, nxt), label, (first, nxt)


# Hindu lunisolar calendar (panchangam) --------------------------------------
# Drik-ganita (astronomical) method, as used by most modern panchangs:
#   tithi  = which 12-degree step of the Moon-Sun elongation is current at
#            local sunrise (shukla 1-15, krishna 16-30; 30 = amavasya)
#   masa   = amanta month, named from the sidereal sign the Sun occupies at
#            the new moon that starts it; no solar ingress in a month = adhika
#   year   = Vikram Samvat (Gregorian + 57) or Shaka (Gregorian - 78),
#            both counted from Chaitra shukla pratipada
# Sun: Meeus ch. 25; Moon: main terms of Meeus ch. 47 (ELP-2000/82);
# ayanamsa: Lahiri (Chitrapaksha); Delta-T: Espenak-Meeus. Good to minutes
# for 1500-2500 CE; dates are given a +/-1 day window for published
# panchangs that differ (location, ayanamsa, Surya-Siddhanta tradition).

PANCHANG_LOCATIONS = {  # lat, lon (east +), UTC offset in hours
    "delhi": (28.6139, 77.2090, 5.5), "new delhi": (28.6139, 77.2090, 5.5),
    "ujjain": (23.1765, 75.7885, 5.5), "mumbai": (19.0760, 72.8777, 5.5),
    "chennai": (13.0827, 80.2707, 5.5), "kolkata": (22.5726, 88.3639, 5.5),
    "bengaluru": (12.9716, 77.5946, 5.5), "bangalore": (12.9716, 77.5946, 5.5),
    "hyderabad": (17.3850, 78.4867, 5.5), "varanasi": (25.3176, 82.9739, 5.5),
    "pune": (18.5204, 73.8567, 5.5), "ahmedabad": (23.0225, 72.5714, 5.5),
    "kathmandu": (27.7172, 85.3240, 5.75),
}
MASA_NAMES = ["Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
              "Ashvina", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna"]
MASA_LOOKUP = {}
for _i, _names in enumerate([
        "chaitra chaitr chait", "vaishakha vaisakha vaishakh baisakh vaisakh",
        "jyeshtha jyaistha jyeshta jeth jyestha", "ashadha asadha ashadh asharh aashadha",
        "shravana sravana shravan sawan savan", "bhadrapada bhadra bhadrapad bhado bhadon",
        "ashvina asvina ashwin ashvin aswayuja asvayuja kunwar",
        "kartika karthika kartik karttika", "margashirsha margasira agrahayana aghan "
        "margashira margshirsh", "pausha pushya paush pausa", "magha magh",
        "phalguna phalgun phagun"]):
    for _n in _names.split():
        MASA_LOOKUP[_n] = _i + 1
TITHI_NAMES = ["Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
               "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dvadashi",
               "Trayodashi", "Chaturdashi"]
TITHI_LOOKUP = {n.lower(): i + 1 for i, n in enumerate(TITHI_NAMES)}
TITHI_LOOKUP.update({"prathama": 1, "padyami": 1, "dwitiya": 2, "dvitiya": 2, "tritiya": 3,
                     "chauth": 4, "chaturthi": 4, "shashti": 6, "sashti": 6, "ashtami": 8,
                     "navmi": 9, "dasami": 10, "ekadasi": 11, "dwadashi": 12,
                     "dvadasi": 12, "trayodasi": 13, "chaturdasi": 14,
                     "purnima": 15, "poornima": 15, "pournami": 15, "punnami": 15,
                     "amavasya": 30, "amavasai": 30, "amavas": 30})
PAKSHA_LOOKUP = {"shukla": 0, "sukla": 0, "sudi": 0, "sud": 0, "bright": 0, "s": 0,
                 "krishna": 15, "krsna": 15, "vadi": 15, "vad": 15, "badi": 15,
                 "bahula": 15, "dark": 15, "k": 15}
SYNODIC = 29.530588853


def _delta_t(y):
    """Earth rotation correction TT-UT in seconds (Espenak-Meeus)."""
    if 2005 <= y < 2050:
        t = y - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t * t
    if 1986 <= y < 2005:
        t = y - 2000
        return (63.86 + 0.3345 * t - 0.060374 * t ** 2 + 0.0017275 * t ** 3
                + 0.000651814 * t ** 4 + 0.00002373599 * t ** 5)
    if 1961 <= y < 1986:
        t = y - 1975
        return 45.45 + 1.067 * t - t * t / 260 - t ** 3 / 718
    if 1941 <= y < 1961:
        t = y - 1950
        return 29.07 + 0.407 * t - t * t / 233 + t ** 3 / 2547
    if 1920 <= y < 1941:
        t = y - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t * t + 0.0020936 * t ** 3
    if 1900 <= y < 1920:
        t = y - 1900
        return (-2.79 + 1.494119 * t - 0.0598939 * t * t + 0.0061966 * t ** 3
                - 0.000197 * t ** 4)
    u = (y - 1820) / 100.0
    dt_ = -20 + 32 * u * u
    if 2050 <= y < 2150:
        dt_ -= 0.5628 * (2150 - y)
    return dt_


def _T(ud):
    """Julian centuries (TT) from J2000 for unix days ud (UT)."""
    jd = ud + 2440587.5
    return (jd + _delta_t(1970 + ud / 365.2425) / 86400.0 - 2451545.0) / 36525.0


def _nutation_lon(T):
    return -0.00478 * math.sin(math.radians(125.04 - 1934.136 * T))


def sun_longitude(ud):
    """Apparent tropical longitude of the Sun in degrees (Meeus 25)."""
    T = _T(ud)
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M) + 0.000289 * math.sin(3 * M))
    return (L0 + C - 0.00569 + _nutation_lon(T)) % 360.0


# Meeus table 47.A: (D, M, M', F, coefficient in 1e-6 degree) for longitude
_MOON_TERMS = [
    (0, 0, 1, 0, 6288774), (2, 0, -1, 0, 1274027), (2, 0, 0, 0, 658314),
    (0, 0, 2, 0, 213618), (0, 1, 0, 0, -185116), (0, 0, 0, 2, -114332),
    (2, 0, -2, 0, 58793), (2, -1, -1, 0, 57066), (2, 0, 1, 0, 53322),
    (2, -1, 0, 0, 45758), (0, 1, -1, 0, -40923), (1, 0, 0, 0, -34720),
    (0, 1, 1, 0, -30383), (2, 0, 0, -2, 15327), (0, 0, 1, 2, -12528),
    (0, 0, 1, -2, 10980), (4, 0, -1, 0, 10675), (0, 0, 3, 0, 10034),
    (4, 0, -2, 0, 8548), (2, 1, -1, 0, -7888), (2, 1, 0, 0, -6766),
    (1, 0, -1, 0, -5163), (1, 1, 0, 0, 4987), (2, -1, 1, 0, 4036),
    (2, 0, 2, 0, 3994), (4, 0, 0, 0, 3861), (2, 0, -3, 0, 3665),
    (0, 1, -2, 0, -2689), (2, 0, -1, 2, -2602), (2, -1, -2, 0, 2390),
    (1, 0, 1, 0, -2348), (2, -2, 0, 0, 2236), (0, 1, 2, 0, -2120),
    (0, 2, 0, 0, -2069), (2, -2, -1, 0, 2048), (2, 0, 1, -2, -1773),
    (2, 0, 0, 2, -1595), (4, -1, -1, 0, 1215), (0, 0, 2, 2, -1110),
    (3, 0, -1, 0, -892), (2, 1, 1, 0, -810), (4, -1, -2, 0, 759),
    (0, 2, -1, 0, -713), (2, 2, -1, 0, -700), (2, 1, -2, 0, 691),
    (2, -1, 0, -2, 596), (4, 0, 1, 0, 549), (0, 0, 4, 0, 537),
    (4, -1, 0, 0, 520), (1, 0, -2, 0, -487), (2, 1, 0, -2, -399),
    (0, 0, 2, -2, -381), (1, 1, 1, 0, 351), (3, 0, -2, 0, -340),
    (4, 0, -3, 0, 330), (2, -1, 2, 0, 327), (0, 2, 1, 0, -323),
    (1, 1, -1, 0, 299), (2, 0, 3, 0, 294),
]


def moon_longitude(ud):
    """Apparent tropical longitude of the Moon in degrees (Meeus 47)."""
    T = _T(ud)
    Lp = 218.3164477 + 481267.88123421 * T - 0.0015786 * T * T + T ** 3 / 538841.0
    D = 297.8501921 + 445267.1114034 * T - 0.0018819 * T * T + T ** 3 / 545868.0
    M = 357.5291092 + 35999.0502909 * T - 0.0001536 * T * T
    Mp = 134.9633964 + 477198.8675055 * T + 0.0087414 * T * T + T ** 3 / 69699.0
    F = 93.2720950 + 483202.0175233 * T - 0.0036539 * T * T
    E = 1 - 0.002516 * T - 0.0000074 * T * T
    total = 0.0
    for d, mm, mp, f, coef in _MOON_TERMS:
        arg = math.radians(d * D + mm * M + mp * Mp + f * F)
        total += coef * (E ** abs(mm)) * math.sin(arg)
    A1 = math.radians(119.75 + 131.849 * T)
    A2 = math.radians(53.09 + 479264.290 * T)
    total += 3958 * math.sin(A1) + 1962 * math.sin(math.radians(Lp - F)) + 318 * math.sin(A2)
    return (Lp + total / 1e6 + _nutation_lon(T)) % 360.0


def lahiri_ayanamsa(ud):
    T = _T(ud)
    return 23.857092 + (5028.796195 * T + 1.1054348 * T * T) / 3600.0


def elongation(ud):
    return (moon_longitude(ud) - sun_longitude(ud)) % 360.0


def sidereal_sun(ud):
    return (sun_longitude(ud) - lahiri_ayanamsa(ud)) % 360.0


def _solve(f, target, ud, rate):
    """Moment near ud where angle f reaches target (degrees, mod 360)."""
    for _ in range(50):
        diff = (target - f(ud) + 180.0) % 360.0 - 180.0
        ud += diff / rate
        if abs(diff) < 1e-7:
            break
    return ud


def new_moon_before(ud):
    t = _solve(elongation, 0.0, ud - elongation(ud) / 12.19, 12.19)
    return t if t <= ud else _solve(elongation, 0.0, t - SYNODIC, 12.19)


def new_moon_after(ud):
    return new_moon_before(new_moon_before(ud) + SYNODIC + 2)


def sunrise(year, month, day, loc):
    """Sunrise (unix days, UT) on a local civil date at loc = (lat, lon, tz)."""
    lat, lon, tz = loc
    t = days_from_civil(year, month, day) + 0.25 - tz / 24.0
    phi = math.radians(lat)
    for _ in range(5):
        T = _T(t)
        lam = math.radians(sun_longitude(t))
        eps = math.radians(23.4392911 - 0.0130042 * T + 0.00256 * math.cos(math.radians(
            125.04 - 1934.136 * T)))
        dec = math.asin(math.sin(eps) * math.sin(lam))
        ra = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360
        cos_h = ((math.sin(math.radians(-0.8333)) - math.sin(phi) * math.sin(dec))
                 / (math.cos(phi) * math.cos(dec)))
        h0 = math.degrees(math.acos(max(-1.0, min(1.0, cos_h))))
        gmst = (280.46061837 + 360.98564736629 * (t + 2440587.5 - 2451545.0)) % 360
        ha = (gmst + lon - ra + 180) % 360 - 180          # current hour angle
        delta = ((-h0 - ha) + 180) % 360 - 180            # to reach -h0
        t += delta / 360.98564736629
        if abs(delta) < 1e-4:
            break
    return t


def _local_date(ud, tz):
    a, m, d = civil_from_days(int(math.floor(ud + tz / 24.0)))
    return a, m, d


def tithi_at(ud):
    return int(elongation(ud) // 12) + 1


def _rashi(ud):
    return int(sidereal_sun(ud) // 30)  # 0 = Mesha ... 11 = Meena


def lunar_months(ud_from, count):
    """Amanta months from the new moon before ud_from:
    [(start, end, masa 1-12, adhika)]."""
    out, nm = [], new_moon_before(ud_from)
    for _ in range(count):
        nxt = new_moon_after(nm + 1)
        r1, r2 = _rashi(nm), _rashi(nxt)
        out.append((nm, nxt, (r1 + 1) % 12 + 1, r1 == r2))
        nm = nxt
    return out


PANCHANG_RE = re.compile(
    r"^\s*(?:(amanta|purnimanta)\s+)?(vs|v\.s\.|vikram(?:a)?(?:\s+samvat)?|samvat|"
    r"shaka|saka|śaka|se|s\.e\.)\s*(\d{1,4})\s*(.*)$", re.I)


def _parse_panchang(text):
    year_start = None
    for word, start in (("kartikadi", "kartika"), ("chaitradi", "chaitra")):
        if re.search(r"\b%s\b" % word, text, re.I):
            year_start = start
            text = re.sub(r"\b%s\b" % word, " ", text, flags=re.I)
    m = PANCHANG_RE.match(text)
    if not m:
        raise ValueError("expected '[amanta|purnimanta] VS|Shaka YEAR [adhika] MASA "
                         "[shukla|krishna] [TITHI]', e.g. 'VS 2081 Chaitra shukla 9'")
    scheme = (m.group(1) or "").lower() or None
    era = m.group(2).lower()
    year = int(m.group(3))
    greg = year - 57 if era[0] in "vs" and not era.startswith(("sh", "sa", "śa", "se", "s.e")) \
        else year + 78
    words = [w for w in re.split(r"[\s,/-]+", m.group(4).lower()) if w]
    adhika = masa = paksha = tithi = None
    for w in words:
        if w in ("adhika", "adhik", "mala", "purushottam", "nija"):
            adhika = w != "nija"
        elif w in MASA_LOOKUP and masa is None:
            masa = MASA_LOOKUP[w]
        elif w in PAKSHA_LOOKUP and paksha is None and len(w) > 1:
            paksha = PAKSHA_LOOKUP[w]
        elif w in TITHI_LOOKUP:
            tithi = TITHI_LOOKUP[w]
        elif w.isdigit() and 1 <= int(w) <= 15:
            tithi = int(w)
        elif w in ("paksha", "paksh", "tithi", "masa", "month"):
            continue
        else:
            raise ValueError("unrecognised panchang word '%s'" % w)
    if tithi is not None and tithi <= 15 and paksha == 15:
        tithi += 15
    if tithi == 15 and paksha == 15:
        tithi = 30
    if tithi is not None and paksha is None and tithi not in (15, 30):
        raise ValueError("give the paksha (shukla or krishna) with the tithi")
    if tithi is not None and masa is None:
        raise ValueError("give the masa (month) with the tithi")
    return scheme, era, year, greg, bool(adhika), masa, paksha, tithi, year_start


def panchang_window(text, meta):
    """((lo, hi), label, (first_day, next_day)) for a panchang date."""
    cfg = meta.get("panchang") or {}
    scheme_t, era, year, greg, adhika, masa, paksha, tithi, ys = _parse_panchang(text)
    scheme = (scheme_t or cfg.get("scheme") or "amanta").lower()
    year_start = (ys or cfg.get("year_start") or "chaitra").lower()
    if year_start == "kartika":
        # Kartikadi years (Gujarat) begin at Kartika shukla 1 of the Chaitradi
        # year with the same number: Chaitra-Ashvina belong to the next one.
        if masa is None:
            raise ValueError("a whole Kartikadi year is not supported; give the masa")
        if masa <= 7:
            greg += 1
    loc_cfg = cfg.get("location", "delhi")
    if isinstance(loc_cfg, dict):
        loc = (float(loc_cfg["lat"]), float(loc_cfg["lon"]), float(loc_cfg.get("tz", 5.5)))
        loc_name = loc_cfg.get("name", "%.2f, %.2f" % loc[:2])
    else:
        if str(loc_cfg).lower() not in PANCHANG_LOCATIONS:
            raise ValueError("unknown panchang location '%s' (use one of %s, or "
                             "{lat, lon, tz})" % (loc_cfg, ", ".join(sorted(PANCHANG_LOCATIONS))))
        loc, loc_name = PANCHANG_LOCATIONS[str(loc_cfg).lower()], str(loc_cfg).title()
    if not 1 <= greg <= 2999:
        raise ValueError("panchang year out of the supported range")
    era_label = "VS" if era[0] in "vs" and not era.startswith(("sh", "sa", "śa", "se", "s.e")) \
        else "Shaka"
    # Purnimanta krishna paksha = krishna paksha of the previous amanta month.
    a_masa = masa
    if scheme == "purnimanta" and masa and paksha == 15:
        a_masa = masa - 1 if masa > 1 else 12
    months = lunar_months(days_from_civil(greg, 2, 1), 15)
    start = next((i for i, mo in enumerate(months) if mo[2] == 1 and not mo[3]), None)
    if start is None:
        raise ValueError("could not locate Chaitra of %s %d" % (era_label, year))
    year_months = months[start:]
    nxt = next((i for i, mo in enumerate(year_months[1:], 1) if mo[2] == 1 and not mo[3]),
               len(year_months))
    # The year number changes at Chaitra shukla 1, so purnimanta "VS Y Chaitra
    # krishna" is the amanta Phalguna krishna at the END of year Y.
    year_months = year_months[:nxt]
    label_bits = ["%s %d" % (era_label, year)]
    if masa is None:
        first_ud, end_ud = year_months[0][0], year_months[-1][1]
    else:
        pick = [mo for mo in year_months if mo[2] == a_masa and mo[3] == adhika]
        if not pick:
            raise ValueError("%s %d has no %s%s month" % (
                era_label, year, "adhika " if adhika else "", MASA_NAMES[a_masa - 1]))
        first_ud, end_ud = pick[0][0], pick[0][1]
        label_bits.append(("Adhika " if adhika else "") + MASA_NAMES[masa - 1])
        if paksha is not None and tithi is None:
            full = _solve(elongation, 180.0, first_ud + SYNODIC / 2, 12.19)
            first_ud, end_ud = (first_ud, full) if paksha == 0 else (full, end_ud)
            label_bits.append("Shukla" if paksha == 0 else "Krishna")
    if tithi is None:
        # Civil days whose sunrise falls inside [first_ud, end_ud).
        d0 = _local_date(first_ud, loc[2])
        if sunrise(*d0, loc) < first_ud:
            d0 = civil_from_days(days_from_civil(*d0) + 1)
        d1 = _local_date(end_ud, loc[2])
        if sunrise(*d1, loc) >= end_ud:
            d1 = civil_from_days(days_from_civil(*d1) - 1)
        first, nxt_day = days_from_civil(*d0), days_from_civil(*d1) + 1
        note_extra = ""
    else:
        hits, day = [], days_from_civil(*_local_date(first_ud, loc[2]))
        while day <= days_from_civil(*_local_date(end_ud, loc[2])):
            sr = sunrise(*civil_from_days(day), loc)
            # Only sunrises inside this lunar month count.
            if first_ud <= sr < end_ud and tithi_at(sr) == tithi:
                hits.append(day)
            day += 1
        note_extra = ""
        if not hits:  # kshaya tithi: it begins and ends between two sunrises
            ref = _solve(elongation, (tithi - 1) * 12.0, first_ud + (tithi - 1) * 0.98, 12.19)
            hits = [days_from_civil(*_local_date(ref, loc[2]))]
            note_extra = " (kshaya tithi: no sunrise falls in it)"
        else:
            ref = sunrise(*civil_from_days(hits[0]), loc)
            if len(hits) > 1:
                note_extra = " (vriddhi tithi: current at two sunrises)"
        # When the tithi actually ran: events recorded by the tithi current at
        # the moment (births, deaths, battles) can fall on the day it began.
        e_ref = elongation(ref)
        t_begin = _solve(elongation, (tithi - 1) * 12.0,
                         ref - ((e_ref - (tithi - 1) * 12.0) % 360.0) / 12.19, 12.19)
        t_end = _solve(elongation, (tithi * 12.0) % 360.0,
                       ref + ((tithi * 12.0 - e_ref) % 360.0) / 12.19, 12.19)
        first = min(hits[0], days_from_civil(*_local_date(t_begin, loc[2])))
        nxt_day = max(hits[-1], days_from_civil(*_local_date(t_end, loc[2]))) + 1

        def _clock(ud):
            a, mo, d = _local_date(ud, loc[2])
            mins = int(round(((ud + loc[2] / 24.0) % 1) * 1440)) % 1440
            return "%d %s %s %02d:%02d" % (d, MONTHS[mo - 1], a if a > 0 else "%d BCE" % (1 - a),
                                          mins // 60, mins % 60)
        sign = "+" if loc[2] >= 0 else "-"
        hh, mm = divmod(int(round(abs(loc[2]) * 60)), 60)
        span = "tithi ran %s to %s, UTC%s%d:%02d" % (_clock(t_begin), _clock(t_end), sign, hh, mm)
        sunrise_day = hits[0]
        t_name = ("Purnima" if tithi == 15 else "Amavasya" if tithi == 30
                  else TITHI_NAMES[(tithi - 1) % 15])
        pk = "Shukla" if tithi <= 15 else "Krishna"
        label_bits.append("%s %s (%s)%s" % (pk, (tithi - 1) % 15 + 1 if tithi not in (15, 30)
                                            else "", t_name, note_extra))
        label_bits.append("[at sunrise on %s; %s]" % (
            exact_label(from_seconds(sunrise_day * DAY, "day")), span))
    label = " ".join(label_bits).replace("  ", " ")
    if scheme == "purnimanta":
        label += " [purnimanta]"
    if year_start == "kartika":
        label += " [Kartikadi year]"
    note = ("Hindu panchang dates use the drik (astronomical) method with Lahiri "
            "ayanamsa and sunrise at %s, %s months; published panchangs can differ by "
            "a day, and festivals often follow other rules than the sunrise tithi"
            % (loc_name, scheme))
    # +/-1 day for published panchangs that differ.
    return _span(first - 1, nxt_day + 1), label, (first, nxt_day), note


# Japanese eras (Gregorian months and days since 1873) -----------------------

JAPANESE_ERAS = {"meiji": (1867, "Meiji"), "taisho": (1911, "Taishō"),
                 "showa": (1925, "Shōwa"), "heisei": (1988, "Heisei"),
                 "reiwa": (2018, "Reiwa"), "明治": (1867, "Meiji"),
                 "大正": (1911, "Taishō"), "昭和": (1925, "Shōwa"),
                 "平成": (1988, "Heisei"), "令和": (2018, "Reiwa"),
                 "m": (1867, "Meiji"), "t": (1911, "Taishō"), "s": (1925, "Shōwa"),
                 "h": (1988, "Heisei"), "r": (2018, "Reiwa")}
JAPANESE_RE = re.compile(r"^\s*([^\d\s-]+)\s*(\d{1,2}|元)\s*(?:年)?\s*(?:-(\d{1,2})(?:-(\d{1,2}))?)?\s*$")


def japanese_window(text):
    m = JAPANESE_RE.match(text)
    if not m:
        raise ValueError("expected ERA YEAR[-MONTH[-DAY]], e.g. 'Showa 20-08-15'")
    key = m.group(1).lower().replace("ō", "o").replace("ou", "o").strip()
    if key not in JAPANESE_ERAS:
        raise ValueError("unknown Japanese era '%s' (supported: Meiji 6 onward)"
                         % m.group(1))
    offset, name = JAPANESE_ERAS[key]
    ey = 1 if m.group(2) == "元" else int(m.group(2))
    y = offset + ey
    if y < 1873:
        raise ValueError("%s %d predates Japan's 1873 adoption of the Gregorian "
                         "calendar; convert the lunisolar date by hand" % (name, ey))
    mo, d = m.group(3), m.group(4)
    greg = "%d" % y + ("-%s" % mo if mo else "") + ("-%s" % d if d else "")
    lo, hi = period_bounds(parse_date(greg))
    label = "%s %d" % (name, ey) + ("-%s" % mo if mo else "") + ("-%s" % d if d else "")
    return (lo, hi), label


# Regnal and fiscal years (need configuration in the file's metadata) -------

def regnal_window(text, meta):
    """'Elizabeth II:3' → the third year of the reign (from accession day)."""
    name, _, n = text.rpartition(":")
    reigns = meta.get("reigns") or {}
    if not name or name.strip() not in reigns:
        raise ValueError("regnal date needs \"reigns\": {\"%s\": \"<accession date>\"} "
                         "in the file metadata" % (name.strip() or "?"))
    acc = parse_date(reigns[name.strip()])
    if acc.day is None:
        raise ValueError("the accession date of %s needs a day" % name.strip())
    n = int(n)
    return ((_add_months(acc, 12 * (n - 1)), _add_months(acc, 12 * n) - 1),
            "year %d of %s" % (n, name.strip()))


def _add_months(dp, n):
    """Start (in seconds) of the day n months after the day dp, clamping the
    day to the month's length (29 Feb + 1 year → 28 Feb)."""
    a, m0 = divmod(dp.astro * 12 + dp.month - 1 + n, 12)
    dim = (_month_start(a, m0 + 2) - _month_start(a, m0 + 1)) // DAY
    return days_from_civil(a, m0 + 1, min(dp.day, dim)) * DAY


FISCAL_RE = re.compile(r"^\s*(\d{4})(?:\s*-?\s*Q([1-4]))?\s*$", re.I)


def fiscal_window(text, meta):
    """'2024' or '2024-Q2' using meta "fiscal_year": {"start": "MM-DD",
    "label": "end" | "start"} (default: starts 01-01)."""
    m = FISCAL_RE.match(text)
    if not m:
        raise ValueError("expected FY like 2024 or 2024-Q2, got '%s'" % text)
    cfg = meta.get("fiscal_year") or {}
    sm, sd = [int(x) for x in str(cfg.get("start", "01-01")).split("-")]
    fy = int(m.group(1))
    # Calendar year in which this fiscal year starts.
    y0 = fy - 1 if (cfg.get("label", "end") == "end" and (sm, sd) != (1, 1)) else fy
    start = DateParts(y0, sm, sd)
    if m.group(2):
        q = int(m.group(2))
        a, b = 3 * (q - 1), 3 * q
        label = "FY%d Q%d" % (fy, q)
    else:
        a, b, label = 0, 12, "FY%d" % fy
    return (_add_months(start, a), _add_months(start, b) - 1), label


def fit_precision(lo, hi):
    """Finest Gregorian level whose single period contains [lo, hi]."""
    for lvl in ("second", "minute", "hour", "day", "month", "quarter", "year",
                "decade", "century", "millennium"):
        if bucket(from_seconds(lo, lvl), lvl)[0] == bucket(from_seconds(hi, lvl), lvl)[0]:
            return lvl
    return "millennium"


def convert_calendar(cal, text, meta):
    """Returns (lo, hi, label, gregorian_label, note) for a non-Gregorian date."""
    note = ""
    exact_days = None
    if cal == "julian":
        (lo, hi), label = julian_window(text)
    elif cal == "hijri":
        (lo, hi), label, exact_days = hijri_window(text)
        note = ("tabular Islamic calendar; observed dates can differ by 1-2 days, "
                "and the day begins at sunset")
    elif cal == "hebrew":
        (lo, hi), label, exact_days = hebrew_window(text)
        note = "the Hebrew day begins at sunset on the previous civil day"
    elif cal == "japanese":
        (lo, hi), label = japanese_window(text)
    elif cal == "regnal":
        (lo, hi), label = regnal_window(text, meta)
    elif cal == "fiscal":
        (lo, hi), label = fiscal_window(text, meta)
    elif cal == "panchang":
        (lo, hi), label, exact_days, note = panchang_window(text, meta)
    elif cal == "chinese":
        raise ValueError("the Chinese lunisolar calendar needs astronomical tables; "
                         "convert to Gregorian by hand and keep the original in details")
    else:
        raise ValueError("unknown calendar '%s'" % cal)
    g_lo, g_hi = (exact_days[0] * DAY, exact_days[1] * DAY - 1) if exact_days else (lo, hi)
    a = exact_label(from_seconds(g_lo, "day"))
    b = exact_label(from_seconds(g_hi, "day"))
    greg = a if a == b else "%s – %s" % (a, b)
    return lo, hi, label, greg, note, g_lo


def split_calendar(value, default=None):
    """('julian', '1616-03-05') from 'julian:1616-03-05', else (default, value)."""
    if isinstance(value, str):
        m = CALENDAR_RE.match(value)
        if m and m.group(1).lower() in CALENDAR_ALIASES:
            return CALENDAR_ALIASES[m.group(1).lower()], m.group(2)
    if default and isinstance(value, str):
        cal = CALENDAR_ALIASES.get(str(default).lower())
        if cal is None:
            raise ValueError("unknown calendar '%s'" % default)
        return cal, value
    return None, value


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

class Event(object):
    def __init__(self, raw, seq, doc="", meta=None):
        self.raw = raw
        self.seq = seq
        self.doc = doc
        self.meta = meta or {}
        self.errors = []
        self.calendar = raw.get("calendar")
        self.cal_start = self.cal_end = None  # (original label, Gregorian label)
        self.cal_notes = []
        self.told = raw.get("told")
        self.change = None  # "new" / "changed: <old date>" when diffing runs
        self.hedged = bool(raw.get("hedged"))
        self.certainty = str(raw.get("certainty") or raw.get("reliability") or "").lower()
        self.conf, self.conf_score, self.conf_why = "high", 100, []
        self.scope_note = ""  # set by --from/--to/--as-of/--before/--after
        self.quote = str(raw.get("quote") or "").strip()
        self.verify = None  # verified / approximate / not found (set by --verify)
        self.id = str(raw["id"]) if raw.get("id") is not None else None
        self.title = str(raw.get("title") or raw.get("event") or "").strip()
        self.details = str(raw.get("details") or raw.get("context") or "").strip()
        self.source = str(raw.get("source") or "").strip()
        self.approx = bool(raw.get("approximate"))
        self.derived = bool(raw.get("derived"))
        self.tags = list(raw.get("tags") or [])
        self.entities = list(raw.get("entities") or [])
        self.lifespan = raw.get("lifespan")
        self.after = _as_list(raw.get("after"))
        self.before = _as_list(raw.get("before"))
        self.offset = raw.get("offset")
        self.reason = str(raw.get("reason") or "").strip()
        self._cal_window = None
        self.start = self._date(raw.get("start", raw.get("date")), "start")
        cal_window, self._cal_window = self._cal_window, None
        self.end = self._date(raw.get("end"), "end")
        self.earliest = self._date(raw.get("earliest"), "earliest")
        self.latest = self._date(raw.get("latest"), "latest")
        self.not_before = self._date(raw.get("not_before"), "earliest")
        self.not_after = self._date(raw.get("not_after"), "latest")
        self.planned = self._date(raw.get("planned", raw.get("due")), "point")
        if cal_window:
            # A converted calendar date is a window of Gregorian days.
            if self.earliest is None:
                self.earliest = from_seconds(cal_window[0], "day")
            if self.latest is None:
                self.latest = from_seconds(cal_window[1], "day")
        override = raw.get("precision")
        if override and self.start is not None:
            p = norm_level(override)
            if RANK[p] < RANK[self.start.precision]:
                self.start.precision = p  # declared coarser than written
        if self.start is None and (self.earliest or self.latest):
            self.start = self.earliest or self.latest  # only a window is known
            self.approx = True
        # Merging and display state
        self.sources = [{"doc": doc, "loc": self.source, "event": self}]
        self.conflict = False
        self.order_uncertain = False
        self.show_doc = False
        self.lo = self.hi = None

    def _date(self, value, role="start"):
        """Parse a date field. role: start, end, earliest or latest."""
        try:
            cal, text = split_calendar(value, self.calendar)
            if cal is None or cal == "gregorian":
                return parse_date(text)
            lo, hi, label, greg, note, g_lo = convert_calendar(cal, text, self.meta)
        except ValueError as exc:
            self.errors.append(str(exc))
            return None
        if note and note not in self.cal_notes:
            self.cal_notes.append(note)
        if role == "earliest":
            return from_seconds(lo, "day")
        if role == "latest":
            return from_seconds(hi, "day")
        if role == "start":
            self.cal_start = (label, greg)
            self._cal_window = (lo, hi)
        elif role == "end":
            self.cal_end = (label, greg)
        # Day-level components keep the sort position; the precision is the
        # finest Gregorian period that holds the whole window.
        dp = from_seconds(g_lo, "day")
        dp.precision = fit_precision(lo, hi)
        return dp

    def compute_interval(self):
        """Earliest/latest possible instant of the start, and of the end."""
        lo, hi = period_bounds(self.start)
        if self.earliest is not None:
            lo = period_bounds(self.earliest)[0]
        if self.latest is not None:
            hi = period_bounds(self.latest)[1]
        if self.approx and self.earliest is None and self.latest is None:
            # "c." with no stated window: allow the neighbouring period on
            # each side (c. 1969 → 1968..1970).
            p = self.start.precision
            lo = period_bounds(from_seconds(lo - 1, p))[0]
            hi = period_bounds(from_seconds(hi + 1, p))[1]
        self.lo, self.hi = lo, hi
        if self.end is not None:
            self.end_lo, self.end_hi = period_bounds(self.end)
        else:
            self.end_lo, self.end_hi = lo, hi

    def has_window(self):
        return self.earliest is not None or self.latest is not None or self.approx

    def window_bounds(self):
        """Labels for the earliest and latest possible date."""
        p_lo = (self.earliest or self.start).precision
        p_hi = (self.latest or self.start).precision
        return (exact_label(from_seconds(self.lo, p_lo)),
                exact_label(from_seconds(self.hi, p_hi)))

    def window(self):
        return "between %s and %s" % self.window_bounds()

    def when(self, gran):
        """Display string for the event's date, honouring granularity."""
        def fmt(dp):
            lvl = gran if can_bucket(dp, gran) else dp.precision
            return bucket(dp, lvl)[1]
        if self.cal_start and not can_bucket(self.start, gran):
            return self.exact()  # e.g. "Ramadan 1445 AH (= 11 Mar 2024 – 9 Apr 2024)"
        s = fmt(self.start)
        if self.end is not None:
            e = fmt(self.end)
            if e != s:
                s = "%s – %s" % (s, e)
        if self.approx:
            s = "c. " + s
        return s

    def exact(self):
        def one(dp, cal):
            return "%s (= %s)" % cal if cal else exact_label(dp)
        s = one(self.start, self.cal_start)
        if self.end is not None:
            s += " – " + one(self.end, self.cal_end)
        if self.approx:
            s = "c. " + s
        if self.lo is not None and self.has_window() and not self.cal_start:
            s += ", " + self.window()
        return s

    def headline(self, marks=True):
        t = self.title
        if marks and self.conflict:
            t = "⚠ " + t
        if marks and self.order_uncertain:
            t = "≈ " + t
        if self.derived:
            t += " [derived date]"
        if marks and self.change:
            t += " [%s]" % self.change
        if marks and self.conf == "low":
            t += " [low confidence]"
        if marks and self.verify == "not found":
            t += " [quote not found in source]"
        if marks and self.scope_note:
            t += " [%s]" % self.scope_note
        return t

    def doc_count(self):
        return len({s["doc"] for s in self.sources})

    def source_text(self):
        locs = []
        for s in self.sources:
            loc = s["loc"]
            if self.show_doc and s["doc"]:
                loc = "%s · %s" % (loc, s["doc"]) if loc else s["doc"]
            if loc and loc not in locs:
                locs.append(loc)
        text = "; ".join(locs)
        n = self.doc_count()
        if n > 1:
            text = "%d sources: %s" % (n, text)
        return text

    def sort_key(self):
        return (self.start.sort_key(), RANK[self.start.precision], self.seq)


def _as_list(v):
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]


# --------------------------------------------------------------------------
# Tables: CSV / TSV / SQLite rows as events
# --------------------------------------------------------------------------
# Each row becomes an event. The date column is found from column names and
# from how many values parse as dates; numeric columns count as dates only
# when their name says so (epoch seconds/ms, Excel serials, plain years).

TABLE_EXTS = (".csv", ".tsv", ".db", ".sqlite", ".sqlite3")
DATE_HINT = re.compile(r"(date|time|timestamp|^ts$|_ts$|_at$|_on$|^at$|created|updated|"
                       r"modified|when|^day$|^year$|period|start|end|begin|finish|due)", re.I)
TITLE_HINT = re.compile(r"^(title|name|event|subject|summary|headline|message|msg|"
                        r"description|desc|text|what)$", re.I)
WEAK_TITLE_HINT = re.compile(r"^(action|activity|status|type|kind|category)$", re.I)
ID_HINT = re.compile(r"^(id|_id|rowid|pk|key|uuid|guid|ref|reference)$|_id$|^id_", re.I)
MONTH_NAMES = {}
for _i, _m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                         "august", "september", "october", "november", "december"]):
    MONTH_NAMES[_m] = MONTH_NAMES[_m[:3]] = _i + 1
MONTH_NAMES["sept"] = 9
_TIME = r"(?:[ T,]+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*([ap]\.?m\.?)?)?"
NUMERIC_DATE_RE = re.compile(r"^(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})" + _TIME + "$", re.I)
DMY_NAME_RE = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+(\d{1,4})" + _TIME + "$", re.I)
MDY_NAME_RE = re.compile(r"^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{1,4})" + _TIME + "$", re.I)
MY_NAME_RE = re.compile(r"^([a-z]+)\.?,?\s+(\d{3,4})$", re.I)


def _iso(y, mo=None, d=None, h=None, mi=None, sec=None, ampm=None):
    if h is not None and ampm:
        h = h % 12 + (12 if ampm.lower().startswith("p") else 0)
    out = ("%04d" % y) if y > 0 else str(y)
    if mo:
        out += "-%02d" % mo
    if d:
        out += "-%02d" % d
    if h is not None:
        out += "T%02d:%02d" % (h, mi or 0)
        if sec is not None:
            out += ":%02d" % sec
    parse_date(out)  # validates the ranges
    return out


def _year4(y, flags):
    if len(y) == 2:
        flags.add("two-digit years")
        n = int(y)
        return 2000 + n if n < 50 else 1900 + n
    return int(y)


def cell_to_date(text, order="dmy", flags=None):
    """ISO string for one text cell, or None. order: 'dmy' or 'mdy'."""
    flags = set() if flags is None else flags
    s = str(text).strip()
    if not s:
        return None
    try:
        parse_date(s)
        return s
    except ValueError:
        pass
    try:
        m = NUMERIC_DATE_RE.match(s)
        if m:
            a, b, c = m.group(1), m.group(2), m.group(3)
            if len(a) == 4:
                y, mo, d = int(a), int(b), int(c)
            elif order == "mdy":
                mo, d, y = int(a), int(b), _year4(c, flags)
            else:
                d, mo, y = int(a), int(b), _year4(c, flags)
            t = [int(x) if x else None for x in m.group(4, 5, 6)]
            return _iso(y, mo, d, t[0], t[1], t[2], m.group(7))
        m = DMY_NAME_RE.match(s)
        if m and m.group(2).lower() in MONTH_NAMES:
            t = [int(x) if x else None for x in m.group(4, 5, 6)]
            return _iso(_year4(m.group(3), flags), MONTH_NAMES[m.group(2).lower()],
                        int(m.group(1)), t[0], t[1], t[2], m.group(7))
        m = MDY_NAME_RE.match(s)
        if m and m.group(1).lower() in MONTH_NAMES:
            t = [int(x) if x else None for x in m.group(4, 5, 6)]
            return _iso(_year4(m.group(3), flags), MONTH_NAMES[m.group(1).lower()],
                        int(m.group(2)), t[0], t[1], t[2], m.group(7))
        m = MY_NAME_RE.match(s)
        if m and m.group(1).lower() in MONTH_NAMES:
            return _iso(int(m.group(2)), MONTH_NAMES[m.group(1).lower()])
    except ValueError:
        return None
    return None


def _numeric_kind(vals):
    try:
        f = [float(v) for v in vals]
    except ValueError:
        return None
    if all(x == int(x) and 1000 <= x <= 2100 for x in f):
        return "year"
    if all(1e11 <= x < 1e13 for x in f):
        return "epoch_ms"
    if all(1e8 <= x < 1e10 for x in f):
        return "epoch_s"
    if all(1 <= x < 1e6 for x in f):
        return "excel"
    return None


def numeric_to_date(v, kind):
    x = float(v)
    if kind == "year":
        return "%04d" % int(x)
    if kind == "excel":  # days since 1899-12-30, fraction = time of day
        sec = (days_from_civil(1899, 12, 30) + int(x)) * DAY + int(round((x % 1) * DAY))
        return _iso_from_seconds(sec, "second" if x % 1 else "day")
    sec = int(x // 1000) if kind == "epoch_ms" else int(x)
    return _iso_from_seconds(sec, "second") + "Z"


def _iso_from_seconds(sec, precision):
    dp = from_seconds(sec, precision)
    return _iso(dp.year, dp.month, dp.day, dp.hour, dp.minute, dp.second)


def analyse_columns(header, rows, order_pref=None):
    """Per column: kind, share of values readable as dates, name hint, order."""
    out = {}
    sample = rows[:2000]
    for ci, name in enumerate(header):
        vals = [str(r[ci]).strip() for r in sample
                if ci < len(r) and r[ci] is not None and str(r[ci]).strip()]
        if not vals:
            continue
        hint = bool(DATE_HINT.search(str(name)))
        if all(re.match(r"^-?\d+(\.\d+)?$", v) for v in vals):
            kind = _numeric_kind(vals) if hint else None
            if kind:
                out[name] = {"kind": kind, "rate": 1.0, "hint": hint, "order": None,
                             "ambiguous": False}
            continue
        first = second = False
        for v in vals:
            m = NUMERIC_DATE_RE.match(v)
            if m and len(m.group(1)) <= 2:
                first = first or int(m.group(1)) > 12
                second = second or int(m.group(2)) > 12
        if first and not second:
            order = "dmy"
        elif second and not first:
            order = "mdy"
        else:
            order = order_pref or "dmy"
        overridden = bool(order_pref) and order != order_pref
        ambiguous = not first and not second and any(
            NUMERIC_DATE_RE.match(v) and len(NUMERIC_DATE_RE.match(v).group(1)) <= 2
            for v in vals) and not order_pref
        rate = sum(1 for v in vals if cell_to_date(v, order)) / float(len(vals))
        if rate >= 0.8:
            out[name] = {"kind": "text", "rate": rate, "hint": hint, "order": order,
                         "ambiguous": ambiguous, "overridden": overridden}
    return out


def _read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(65536)
        fh.seek(0)
        if path.lower().endswith(".tsv"):
            dialect = csv.excel_tab
        else:
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
        rows = [r for r in csv.reader(fh, dialect) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("%s is empty" % path)
    return rows[0], rows[1:]


def _read_sqlite(path, opts):
    import os
    import sqlite3
    from urllib.request import pathname2url
    con = sqlite3.connect("file:%s?mode=ro" % pathname2url(os.path.abspath(path)), uri=True)
    try:
        if opts.get("sql"):
            try:
                cur = con.execute(opts["sql"])
            except sqlite3.Error as exc:
                raise ValueError("SQL error in --sql (the database is opened read-only): "
                                 "%s" % exc)
            if cur.description is None:
                raise ValueError("--sql must be a query that returns rows (SELECT …)")
        else:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            t = opts.get("table") or (tables[0] if len(tables) == 1 else None)
            if t is None or t not in tables:
                raise ValueError("%s has tables %s: choose one with --table, or give --sql"
                                 % (path, ", ".join(tables) or "(none)"))
            cur = con.execute('SELECT * FROM "%s"' % t.replace('"', '""'))
        header = [d[0] for d in cur.description]
        rows = [list(r) for r in cur.fetchall()]
    finally:
        con.close()
    return header, rows


def _most_varied_text(header, rows, exclude):
    """The non-numeric text column with the most distinct values (a good title)."""
    best, best_n = None, 0
    for ci, c in enumerate(header):
        if c in exclude:
            continue
        vals = [str(r[ci]).strip() for r in rows[:500]
                if ci < len(r) and r[ci] not in (None, "") and str(r[ci]).strip()]
        if not vals or sum(bool(re.match(r"^-?[\d.,]+$", v)) for v in vals) > len(vals) / 2:
            continue
        n = len(set(vals))
        if n > best_n:
            best, best_n = c, n
    return best


def load_table(path, opts):
    """(file_meta, raw events, notes) for a CSV/TSV/SQLite source."""
    if path.lower().endswith((".csv", ".tsv")):
        header, rows = _read_csv(path)
    else:
        header, rows = _read_sqlite(path, opts)
    header = [str(h).strip() for h in header]
    order_pref = opts.get("order")
    cols = analyse_columns(header, rows, order_pref)
    notes = []

    def pick(flag, candidates):
        if opts.get(flag):
            if opts[flag] not in header:
                raise ValueError("no column '%s' in %s (columns: %s)"
                                 % (opts[flag], path, ", ".join(header)))
            return opts[flag]
        return candidates[0] if candidates else None

    ranked = sorted(cols, key=lambda c: (-cols[c]["hint"], -cols[c]["rate"],
                                         cols[c]["kind"] != "text", header.index(c)))
    date_col = pick("date_col", ranked)
    if date_col is None:
        raise ValueError("no date column found in %s; name one with --date-col "
                         "(columns: %s)" % (path, ", ".join(header)))
    if date_col not in cols:  # named explicitly but not detected: analyse leniently
        cols[date_col] = {"kind": "text", "rate": 0, "hint": True,
                          "order": order_pref or "dmy", "ambiguous": False}
    others = [c for c in ranked if c != date_col]
    notes.append("dates from column '%s'%s" % (
        date_col, " (other date-like columns: %s)" % ", ".join(others) if others else ""))
    info = cols[date_col]
    if info.get("overridden"):
        notes.append("the requested %s order was not used: values in '%s' can only be "
                     "read %s" % ("month-first" if order_pref == "mdy" else "day-first",
                                  date_col, "day-first" if info["order"] == "dmy"
                                  else "month-first"))
    if info["ambiguous"]:
        notes.append("dates like 03/04/2024 in '%s' are ambiguous; read as %s "
                     "(use --monthfirst or --dayfirst to choose)"
                     % (date_col, "day-first" if info["order"] == "dmy" else "month-first"))
    end_col = opts.get("end_col")
    id_col = next((c for c in header if ID_HINT.search(c)), None)
    title_col = opts.get("title_col") or next(
        (c for c in header if TITLE_HINT.match(c)), None) or _most_varied_text(
        header, rows, exclude=set(cols) | {id_col, opts.get("entity_col"), opts.get("tag_col")}
        | {c for c in header if WEAK_TITLE_HINT.match(c)}) or next(
        (c for c in header if WEAK_TITLE_HINT.match(c)), None)
    multi = lambda v: [x.strip() for x in re.split(r"[;,|]", str(v or "")) if x.strip()]  # noqa: E731
    skip = {date_col, end_col, title_col, id_col, opts.get("entity_col"), opts.get("tag_col")}
    flags, unreadable, records = set(), 0, []

    def to_date(v, inf):
        if v is None or str(v).strip() == "":
            return None
        if inf["kind"] == "text":
            return cell_to_date(v, inf["order"], flags)
        try:
            return numeric_to_date(v, inf["kind"])
        except (ValueError, OverflowError):
            return None

    end_info = cols.get(end_col) or {"kind": "text", "order": info["order"]}
    for n, r in enumerate(rows, 1):
        row = dict(zip(header, r))
        date = to_date(row.get(date_col), info)
        if date is None and str(row.get(date_col) or "").strip():
            unreadable += 1
        rec = {"date": date, "_row": n,
               "title": str(row.get(title_col) or "").strip() if title_col else "",
               "source": ("%s=%s" % (id_col, row[id_col])) if id_col and row.get(id_col)
               not in (None, "") else "row %d" % n}
        if not rec["title"]:
            rec["title"] = "row %d" % n
        if end_col:
            rec["end"] = to_date(row.get(end_col), end_info)
        if opts.get("entity_col"):
            rec["entities"] = multi(row.get(opts["entity_col"]))
        if opts.get("tag_col"):
            rec["tags"] = multi(row.get(opts["tag_col"]))
        det = "; ".join("%s: %s" % (c, row[c]) for c in header
                        if c not in skip and row.get(c) not in (None, ""))
        rec["details"] = det[:300] + ("…" if len(det) > 300 else "")
        records.append(rec)
    if unreadable:
        notes.append("%d row(s) have a value in '%s' that is not a readable date; "
                     "they are listed as undated" % (unreadable, date_col))
    if "two-digit years" in flags:
        notes.append("two-digit years were read as 1950-2049")
    if title_col:
        notes.append("event titles from column '%s'" % title_col)
    name = re.split(r"[\\/]", path)[-1]
    meta = {"source_document": name + ("" if not opts.get("table") else ":" + opts["table"])}
    return meta, records, notes


def load_events(paths, table_opts=None):
    """Load event files (JSON) or tables (CSV/TSV/SQLite).
    Returns (meta, events, errors); table notes go to meta["table_notes"]."""
    meta, events, errors = {}, [], []
    for path in paths:
        if path.lower().endswith(TABLE_EXTS):
            file_meta, data, notes = load_table(path, table_opts or {})
            meta.setdefault("table_notes", []).extend(
                "%s: %s" % (file_meta["source_document"], n) for n in notes)
        else:
            with (sys.stdin if path == "-" else io.open(path, encoding="utf-8")) as fh:
                data = json.load(fh)
            file_meta = {}
            if isinstance(data, dict):
                file_meta = {k: v for k, v in data.items() if k != "events"}
                data = data.get("events", [])
        for k, v in file_meta.items():
            meta.setdefault(k, v)
        doc = str(file_meta.get("source_document") or
                  ("stdin" if path == "-" else re.split(r"[\\/]", path)[-1]))
        meta.setdefault("files", []).append({
            "doc": doc, "path": path,
            "extracted_through": file_meta.get("extracted_through")})
        ev_meta = dict(meta, **file_meta)
        for raw in data:
            ev = Event(raw, len(events), doc, ev_meta)
            for e in ev.errors:
                errors.append("event '%s' (%s): %s" % (ev.title or "?", doc, e))
            events.append(ev)
    return meta, events, errors


# --------------------------------------------------------------------------
# Merging several sources
# --------------------------------------------------------------------------

def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _overlaps(a, b):
    return a.lo <= b.hi and b.lo <= a.hi


def merge_events(events, auto=False):
    """Merge events that describe the same happening.

    Events sharing an `id` (across or within files) are the same event.
    With auto=True, events without an id that share a normalised title are
    merged too. The merged event keeps every source; if the sources give
    dates that cannot both be true, it is flagged as a conflict.
    """
    groups, order = {}, []
    for ev in events:
        if ev.id is not None:
            key = ("id", ev.id)
        elif auto and ev.title:
            key = ("title", _norm_title(ev.title))
        else:
            key = ("seq", ev.seq)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(ev)

    merged = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged.append(group[0])
            continue
        dated = [e for e in group if e.start is not None]
        if dated:
            # The representative is the date most other sources agree with,
            # then the most precise one, then the first one seen.
            def score(e):
                agree = sum(1 for o in dated if _overlaps(e, o))
                return (-agree, -RANK[e.start.precision], e.seq)
            rep = min(dated, key=score)
            agreeing = [e for e in dated if _overlaps(e, rep)]
            lo = max(e.lo for e in agreeing)
            hi = min(e.hi for e in agreeing)
            if lo <= hi:  # corroborating sources narrow the window
                rep.lo, rep.hi = lo, hi
            rep.conflict = len(agreeing) < len(dated)
        else:
            rep = group[0]
        rep.sources = [s for e in group for s in e.sources]
        rep.variants = group
        if not rep.details:
            rep.details = next((e.details for e in group if e.details), "")
        for e in group:
            for t in e.tags:
                if t not in rep.tags:
                    rep.tags.append(t)
            for x in e.entities:
                if x not in rep.entities:
                    rep.entities.append(x)
            rep.after += [x for x in e.after if x not in rep.after]
            rep.before += [x for x in e.before if x not in rep.before]
            rep.lifespan = rep.lifespan or e.lifespan
            rep.offset = rep.offset or e.offset
            rep.not_before = rep.not_before or e.not_before
            rep.not_after = rep.not_after or e.not_after
            rep.reason = rep.reason or e.reason
        merged.append(rep)
    return merged


def collapse_events(events, gran):
    """Fold repeats (same source, title, tags and entities in the same period
    at `gran`) into one event with a count, e.g. log lines or table rows."""
    out, groups = [], {}
    for e in events:
        if e.start is None:
            out.append(e)
            continue
        key = (e.doc, e.title.lower(), tuple(map(str, e.tags)),
               tuple(map(str, e.entities)), group_of(e, gran)[0])
        if key in groups:
            groups[key].append(e)
        else:
            groups[key] = [e]
            out.append(e)
    for g in groups.values():
        if len(g) < 2:
            continue
        rep_ = g[0]
        first = min(g, key=Event.sort_key)
        last = max(g, key=lambda e: (e.hi, e.seq))
        note = "%d occurrences; first %s, last %s" % (len(g), first.exact(), last.exact())
        rep_.start, rep_.earliest = first.start, first.earliest
        rep_.end = last.start if last is not first and last.lo > first.hi else None
        rep_.latest = None
        rep_.approx = any(e.approx for e in g)
        rep_.title = "%s (×%d)" % (rep_.title, len(g))
        rep_.details = note + ("; e.g. " + first.details if first.details else "")
        locs = [s["loc"] for e in (first, last) for s in e.sources if s["loc"]]
        rep_.sources = [{"doc": rep_.doc, "loc": " … ".join(dict.fromkeys(locs)),
                         "event": first}]
        rep_.collapsed = len(g)
        rep_.compute_interval()
    return out


# --------------------------------------------------------------------------
# Relative dates ("3 days after X")
# --------------------------------------------------------------------------

def _offset_spec(ev):
    """(ref id, n, unit, anchor) from ev.offset, or None."""
    o = ev.offset
    if not o:
        return None
    if isinstance(o, str):
        raise ValueError("offset must be an object like "
                         '{"from": "id", "by": "3d", "anchor": "start"}')
    n, unit = parse_offset(o.get("by", ""))
    return str(o.get("from")), n, unit, (o.get("anchor") or "start").lower()


def _anchor(ref, anchor):
    return ref.end if anchor == "end" and ref.end is not None else ref.start


def derive_offsets(events, by_id, issues):
    """Fill in undated events whose date is given relative to another event."""
    pending = [e for e in events if e.start is None and e.offset]
    for _ in range(len(pending) + 1):
        progress = False
        for ev in pending:
            if ev.start is not None:
                continue
            try:
                ref_id, n, unit, anchor = _offset_spec(ev)
            except ValueError as exc:
                issues.append(("WARNING", "offset", "'%s': %s" % (ev.title, exc), (ev,)))
                ev.offset = None
                continue
            ref = by_id.get(ref_id)
            if ref is None or ref.start is None:
                continue
            ev.start = shift(_anchor(ref, anchor), n, unit)
            ev.approx = ev.approx or ref.approx
            ev.derived = True
            note = "date derived: %s from '%s'" % (offset_text(n, unit), ref.title)
            ev.details = "%s (%s)" % (ev.details, note) if ev.details else note
            ev.compute_interval()
            progress = True
        if not progress:
            break


# --------------------------------------------------------------------------
# Consistency checks
# --------------------------------------------------------------------------

SEVERITY = {"ERROR": 0, "WARNING": 1, "INFO": 2}


def _lbl(ev):
    return "'%s' (%s)" % (ev.title, ev.exact())


def _slip(least, most):
    """'6 days', 'up to 1 month' or '13 days to 1.1 months'."""
    a, b = human_duration(least), human_duration(most)
    if a == b:
        return a
    if least < DAY:
        return "up to %s" % b
    return "%s to %s" % (a, b)


def check_events(events, by_id):
    """Find places where the timeline contradicts itself.

    Returns (severity, kind, message, involved_events) tuples.
    """
    issues = []

    def add(sev, kind, msg, *evs):
        issues.append((sev, kind, msg, evs))

    def ref(ev, rid, what):
        r = by_id.get(rid)
        if r is None:
            add("WARNING", "reference",
                "%s refers to unknown id '%s' in %s" % (_lbl(ev), rid, what), ev)
        elif r.start is None:
            add("INFO", "reference",
                "%s: cannot check %s '%s', which is undated" % (_lbl(ev), what, rid), ev)
            return None
        return r

    for ev in events:
        if ev.start is None:
            continue
        # A range that ends before it starts.
        if ev.end is not None and ev.end_hi < ev.lo:
            add("ERROR", "range", "%s ends before it starts" % _lbl(ev), ev)
        # Sources disagree on the date.
        if ev.conflict:
            parts = ["%s: %s" % (" · ".join(x for x in (s["loc"], s["doc"]) if x)
                                 or "?", s["event"].exact())
                     for s in ev.sources if s["event"].start is not None]
            add("WARNING", "conflict", "'%s' - sources disagree: %s"
                % (ev.title, "; ".join(parts)), ev)
        # Stated ordering against other events.
        for rid in ev.after:
            r = ref(ev, rid, "after")
            if r is not None and ev.hi < r.lo:
                add("ERROR", "order", "%s should be after %s but is entirely "
                    "before it" % (_lbl(ev), _lbl(r)), ev, r)
        for rid in ev.before:
            r = ref(ev, rid, "before")
            if r is not None and ev.lo > r.hi:
                add("ERROR", "order", "%s should be before %s but is entirely "
                    "after it" % (_lbl(ev), _lbl(r)), ev, r)
        # A stated offset ("3 days after X") that doesn't match the stated date.
        if ev.offset and not ev.derived:
            try:
                spec = _offset_spec(ev)
            except ValueError as exc:
                add("WARNING", "offset", "'%s': %s" % (ev.title, exc), ev)
                spec = None
            if spec:
                rid, n, unit, anchor = spec
                r = ref(ev, rid, "offset")
                if r is not None:
                    expected = shift(_anchor(r, anchor), n, unit)
                    lo, hi = period_bounds(expected)
                    if unit in ("hour", "minute", "second"):
                        # "5 minutes later" is said loosely: allow one unit.
                        lo, hi = lo - UNIT_SECONDS[unit], hi + UNIT_SECONDS[unit]
                    if hi < ev.lo or lo > ev.hi:
                        add("ERROR", "offset", "%s is stated, but %s from %s gives %s"
                            % (_lbl(ev), offset_text(n, unit), _lbl(r),
                               exact_label(expected)), ev, r)
        # Planned (or due) date against what actually happened.
        if ev.planned is not None:
            p_lo, p_hi = period_bounds(ev.planned)
            # Same precision on both sides: compare like with like (7 days,
            # not "6 to 8 days" from the edges of the two days).
            same = (ev.planned.precision == ev.start.precision and not ev.has_window())
            diff = human_duration(abs(period_bounds(ev.start)[0] - p_lo))
            if ev.lo > p_hi:
                add("WARNING", "schedule", "%s happened after its planned date (%s): "
                    "late by %s" % (_lbl(ev), exact_label(ev.planned),
                                    diff if same else _slip(ev.lo - p_hi, ev.hi - p_lo)), ev)
            elif ev.hi < p_lo:
                add("INFO", "schedule", "%s happened before its planned date (%s): "
                    "early by %s" % (_lbl(ev), exact_label(ev.planned),
                                     diff if same else _slip(p_lo - ev.hi, p_hi - ev.lo)), ev)
        # Anachronism bounds supplied during extraction.
        why = ": " + ev.reason if ev.reason else ""
        if ev.not_before is not None and ev.hi < period_bounds(ev.not_before)[0]:
            add("ERROR", "anachronism", "%s is before %s, the earliest it could "
                "be%s" % (_lbl(ev), exact_label(ev.not_before), why), ev)
        if ev.not_after is not None and ev.lo > period_bounds(ev.not_after)[1]:
            add("ERROR", "anachronism", "%s is after %s, the latest it could "
                "be%s" % (_lbl(ev), exact_label(ev.not_after), why), ev)

    # Lifespans: nothing involving an entity before it begins or after it ends.
    life = {}
    for ev in events:
        if ev.start is not None and isinstance(ev.lifespan, dict):
            ent = str(ev.lifespan.get("entity"))
            boundary = str(ev.lifespan.get("boundary", "")).lower()
            if boundary in ("start", "end"):
                life.setdefault(ent, {})[boundary] = ev
    for ent, b in life.items():
        s, e = b.get("start"), b.get("end")
        if s and e and e.end_hi < s.lo:
            add("ERROR", "lifespan", "%s ends (%s) before it begins (%s)"
                % (ent, e.exact(), s.exact()), s, e)
        for ev in events:
            if ev.start is None or ent not in ev.entities or ev in (s, e):
                continue
            if s and ev.hi < s.lo:
                add("ERROR", "lifespan", "%s involves %s before %s"
                    % (_lbl(ev), ent, _lbl(s)), ev, s)
            if e and ev.lo > e.end_hi:
                add("WARNING", "lifespan", "%s involves %s after %s (posthumous "
                    "or legacy?)" % (_lbl(ev), ent, _lbl(e)), ev, e)
    return issues


def mark_uncertain_order(events):
    """Flag events that could have happened before the one listed above."""
    for prev, ev in zip(events, events[1:]):
        ev.order_uncertain = ev.lo <= prev.hi
    return sum(1 for e in events if e.order_uncertain)


def render_report(issues, n_uncertain, n_conflict):
    lines = ["Consistency report:"]
    for sev, kind, msg, _ in sorted(issues, key=lambda i: SEVERITY[i[0]]):
        lines.append("- %s [%s] %s" % (sev, kind, msg))
    if n_uncertain:
        lines.append("- INFO [order] %d event(s) marked ≈ could have happened "
                     "before the event listed just above them (their possible "
                     "date ranges overlap)." % n_uncertain)
    if n_conflict:
        lines.append("- INFO [legend] ⚠ marks events whose sources disagree on the date.")
    if len(lines) == 1:
        lines.append("- No problems found.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Hierarchy
# --------------------------------------------------------------------------

def choose_levels(events, gran, top=None, explicit=None):
    if explicit:
        levels = [norm_level(x) for x in explicit.split(",") if x.strip()]
        return sorted(levels, key=RANK.get)
    if top is None:
        years = [e.start.astro for e in events] or [0]
        span = max(years) - min(years)
        if RANK[gran] <= RANK["year"]:
            top = gran
        elif span > 500:
            top = "century"
        else:
            top = "year"
    top = norm_level(top)
    if RANK[top] > RANK[gran]:
        top = gran
    if gran == "quarter":
        chain = BASE_CHAIN[:4] + ["quarter"]
    elif gran == "week":
        chain = BASE_CHAIN[:4] + ["week"]
    else:
        chain = BASE_CHAIN
    return [l for l in chain
            if RANK[top] <= RANK[l] <= RANK[gran]
            and (l not in ("millennium", "decade") or l in (top, gran))]


class Node(object):
    def __init__(self, key=None, label=None, level=None):
        self.key, self.label, self.level = key, label, level
        self.children = {}
        self.events = []
        self.first = None  # earliest start sort key of any event below

    def items(self):
        """Events and child periods merged in time order (coarse first)."""
        merged = [((e.start.sort_key(), 0, e.seq), "ev", e) for e in self.events]
        merged += [((c.first, 1, 0), "node", c) for c in self.children.values()]
        merged.sort(key=lambda t: t[0], reverse=getattr(self, "reverse", False))
        return [(kind, obj) for _, kind, obj in merged]


def _touch(node, ev):
    k = ev.start.sort_key()
    if node.first is None or k < node.first:
        node.first = k


def build_tree(events, levels):
    root = Node()
    for ev in events:
        node = root
        _touch(node, ev)
        for i, lvl in enumerate(levels):
            if not can_bucket(ev.start, lvl):
                break
            # Use a short label when the parent level already names the
            # enclosing period (e.g. "Jul" under "1969").
            short = i > 0 and levels[i - 1] in ("year", "month", "day", "hour",
                                                "minute", "quarter", "week")
            if lvl == "day" and i > 0 and levels[i - 1] == "week":
                short = False
            key, label = bucket(ev.start, lvl, short=short)
            node = node.children.setdefault(key, Node(key, label, lvl))
            _touch(node, ev)
        node.events.append(ev)
    return root


def sorted_children(node):
    rev = getattr(node, "reverse", False)
    return [node.children[k] for k in sorted(node.children, reverse=rev)]


# --------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------

def _event_text(ev, gran, show_exact, with_details=True):
    t = ev.headline()
    extra = []
    if show_exact and (RANK[ev.start.precision] > RANK[gran] or ev.end is not None
                       or ev.has_window()):
        extra.append(ev.exact())
    elif RANK[ev.start.precision] < RANK[gran]:
        extra.append("date known only to %s" % ev.start.precision)
    if extra:
        t += " (%s)" % "; ".join(extra)
    if with_details and ev.details:
        t += " — " + ev.details
    src = ev.source_text()
    if src:
        t += " [%s]" % src
    return t


def render_tree(root, gran, title, show_exact):
    out = [title or "Chronology"]

    def walk(node, prefix):
        items = node.items()
        for i, (kind, item) in enumerate(items):
            last = i == len(items) - 1
            branch = "└── " if last else "├── "
            nxt = prefix + ("    " if last else "│   ")
            if kind == "ev":
                out.append(prefix + branch + _event_text(item, gran, show_exact))
            else:
                out.append(prefix + branch + item.label)
                walk(item, nxt)
    walk(root, "")
    return "\n".join(out)


def render_bullets(root, gran, title, show_exact):
    out = ["# " + (title or "Chronology"), ""]

    def walk(node, depth):
        pad = "  " * depth
        for kind, item in node.items():
            if kind == "ev":
                out.append("%s- %s" % (pad, _event_text(item, gran, show_exact)))
            else:
                out.append("%s- **%s**" % (pad, item.label))
                walk(item, depth + 1)
    walk(root, 0)
    return "\n".join(out)


def group_of(ev, gran):
    """(key, label) of the period holding ev at `gran`, or at its own
    precision when that is coarser."""
    lvl = gran if can_bucket(ev.start, gran) else ev.start.precision
    key, label = bucket(ev.start, lvl)
    if ev.approx:
        label = "c. " + label
    return (lvl, key), label


def _flat_groups(events, gran):
    """Group consecutive events by their bucket at `gran` (or coarser)."""
    groups = []
    for ev in events:
        g = group_of(ev, gran)
        if groups and groups[-1][0] == g:
            groups[-1][1].append(ev)
        else:
            groups.append((g, [ev]))
    return groups


def render_timeline(events, gran, title, show_exact):
    out = [title or "Chronology", "│"]
    for (_, label), evs in _flat_groups(events, gran):
        out.append("◆ " + label)
        for ev in evs:
            out.append("│   • " + _event_text(ev, gran, show_exact, False))
            if ev.details:
                out.append("│       " + ev.details)
        out.append("│")
    out.append("▼")
    return "\n".join(out)


def _md_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_table(events, gran, title, show_exact):
    head = ["#", "When", "Event", "Confidence", "Details", "Source"]
    if show_exact:
        head.insert(2, "Exact date")
    out = ["## " + (title or "Chronology"), "",
           "| " + " | ".join(head) + " |",
           "|" + "|".join("---" for _ in head) + "|"]
    for i, ev in enumerate(events, 1):
        row = [i, ev.when(gran), ev.headline(), ev.conf, ev.details, ev.source_text()]
        if show_exact:
            row.insert(2, ev.exact())
        out.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
    return "\n".join(out)


def render_mermaid(events, gran, title, show_exact):
    def clean(s):
        return re.sub(r"[:;#]", " ", s).strip()
    out = ["```mermaid", "timeline"]
    if title:
        out.append("    title " + clean(title))
    for (_, label), evs in _flat_groups(events, gran):
        out.append("    %s : %s" % (clean(label),
                                     " : ".join(clean(e.headline()) for e in evs)))
    out.append("```")
    return "\n".join(out)


def render_csv(events, gran, title, show_exact):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["order", "when", "exact", "earliest_possible", "latest_possible",
                "precision", "approximate", "order_uncertain", "conflict",
                "source_count", "confidence", "confidence_score",
                "confidence_reasons", "title", "details", "source", "tags"])
    for i, ev in enumerate(events, 1):
        lo, hi = ev.window_bounds()
        w.writerow([i, ev.when(gran), ev.exact(), lo, hi,
                    ev.start.precision, ev.approx,
                    ev.order_uncertain, ev.conflict, ev.doc_count(),
                    ev.conf, ev.conf_score, "; ".join(ev.conf_why),
                    ev.title, ev.details, ev.source_text(),
                    ";".join(map(str, ev.tags))])
    return buf.getvalue().rstrip("\n")


def event_json(ev, gran):
    d = dict(ev.raw, when=ev.when(gran), exact=ev.exact(),
             confidence={"level": ev.conf, "score": ev.conf_score, "why": ev.conf_why})
    if ev.scope_note:
        d["scope_note"] = ev.scope_note
    if ev.lo is not None:
        lo, hi = ev.window_bounds()
        d["window"] = {"earliest": lo, "latest": hi}
        d["order_uncertain"] = ev.order_uncertain
    if ev.derived:
        d["derived"] = True
        d["details"] = ev.details
    if len(ev.sources) > 1:
        d["sources"] = [{"document": s["doc"], "locator": s["loc"],
                         "date": s["event"].exact() if s["event"].start else None}
                        for s in ev.sources]
        d["conflict"] = ev.conflict
    return d


def render_json(root, gran, title, show_exact, issues=()):
    def node_json(n):
        d = {}
        if n.label is not None:
            d["period"] = n.label
            d["level"] = n.level
        if n.events:
            d["events"] = [event_json(e, gran) for e in n.events]
        kids = [node_json(c) for c in sorted_children(n)]
        if kids:
            d["children"] = kids
        return d
    doc = {"title": title or "Chronology", "granularity": gran}
    doc.update(node_json(root))
    doc["issues"] = [{"severity": s, "kind": k, "message": m} for s, k, m, _ in issues]
    return json.dumps(doc, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Gaps and density
# --------------------------------------------------------------------------

def human_duration(sec):
    for name, size in (("year", UNIT_SECONDS["year"]), ("month", UNIT_SECONDS["month"]),
                       ("day", DAY), ("hour", 3600), ("minute", 60)):
        if sec >= size:
            v = sec / float(size)
            num = "%d" % round(v) if v >= 10 else ("%.1f" % v).rstrip("0").rstrip(".")
            return "%s %s%s" % (num, name, "" if num == "1" else "s")
    return "%d second%s" % (sec, "" if sec == 1 else "s")


def find_gaps(events, top=5):
    """Longest stretches in which no event can have happened.

    Measured from the latest possible moment of everything before to the
    earliest possible moment of the next event, so every gap is certain.
    Returns [(seconds, event_before, event_after)], longest first.
    """
    gaps, reach, last = [], None, None
    for ev in sorted(events, key=lambda e: (e.lo, e.seq)):
        if reach is not None and ev.lo > reach + 1:
            gaps.append((ev.lo - reach - 1, last, ev))
        end = max(ev.hi, ev.end_hi)
        if reach is None or end > reach:
            reach, last = end, ev
    gaps.sort(key=lambda g: -g[0])
    return gaps[:top]


def period_counts(events, gran):
    """[(label, count, DateParts of the period)] in time order, and the
    number of events too coarse to place at `gran`."""
    counts, coarse = {}, 0
    for ev in events:
        if not can_bucket(ev.start, gran):
            coarse += 1
            continue
        key, label = bucket(ev.start, gran)
        if key not in counts:
            counts[key] = [label, 0, from_seconds(period_bounds(ev.start)[0], gran)]
        counts[key][1] += 1
    return [tuple(counts[k]) for k in sorted(counts)], coarse


def _next_period(dp, gran):
    return from_seconds(period_bounds(dp)[1] + 1, gran)


def _empty_between(a, b, gran, width):
    """Histogram lines for the empty periods between periods a and b."""
    target = bucket(b, gran)[0]
    empties, cur = [], a
    for _ in range(4):
        cur = _next_period(cur, gran)
        if bucket(cur, gran)[0] == target:
            return ["%s │" % bucket(e, gran)[1].ljust(width) for e in empties]
        empties.append(cur)
    last = from_seconds(period_bounds(b)[0] - 1, gran)
    n = int(round((period_bounds(b)[0] - period_bounds(a)[1] - 1)
                  / float(UNIT_SECONDS[gran])))
    return ["%s ┊ %d empty %ss (%s – %s)" % ("".ljust(width), n, gran,
                                            bucket(empties[0], gran)[1],
                                            bucket(last, gran)[1])]


def render_gaps(events, gran):
    out = ["Largest gaps (periods in which no event can have happened):"]
    gaps = find_gaps(events)
    if not gaps:
        out.append("- None: the events' possible dates overlap or touch throughout.")
    for sec, a, b in gaps:
        out.append("- %s: after %s → before %s" % (human_duration(sec), _lbl(a), _lbl(b)))
    rows, _ = period_counts(events, gran)
    total = sum(r[1] for r in rows)
    busy = [r for r in sorted(rows, key=lambda r: -r[1]) if r[1] > 1][:5]
    if rows:
        out.append("")
        out.append("Busiest periods (by %s):" % gran)
        if not busy:
            out.append("- None: no %s has more than one event." % gran)
        for label, n, _ in busy:
            out.append("- %s: %d event%s (%d%% of events placed at this level)"
                       % (label, n, "" if n == 1 else "s", round(100.0 * n / total)))
    return "\n".join(out)


def render_density(events, gran, title, show_exact, width=40):
    rows, coarse = period_counts(events, gran)
    out = ["%s — events per %s" % (title or "Chronology", gran), ""]
    if not rows:
        out.append("(no events are dated precisely enough to place at %s level)" % gran)
    else:
        peak = max(r[1] for r in rows)
        lw = max(len(r[0]) for r in rows)
        prev = None
        for label, n, dp in rows:
            if prev is not None:
                out += _empty_between(prev, dp, gran, lw)
            out.append("%s │%s %d" % (label.ljust(lw),
                                       "█" * max(1, int(round(n * width / float(peak)))), n))
            prev = dp
    if coarse:
        out += ["", "+ %d event(s) dated only to a level coarser than %s (not counted)."
                % (coarse, gran)]
    out += ["", render_gaps(events, gran)]
    return "\n".join(out)


# --------------------------------------------------------------------------
# Parallel tracks (swimlanes)
# --------------------------------------------------------------------------

OTHER_LANE = "(other)"
TRACK_ALIASES = {
    "entity": "entities", "people": "entities", "who": "entities",
    "actors": "entities", "tag": "tags", "theme": "tags", "themes": "tags",
    "topic": "tags", "topics": "tags", "sources": "source", "doc": "source",
    "document": "source", "documents": "source",
}


def track_values(ev, field):
    field = TRACK_ALIASES.get(field.lower(), field)
    if field == "entities":
        vals = ev.entities
    elif field == "tags":
        vals = ev.tags
    elif field == "source":
        vals = [s["doc"] for s in ev.sources]
    else:
        v = ev.raw.get(field)
        vals = v if isinstance(v, list) else [v]
    out = []
    for v in vals:
        if v not in (None, "") and str(v) not in out:
            out.append(str(v))
    return out


def auto_track_field(events):
    for f in ("entities", "tags"):
        if any(track_values(e, f) for e in events):
            return f
    return "source"


def lane_names(events, field, chosen=None):
    if chosen:
        return list(chosen)
    names = []
    for ev in events:
        for v in track_values(ev, field) or [OTHER_LANE]:
            if v not in names:
                names.append(v)
    if OTHER_LANE in names:
        names.remove(OTHER_LANE)
        names.append(OTHER_LANE)
    return names


def render_lanes(events, gran, title, show_exact, field, chosen=None):
    lanes = lane_names(events, field, chosen)
    by_source = TRACK_ALIASES.get(field.lower(), field) == "source"
    out = ["## %s — by %s" % (title or "Chronology", TRACK_ALIASES.get(field, field)), "",
           "| When | " + " | ".join(_md_cell(l) for l in lanes) + " |",
           "|" + "|".join("---" for _ in range(len(lanes) + 1)) + "|"]
    shown = set()
    for (_, label), evs in _flat_groups(events, gran):
        cells = {l: [] for l in lanes}
        for ev in evs:
            for v in track_values(ev, field) or [OTHER_LANE]:
                if v not in cells:
                    continue
                text, exact = ev.headline(), ev.exact()
                if by_source:
                    # Each source's lane shows the date that source gives.
                    own = [s["event"] for s in ev.sources
                           if s["doc"] == v and s["event"].start is not None]
                    if own:
                        exact = own[0].exact()
                if show_exact and (RANK[ev.start.precision] > RANK[gran]
                                   or exact != ev.exact()):
                    text += " (%s)" % exact
                cells[v].append(_md_cell(text))
                shown.add(ev.seq)
        if any(cells.values()):
            out.append("| %s | %s |" % (_md_cell(label), " | ".join(
                "<br>".join(cells[l]) for l in lanes)))
    hidden = len(events) - len(shown)
    if hidden:
        out += ["", "%d event(s) not in the selected lanes are omitted." % hidden]
    return "\n".join(out)


# --------------------------------------------------------------------------
# Telling order vs. story order
# --------------------------------------------------------------------------
# "Story order" is chronological. "Telling order" is the order in which the
# source presents events: the `told` field if given, otherwise the order of
# events in each file (extraction should follow reading order).

def _told_num(ev):
    try:
        return float(ev.told)
    except (TypeError, ValueError):
        return float(ev.seq)


def telling_steps(dated, undated, files):
    """[(event, story_rank or None, movement)] in telling order.

    The "main line" is the furthest point the telling has reached without
    an excursion. An event certainly before it is a flashback; an event
    after it that skips over events told later is a flash-forward. Neither
    moves the main line; coming back to it is marked "resumes".
    """
    doc_order = {f["doc"]: i for i, f in enumerate(files)}
    rank = {id(e): i + 1 for i, e in enumerate(sorted(dated, key=Event.sort_key))}
    told = sorted(dated + undated,
                  key=lambda e: (doc_order.get(e.doc, 0), _told_num(e), e.seq))
    told_pos = {id(e): i for i, e in enumerate(told)}
    by_rank = {r: e for e, r in ((e, rank[id(e)]) for e in dated)}
    steps, main, prev, prev_kind = [], None, None, None
    for e in told:
        if e.start is None:
            steps.append((e, None, "undated"))
            continue
        if prev is not None and prev.doc != e.doc:
            main = prev = prev_kind = None  # a new source starts its own telling
        r, move, kind = rank[id(e)], "", "main"
        if main is not None:
            mr = rank[id(main)]
            later = [by_rank[k] for k in range(mr + 1, r)
                     if told_pos[id(by_rank[k])] > told_pos[id(e)]]
            if e.hi < main.lo:
                kind = "back"
                if prev_kind == "back" and e.lo >= prev.lo:
                    move = "↩ flashback continues"
                else:
                    move = "↩ flashback %s" % human_duration(max(main.lo - e.lo, 0))
            elif later and e.lo > main.hi:
                kind = "forward"
                move = "↪ flash-forward %s (skips %d event%s told later)" % (
                    human_duration(e.lo - main.hi), len(later),
                    "" if len(later) == 1 else "s")
            elif r < mr:
                move = "≈ told after, may be earlier (dates overlap)"
            elif prev_kind in ("back", "forward"):
                move = "→ resumes"
        if kind == "main" and (main is None or r > rank[id(main)]):
            main = e
        steps.append((e, r, move))
        prev, prev_kind = e, kind
    return steps


def telling_summary(steps):
    dated = [(e, r, m) for e, r, m in steps if r is not None]
    starts = sum(1 for _, _, m in dated if m.startswith("↩ flashback ")
                 and not m.endswith("continues"))
    fwd = sum(1 for _, _, m in dated if m.startswith("↪"))
    text = ("%d event(s) in telling order; %d flashback(s), %d flash-forward(s)."
            % (len(steps), starts, fwd))
    if len(dated) > 1:
        ahead = sum(1 for a, b in zip(dated, dated[1:]) if b[1] > a[1])
        text += " Linearity: %d%% of steps move forward in story time." % round(
            100.0 * ahead / (len(dated) - 1))
    return text


def render_telling(steps, gran, title):
    out = ["## %s — as told vs. as happened" % (title or "Chronology"), "",
           telling_summary(steps), "",
           "| Told | Story # | When | Event | Movement |", "|---|---|---|---|---|"]
    for i, (e, r, move) in enumerate(steps, 1):
        when = e.when(gran) if e.start is not None else "—"
        out.append("| %d | %s | %s | %s | %s |" % (
            i, r if r is not None else "—", _md_cell(when),
            _md_cell(e.headline()), _md_cell(move)))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Re-running on updated sources
# --------------------------------------------------------------------------
# A state file records what the last run produced, so the next run can say
# what changed: new or removed events, moved dates, new corroboration,
# new or resolved issues, and how far each source has been extracted.

def event_key(ev):
    return ("id:" + ev.id) if ev.id else "t:%s:%s" % (ev.doc, _norm_title(ev.title))


def snapshot(events, issues, files):
    return {
        "version": 1,
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "files": {f["doc"]: f.get("extracted_through") for f in files},
        "events": {event_key(e): {"title": e.title,
                                  "date": e.exact() if e.start is not None else None,
                                  "sources": e.doc_count(), "conflict": e.conflict}
                   for e in events},
        "issues": sorted("%s [%s] %s" % (s, k, m) for s, k, m, _ in issues),
    }


def diff_state(old, new, events):
    """Mark changed events and return the 'Changes since' lines."""
    by_key = {event_key(e): e for e in events}
    oe, ne = old.get("events", {}), new["events"]
    lines = []
    added = [k for k in ne if k not in oe]
    removed = [k for k in oe if k not in ne]
    moved = [k for k in ne if k in oe and oe[k]["date"] != ne[k]["date"]]
    corrob = [k for k in ne if k in oe and ne[k]["sources"] > oe[k]["sources"]]
    for k in added:
        by_key[k].change = "new"
    for k in moved:
        by_key[k].change = "date was %s" % (oe[k]["date"] or "undated")
    if added:
        lines.append("- %d new event(s): %s" % (len(added), "; ".join(
            "'%s' (%s)" % (ne[k]["title"], ne[k]["date"] or "undated") for k in added[:20])
            + (" …" if len(added) > 20 else "")))
    if removed:
        lines.append("- %d event(s) no longer present: %s" % (len(removed), "; ".join(
            "'%s'" % oe[k]["title"] for k in removed[:20])))
    for k in moved:
        lines.append("- date changed: '%s': %s → %s" % (
            ne[k]["title"], oe[k]["date"] or "undated", ne[k]["date"] or "undated"))
    for k in corrob:
        lines.append("- now backed by %d sources (was %d): '%s'" % (
            ne[k]["sources"], oe[k]["sources"], ne[k]["title"]))
    for k in ne:
        if k in oe and ne[k]["conflict"] and not oe[k]["conflict"]:
            lines.append("- sources now disagree on '%s'" % ne[k]["title"])
    new_issues = [i for i in new["issues"] if i not in old.get("issues", [])]
    resolved = [i for i in old.get("issues", []) if i not in new["issues"]]
    lines += ["- new issue: " + i for i in new_issues]
    lines += ["- resolved: " + i for i in resolved]
    of = old.get("files", {})
    for doc, through in new["files"].items():
        if doc not in of:
            lines.append("- new source: %s%s" % (doc, " (extracted through %s)" % through
                                                 if through else ""))
        elif through and through != of[doc]:
            lines.append("- %s: extracted through %s (was %s)"
                         % (doc, through, of[doc] or "unknown"))
    head = "Changes since last run (%s):" % old.get("created", "unknown time")
    return [head] + (lines or ["- No changes."])


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------
# A 0-100 score per event from how the date was stated and how well it is
# supported. It is a reading aid, not a probability.

PRECISION_SCORE = {"second": 90, "minute": 90, "hour": 88, "day": 85, "week": 75,
                   "month": 70, "quarter": 65, "year": 60, "decade": 45,
                   "century": 35, "millennium": 25}
CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def score_confidence(events, issues):
    worst = {}
    for sev, kind, _, evs in issues:
        if sev == "INFO" or kind == "conflict":
            continue  # conflicts are scored from the event itself
        for e in evs:
            if id(e) not in worst or SEVERITY[sev] < SEVERITY[worst[id(e)]]:
                worst[id(e)] = sev
    for e in events:
        score = PRECISION_SCORE[e.start.precision]
        why = ["date precise to the %s" % e.start.precision]
        if e.approx:
            score -= 15
            why.append("approximate (c.)")
        if e.derived:
            score -= 10
            why.append("derived from a relative statement")
        if e.cal_notes:
            score -= 5
            why.append("calendar conversion uncertainty")
        if e.verify == "verified":
            score += 5
            why.append("quote verified in the source")
        elif e.verify == "not found":
            score -= 30
            why.append("quote NOT found in the source")
        elif e.verify == "approximate":
            score -= 5
            why.append("quote only approximately matches the source")
        if getattr(e, "quote_contradicts", False):
            score -= 20
            why.append("its own quote does not support the date")
        if e.hedged:
            score -= 20
            why.append("the source hedges (e.g. 'reportedly')")
        n = e.doc_count()
        if n > 1:
            score += min(20, 10 * (n - 1))
            why.append("backed by %d sources" % n)
        if e.conflict:
            score -= 25
            why.append("sources disagree on the date")
        sev = worst.get(id(e))
        if sev == "ERROR":
            score -= 20
            why.append("involved in a consistency ERROR")
        elif sev == "WARNING":
            score -= 10
            why.append("involved in a consistency WARNING")
        cap = {"low": 45, "medium": 70}.get(e.certainty)
        if cap is not None and score > cap:
            score = cap
            why.append("source reliability rated %s" % e.certainty)
        e.conf_score = max(5, min(100, score))
        e.conf = "high" if e.conf_score >= 75 else "medium" if e.conf_score >= 50 else "low"
        e.conf_why = why


# --------------------------------------------------------------------------
# Domain presets
# --------------------------------------------------------------------------
# Defaults for common jobs. Anything given explicitly on the command line wins.

PRESETS = {
    "incident": {"granularity": "second", "layout": "table", "tracks": "tags",
                 "gaps": True},
    "legal": {"granularity": "day", "layout": "table", "tracks": "source"},
    "biography": {"granularity": "year", "layout": "tree", "top": "decade",
                  "tracks": "entities"},
    "history": {"granularity": "year", "layout": "tree", "top": "century",
                "gaps": True},
    "project": {"granularity": "week", "layout": "lanes", "tracks": "tags",
                "gaps": True},
    "story": {"granularity": "year", "layout": "telling", "tracks": "entities"},
}
PRESET_ALIASES = {"postmortem": "incident", "outage": "incident", "logs": "incident",
                  "case": "legal", "litigation": "legal", "investigation": "legal",
                  "life": "biography", "memoir": "biography", "historical": "history",
                  "schedule": "project", "plan": "project", "novel": "story",
                  "narrative": "story", "fiction": "story"}


def apply_preset(a):
    if not a.preset:
        return None
    name = PRESET_ALIASES.get(a.preset.lower(), a.preset.lower())
    if name not in PRESETS:
        raise SystemExit("unknown preset '%s' (use one of: %s)"
                         % (a.preset, ", ".join(sorted(PRESETS))))
    for k, v in PRESETS[name].items():
        if getattr(a, k) in (None, False):
            setattr(a, k, v)
    return name


# --------------------------------------------------------------------------
# Questions and filters
# --------------------------------------------------------------------------

def date_window(text, meta):
    """(lo, hi) seconds for a date given on the command line (any calendar)."""
    cal, t = split_calendar(text)
    if cal and cal != "gregorian":
        return convert_calendar(cal, t, meta)[:2]
    return period_bounds(parse_date(t))


def find_event(events, ref):
    """An event by id, or by a title fragment that matches exactly one event."""
    for e in events:
        for v in getattr(e, "variants", [e]):
            if v.id == ref:
                return e
    hits = [e for e in events if ref.lower() in e.title.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError("no event matches '%s'" % ref)
    raise ValueError("'%s' matches %d events: %s" % (
        ref, len(hits), "; ".join("'%s'" % e.title for e in hits[:8])))


def _span_of(e):
    return e.lo, max(e.hi, e.end_hi)


def apply_filters(events, undated, a, meta):
    """Filter events for --from/--to/--as-of/--before/--after/--entity/--tag/
    --source/--search. Returns (events, undated, answer_lines)."""
    answer = []

    def keep_text(e):
        if a.entity and not any(x.lower() in (v.lower() for v in e.entities)
                                for x in a.entity):
            return False
        if a.tag and not any(x.lower() in (str(v).lower() for v in e.tags) for x in a.tag):
            return False
        if a.source and not any(x.lower() in (s["doc"] or "").lower() for x in a.source
                                for s in e.sources):
            return False
        if a.search:
            hay = " ".join([e.title, e.details, e.source_text()]).lower()
            if not all(w.lower() in hay for w in a.search):
                return False
        return True

    events = [e for e in events if keep_text(e)]
    undated = [e for e in undated if keep_text(e)]
    dated_filter = a.date_from or a.date_to or a.as_of or a.before or a.after

    if a.date_from or a.date_to:
        lo = date_window(a.date_from, meta)[0] if a.date_from else None
        hi = date_window(a.date_to, meta)[1] if a.date_to else None
        kept = []
        for e in events:
            e_lo, e_hi = _span_of(e)
            if (lo is not None and e_hi < lo) or (hi is not None and e_lo > hi):
                continue
            if (lo is not None and e_lo < lo) or (hi is not None and e_hi > hi):
                e.scope_note = "may fall outside the range"
            kept.append(e)
        events = kept
        answer.append("%d event(s) between %s and %s (%d only possibly)." % (
            len(events), a.date_from or "the start", a.date_to or "the end",
            sum(1 for e in events if e.scope_note)))

    for flag, ref in (("before", a.before), ("after", a.after)):
        if not ref:
            continue
        x = find_event(events + undated, ref)
        if x.start is None:
            raise ValueError("'%s' is undated, so nothing can be placed relative to it"
                             % x.title)
        kept = []
        for e in events:
            if e is x:
                continue
            certain = e.hi < x.lo if flag == "before" else e.lo > x.hi
            possible = e.lo < x.hi if flag == "before" else e.hi > x.lo
            if certain or possible:
                if not certain:
                    e.scope_note = "order relative to '%s' uncertain" % x.title
                kept.append(e)
        events = kept
        answer.append("%d event(s) %s %s (%d only possibly)." % (
            len(events), flag, _lbl(x), sum(1 for e in events if e.scope_note)))

    if a.as_of:
        d_lo, d_hi = date_window(a.as_of, meta)
        done = [e for e in events if e.hi <= d_hi]
        maybe = [e for e in events if e.lo <= d_hi < e.hi]
        for e in maybe:
            e.scope_note = "may not have happened yet"
        events = [e for e in events if e in done or e in maybe]
        answer.append("By the end of %s: %d event(s) had certainly happened, %d possibly."
                      % (a.as_of, len(done), len(maybe)))
        if done:
            last = max(done, key=lambda e: (e.lo, e.seq))
            answer.append("Most recent certain event: %s." % _lbl(last))
        life = {}
        for e in done + maybe + [e for e in getattr(a, "_all", [])]:
            if isinstance(e.lifespan, dict):
                life.setdefault(str(e.lifespan.get("entity")), {})[
                    str(e.lifespan.get("boundary", "")).lower()] = e
        for ent, b in sorted(life.items()):
            st, en = b.get("start"), b.get("end")
            if en is not None and en.hi <= d_hi:
                state = "had ended (%s)" % en.exact()
            elif st is not None and st.lo > d_hi:
                state = "had not yet begun (%s)" % st.exact()
            elif st is not None and st.hi <= d_hi and (en is None or en.lo > d_hi):
                state = "was active (began %s)" % st.exact()
            else:
                state = "status uncertain at that date"
            answer.append("%s %s." % (ent, state))

    if dated_filter and undated:
        answer.append("%d undated event(s) could not be placed and are left out."
                      % len(undated))
        undated = []
    return events, undated, answer


def how_long(events, ref_a, ref_b):
    a, b = find_event(events, ref_a), find_event(events, ref_b)
    if a.start is None or b.start is None:
        raise ValueError("both events need dates")
    def point(e):
        # Best single estimate: the middle of a stated window, else the start.
        return (e.lo + e.hi) // 2 if e.has_window() else period_bounds(e.start)[0]
    best = point(b) - point(a)
    least, most = b.lo - a.hi, b.hi - a.lo
    sign = "after" if best >= 0 else "before"
    line = "%s is about %s %s %s" % (_lbl(b), human_duration(abs(best)), sign, _lbl(a))
    if least > 0 or most < 0:
        lo_d, hi_d = sorted((abs(least), abs(most)))
        if human_duration(lo_d) != human_duration(hi_d):
            line += " (at least %s, at most %s)" % (human_duration(lo_d), human_duration(hi_d))
        line += "."
    else:
        line += "; their possible dates overlap, so either could be first."
    return [line]


# --------------------------------------------------------------------------
# Interactive HTML
# --------------------------------------------------------------------------

def html_payload(events, undated, issues, gran, title, lane_field, steps=(), changes=(),
                 answer=()):
    index = {id(e): i for i, e in enumerate(events)}
    finest = max([RANK[e.start.precision] for e in events] + [RANK[gran]])
    levels = [l for l in RANK if RANK[l] <= finest
              and (l != "week" or any(can_bucket(e.start, "week") for e in events))]

    ordered = sorted(issues, key=lambda i: SEVERITY[i[0]])
    issue_json, per_event = [], {}
    for n, (sev, kind, msg, evs) in enumerate(ordered):
        ids = [index[id(e)] for e in evs if id(e) in index]
        issue_json.append({"severity": sev, "kind": kind, "message": msg,
                           "cls": {"ERROR": "err", "WARNING": "warn"}.get(sev, "info"),
                           "events": ids})
        for i in ids:
            per_event.setdefault(i, []).append(n)

    fields = [f for f in ("entities", "tags") if any(track_values(e, f) for e in events)]
    fields.append("source")
    if lane_field:
        lane_field = TRACK_ALIASES.get(lane_field.lower(), lane_field)
        if lane_field in fields:
            fields.remove(lane_field)
        fields.insert(0, lane_field)

    out_events = []
    for i, e in enumerate(events):
        g = {}
        for lvl in levels:
            (l, key), label = group_of(e, lvl)
            g[lvl] = [l + repr(key), label]
        lo, hi = e.window_bounds()
        out_events.append({
            "i": i, "id": e.id, "title": e.title, "details": e.details,
            "exact": e.exact(), "window": e.window() if e.has_window() else "",
            "precision": e.start.precision, "derived": e.derived,
            "uncertain": e.order_uncertain, "conflict": e.conflict,
            "sourceText": e.source_text(),
            "sources": [{"doc": s["doc"], "loc": s["loc"],
                         "date": s["event"].exact() if s["event"].start else ""}
                        for s in e.sources],
            "tags": [str(t) for t in e.tags], "entities": [str(x) for x in e.entities],
            "docs": track_values(e, "source"),
            "lanes": {f: track_values(e, f) for f in fields},
            "g": g, "issues": per_event.get(i, []), "change": e.change or "",
            "conf": e.conf, "confScore": e.conf_score, "confWhy": e.conf_why,
            "scope": e.scope_note, "quote": e.quote, "verify": e.verify or "",
        })

    gaps = [{"text": "%s: after %s → before %s" % (human_duration(s), _lbl(a), _lbl(b)),
             "events": [index[id(a)], index[id(b)]]} for s, a, b in find_gaps(events)]
    sev_count = {k: sum(1 for x in issues if x[0] == k) for k in SEVERITY}
    first, last = (min(events, key=lambda e: e.lo), max(events, key=lambda e: e.hi)) \
        if events else (None, None)
    stats = "%d events" % len(events)
    if events:
        stats += " · %s → %s" % (first.exact(), last.exact())
    docs = {s["doc"] for e in events for s in e.sources if s["doc"]}
    if len(docs) > 1:
        stats += " · %d sources" % len(docs)
    stats += " · %d errors, %d warnings" % (sev_count["ERROR"], sev_count["WARNING"])
    return {
        "title": title or "Chronology", "stats": stats, "granularity": gran,
        "levels": [[l, l.capitalize()] for l in levels], "laneFields": fields,
        "events": out_events, "issues": issue_json, "gaps": gaps,
        "undated": [{"title": u.title, "source": u.source_text(),
                     "why": u.errors[0] if u.errors else ""} for u in undated],
        "told": [{"i": index.get(id(e)), "title": e.title, "rank": r, "move": mv,
                  "when": e.exact() if e.start is not None else "undated"}
                 for e, r, mv in steps],
        "toldSummary": telling_summary(steps) if steps else "",
        "changes": list(changes),
        "answer": list(answer),
    }


def render_html(events, undated, issues, gran, title, lane_field, steps=(), changes=(),
                answer=()):
    import html as htmlmod
    data = json.dumps(html_payload(events, undated, issues, gran, title, lane_field,
                                   steps, changes, answer),
                      ensure_ascii=False).replace("</", "<\\/")
    return (HTML_TEMPLATE.replace("__TITLE__", htmlmod.escape(title or "Chronology"))
            .replace("__DATA__", data))


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fbfaf7;--panel:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e1db;--accent:#2f6fde;--accent-soft:#e8effc;--err:#b3261e;--err-soft:#fdecea;--warn:#8a5000;--warn-soft:#fff2db;--info:#4a5568;--info-soft:#eef0f3;--bar:#9db7ea}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141416;--panel:#1d1d20;--ink:#ececee;--muted:#9a9aa2;--line:#2e2e33;--accent:#7aa5f5;--accent-soft:#1f2a40;--err:#ff8a80;--err-soft:#3a1d1d;--warn:#ffc266;--warn-soft:#3a2c14;--info:#b8c0cc;--info-soft:#25282e;--bar:#46679f}}
:root[data-theme="dark"]{--bg:#141416;--panel:#1d1d20;--ink:#ececee;--muted:#9a9aa2;--line:#2e2e33;--accent:#7aa5f5;--accent-soft:#1f2a40;--err:#ff8a80;--err-soft:#3a1d1d;--warn:#ffc266;--warn-soft:#3a2c14;--info:#b8c0cc;--info-soft:#25282e;--bar:#46679f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:1140px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 4px}
.stats{color:var(--muted);font-size:.9rem}
.controls{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px}
.row{max-width:1140px;margin:0 auto;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
select,input[type=search],button{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:5px 10px}
input[type=search]{flex:1 1 200px;min-width:0}
button{cursor:pointer}
button[aria-pressed="true"]{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
.facets{max-width:1140px;margin:8px auto 0;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.facets span{color:var(--muted);font-size:.8rem;margin-left:4px}
.chip{font-size:.8rem;padding:1px 9px;border-radius:999px}
main{max-width:1140px;margin:0 auto;padding:12px 16px 60px;display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px}
@media (max-width:860px){main{grid-template-columns:minmax(0,1fr)}}
.density{display:flex;align-items:flex-end;gap:2px;height:56px;margin:4px 0 18px;overflow-x:auto;border-bottom:1px solid var(--line)}
.density button{flex:1 0 6px;min-width:6px;max-width:28px;padding:0;border:0;border-radius:3px 3px 0 0;background:var(--bar)}
.density button:hover{background:var(--accent)}
.period{margin:0 0 18px 6px;padding-left:18px;border-left:2px solid var(--line)}
.period h3{margin:0 0 8px;font-size:1rem;position:relative}
.period h3::before{content:"";position:absolute;left:-25px;top:6px;width:12px;height:12px;border-radius:50%;background:var(--accent)}
.period h3 small,.lanes small{color:var(--muted);font-weight:400;margin-left:6px}
.ev{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:0 0 8px;cursor:pointer}
.ev.hl{outline:2px solid var(--accent);outline-offset:1px}
.ev .when{font-size:.8rem;color:var(--muted)}
.ev .t{font-weight:600}
.ev .more{display:none;margin-top:8px;font-size:.9rem;cursor:auto}
.ev.open .more{display:block}
.ev .more p{margin:0 0 6px}
.mark{font-weight:700;margin-right:3px}
.badge{display:inline-block;font-size:.7rem;padding:0 6px;border-radius:6px;margin-left:6px;font-weight:600;vertical-align:1px}
.b-err{background:var(--err-soft);color:var(--err)}.b-warn{background:var(--warn-soft);color:var(--warn)}.b-info{background:var(--info-soft);color:var(--info)}
.more table{border-collapse:collapse;width:100%;font-size:.85rem}
.more td{border-top:1px solid var(--line);padding:3px 8px 3px 0;vertical-align:top;overflow-wrap:anywhere}
.more table{table-layout:fixed}
.tagline{color:var(--muted);font-size:.8rem}
aside section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:14px;font-size:.88rem}
aside h2{font-size:.95rem;margin:0 0 6px}
.issue,.gap{padding:6px 0;border-top:1px solid var(--line);cursor:pointer}
.issue:hover,.gap:hover{color:var(--accent)}
.lanes{overflow-x:auto}
.lanes table{border-collapse:separate;border-spacing:6px 0;min-width:100%}
.lanes th{text-align:left;font-size:.85rem;color:var(--muted);padding:4px 0;border-bottom:1px solid var(--line)}
.lanes td{vertical-align:top;min-width:200px;max-width:300px;padding-top:8px}
body.lanes-mode main{grid-template-columns:minmax(0,1fr)}
body.lanes-mode aside{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
body.lanes-mode aside section{margin:0}
.lanes td.when{min-width:110px;font-weight:600;font-size:.9rem}
.lanes .ev{margin:0 0 6px}
.empty{color:var(--muted);padding:20px 0}
.b-new{background:var(--accent-soft);color:var(--accent)}
.b-low{background:var(--warn-soft);color:var(--warn)}
.answer{margin-top:10px;padding:10px 12px;background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;font-size:.92rem}
.answer div+div{margin-top:4px}
.told td{padding:6px 8px 6px 0;border-top:1px solid var(--line);vertical-align:top;font-size:.9rem}
.told th{text-align:left;font-size:.8rem;color:var(--muted);padding:4px 8px 4px 0}
.told table{border-collapse:collapse;width:100%}
.told .mv{color:var(--accent)}
</style>
</head>
<body>
<header><h1 id="title"></h1><div class="stats" id="stats"></div><div class="answer" id="answer" hidden></div></header>
<div class="controls">
  <div class="row">
    <label>Zoom <select id="level" aria-label="Granularity"></select></label>
    <button id="v-timeline" aria-pressed="true">Timeline</button>
    <button id="v-lanes" aria-pressed="false">Lanes</button>
    <button id="v-told" aria-pressed="false" title="Order in which the source tells events">As told</button>
    <select id="lane-field" aria-label="Lanes by" hidden></select>
    <input type="search" id="q" placeholder="Search titles, details, sources…" aria-label="Search">
    <button id="flagged" aria-pressed="false" title="Only events marked ≈, ⚠ or with issues">Flagged only</button>
    <select id="conf" aria-label="Minimum confidence"><option value="0">Any confidence</option><option value="1">Medium or high</option><option value="2">High only</option></select>
    <button id="theme" title="Toggle light/dark">◐</button>
  </div>
  <div class="facets" id="facets"></div>
</div>
<main>
  <div>
    <div class="density" id="density" aria-label="Events per period"></div>
    <div id="view"></div>
  </div>
  <aside>
    <section id="changes-sec"><h2>Changes since last run</h2><div id="changes"></div></section>
    <section><h2>Consistency report</h2><div id="report"></div></section>
    <section><h2>Gaps</h2><div id="gaps"></div></section>
    <section><h2>Busiest periods</h2><div id="busy"></div></section>
    <section id="undated-sec"><h2>Undated</h2><div id="undated"></div></section>
    <section><h2>Legend</h2>
      <div><span class="mark">≈</span>could have happened before the previous event</div>
      <div><span class="mark">⚠</span>sources disagree on the date</div>
      <div><span class="mark">[derived]</span>date computed from a relative statement</div>
    </section>
  </aside>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('data').textContent);
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  var S = {level: D.granularity, view: 'timeline', lane: D.laneFields[0], q: '',
           f: {tags: {}, entities: {}, docs: {}}, flagged: false, open: {}, hl: {}, minConf: 0};
  try {
    var saved = localStorage.getItem('chronology-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  } catch (e) {}

  $('title').textContent = D.title;
  $('stats').textContent = D.stats;
  if (D.answer.length) {
    $('answer').hidden = false;
    $('answer').innerHTML = D.answer.map(function (l) { return '<div>' + esc(l) + '</div>'; }).join('');
  }
  var CONF = {low: 0, medium: 1, high: 2};

  D.levels.forEach(function (l) {
    var o = document.createElement('option');
    o.value = l[0]; o.textContent = l[1]; o.selected = l[0] === S.level;
    $('level').appendChild(o);
  });
  D.laneFields.forEach(function (f) {
    var o = document.createElement('option');
    o.value = f; o.textContent = 'by ' + f; $('lane-field').appendChild(o);
  });

  var FACETS = [['entities', 'Who'], ['tags', 'Tags'], ['docs', 'Sources']];
  var fhtml = '';
  FACETS.forEach(function (fc) {
    var vals = [];
    D.events.forEach(function (e) {
      e[fc[0]].forEach(function (v) { if (vals.indexOf(v) < 0) vals.push(v); });
    });
    if (vals.length < (fc[0] === 'docs' ? 2 : 1)) return;
    fhtml += '<span>' + fc[1] + '</span>' + vals.map(function (v) {
      return '<button class="chip" aria-pressed="false" data-k="' + fc[0] + '" data-v="' +
        esc(v) + '">' + esc(v) + '</button>';
    }).join('');
  });
  $('facets').innerHTML = fhtml;

  function active(k) { return Object.keys(S.f[k]); }
  function match(e) {
    if (S.flagged && !(e.uncertain || e.conflict || e.issues.length)) return false;
    if (CONF[e.conf] < S.minConf) return false;
    for (var n = 0; n < FACETS.length; n++) {
      var k = FACETS[n][0], sel = active(k);
      if (sel.length && !e[k].some(function (v) { return S.f[k][v]; })) return false;
    }
    if (S.q) {
      var hay = [e.title, e.details, e.sourceText, e.exact, e.tags.join(' '),
                 e.entities.join(' ')].join(' ').toLowerCase();
      if (hay.indexOf(S.q) < 0) return false;
    }
    return true;
  }
  function groups(list) {
    var out = [];
    list.forEach(function (e) {
      var g = e.g[S.level], last = out[out.length - 1];
      if (last && last.k === g[0]) last.items.push(e);
      else out.push({k: g[0], lab: g[1], items: [e]});
    });
    return out;
  }
  function card(e, lane) {
    var when = e.exact;
    if (lane && S.lane === 'source') {
      // In a source's lane, show the date that source gives.
      e.sources.forEach(function (s) { if (s.doc === lane && s.date) when = s.date; });
    }
    var marks = (e.uncertain ? '<span class="mark" title="Could have happened before the previous event">≈</span>' : '') +
                (e.conflict ? '<span class="mark" title="Sources disagree on the date">⚠</span>' : '');
    var sevs = {};
    e.issues.forEach(function (n) { sevs[D.issues[n].cls] = D.issues[n].severity; });
    var badges = Object.keys(sevs).map(function (c) {
      return '<span class="badge b-' + c + '">' + sevs[c] + '</span>';
    }).join('') + (e.change ? '<span class="badge b-new" title="' + esc(e.change) + '">' +
      (e.change === 'new' ? 'NEW' : 'CHANGED') + '</span>' : '') +
      (e.verify === 'not found' ? '<span class="badge b-err">QUOTE NOT FOUND</span>' : '') +
      (e.conf === 'low' ? '<span class="badge b-low" title="' + esc(e.confWhy.join('; ')) +
       '">LOW CONFIDENCE</span>' : '') +
      (e.scope ? '<span class="badge b-info">' + esc(e.scope) + '</span>' : '');
    var more = '';
    if (e.details) more += '<p>' + esc(e.details) + '</p>';
    if (e.window) more += '<p class="tagline">Possible dates: ' + esc(e.window) + '</p>';
    if (e.quote) more += '<p class="tagline">“' + esc(e.quote) + '”' +
      (e.verify ? ' — ' + esc(e.verify === 'verified' ? 'verified in source' : e.verify) : '') + '</p>';
    more += '<p class="tagline">Confidence: ' + esc(e.conf) + ' (' + e.confScore + '/100) — ' +
      esc(e.confWhy.join('; ')) + '</p>';
    if (e.sources.length) {
      more += '<table>' + e.sources.map(function (s) {
        return '<tr><td>' + esc(s.loc || '—') + '</td><td>' + esc(s.doc) + '</td><td>' +
          esc(s.date) + '</td></tr>';
      }).join('') + '</table>';
    }
    var labels = e.entities.concat(e.tags);
    if (labels.length) more += '<p class="tagline">' + esc(labels.join(' · ')) + '</p>';
    e.issues.forEach(function (n) {
      var x = D.issues[n];
      more += '<p><span class="badge b-' + x.cls + '">' + x.severity + '</span> ' +
        esc(x.message) + '</p>';
    });
    return '<article class="ev' + (S.open[e.i] ? ' open' : '') + (S.hl[e.i] ? ' hl' : '') +
      '" data-i="' + e.i + '"' + (lane ? '' : ' id="ev-' + e.i + '"') +
      '><div class="when">' + esc(when) +
      '</div><div class="t">' + marks + esc(e.title) + (e.derived ? ' <span class="tagline">[derived]</span>' : '') +
      badges + '</div><div class="more">' + more + '</div></article>';
  }
  function lanesOf(e) {
    var v = e.lanes[S.lane] || [];
    return v.length ? v : ['(other)'];
  }
  function render() {
    var list = D.events.filter(match), gs = groups(list);
    var max = 1;
    gs.forEach(function (g) { max = Math.max(max, g.items.length); });
    $('density').innerHTML = gs.map(function (g, ix) {
      return '<button data-g="' + ix + '" style="height:' +
        Math.max(10, Math.round(g.items.length / max * 100)) + '%" title="' +
        esc(g.lab) + ': ' + g.items.length + '" aria-label="' + esc(g.lab) + ', ' +
        g.items.length + ' events"></button>';
    }).join('');
    if (S.view === 'told') {
      var keep = {};
      list.forEach(function (e) { keep[e.i] = true; });
      var rows = D.told.filter(function (t) {
        return t.i === null ? !S.flagged && !S.q : keep[t.i];
      });
      $('view').innerHTML = '<div class="told"><p class="tagline">' + esc(D.toldSummary) +
        '</p><table><thead><tr><th>Told</th><th>Story #</th><th>When</th><th>Event</th>' +
        '<th>Movement</th></tr></thead><tbody>' + rows.map(function (t) {
          return '<tr><td>' + (D.told.indexOf(t) + 1) + '</td><td>' + (t.rank || '—') +
            '</td><td>' + esc(t.when) + '</td><td>' + esc(t.title) + '</td><td class="mv">' +
            esc(t.move) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    } else if (!gs.length) {
      $('view').innerHTML = '<p class="empty">No events match.</p>';
    } else if (S.view === 'timeline') {
      $('view').innerHTML = gs.map(function (g, ix) {
        return '<section class="period" id="g-' + ix + '"><h3>' + esc(g.lab) + '<small>' +
          g.items.length + '</small></h3>' + g.items.map(function (e) { return card(e); }).join('') +
          '</section>';
      }).join('');
    } else {
      var names = [];
      list.forEach(function (e) {
        lanesOf(e).forEach(function (v) { if (names.indexOf(v) < 0) names.push(v); });
      });
      var oi = names.indexOf('(other)');
      if (oi >= 0) { names.splice(oi, 1); names.push('(other)'); }
      $('view').innerHTML = '<div class="lanes"><table><thead><tr><th>When</th>' +
        names.map(function (n) { return '<th>' + esc(n) + '</th>'; }).join('') +
        '</tr></thead><tbody>' + gs.map(function (g, ix) {
          return '<tr><td class="when" id="g-' + ix + '">' + esc(g.lab) + '<small>' +
            g.items.length + '</small></td>' + names.map(function (n) {
              return '<td>' + g.items.filter(function (e) {
                return lanesOf(e).indexOf(n) >= 0;
              }).map(function (e) { return card(e, n); }).join('') + '</td>';
            }).join('') + '</tr>';
        }).join('') + '</tbody></table></div>';
    }
    var busy = gs.filter(function (g) { return g.items.length > 1; })
      .sort(function (a, b) { return b.items.length - a.items.length; }).slice(0, 5);
    $('busy').innerHTML = busy.length ? busy.map(function (g) {
      return '<div class="gap" data-g="' + gs.indexOf(g) + '">' + esc(g.lab) + ': ' +
        g.items.length + ' event' + (g.items.length === 1 ? '' : 's') + '</div>';
    }).join('') : '<div class="tagline">No period at this zoom has more than one event.</div>';
  }

  $('report').innerHTML = D.issues.length ? D.issues.map(function (x, n) {
    return '<div class="issue" data-n="' + n + '"><span class="badge b-' + x.cls + '">' +
      x.severity + '</span> <b>' + esc(x.kind) + '</b> ' + esc(x.message) + '</div>';
  }).join('') : '<div class="tagline">No problems found.</div>';
  $('gaps').innerHTML = D.gaps.length ? D.gaps.map(function (g, n) {
    return '<div class="gap" data-gap="' + n + '">' + esc(g.text) + '</div>';
  }).join('') : '<div class="tagline">No certain gaps.</div>';
  if (D.undated.length) {
    $('undated').innerHTML = D.undated.map(function (u) {
      return '<div>' + esc(u.title) + (u.source ? ' <span class="tagline">[' + esc(u.source) + ']</span>' : '') +
        (u.why ? '<div class="tagline">Date not usable: ' + esc(u.why) + '</div>' : '') + '</div>';
    }).join('');
  } else { $('undated-sec').hidden = true; }

  function focusEvents(ids) {
    S.hl = {}; S.flagged = false; S.q = ''; $('q').value = '';
    $('flagged').setAttribute('aria-pressed', 'false');
    FACETS.forEach(function (fc) { S.f[fc[0]] = {}; });
    Array.prototype.forEach.call(document.querySelectorAll('.chip'), function (c) {
      c.setAttribute('aria-pressed', 'false');
    });
    ids.forEach(function (i) { S.hl[i] = true; S.open[i] = true; });
    render();
    var el = ids.length && document.querySelector('.ev[data-i="' + ids[0] + '"]');
    if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  $('level').onchange = function () { S.level = this.value; render(); };
  $('conf').onchange = function () { S.minConf = +this.value; render(); };
  $('lane-field').onchange = function () { S.lane = this.value; render(); };
  function setView(v) {
    S.view = v;
    $('v-timeline').setAttribute('aria-pressed', String(v === 'timeline'));
    $('v-lanes').setAttribute('aria-pressed', String(v === 'lanes'));
    $('v-told').setAttribute('aria-pressed', String(v === 'told'));
    $('lane-field').hidden = v !== 'lanes';
    document.body.classList.toggle('lanes-mode', v === 'lanes');
    render();
  }
  $('v-timeline').onclick = function () { setView('timeline'); };
  $('v-lanes').onclick = function () { setView('lanes'); };
  $('v-told').onclick = function () { setView('told'); };
  if (!D.told.length) $('v-told').hidden = true;
  if (D.changes.length) {
    $('changes').innerHTML = D.changes.map(function (c, n) {
      return '<div' + (n ? '' : ' class="tagline"') + '>' + esc(c) + '</div>';
    }).join('');
  } else { $('changes-sec').hidden = true; }
  $('q').oninput = function () { S.q = this.value.trim().toLowerCase(); render(); };
  $('flagged').onclick = function () {
    S.flagged = !S.flagged; this.setAttribute('aria-pressed', String(S.flagged)); render();
  };
  $('theme').onclick = function () {
    var root = document.documentElement, cur = root.getAttribute('data-theme');
    if (!cur) cur = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    var next = cur === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('chronology-theme', next); } catch (e) {}
  };
  $('facets').onclick = function (ev) {
    var c = ev.target.closest('.chip'); if (!c) return;
    var k = c.getAttribute('data-k'), v = c.getAttribute('data-v');
    if (S.f[k][v]) delete S.f[k][v]; else S.f[k][v] = true;
    c.setAttribute('aria-pressed', String(!!S.f[k][v]));
    render();
  };
  $('view').onclick = function (ev) {
    if (ev.target.closest('.more')) return;
    var a = ev.target.closest('.ev'); if (!a) return;
    var i = +a.getAttribute('data-i');
    S.open[i] = !S.open[i];
    a.classList.toggle('open', S.open[i]);
  };
  function scrollToGroup(ix) {
    var el = $('g-' + ix);
    if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  $('density').onclick = function (ev) {
    var b = ev.target.closest('button'); if (b) scrollToGroup(b.getAttribute('data-g'));
  };
  $('busy').onclick = function (ev) {
    var b = ev.target.closest('.gap'); if (b) scrollToGroup(b.getAttribute('data-g'));
  };
  $('report').onclick = function (ev) {
    var x = ev.target.closest('.issue'); if (x) focusEvents(D.issues[+x.getAttribute('data-n')].events);
  };
  $('gaps').onclick = function (ev) {
    var x = ev.target.closest('.gap'); if (x) focusEvents(D.gaps[+x.getAttribute('data-gap')].events);
  };
  render();
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Self-check: verify quotes against the source text
# --------------------------------------------------------------------------
# During extraction each event can carry `quote`: the source's exact words
# for it. --verify re-reads the source text and checks every quote (or a
# sample): is it there, is it on the cited page, and does it support the date?

_QUOTE_MAP = {ord(k): v for k, v in {
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
    "—": "-", "­": "", " ": " ", "…": "..."}.items()}
PAGE_RE = re.compile(r"\bp(?:age|g|p)?\.?\s*(\d+)\b", re.I)
YEAR_IN_TEXT_RE = re.compile(r"(?<![\d.,])([12]\d{3})(?![\d,])")


def _norm_text(t, lower=True):
    t = t.translate(_QUOTE_MAP)
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)  # hyphenation across line breaks
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower() if lower else t


def find_quote(quote, text):
    """(position, share of the quote matched in order) in normalised text."""
    q = _norm_text(quote)
    if not q:
        return None, 0.0
    i = text.find(q)
    if i >= 0:
        return i, 1.0
    words = sorted(set(re.findall(r"\w{4,}", q)), key=lambda w: text.count(w) or 10 ** 9)
    best = (None, 0.0)
    for w in words[:4]:
        start, tries = 0, 0
        while tries < 300:
            j = text.find(w, start)
            if j < 0:
                break
            lo = max(0, j - len(q))
            window = text[lo:j + len(q)]
            m = difflib.SequenceMatcher(None, q, window, autojunk=False)
            share = sum(b.size for b in m.get_matching_blocks()) / float(len(q))
            if share > best[1]:
                blocks = [b for b in m.get_matching_blocks() if b.size]
                at = lo + (blocks[0].b if blocks else 0)
                best = (at, share)
            start, tries = j + 1, tries + 1
    return best


def _date_words(e, quote):
    """A reason the quote doesn't support the event's date, or None."""
    if e.cal_start or e.derived or e.start is None:
        return None  # original-calendar wording or a computed date
    q = quote.lower()
    years = sorted({int(y) for y in YEAR_IN_TEXT_RE.findall(q)})
    if years and RANK[e.start.precision] >= RANK["year"] and e.start.year > 0:
        lo_y = from_seconds(e.lo, "year").year
        hi_y = from_seconds(e.hi, "year").year
        if not any(lo_y <= y <= hi_y for y in years):
            return "the quote mentions %s but the event is dated %s" % (
                ", ".join(map(str, years)), e.exact())
    if e.start.month and RANK[e.start.precision] >= RANK["month"]:
        named = set()
        for w in re.findall(r"[a-z]+", q):
            if w in MONTH_NAMES and len(w) > 3 and w not in ("march", "sept"):
                named.add(MONTH_NAMES[w])
        # "may" and "march" are also ordinary words: count them only next to a number.
        # The same for three-letter abbreviations ("Jul 1969", "20 Jul").
        for w, n in [("march", 3)] + [(k, v) for k, v in MONTH_NAMES.items() if len(k) == 3]:
            if re.search(r"\b%s\.?\s+\d|\d(?:st|nd|rd|th)?\s+%s\b" % (w, w), q):
                named.add(n)
        if named and e.start.month not in named and not e.has_window():
            return "the quote names %s but the event is dated %s" % (
                "/".join(MONTHS[m - 1] for m in sorted(named)), e.exact())
    return None


def verify_quotes(events, paths, sample=None):
    """Check quotes against source files. Returns issues and marks events."""
    import hashlib
    import os
    texts = {}
    for path in paths:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        base = os.path.basename(path)
        pages = raw.split("\f")
        cased = _norm_text(raw, lower=False)  # same positions, original case
        texts[base.lower()] = (base, cased.lower(), cased,
                               [_norm_text(pg) for pg in pages] if len(pages) > 1 else None)
    stems = {os.path.splitext(k)[0]: k for k in texts}

    def text_for(doc):
        d = (doc or "").lower()
        if d in texts:
            return texts[d]
        if os.path.splitext(d)[0] in stems:
            return texts[stems[os.path.splitext(d)[0]]]
        return next(iter(texts.values())) if len(texts) == 1 else None

    items = [(e, s["event"]) for e in events for s in e.sources]
    with_quote = [(e, v) for e, v in items if v.quote]
    chosen = with_quote
    if sample and sample < len(with_quote):
        chosen = sorted(with_quote, key=lambda ev: hashlib.sha1(
            ("%s|%s" % (ev[1].doc, ev[1].quote)).encode("utf-8")).hexdigest())[:sample]
    issues, counts = [], {"verified": 0, "approximate": 0, "not found": 0}
    rank = {None: 0, "verified": 1, "approximate": 2, "not found": 3}
    for e, v in chosen:
        src = text_for(v.doc)
        if src is None:
            issues.append(("INFO", "verify", "'%s': no source text given for %s"
                           % (v.title, v.doc or "?"), (e,)))
            continue
        name, full, cased, pages = src
        pos, share = find_quote(v.quote, full)
        excerpt = v.quote if len(v.quote) <= 90 else v.quote[:87] + "..."
        if share >= 0.98:
            status = "verified"
        elif share >= 0.85:
            status = "approximate"
            found = ""
            if pos is not None:
                found = cased[pos:pos + len(_norm_text(v.quote)) + 12]
                found = found[:found.rfind(" ")] if " " in found[8:] else found
            issues.append(("WARNING", "verify", "'%s': quote matches %s only approximately "
                           "(%d%%). Quoted: “%s”. Source has: “%s”"
                           % (v.title, name, round(share * 100), excerpt, found.strip()), (e,)))
        else:
            status = "not found"
            issues.append(("ERROR", "verify", "'%s': quote not found in %s: “%s”"
                           % (v.title, name, excerpt), (e,)))
        counts[status] += 1
        if rank[status] > rank[e.verify]:
            e.verify = status
        if status == "not found":
            continue
        # Page check: sources extracted with page breaks (\f), cited as "p. N".
        m = PAGE_RE.search(v.source or "")
        if pages and m:
            cited = int(m.group(1))
            q = _norm_text(v.quote)
            on = [i + 1 for i, pg in enumerate(pages) if q in pg]
            if on and not any(abs(n - cited) <= 0 for n in on):
                issues.append(("WARNING", "verify", "'%s': quote is on page %s of %s, "
                               "but cited as %s" % (v.title, "/".join(map(str, on)), name,
                                                    v.source), (e,)))
        why = _date_words(v, v.quote)
        if why:
            e.quote_contradicts = True
            issues.append(("WARNING", "verify", "'%s': %s" % (v.title, why), (e,)))
    total = len(with_quote)
    summary = "Verified %d of %d checked quote(s) word for word; %d approximate, %d not found." \
        % (counts["verified"], len(chosen), counts["approximate"], counts["not found"])
    if sample and sample < total:
        summary += " (A sample of %d of %d quotes.)" % (len(chosen), total)
    missing = sum(1 for _, v in items if not v.quote)
    if missing:
        summary += " %d event source(s) have no quote to check." % missing
    issues.append(("INFO", "verify", summary, ()))
    return issues


# --------------------------------------------------------------------------
# Exports: iCalendar, Mermaid Gantt, TimelineJS, vis-timeline
# --------------------------------------------------------------------------

def _exportable(e):
    """Calendar and charting tools need 4-digit CE years."""
    return 1 <= e.start.year <= 9999 and (e.end is None or 1 <= e.end.year <= 9999)


def _span_secs(e):
    """(start, end) seconds: an end date, else the whole period of the start."""
    lo = period_bounds(e.start)[0]
    hi = period_bounds(e.end)[1] if e.end is not None else period_bounds(e.start)[1]
    return lo, hi


def _plain(e):
    t = e.title + (" [derived date]" if e.derived else "")
    return ("c. " + t) if e.approx else t


def _ics_escape(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _ics_fold(line):
    """Fold to 75 octets per line (RFC 5545 §3.1)."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 75:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def _ics_stamp(sec, timed):
    dp = from_seconds(sec, "second")
    if timed:
        return "%04d%02d%02dT%02d%02d%02dZ" % (dp.year, dp.month, dp.day,
                                               dp.hour, dp.minute, dp.second)
    return "%04d%02d%02d" % (dp.year, dp.month, dp.day)


def render_ics(events, gran, title, show_exact):
    import hashlib
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//chronology skill//EN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:" + _ics_escape(title or "Chronology")]
    skipped = 0
    for e in events:
        if not _exportable(e):
            skipped += 1
            continue
        lo, hi = _span_secs(e)
        timed = RANK[e.start.precision] >= RANK["hour"]
        uid = hashlib.sha1(("%s|%s|%s" % (e.id, e.title, e.exact())).encode("utf-8"))
        desc = "\n".join(x for x in (
            "Date: " + e.exact(), e.details, "Sources: " + e.source_text(),
            "Confidence: %s (%s)" % (e.conf, "; ".join(e.conf_why))) if x)
        lines += ["BEGIN:VEVENT", "UID:%s@chronology" % uid.hexdigest()[:20],
                  "DTSTAMP:" + now]
        if timed:
            lines.append("DTSTART:" + _ics_stamp(lo, True))
            if e.end is not None:
                lines.append("DTEND:" + _ics_stamp(hi + 1, True))
        else:  # all-day over the whole period (a day, a month, a year …)
            lines.append("DTSTART;VALUE=DATE:" + _ics_stamp(lo, False))
            lines.append("DTEND;VALUE=DATE:" + _ics_stamp(hi + 1, False))
        lines.append("SUMMARY:" + _ics_escape(_plain(e)))
        lines.append("DESCRIPTION:" + _ics_escape(desc))
        if e.tags:
            lines.append("CATEGORIES:" + ",".join(_ics_escape(str(t)) for t in e.tags))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    if skipped:
        print("info: %d event(s) before 1 CE or after 9999 were left out of the "
              "calendar" % skipped, file=sys.stderr)
    return "\r\n".join(_ics_fold(l) for l in lines)


def render_gantt(events, gran, title, show_exact, field=None):
    field = field or auto_track_field(events)
    timed = any(RANK[e.start.precision] >= RANK["hour"] for e in events if _exportable(e))
    fmt = "YYYY-MM-DD HH:mm" if timed else "YYYY-MM-DD"

    def stamp(sec):
        dp = from_seconds(sec, "minute")
        out = "%04d-%02d-%02d" % (dp.year, dp.month, dp.day)
        return out + (" %02d:%02d" % (dp.hour, dp.minute) if timed else "")

    def clean(t):
        return re.sub(r"[:;#]", " ", t).strip()

    out = ["```mermaid", "gantt"]
    if title:
        out.append("    title " + clean(title))
    out += ["    dateFormat " + fmt, "    axisFormat %Y-%m-%d" + (" %H:%M" if timed else "")]
    lanes = lane_names(events, field)
    n = 0
    for lane in lanes:
        rows = []
        for e in events:
            if not _exportable(e) or lane not in (track_values(e, field) or [OTHER_LANE]):
                continue
            n += 1
            lo, hi = _span_secs(e)
            point = e.end is None and RANK[e.start.precision] >= RANK["day"]
            if point:
                rows.append("    %s :milestone, t%d, %s, 0d" % (clean(_plain(e)), n, stamp(lo)))
            else:
                rows.append("    %s :t%d, %s, %s" % (clean(_plain(e)), n, stamp(lo),
                                                     stamp(hi + 1)))
        if rows:
            out.append("    section " + clean(lane))
            out += rows
    out.append("```")
    return "\n".join(out)


def _tl_date(dp):
    d = {"year": dp.year}
    for k in ("month", "day", "hour", "minute", "second"):
        if getattr(dp, k) is not None and RANK[dp.precision] >= RANK[
                {"month": "month", "day": "day", "hour": "hour",
                 "minute": "minute", "second": "second"}[k]]:
            d[k] = getattr(dp, k)
    if dp.precision == "quarter" and "month" not in d:
        d["month"] = (dp.quarter - 1) * 3 + 1
    return d


def render_timelinejs(events, gran, title, show_exact, field=None):
    """TimelineJS 3 JSON (negative years for BCE)."""
    import html as htmlmod
    field = field or auto_track_field(events)
    items = []
    for e in events:
        body = [htmlmod.escape(x) for x in (e.details, "Sources: " + e.source_text()) if x]
        item = {"start_date": _tl_date(e.start),
                "text": {"headline": htmlmod.escape(_plain(e)), "text": "<br>".join(body)},
                "display_date": e.exact(),
                "unique_id": "e%d" % e.seq}
        if e.end is not None:
            item["end_date"] = _tl_date(e.end)
        lanes = track_values(e, field)
        if lanes:
            item["group"] = lanes[0]
        items.append(item)
    return json.dumps({"title": {"text": {"headline": htmlmod.escape(title or "Chronology")}},
                       "events": items}, ensure_ascii=False, indent=1)


def render_vis(events, gran, title, show_exact, field=None):
    """vis-timeline items and groups (CE dates only)."""
    field = field or auto_track_field(events)
    lanes = lane_names(events, field)
    items = []
    for e in events:
        if not _exportable(e):
            continue
        lo, hi = _span_secs(e)

        def iso(sec):
            dp = from_seconds(sec, "second")
            return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (dp.year, dp.month, dp.day,
                                                       dp.hour, dp.minute, dp.second)
        point = e.end is None and RANK[e.start.precision] >= RANK["day"]
        item = {"id": e.seq, "content": _plain(e), "start": iso(lo),
                "title": "%s — %s" % (e.exact(), e.source_text()),
                "type": "point" if point else "range",
                "group": lanes.index((track_values(e, field) or [OTHER_LANE])[0])}
        if not point:
            item["end"] = iso(hi + 1)
        items.append(item)
    return json.dumps({"title": title or "Chronology", "items": items,
                       "groups": [{"id": i, "content": l} for i, l in enumerate(lanes)]},
                      ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

LAYOUTS = ("tree", "timeline", "table", "bullets", "mermaid", "csv", "json",
           "density", "lanes", "html", "telling", "ics", "gantt", "timelinejs", "vis")
MACHINE = ("csv", "json", "html", "ics", "timelinejs", "vis")  # no text appended
LAYOUT_ALIASES = {"tabular": "table", "bullet": "bullets", "indented": "bullets",
                  "list": "bullets", "outline": "bullets", "hierarchy": "tree",
                  "vertical": "timeline", "markdown": "table",
                  "histogram": "density", "gaps": "density", "heatmap": "density",
                  "swimlane": "lanes", "swimlanes": "lanes", "tracks": "lanes",
                  "parallel": "lanes", "interactive": "html", "web": "html",
                  "page": "html", "narrative": "telling", "told": "telling",
                  "discourse": "telling", "story": "telling", "flashbacks": "telling",
                  "ical": "ics", "icalendar": "ics", "calendar": "ics",
                  "tljs": "timelinejs", "timeline-js": "timelinejs",
                  "vis-timeline": "vis", "visjs": "vis"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("events", nargs="+",
                    help="one or more events JSON files ('-' for stdin); "
                         "several files are merged into one chronology")
    ap.add_argument("-g", "--granularity")
    ap.add_argument("-l", "--layout")
    ap.add_argument("--preset", help="defaults for a kind of job: incident, legal, "
                                     "biography, history, project, story")
    ap.add_argument("-t", "--title")
    ap.add_argument("--top", help="coarsest grouping level for tree/bullets/json")
    ap.add_argument("--levels", help="explicit comma-separated grouping levels")
    ap.add_argument("--no-exact", action="store_true",
                    help="hide exact dates that are finer than the granularity")
    ap.add_argument("--reverse", action="store_true", help="newest first")
    ap.add_argument("--auto-merge", action="store_true",
                    help="also merge events without an id that share a title")
    ap.add_argument("--no-checks", action="store_true",
                    help="skip the consistency report and the ≈ / ⚠ marks")
    ap.add_argument("--report-only", action="store_true",
                    help="print only the consistency report")
    ap.add_argument("--tracks", metavar="FIELD",
                    help="lane field for the lanes and html layouts: entities, "
                         "tags, source, or any event field (default: auto)")
    ap.add_argument("--lanes", metavar="A,B,...",
                    help="only these lanes, in this order (lanes layout)")
    ap.add_argument("--gaps", action="store_true",
                    help="append largest gaps and busiest periods to the output")
    ap.add_argument("--min-confidence", choices=("low", "medium", "high"),
                    help="only show events at or above this confidence")
    q = ap.add_argument_group("questions and filters")
    q.add_argument("--from", dest="date_from", metavar="DATE", help="from this date")
    q.add_argument("--to", dest="date_to", metavar="DATE", help="up to this date")
    q.add_argument("--as-of", metavar="DATE", help="what had happened by this date")
    q.add_argument("--before", metavar="EVENT", help="events before this event (id or title)")
    q.add_argument("--after", metavar="EVENT", help="events after this event (id or title)")
    q.add_argument("--how-long", nargs=2, metavar=("EVENT_A", "EVENT_B"),
                   help="time between two events, with bounds")
    q.add_argument("--entity", action="append", help="only events involving this entity")
    q.add_argument("--tag", action="append", help="only events with this tag")
    q.add_argument("--source", action="append", help="only events from this source document")
    q.add_argument("--search", action="append", help="only events containing this text")
    q.add_argument("--answer-only", action="store_true",
                   help="print only the answer to the question")
    t = ap.add_argument_group("tables (CSV / TSV / SQLite inputs)")
    t.add_argument("--date-col", help="column holding the event date (default: detected)")
    t.add_argument("--end-col", help="column holding an end date")
    t.add_argument("--title-col", help="column for the event title (default: detected)")
    t.add_argument("--entity-col", help="column of people/organisations (; or , separated)")
    t.add_argument("--tag-col", help="column of tags, e.g. service or category")
    t.add_argument("--dayfirst", dest="order", action="store_const", const="dmy",
                   help="read 03/04/2024 as 3 April")
    t.add_argument("--monthfirst", dest="order", action="store_const", const="mdy",
                   help="read 03/04/2024 as 4 March")
    t.add_argument("--sql", help="SQL query to run on a SQLite input (read-only)")
    t.add_argument("--table", help="table or view to read from a SQLite input")
    ap.add_argument("--verify", action="append", metavar="SOURCE_TEXT",
                    help="check each event's `quote` against this source text "
                         "(.txt/.md; repeat for several sources)")
    ap.add_argument("--verify-sample", type=int, metavar="N",
                    help="check only N quotes (a fixed, repeatable sample)")
    ap.add_argument("--collapse", action="store_true",
                    help="fold repeated events (same title, same period) into one with a count")
    ap.add_argument("--state", metavar="FILE",
                    help="compare with the previous run saved in FILE (if any), "
                         "then save this run to FILE")
    ap.add_argument("--since", metavar="FILE", help="compare with a saved run only")
    ap.add_argument("--save-state", metavar="FILE", help="save this run only")
    ap.add_argument("-o", "--output", help="write to file instead of stdout")
    a = ap.parse_args(argv)

    preset = apply_preset(a)
    gran = norm_level(a.granularity or "day")
    layout = LAYOUT_ALIASES.get((a.layout or "timeline").lower(), (a.layout or "timeline").lower())
    if layout not in LAYOUTS:
        ap.error("unknown layout '%s' (use one of: %s)" % (a.layout, ", ".join(LAYOUTS)))

    table_opts = {k: getattr(a, k) for k in ("date_col", "end_col", "title_col",
                                              "entity_col", "tag_col", "order", "sql", "table")}
    try:
        meta, events, errors = load_events(a.events, table_opts)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    for ev in events:
        ev.show_doc = len(a.events) > 1
        if ev.start is not None:
            ev.compute_interval()
    events = merge_events(events, auto=a.auto_merge)
    if a.collapse:
        events = collapse_events(events, gran)
    by_id = {}
    for ev in events:
        for v in getattr(ev, "variants", [ev]):
            if v.id is not None:
                by_id[v.id] = ev
    issues = [("INFO", "table", n, ()) for n in meta.get("table_notes", [])]
    derive_offsets(events, by_id, issues)
    undated = [e for e in events if e.start is None]
    events = sorted((e for e in events if e.start is not None), key=Event.sort_key)

    checks = not a.no_checks
    n_uncertain = n_conflict = 0
    if checks:
        issues += check_events(events, by_id)
        n_uncertain = mark_uncertain_order(events)
        n_conflict = sum(1 for e in events if e.conflict)
    else:
        for e in events:
            e.conflict = False
    if checks:
        notes = []
        for e in events + undated:
            for v in getattr(e, "variants", [e]):
                notes += [n for n in v.cal_notes if n not in notes]
        issues += [("INFO", "calendar", n, ()) for n in notes]
    if a.verify:
        try:
            issues += verify_quotes(events + undated, a.verify, a.verify_sample)
        except (IOError, OSError) as exc:
            ap.error("cannot read source text for --verify: %s" % exc)
    report = render_report(issues, n_uncertain, n_conflict) if checks or a.verify else ""

    # Compare with the previous run, then (optionally) save this one.
    since, save = a.since or a.state, a.save_state or a.state
    snap = snapshot(events + undated, issues, meta.get("files", []))
    changes = []
    if since:
        try:
            with io.open(since, encoding="utf-8") as fh:
                changes = diff_state(json.load(fh), snap, events + undated)
        except (IOError, OSError):
            changes = ["Changes since last run: no previous state at %s; "
                       "this run is the baseline." % since]
    score_confidence(events, issues)

    # Questions and filters narrow what is shown; checks ran on everything.
    answer = []
    try:
        if a.how_long:
            answer += how_long(events + undated, *a.how_long)
        a._all = events + undated
        events, undated, more = apply_filters(events, undated, a, meta)
        answer += more
    except ValueError as exc:
        ap.error(str(exc))
    if a.min_confidence:
        floor = CONF_RANK[a.min_confidence]
        hidden = [e for e in events if CONF_RANK[e.conf] < floor]
        events = [e for e in events if CONF_RANK[e.conf] >= floor]
        if hidden:
            answer.append("%d event(s) below %s confidence are hidden."
                          % (len(hidden), a.min_confidence))
    steps = telling_steps(events, undated, meta.get("files", []))

    title = a.title or meta.get("title")
    show_exact = not a.no_exact
    if a.reverse:
        events.reverse()

    if a.report_only:
        text = report or "Consistency checks disabled."
    elif layout in ("tree", "bullets", "json"):
        levels = choose_levels(events, gran, a.top, a.levels)
        root = build_tree(events, levels)
        if a.reverse:
            _reverse_tree(root)
        if layout == "json":
            text = render_json(root, gran, title, show_exact, issues)
        else:
            text = {"tree": render_tree, "bullets": render_bullets}[layout](
                root, gran, title, show_exact)
    elif layout == "lanes":
        field = a.tracks or auto_track_field(events)
        chosen = [x.strip() for x in a.lanes.split(",") if x.strip()] if a.lanes else None
        text = render_lanes(events, gran, title, show_exact, field, chosen)
    elif layout == "html":
        text = render_html(events, undated, issues if checks else [], gran, title,
                           a.tracks, steps, changes, answer)
    elif layout == "telling":
        text = render_telling(steps, gran, title)
    elif layout in ("gantt", "timelinejs", "vis"):
        text = {"gantt": render_gantt, "timelinejs": render_timelinejs,
                "vis": render_vis}[layout](events, gran, title, show_exact, a.tracks)
    elif layout == "ics":
        text = render_ics(events, gran, title, show_exact)
    else:
        text = {"timeline": render_timeline, "table": render_table,
                "mermaid": render_mermaid, "csv": render_csv,
                "density": render_density}[layout](events, gran, title, show_exact)

    if len(events) > 2000 and layout not in MACHINE + ("density",) and not a.collapse:
        print("info: %d events; consider --collapse, -l density, or filters "
              "(--from/--to, --tag, --search)" % len(events), file=sys.stderr)
    if a.gaps and not a.report_only and layout not in MACHINE + ("density",):
        text += "\n\n" + render_gaps(events, gran)
    if layout == "json" and not a.report_only and (changes or answer):
        doc = json.loads(text)
        doc["changes"] = changes
        doc["answer"] = answer
        text = json.dumps(doc, ensure_ascii=False, indent=2)
    if not a.report_only and layout not in MACHINE:
        if changes:
            text += "\n\n" + "\n".join(changes)
        if undated and layout != "telling":
            text += "\n\nUndated / unresolved:\n" + "\n".join(
                "- " + u.title + (" (date not usable: %s)" % u.errors[0] if u.errors else "")
                for u in undated)
        if report:
            text += "\n\n" + report
    elif layout in MACHINE and layout not in ("json", "html"):
        for block in (changes and "\n".join(changes), report):
            if block:
                print(block, file=sys.stderr)
    if a.report_only and changes:
        text = "\n".join(changes) + "\n\n" + text
    if answer and layout not in MACHINE:
        text = "Answer:\n" + "\n".join("- " + l for l in answer) + "\n\n" + text
    elif answer and layout not in ("json", "html"):
        print("Answer:\n" + "\n".join("- " + l for l in answer), file=sys.stderr)
    if a.answer_only:
        text = "\n".join(answer) if answer else "No question was asked."

    if a.output:
        with io.open(a.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(text + ("\r\n" if layout == "ics" else "\n"))
    else:
        sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
        print(text)
    for e in errors:
        print("warning: " + e, file=sys.stderr)
    if save:
        with io.open(save, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=1)
    print("info: %d dated, %d undated, granularity=%s, layout=%s%s"
          % (len(events), len(undated), gran, layout,
             ", preset=%s" % preset if preset else ""), file=sys.stderr)


def _reverse_tree(node):
    for c in node.children.values():
        _reverse_tree(c)
    node.events.reverse()
    node.reverse = True


if __name__ == "__main__":
    main()
