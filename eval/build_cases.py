"""Write the evaluation cases: input documents, prompts and gold standards.

Each case folder gets:
    inputs/      the documents Claude sees (copied into the run folder)
    gold.json    prompt, expectations and the gold-standard events (never shown)

Run:  python eval/build_cases.py
All documents are written for this evaluation (fictional unless noted), so
every event and date in them is known exactly.
"""
import csv
import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases")
sys.path.insert(0, os.path.join(HERE, "..", "chronology", "scripts"))


def ev(key, start, end=None, keywords=(), must=True, vague=False):
    """A gold event. start/end: ISO dates or date-times (end inclusive)."""
    return {"key": key, "window": [start, end or start], "keywords": list(keywords),
            "must": must, "vague": vague}


def write_case(name, prompt, inputs, events, **extra):
    d = os.path.join(CASES, name)
    os.makedirs(os.path.join(d, "inputs"), exist_ok=True)
    for fname, content in inputs.items():
        path = os.path.join(d, "inputs", fname)
        if isinstance(content, list):  # CSV rows
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                csv.writer(fh).writerows(content)
        else:
            with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content.strip() + "\n")
    gold = {"id": name, "prompt": prompt, "inputs": sorted(inputs), "should_trigger": True,
            "events": events}
    gold.update(extra)
    with io.open(os.path.join(d, "gold.json"), "w", encoding="utf-8") as fh:
        json.dump(gold, fh, ensure_ascii=False, indent=1)
    print("wrote", name, "(%d gold events)" % len(events))


# ---------------------------------------------------------------- 01 news article
write_case(
    "01-news-relative-dates",
    "Can you put the events in this article in chronological order? Day level is fine, "
    "as a table.",
    {"article.md": """
# Fire at old Harlow mill treated as suspicious

**RIVERTON, Friday 14 March 2025** — Fire crews were still damping down the old Harlow
textile mill on Friday morning, three days after a blaze broke out in its east wing.

The fire was first reported at 11:40 pm on Tuesday, according to the county fire
service, and was declared under control at around 6 am the next day. Two firefighters
were treated for smoke inhalation.

The mill, built in 1887, closed in 1994 and was bought by developer Kestrel Homes last
autumn. Kestrel submitted plans for 140 flats in January; a planning decision is due on
2 April.

Residents said they had seen people on the site "a week or so" before the fire. Police
said on Thursday that they were treating the fire as suspicious, and that they had
arrested a 19-year-old man the previous evening.

The council will meet on 28 March to discuss the site's safety.
"""},
    [ev("built", "1887", keywords=["built"]),
     ev("closed", "1994", keywords=["closed"]),
     ev("bought", "2024-09-01", "2024-11-30", ["bought", "kestrel"], vague=True),
     ev("plans", "2025-01", None, ["plans", "flats"]),
     ev("seen", "2025-02-25", "2025-03-08", ["people", "site", "seen"], must=False, vague=True),
     ev("fire-reported", "2025-03-11", None, ["fire", "reported"]),
     ev("under-control", "2025-03-12", None, ["control"]),
     ev("arrest", "2025-03-12", None, ["arrest"]),
     ev("suspicious", "2025-03-13", None, ["suspicious"]),
     ev("damping", "2025-03-14", None, ["damping", "crews"], must=False),
     ev("council", "2025-03-28", None, ["council"]),
     ev("planning-decision", "2025-04-02", None, ["planning", "decision"])],
    expect={"layout": "table", "behaviours": ["derived_dates"]})

