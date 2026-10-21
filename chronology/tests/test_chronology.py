"""Tests for scripts/chronology.py (standard library only).

Run from the skill folder:
    python -m unittest discover -s tests -v
"""
import contextlib
import datetime as dt
import io
import json
import re
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import chronology as c  # noqa: E402

EX = os.path.join(SKILL, "examples")
MULTI = [os.path.join(EX, "multi-source", f)
         for f in ("witness.json", "police-log.json", "newspaper.json")]


def run(*argv):
    """Run the CLI in-process. Returns (stdout, stderr, exit_code)."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            c.main([str(a) for a in argv])
    except SystemExit as exc:
        code = exc.code or 0
    return out.getvalue(), err.getvalue(), code


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chronology-test-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))
        return path


# ---------------------------------------------------------------- calendar math

class CalendarMath(unittest.TestCase):
    def test_days_round_trip_matches_datetime(self):
        for d in (dt.date(1, 1, 1), dt.date(1582, 10, 15), dt.date(1970, 1, 1),
                  dt.date(2000, 2, 29), dt.date(9999, 12, 31)):
            z = c.days_from_civil(d.year, d.month, d.day)
            self.assertEqual(z, (d - dt.date(1970, 1, 1)).days)
            self.assertEqual(c.civil_from_days(z), (d.year, d.month, d.day))

    def test_round_trip_across_bce(self):
        for z in range(-1200000, 1200000, 7919):
            self.assertEqual(c.days_from_civil(*c.civil_from_days(z)), z)

    def bounds(self, text):
        lo, hi = c.period_bounds(c.parse_date(text))
        return (c.exact_label(c.from_seconds(lo, "day")),
                c.exact_label(c.from_seconds(hi, "day")))

    def test_period_bounds(self):
        self.assertEqual(self.bounds("C19"), ("1 Jan 1801", "31 Dec 1900"))
        self.assertEqual(self.bounds("-C1"), ("1 Jan 100 BCE", "31 Dec 1 BCE"))
        self.assertEqual(self.bounds("1960s"), ("1 Jan 1960", "31 Dec 1969"))
        self.assertEqual(self.bounds("40s BCE"), ("1 Jan 49 BCE", "31 Dec 40 BCE"))
        self.assertEqual(self.bounds("2000-02"), ("1 Feb 2000", "29 Feb 2000"))
        self.assertEqual(self.bounds("1969-W29"), ("14 Jul 1969", "20 Jul 1969"))
        self.assertEqual(self.bounds("1969-Q4"), ("1 Oct 1969", "31 Dec 1969"))


class Parsing(unittest.TestCase):
    def test_partial_and_era_forms(self):
        self.assertEqual(c.parse_date("1969-07").precision, "month")
        self.assertEqual(c.parse_date("753 BC").year, -753)
        self.assertEqual(c.parse_date("C5").precision, "century")
        self.assertEqual(c.parse_date("1969-07-20T20:17:40Z").precision, "second")

    def test_rejects_impossible_dates(self):
        for bad in ("0", "1969-13-01", "2023-02-29", "1969-07-20T24:00", "soon"):
            with self.assertRaises(ValueError, msg=bad):
                c.parse_date(bad)

    def test_timezone_converted_to_utc(self):
        dp = c.parse_date("2024-03-10T01:30-05:00")
        self.assertEqual((dp.day, dp.hour, dp.minute), (10, 6, 30))


# ---------------------------------------------------------------- other calendars

class Calendars(unittest.TestCase):
    META = {"reigns": {"Elizabeth II": "1952-02-06"},
            "fiscal_year": {"start": "10-01", "label": "end"}}

    def greg(self, value):
        cal, text = c.split_calendar(value)
        return c.convert_calendar(cal, text, self.META)[3]

    def test_known_conversions(self):
        cases = {
            "julian:1582-10-04": "14 Oct 1582",       # day before the first Gregorian day
            "julian:1616-04-23": "3 May 1616",        # Shakespeare's death
            "julian:-44-03-15": "13 Mar 44 BCE",
            "julian:1917-10-25": "7 Nov 1917",
            "hijri:1445-09-01": "11 Mar 2024",
            "hebrew:5785-tishrei-01": "3 Oct 2024",
            "hebrew:5784-nisan-15": "23 Apr 2024",
            "hebrew:5784-adar2-14": "24 Mar 2024",
            "hebrew:5784-adar i-14": "23 Feb 2024",
            "japanese:Showa 20-08-15": "15 Aug 1945",
            "japanese:令和元年-05-01": "1 May 2019",
            "regnal:Elizabeth II:3": "6 Feb 1954 – 5 Feb 1955",
            "fy:2024": "1 Oct 2023 – 30 Sep 2024",
            "fy:2024-Q2": "1 Jan 2024 – 31 Mar 2024",
        }
        for value, want in cases.items():
            self.assertEqual(self.greg(value), want, value)

    def test_unsupported_calendars_explain_why(self):
        for value in ("chinese:2024-01-01", "japanese:Meiji 3", "regnal:Victoria:2"):
            cal, text = c.split_calendar(value)
            with self.assertRaises(ValueError, msg=value):
                c.convert_calendar(cal, text, self.META)


class Panchang(unittest.TestCase):
    """Hindu lunisolar calendar (drik method, New Delhi sunrise by default)."""

    def sunrise_day(self, value, meta=None):
        (_, _), label, (first, nxt), _ = c.panchang_window(value, meta or {})
        m = re.search(r"at sunrise on ([^;\]]+)", label)
        return m.group(1) if m else None

    def test_new_moon_matches_published_time(self):
        # New moon of the total solar eclipse: 2024-04-08 18:21 UTC
        want = c.days_from_civil(2024, 4, 8) + (18 * 60 + 21) / 1440.0
        got = c.new_moon_before(want + 1)
        self.assertLess(abs(got - want) * 1440, 3)

    def test_adhika_months(self):
        found = {}
        for y in (2020, 2023, 2026):
            for start, _, masa, adhika in c.lunar_months(c.days_from_civil(y, 5, 1), 6):
                if adhika:
                    found[y] = c.MASA_NAMES[masa - 1]
        self.assertEqual(found, {2020: "Ashvina", 2023: "Shravana", 2026: "Jyeshtha"})

    def test_sunrise_tithi_days(self):
        cases = {
            "VS 2080 Chaitra shukla 1": "22 Mar 2023",            # Ugadi / Gudi Padwa
            "VS 2081 Chaitra shukla pratipada": "9 Apr 2024",
            "Shaka 1947 Chaitra shukla 1": "30 Mar 2025",
            "VS 2080 Chaitra shukla 9": "30 Mar 2023",            # Ram Navami
            "VS 2081 Chaitra sudi navami": "17 Apr 2024",
            "VS 2082 Chaitra shukla 9": "6 Apr 2025",
            "VS 2080 adhika Shravana shukla 1": "18 Jul 2023",
            "VS 2080 Ashvina krishna amavasya": "13 Nov 2023",    # at sunrise (Diwali: 12 Nov)
            "purnimanta VS 2080 Kartika krishna amavasya": "13 Nov 2023",
            "VS 2080 Kartika shukla purnima": "27 Nov 2023",
            "VS 2080 Phalguna shukla purnima": "25 Mar 2024",     # Holi
            "purnimanta VS 2080 Chaitra krishna 1": "26 Mar 2024",
            "purnimanta VS 2081 Chaitra krishna 1": "15 Mar 2025",
        }
        for value, want in cases.items():
            self.assertEqual(self.sunrise_day(value), want, value)

    def test_tithi_span_matches_published_timings(self):
        _, label, _, _ = c.panchang_window("VS 2081 Chaitra shukla 9", {})
        self.assertIn("tithi ran 16 Apr 2024 13:2", label)   # published 13:23
        self.assertIn("to 17 Apr 2024 15:1", label)          # published 15:14

    def test_historical_dates(self):
        # Shivaji's coronation: computed Gregorian 16 Jun 1674 = Julian 6 Jun 1674.
        self.assertEqual(self.sunrise_day("Shaka 1596 Jyeshtha shukla 13"), "16 Jun 1674")
        self.assertEqual(c.julian_days(1674, 6, 6), c.days_from_civil(1674, 6, 16))
        # Gandhi: tithi current at sunrise 3 Oct, but it began on 2 Oct 1869.
        (_, _), label, (first, nxt), _ = c.panchang_window(
            "kartikadi VS 1925 Bhadrapada krishna 12", {})
        self.assertIn("tithi ran 2 Oct 1869", label)
        self.assertLessEqual(first, c.days_from_civil(1869, 10, 2))

    def test_windows(self):
        (_, _), _, (first, nxt), _ = c.panchang_window("VS 2081", {})
        self.assertEqual((first, nxt), (c.days_from_civil(2024, 4, 9),
                                        c.days_from_civil(2025, 3, 30)))
        (_, _), _, (first, nxt), _ = c.panchang_window("VS 2081 Kartika", {})
        self.assertEqual(first, c.days_from_civil(2024, 11, 2))

    def test_errors_explain_themselves(self):
        for bad, msg in (("VS 2081 adhika Shravana", "no adhika Shravana"),
                         ("VS 2081 Chaitra 9", "give the paksha"),
                         ("Kali 5125 Chaitra", "expected"),
                         ("kartikadi VS 2081", "Kartikadi year")):
            with self.assertRaises(ValueError) as cm:
                c.panchang_window(bad, {})
            self.assertIn(msg, str(cm.exception))
        with self.assertRaises(ValueError):
            c.panchang_window("VS 2081 Chaitra shukla 1", {"panchang": {"location": "atlantis"}})

    def test_end_to_end(self):
        out, _, _ = run(os.path.join(EX, "calendars", "events.json"), "-l", "table", "-g", "day")
        self.assertIn("Shaka 1596 Jyeshtha Shukla 13 (Trayodashi)", out)
        self.assertIn("INFO [calendar] Hindu panchang dates use the drik", out)


# ---------------------------------------------------------------- full runs

class Layouts(unittest.TestCase):
    def test_every_layout_and_granularity_runs(self):
        for layout in c.LAYOUTS:
            for gran in ("century", "year", "week", "day", "second"):
                out, err, code = run(os.path.join(EX, "apollo11-events.json"),
                                     "-l", layout, "-g", gran)
                self.assertEqual(code, 0, (layout, gran, err))
                self.assertTrue(out.strip(), (layout, gran))

    def test_coarse_dates_keep_their_precision(self):
        out, _, _ = run(os.path.join(EX, "apollo11-events.json"), "-l", "tree", "-g", "day")
        self.assertIn("Worldwide TV audience of ~600 million (c. Jul 1969", out)
        self.assertIn("Undated / unresolved", out)

    def test_machine_formats_are_clean(self):
        for layout in ("csv", "json", "ics", "timelinejs", "vis"):
            out, _, _ = run(*MULTI, "-l", layout)
            self.assertNotIn("Consistency report", out, layout)
        for layout in ("json", "timelinejs", "vis"):
            json.loads(run(*MULTI, "-l", layout)[0])


class ChecksAndMerging(unittest.TestCase):
    def setUp(self):
        self.report, _, _ = run(*MULTI, "--report-only")

    def test_expected_issues(self):
        for needle in ("ERROR [anachronism] 'Smith tweets'",
                       "ERROR [order] 'Report filed'",
                       "ERROR [offset] 'Phone call'",
                       "WARNING [conflict] 'Smith meets Jones'",
                       "WARNING [lifespan] 'Letter signed by Smith'"):
            self.assertIn(needle, self.report)

    def test_corroboration_and_derived_date(self):
        out, _, _ = run(*MULTI, "-l", "table", "-g", "day")
        self.assertIn("2 sources: p1 · witness.txt; row 1 · police-log.csv", out)
        self.assertIn("| 19 Jun 1998 |", out)  # +7 days from the meeting
        self.assertIn("⚠ Smith meets Jones", out)

    def test_lanes_show_each_sources_own_date(self):
        out, _, _ = run(*MULTI, "-l", "lanes", "--tracks", "source", "-g", "day")
        for when in ("12 Jun 1998 14:02", "12 Jun 1998 14:10", "13 Jun 1998"):
            self.assertIn(when, out)


class Telling(unittest.TestCase):
    def test_story_movements(self):
        out, _, _ = run(os.path.join(EX, "story", "events.json"), "-l", "telling", "-g", "month")
        self.assertIn("2 flashback(s), 1 flash-forward(s)", out)
        self.assertIn("Linearity: 62%", out)
        for move in ("↩ flashback 24 years", "→ resumes", "↪ flash-forward 11 years",
                     "↩ flashback continues"):
            self.assertIn(move, out)


class Questions(unittest.TestCase):
    def test_how_long_with_bounds(self):
        out, _, _ = run(*MULTI, "--how-long", "Smith marries", "Smith born", "--answer-only")
        self.assertIn("about 27 years before", out)
        self.assertIn("at least 25 years, at most 30 years", out)

    def test_as_of(self):
        out, _, _ = run(*MULTI, "--as-of", "1998-06-13", "--answer-only")
        self.assertIn("5 event(s) had certainly happened", out)
        self.assertIn("Smith was active", out)

    def test_ambiguous_reference_is_an_error(self):
        _, err, code = run(*MULTI, "--how-long", "Smith", "born")
        self.assertNotEqual(code, 0)
        self.assertIn("matches 6 events", err)


class Presets(unittest.TestCase):
    def test_project_schedule(self):
        out, err, _ = run(os.path.join(EX, "presets", "project.json"), "--preset", "project")
        self.assertIn("preset=project", err)
        self.assertIn("'Public launch' (2 May 2025) happened after its planned date "
                      "(11 Apr 2025): late by 21 days", out)
        self.assertIn("late by up to 1.1 months", out)

    def test_minute_offsets_allow_slack(self):
        out, _, _ = run(os.path.join(EX, "presets", "incident.json"), "--preset", "incident")
        self.assertNotIn("[offset]", out)


class Confidence(unittest.TestCase):
    def test_levels(self):
        out, _, _ = run(*MULTI, "-l", "csv", "-g", "day")
        rows = {r[-4]: r for r in __import__("csv").reader(io.StringIO(out))}
        self.assertEqual(rows["Smith born"][10], "high")
        self.assertEqual(rows["Smith marries"][10], "low")


class Incremental(TempDir):
    def test_changes_since_last_run(self):
        inc = os.path.join(EX, "incremental")
        state = os.path.join(self.dir, "state.json")
        run(os.path.join(inc, "witness-run1.json"), "--state", state)
        out, _, _ = run(os.path.join(inc, "witness-run2.json"),
                        os.path.join(inc, "police-log.json"), "--state", state)
        self.assertIn("6 new event(s)", out)
        self.assertIn("date changed: 'Smith meets Jones': 12 Jun 1998 15:00 → "
                      "12 Jun 1998 14:02", out)
        self.assertIn("witness.txt: extracted through p7 (was p3)", out)
        again, _, _ = run(os.path.join(inc, "witness-run2.json"),
                          os.path.join(inc, "police-log.json"), "--state", state)
        self.assertIn("- No changes.", again)


# ---------------------------------------------------------------- tables

class Tables(TempDir):
    def test_day_first_detected_and_ids_used(self):
        out, _, _ = run(os.path.join(EX, "tables", "orders.csv"), "-l", "table", "-g", "day")
        self.assertIn("| 25 Mar 2024 |", out)
        self.assertIn("order_id=A-1001", out)
        self.assertIn("Desk lamp", out)
        self.assertIn("not a readable date", out)

    def test_ambiguous_dates_are_reported(self):
        path = self.write("amb.csv", "when,what\n03/04/2024,a\n05/06/2024,b\n")
        out, _, _ = run(path, "-l", "table")
        self.assertIn("ambiguous; read as day-first", out)
        self.assertIn("3 Apr 2024", out)
        out, _, _ = run(path, "-l", "table", "--monthfirst")
        self.assertIn("4 Mar 2024", out)

    def test_epoch_ms_and_collapse(self):
        out, _, _ = run(os.path.join(EX, "tables", "app-log.csv"), "-l", "table",
                        "-g", "hour", "--collapse")
        self.assertIn("upstream timeout calling payments (×40)", out)
        self.assertIn("3 Jun 2025", out)

    def test_sqlite_needs_table_choice_and_converts_offsets(self):
        db = os.path.join(EX, "tables", "support.db")
        _, err, code = run(db)
        self.assertNotEqual(code, 0)
        self.assertIn("choose one with --table", err)
        out, _, _ = run(db, "--table", "tickets", "-l", "csv", "-g", "minute")
        self.assertIn("1 Mar 2025 08:15", out)  # 09:15+01:00 → UTC

    def test_sqlite_is_read_only(self):
        path = os.path.join(self.dir, "t.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE t (at TEXT, name TEXT)")
        con.execute("INSERT INTO t VALUES ('2020-01-01', 'x')")
        con.commit()
        con.close()
        _, err, code = run(path, "--sql", "DELETE FROM t")
        self.assertNotEqual(code, 0)
        con = sqlite3.connect(path)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        con.close()


# ---------------------------------------------------------------- self-check

class Verify(TempDir):
    VER = os.path.join(EX, "verify")

    def report(self, *extra):
        out, _, code = run(os.path.join(self.VER, "events.json"), "--verify",
                           os.path.join(self.VER, "letters.txt"), "--report-only", *extra)
        self.assertEqual(code, 0)
        return out

    def test_planted_problems_are_caught(self):
        out = self.report()
        self.assertIn("ERROR [verify] 'Hale meets the strikers': quote not found", out)
        self.assertIn("'Carders' strike begins': quote matches letters.txt only "
                      "approximately", out)
        self.assertIn("piece-rates", out)  # shows what the source really says
        self.assertIn("the quote mentions 1888 but the event is dated 12 Nov 1887", out)
        self.assertIn("quote is on page 3 of letters.txt, but cited as p. 1", out)
        self.assertIn("Verified 3 of 5", out)

    def test_sample_is_repeatable(self):
        a = self.report("--verify-sample", "2")
        b = self.report("--verify-sample", "2")
        self.assertEqual(a, b)
        self.assertIn("A sample of 2 of 5 quotes", a)

    def test_confidence_reflects_verification(self):
        out, _, _ = run(os.path.join(self.VER, "events.json"), "--verify",
                        os.path.join(self.VER, "letters.txt"), "-l", "table", "-g", "day")
        self.assertIn("[quote not found in source]", out)
        self.assertIn("| Mill destroyed by fire | medium |", out)

    def test_whitespace_quotes_and_hyphenation_are_tolerated(self):
        src = self.write("s.txt", "He said “the ship sailed on\n 3 May 1910” and the "
                                  "crew cele-\nbrated.")
        ev = self.write("e.json", {"source_document": "s.txt", "events": [
            {"date": "1910-05-03", "title": "Sailing",
             "quote": "\"the ship sailed on 3 May 1910\" and the crew celebrated"}]})
        out, _, _ = run(ev, "--verify", src, "--report-only")
        self.assertIn("Verified 1 of 1", out)

    def test_ordinary_words_are_not_months(self):
        e = c.Event({"date": "1969-03-05", "title": "t"}, 0)
        e.compute_interval()
        self.assertIsNone(c._date_words(e, "they may return before the march, in 1969"))


# ---------------------------------------------------------------- exports

class Exports(unittest.TestCase):
    def test_ics_is_rfc5545_shaped(self):
        out, _, _ = run(os.path.join(EX, "apollo11-events.json"), "-l", "ics")
        raw = out.encode("utf-8")
        lines = out.rstrip("\n").split("\r\n")
        self.assertEqual(lines[0], "BEGIN:VCALENDAR")
        self.assertEqual(lines[-1], "END:VCALENDAR")
        self.assertEqual(out.count("BEGIN:VEVENT"), out.count("END:VEVENT"))
        self.assertTrue(all(len(l.encode("utf-8")) <= 75 for l in lines))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b"").rstrip(b"\n"))
        self.assertIn("DTSTART;VALUE=DATE:19690701", out)  # c. Jul 1969 = whole month
        self.assertIn("DTEND;VALUE=DATE:19690801", out)

    def test_ics_includes_converted_calendar_dates(self):
        out, _, _ = run(os.path.join(EX, "calendars", "events.json"), "-l", "ics")
        self.assertIn("SUMMARY:Last day of the Julian calendar", out)
        self.assertIn("DTSTART;VALUE=DATE:15821014", out)  # Julian 4 Oct = 14 Oct

    def test_ics_skips_bce_with_a_note(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump([{"date": "-44-03-15", "title": "Ides of March"},
                       {"date": "1969-07-20", "title": "Moon landing"}], fh)
        try:
            out, err, _ = run(fh.name, "-l", "ics")
            self.assertEqual(out.count("BEGIN:VEVENT"), 1)
            self.assertIn("before 1 CE", err)
        finally:
            os.unlink(fh.name)

    def test_timelinejs_keeps_bce(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump([{"date": "-44-03-15", "title": "Ides of March"}], fh)
        try:
            out, _, _ = run(fh.name, "-l", "timelinejs")
            self.assertEqual(json.loads(out)["events"][0]["start_date"]["year"], -44)
        finally:
            os.unlink(fh.name)

    def test_gantt_milestones_and_ranges(self):
        out, _, _ = run(os.path.join(EX, "presets", "project.json"), "-l", "gantt")
        self.assertIn("Project kickoff :milestone, t1, 2025-01-06, 0d", out)
        self.assertIn("Content migration finished :t4, 2025-03-01, 2025-04-01", out)


if __name__ == "__main__":
    unittest.main()