# ---------------------------------------------------------------- 02 email thread
write_case(
    "02-email-timezones",
    "Build a timeline of what happened in this email thread, down to the hour, as a "
    "table. Times in UTC please.",
    {"thread.txt": """
From: Priya Nair (Bengaluru)
Date: Mon, 2 Jun 2025 10:15 +0530
Subject: Q2 data export

Hi Mark, the export job failed again last night, around 11. Can you take a look?

----
From: Mark Ellis (San Francisco)
Date: Mon, 2 Jun 2025 08:30 -0700
Subject: Re: Q2 data export

Looking now. It failed at 23:04 IST: the disk on db-2 was full. I'll clear some space
and rerun tonight.

----
From: Mark Ellis
Date: Tue, 3 Jun 2025 07:55 -0700
Subject: Re: Q2 data export

The rerun finished at 02:10 PDT. The export is in the bucket.

----
From: Priya Nair
Date: Tue, 3 Jun 2025 21:05 +0530
Subject: Re: Q2 data export

Thanks! The client signed off this afternoon. I'll close the ticket tomorrow.

----
From: Priya Nair
Date: Wed, 4 Jun 2025 09:00 +0530
Subject: Re: Q2 data export

Ticket closed.
"""},
    [ev("failed", "2025-06-01T17:00Z", "2025-06-01T18:00Z", ["fail"]),
     ev("reported", "2025-06-02T04:00Z", "2025-06-02T05:30Z", ["priya", "report", "look"], must=False),
     ev("diagnosed", "2025-06-02T15:00Z", "2025-06-02T16:00Z", ["disk", "full", "space"]),
     ev("rerun-done", "2025-06-03T09:00Z", "2025-06-03T10:00Z", ["rerun", "finished"]),
     ev("in-bucket", "2025-06-03T09:00Z", "2025-06-03T15:30Z", ["bucket", "deliver"], must=False),
     ev("signed-off", "2025-06-03T06:00Z", "2025-06-03T13:00Z", ["sign"], vague=True),
     ev("closed", "2025-06-03T18:00Z", "2025-06-04T04:00Z", ["closed"])],
    expect={"layout": "table", "granularity": "hour"})

# ---------------------------------------------------------------- 03 witnesses
write_case(
    "03-witnesses-conflict",
    "Here are two witness statements and the police dispatch log. Merge them into one "
    "chronology and tell me where the accounts disagree.",
    {"statement-ortiz.txt": """
Statement of Ana Ortiz, owner, Ortiz Cycles, 14 Elm Street. Taken 9 November 2025.

I locked up the shop at 6:15 pm on Saturday 8 November 2025 and set the alarm. When I
came back on Sunday morning, at about 8, the back door had been forced. Three e-bikes
were gone from the workshop.
""",
     "statement-chen.txt": """
Statement of Wei Chen, 16 Elm Street. Taken 9 November 2025.

On Saturday night I heard glass breaking behind the bike shop at about 11:30 pm. I called
the police straight away, at 11:30. I did not see anyone.
""",
     "dispatch-log.csv": [
         ["time", "unit", "entry"],
         ["2025-11-08 23:52", "Dispatch", "Call from neighbour reporting breaking glass, rear of 14 Elm St"],
         ["2025-11-09 00:07", "Unit 12", "On scene. Rear door forced, no one present"],
         ["2025-11-09 08:20", "Dispatch", "Owner reports 3 e-bikes stolen"]]},
    [ev("locked", "2025-11-08T18:15", None, ["lock"]),
     ev("glass", "2025-11-08T23:15", "2025-11-08T23:45", ["glass"]),
     ev("call", "2025-11-08T23:30", "2025-11-08T23:52", ["call"]),
     ev("on-scene", "2025-11-09T00:07", None, ["scene", "unit"]),
     ev("owner-returns", "2025-11-09T07:30", "2025-11-09T08:30", ["came back", "return", "owner"]),
     ev("reported-stolen", "2025-11-09T08:20", None, ["report", "stolen"]),
     ev("theft", "2025-11-08T18:15", "2025-11-09T08:00", ["e-bike", "gone", "stolen"],
        must=False, vague=True)],
    expect={"issues": [{"kind": "conflict", "keywords": ["call"]}],
            "answer_patterns": [r"(?i)(11:30|23:30)[\s\S]{0,200}(11:52|23:52)|(11:52|23:52)[\s\S]{0,200}(11:30|23:30)"],
            "behaviours": ["merge_ids"]})

# ---------------------------------------------------------------- 04 diary
write_case(
    "04-diary-vague-dates",
    "Make a year-by-year timeline of this diary as bullet points.",
    {"diary.md": """
# Diary of R. Hale (excerpts)

**3 January 1952.** Started at the bank today. Mr. Pike showed me the ledgers.

**Late spring.** Father's illness worse. The doctor comes every week now.

**June 1952.** Father died on the 14th, early in the morning.

That autumn I met Edith at the choir.

Around Christmas we became engaged.

The following winter was the coldest I can remember; we married in the February.

*(Loose page, undated)* Must remember to repay Tom the five shillings.
"""},
    [ev("bank", "1952-01-03", None, ["bank"]),
     ev("illness", "1952-04-15", "1952-06-14", ["illness", "doctor"], vague=True),
     ev("father-died", "1952-06-14", None, ["died"]),
     ev("met-edith", "1952-09-01", "1952-11-30", ["edith", "met"], vague=True),
     ev("engaged", "1952-12-10", "1953-01-10", ["engaged"], vague=True),
     ev("married", "1953-02", None, ["married"], vague=True)],
    undated=[["repay", "tom"]],
    expect={"layout": "bullets", "granularity": "year"})

# ---------------------------------------------------------------- 05 flashbacks
write_case(
    "05-story-flashbacks",
    "Map the flashbacks in this story: what order is it told in, versus what actually "
    "happened?",
    {"story-notes.md": """
# The Boat (plot summary, chapter by chapter)

1. Lisbon, May 1999. Marta stands at her mother's grave.
2. She remembers the summer of 1975, when her mother taught her to sail.
3. Back in the present, the lawyer's letter arrives on 2 June 1999.
4. Years later, in 2012, Marta will sell the boat and regret it.
5. In 1988 her mother had sent her away to school in Porto.
6. The following spring Marta ran away and came home.
7. In June 1999 Marta finally opens the box of letters.
8. Epilogue, 2020: Marta's daughter learns to sail.
"""},
    [ev("grave", "1999-05", None, ["grave"]),
     ev("sailing-1975", "1975-06-01", "1975-08-31", ["sail", "summer"], vague=True),
     ev("letter", "1999-06-02", None, ["lawyer", "letter"]),
     ev("sell-boat", "2012", None, ["sell", "boat"]),
     ev("porto", "1988", None, ["porto", "school"]),
     ev("ran-away", "1989-03-01", "1989-05-31", ["ran away", "home"], vague=True),
     ev("box", "1999-06", None, ["box"]),
     ev("daughter", "2020", None, ["daughter"])],
    expect={"layout": "telling",
            "answer_patterns": [r"(?i)flash-?back[\s\S]{0,400}1975|1975[\s\S]{0,400}flash-?back",
                                r"(?i)flash-?forward[\s\S]{0,400}2012|2012[\s\S]{0,400}flash-?forward"]})

# ---------------------------------------------------------------- 06 incident (CSV)
random.seed(6)
base = 1758117600  # 2025-09-17 14:00:00 UTC
rows = [["timestamp", "severity", "service", "message"],
        [base + 131, "info", "payments", "deploy payments v3.2 started"]]
for i in range(30):
    rows.append([base + 400 + i * 6, "error", "checkout", "HTTP 503 from payments upstream"])
rows += [[base + 542, "warn", "pager", "on-call paged: checkout error rate > 20%"],
         [base + 1297, "info", "payments", "rollback to v3.1 started"],
         [base + 1625, "info", "checkout", "error rate back to baseline"]]
write_case(
    "06-incident-log",
    "Here's the alert log export and my notes from yesterday's outage. Build the incident "
    "timeline for the postmortem.",
    {"alerts.csv": rows,
     "notes.md": """
Outage notes, 17 Sep 2025 (all times UTC)

- We think the DB connection pool ran out a bit before the errors started, probably
  around 14:05, but nobody checked the graphs at the time.
- Rollback started at 14:21.
- All clear was posted in #incidents at 14:40.
"""},
    [ev("deploy", "2025-09-17T14:02Z", "2025-09-17T14:03Z", ["deploy"]),
     ev("pool", "2025-09-17T14:00Z", "2025-09-17T14:07Z", ["pool"], vague=True),
     ev("errors", "2025-09-17T14:06Z", "2025-09-17T14:10Z", ["503", "error"]),
     ev("paged", "2025-09-17T14:09Z", "2025-09-17T14:10Z", ["page"]),
     ev("rollback", "2025-09-17T14:21Z", "2025-09-17T14:22Z", ["rollback"]),
     ev("recovered", "2025-09-17T14:27Z", "2025-09-17T14:28Z", ["baseline"]),
     ev("all-clear", "2025-09-17T14:40Z", "2025-09-17T14:41Z", ["clear"])],
    expect={"behaviours": ["table_input", "hedged"]})

# ---------------------------------------------------------------- 07 project slips
write_case(
    "07-project-slippage",
    "Which milestones in these status reports slipped, and by how much? Give me a "
    "week-level timeline too.",
    {"status-reports.md": """
## Status report 1 — 6 January 2025
Project kicked off today. Plan: design sign-off on 7 February; new API in staging by
28 March; content migration done by the end of February; public launch on 11 April.

## Status report 2 — 17 February 2025
Design was signed off on 14 February.

## Status report 3 — 31 March 2025
The API reached staging on 21 March. Content migration finished during March.

## Status report 4 — 5 May 2025
We launched on 2 May.
"""},
    [ev("kickoff", "2025-01-06", None, ["kick"]),
     ev("design", "2025-02-14", None, ["design"]),
     ev("api", "2025-03-21", None, ["api"]),
     ev("content", "2025-03", None, ["content", "migration"]),
     ev("launch", "2025-05-02", None, ["launch"])],
    expect={"behaviours": ["planned"],
            "answer_patterns": [r"(?i)launch[\s\S]{0,300}(21 days|3 weeks|three weeks)",
                                r"(?i)design[\s\S]{0,300}(7 days|1 week|one week)",
                                r"(?i)api[\s\S]{0,300}(early|ahead)"]})

# ---------------------------------------------------------------- 08 Old Style
write_case(
    "08-old-style-letters",
    "Put these letters, and the events mentioned in them, in chronological order by day. "
    "Some use Old Style dates, so make sure they sort correctly.",
    {"letters.md": """
# Letters of the Bristow family (transcriptions)

**London, 1 January 1731.** Brother — the ship *Mary* sailed for Boston yesterday with
our cloth aboard. *(England, Old Style: the year began on 25 March.)*

**London, 11 February 1731/2.** No news of the *Mary* yet.

**Paris, 3 March 1732 (N.S.).** Your letter of 11 February reached me today.

**London, 25 March 1732.** Lady Day, and the new year begins. Rents collected.

**Boston, 14 June 1732.** The *Mary* arrived here on 2 June, all cloth dry.
"""},
    [ev("mary-sails", "1732-01-11", None, ["sail"]),
     ev("letter-jan", "1732-01-12", None, ["1 january", "london"], must=False),
     ev("letter-feb", "1732-02-22", None, ["no news", "11 february"]),
     ev("paris", "1732-03-03", None, ["paris", "reached"]),
     ev("lady-day", "1732-04-05", None, ["lady day", "rents"]),
     ev("mary-arrives", "1732-06-13", None, ["arrived"]),
     ev("letter-boston", "1732-06-25", None, ["boston", "14 june"], must=False)],
    expect={"behaviours": ["julian"]})

# ---------------------------------------------------------------- 09 panchang
import chronology as _c  # noqa: E402  (gold for the panchang case: see note below)


def _pday(text):
    _, _, (first, nxt), _ = _c.panchang_window(text, {"panchang": {"location": "ujjain"}})
    return _c.exact_label(_c.from_seconds(first * 86400, "day")), first, nxt


_born = _pday("VS 2041 Chaitra shukla 9")
_married = _pday("purnimanta VS 2065 Vaishakha krishna 3")
_house = _pday("VS 2080 adhika Shravana shukla 5")


def _iso(day):
    dp = _c.from_seconds(day * 86400, "day")
    return "%04d-%02d-%02d" % (dp.year, dp.month, dp.day)


write_case(
    "09-panchang-family-record",
    "This is from our family record book (bahi), in Ujjain. Convert the Samvat dates and "
    "put the family events in order.",
    {"bahi.md": """
Family record — Sharma family, Ujjain

- Samvat 2041, Chaitra sudi 9 (Ram Navami): Ramesh was born.
- Samvat 2065, Vaishakh vadi 3 (purnimanta reckoning, as used in our family): Ramesh
  married Sunita.
- Samvat 2080, Adhik Shravan sudi 5: griha pravesh of the new house on Freeganj Road.
- Every year on Diwali we light a lamp for Dadaji.
"""},
    [ev("born", _iso(_born[1] - 1), _iso(_born[2]), ["born"]),
     ev("married", _iso(_married[1] - 1), _iso(_married[2]), ["marri"]),
     ev("griha-pravesh", _iso(_house[1] - 1), _iso(_house[2]), ["griha", "house"])],
    note="Gold dates for this case were computed with the skill's own panchang code "
         "(validated separately against published timings), +/-1 day; the case tests "
         "whether Claude writes panchang-prefixed dates, not the conversion itself.",
    expect={"behaviours": ["panchang"]})

# ---------------------------------------------------------------- 10 anachronism
write_case(
    "10-bio-does-it-add-up",
    "Does the timeline in this short bio add up? List anything that can't be right.",
    {"bio.md": """
# Dana Ruiz — photographer

Dana Ruiz was born on 12 May 1981 in Valencia. She studied fine art in Madrid from 1999
to 2003. In 2003 she posted her first street photographs on Instagram, which brought her
first commissions. She founded Lumen Studio in Barcelona in 2011.

Her mentor, the photographer Carl Weiss, died in March 2015. In 2017, when Dana won the
National Photography Prize, Weiss personally called to congratulate her.
"""},
    [ev("born", "1981-05-12", None, ["born"]),
     ev("studied", "1999", "2003", ["studied", "madrid"]),
     ev("instagram", "2003", None, ["instagram"]),
     ev("lumen", "2011", None, ["lumen", "founded"]),
     ev("weiss-died", "2015-03", None, ["died", "weiss"]),
     ev("prize", "2017", None, ["prize"]),
     ev("congratulated", "2017", None, ["congratulat"])],
    expect={"issues": [{"kind": "anachronism", "keywords": ["instagram"]},
                       {"kind": "lifespan", "keywords": ["weiss", "congratulat"]}],
            "answer_patterns": [r"(?i)instagram[\s\S]{0,300}(2010|did not exist|didn't exist|launched)",
                                r"(?i)(weiss|mentor)[\s\S]{0,300}(died|dead|death|after)"]})

# ---------------------------------------------------------------- 11 how long
write_case(
    "11-how-long-question",
    "From these notes: how long was it between the first symptoms and the diagnosis?",
    {"notes.md": """
My notes (for the specialist appointment)

- First noticed the cough in early October 2024.
- Saw the GP on 21 October 2024; given antibiotics.
- Cough still there; chest X-ray on 4 November 2024.
- Diagnosed with asthma on 18 November 2024 by Dr Osei.
"""},
    [ev("first-symptoms", "2024-10-01", "2024-10-10", ["cough", "noticed"], vague=True),
     ev("gp", "2024-10-21", None, ["gp"]),
     ev("xray", "2024-11-04", None, ["x-ray", "xray"]),
     ev("diagnosis", "2024-11-18", None, ["diagnos"])],
    expect={"answer_patterns": [r"(?i)(6|six|7|seven)\s*(to|–|-|or)?\s*(7|seven)?\s*weeks|"
                                r"(39|4[0-8])\s*(to|–|-)?\s*(\d+\s*)?days|1\.?[45]\s*months|"
                                r"about (a month and a half|six weeks|seven weeks)"]})

# ---------------------------------------------------------------- 12 long document
random.seed(12)
sections, gold12 = [], []
filler = [
    "The company's culture during these years was shaped as much by its customers as by "
    "its founders, and many long-serving staff later described the period as formative.",
    "Internal memos from the time show lively debate about priorities, budgets and the "
    "pace of growth, much of it inconclusive.",
    "Trade press coverage was generally positive, though some analysts questioned whether "
    "the firm could sustain its margins.",
    "Staff numbers rose and fell with demand, and the leadership team tried several "
    "organisational structures before settling on regional divisions.",
    "Customers in the water industry remained the backbone of the order book, and the "
    "sales team spent much of its time on long tender processes.",
    "Engineering meetings were famously informal: decisions were often taken on the shop "
    "floor, and minutes were written up afterwards, if at all.",
    "The finance director of the time kept a tight grip on capital spending, which some "
    "engineers resented and others credited with keeping the firm independent.",
    "Apprentices continued to be the main route into the company, and several later "
    "directors started their careers on the bench.",
]
# (date, sentence that follows "In 1962, " / "On 2 November 1969, ", keywords)
milestones = [
    ("1962", "Ted Archer and Frank Mills founded the business as a two-person repair "
             "workshop in Leeds", ["founded", "workshop"]),
    ("1964-03", "the firm hired its first employee, an apprentice called Joan Mills",
     ["employee", "joan"]),
    ("1967", "the workshop moved to a larger unit on Kirkstall Road", ["kirkstall"]),
    ("1969-11-02", "the first export order was shipped to Rotterdam", ["export", "rotterdam"]),
    ("1971", "the business was incorporated as Mills & Archer Ltd", ["incorporated"]),
    ("1973-10", "the oil crisis cut the order book in half", ["oil crisis"]),
    ("1975", "a contract for hospital equipment brought the firm back to profit",
     ["hospital"]),
    ("1978-06-19", "a second factory opened in Bradford", ["bradford"]),
    ("1980", "the workforce passed 200 people", ["200", "workforce"]),
    ("1983-09", "the company launched its M-series pump", ["m-series"]),
    ("1985", "Mills & Archer won the Queen's Award for Export", ["queen", "award"]),
    ("1987-10-19", "as markets crashed on Black Monday, the directors bought back shares",
     ["black monday", "bought back"]),
    ("1990", "Ted Archer retired from the board", ["archer", "retired"]),
    ("1992-04", "Joan Mills became managing director", ["managing director"]),
    ("1994", "an office opened in Lyon to serve French customers", ["lyon"]),
    ("1997-07-01", "the company's first website went live", ["website"]),
    ("1999", "both factories gained ISO 9001 certification", ["iso"]),
    ("2001-01", "Mills & Archer acquired its rival Pennine Pumps", ["pennine"]),
    ("2003", "a flood badly damaged the Bradford factory", ["flood"]),
    ("2005-05-16", "the rebuilt Bradford factory reopened", ["reopened"]),
    ("2008", "orders fell sharply in the financial crisis", ["financial crisis"]),
    ("2010-02", "the company launched its first electric drive line", ["electric"]),
    ("2012", "Joan Mills retired after 48 years with the firm", ["retired", "48"]),
    ("2014-09-08", "the shares were listed on the AIM market", ["aim"]),
    ("2016", "a research lab opened in partnership with Leeds University",
     ["research", "university"]),
    ("2018-03", "the company recalled 1,200 units of its E4 drive", ["recall", "e4"]),
    ("2020-03-23", "both factories closed for the first lockdown", ["lockdown"]),
    ("2020-06", "the factories reopened with shift working", ["shift"]),
    ("2022", "revenue passed £100 million for the first time", ["100 million", "revenue"]),
    ("2024-11-05", "the board announced merger talks with Hartmann AG", ["hartmann"]),
]
for i, (date, text, kws) in enumerate(milestones):
    if len(date) == 4:
        phrase = "In %s" % date
    elif len(date) == 7:
        y, m = date.split("-")
        phrase = "In %s %s" % (["January", "February", "March", "April", "May", "June", "July",
                                "August", "September", "October", "November", "December"][int(m) - 1], y)
    else:
        y, m, d = date.split("-")
        phrase = "On %d %s %s" % (int(d), ["January", "February", "March", "April", "May", "June",
                                         "July", "August", "September", "October", "November",
                                         "December"][int(m) - 1], y)
    para = "%s, %s." % (phrase, text)
    body = " ".join(random.sample(filler, 4))
    words = text.split(",")[0].split()
    heading = " ".join(words[:7]) + (" …" if len(words) > 7 else "")
    heading = heading[0].upper() + heading[1:]
    sections.append("## %d. %s\n\n%s %s\n" % (i + 1, heading, para, body))
    gold12.append(ev("m%02d" % (i + 1), date, None, kws))
sections.insert(9, "## Interlude\n\nTwo years after the Bradford factory opened, the board "
                   "approved the company's first pension scheme. " + filler[1] + "\n")
gold12.append(ev("pension", "1980", None, ["pension"]))
write_case(
    "12-long-company-history",
    "Here's our company history document. Make a chronology at year level as a tree, "
    "grouped by decade.",
    {"company-history.md": "# Mills & Archer: a company history\n\n" + "\n".join(sections)},
    gold12, expect={"layout": "tree", "granularity": "year"})

# ---------------------------------------------------------------- 13 no dates
write_case(
    "13-no-dates-recipe",
    "Put this in chronological order as a timeline.",
    {"recipe.md": """
# Grandma's bread

First, dissolve the yeast in warm water and leave it for ten minutes. Then mix in the
flour and salt, and knead for about eight minutes. Leave the dough to rise for an hour.
Knock it back, shape it into a loaf and let it prove for 30 minutes. Finally, bake at
220°C for 35 minutes.
"""},
    [],
    expect={"forbidden_dates": True,
            "answer_patterns": [r"(?i)(no (calendar )?dates|not dated|doesn't (contain|have|include) (any )?dates|"
                                r"does not (contain|have|include) (any )?dates|relative|sequence|T\+|minute)"]})

# ---------------------------------------------------------------- 14 outputs
write_case(
    "14-html-and-calendar",
    "Here are my conference notes. Give me something I can click through in a browser, "
    "and a calendar file I can import.",
    {"conference.md": """
# DevCon Lisbon 2025 — my schedule (all times Lisbon, UTC+1)

- 7 Oct 2025, 09:00 — Opening keynote (main hall)
- 7 Oct 2025, 11:30 — Talk: Observability at scale
- 7 Oct 2025, 15:00 — Workshop: Rust for Python developers (until 17:00)
- 8 Oct 2025, 10:00 — Panel: AI in production
- 8 Oct 2025, 19:30 — Speakers' dinner, Time Out Market
- 9 Oct 2025, 12:00 — Closing session
"""},
    [ev("keynote", "2025-10-07T08:00Z", "2025-10-07T08:00Z", ["keynote"]),
     ev("observability", "2025-10-07T10:30Z", None, ["observability"]),
     ev("workshop", "2025-10-07T14:00Z", "2025-10-07T16:00Z", ["rust", "workshop"]),
     ev("panel", "2025-10-08T09:00Z", None, ["panel"]),
     ev("dinner", "2025-10-08T18:30Z", None, ["dinner"]),
     ev("closing", "2025-10-09T11:00Z", None, ["closing"])],
    expect={"artifacts": [r"\.html$", r"\.ics$"]})

# ---------------------------------------------------------------- trigger probes
probes = [
    ("Put these events in order: the bridge opened in 1932, construction began in 1923, "
     "and the design competition was held in 1921.", True),
    ("What happened when in this text? 'On 3 May we signed; two weeks later the money "
     "arrived; the project started on 1 June.'", True),
    ("Does this sequence add up? 'He was born in 1950, retired in 1985 at age 40, and "
     "started his first job in 1972.'", True),
    ("Convert Samvat 2081 Chaitra shukla 9 to a Gregorian date.", True),
    ("Make a timeline of these notes by month: Jan 2024 hired Ana; March 2024 launched v2; "
     "Feb 2024 office move.", True),
    ("Here are three accounts of the meeting with different times — which is right and "
     "where do they disagree? A: 2pm. B: 2:30pm. C: around 3.", True),
    ("What's today's date?", False),
    ("Write a React component that renders a vertical timeline.", False),
    ("Summarize this paragraph: 'The committee met to discuss the budget and agreed to "
     "postpone a decision.'", False),
    ("Convert 250 euros to US dollars.", False),
    ("Sort this list alphabetically: pear, apple, mango.", False),
    ("Write a cron expression for every Monday at 9am.", False),
]
with io.open(os.path.join(HERE, "trigger_probes.json"), "w", encoding="utf-8") as fh:
    json.dump([{"id": "t%02d" % (i + 1), "prompt": p, "should_trigger": t}
               for i, (p, t) in enumerate(probes)], fh, ensure_ascii=False, indent=1)
print("wrote trigger_probes.json (%d probes)" % len(probes))
