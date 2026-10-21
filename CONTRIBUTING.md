# Contributing

Thanks for helping. Bug reports, new test cases and pull requests are all
welcome.

## Setup

No dependencies: Python 3.9+ and its standard library.

```bash
git clone https://github.com/gauravnavgire/chronology
cd chronology
cd chronology && python -m unittest discover -s tests && cd ..   # engine tests
python eval/selftest_scorer.py                                     # evaluation scorer (no API calls)
```

The same checks run in CI on Linux and Windows for Python 3.9, 3.11 and 3.13.

## How the project is organised

- `chronology/SKILL.md` is what Claude reads first. Keep it short (under
  about 200 lines). Detail belongs in `chronology/references/`.
- `chronology/scripts/chronology.py` is the deterministic engine. Anything
  involving dates, ordering or checks belongs here, not in prose.
- `chronology/tests/` holds the unit tests. Every fix or feature needs a test
  with an answer that is **known independently** (a published date, a
  documented record), not just "what the code printed".
- `eval/` holds the skill evaluation: realistic documents with answer keys,
  run through real Claude sessions. New cases are very welcome, especially
  real documents with hand-made answer keys.

## Good first issues

- **More calendars:** Hindu solar calendars (Tamil, Malayalam, Bengali), the
  Chinese calendar, the Persian (Solar Hijri) calendar, the Ethiopian
  calendar.
- **More date languages in tables:** French, German, Spanish and Hindi month
  names in `cell_to_date`.
- **Excel input** without extra dependencies (the `.xlsx` format is zipped XML).
- **More evaluation cases:** e.g. a real 50-page PDF with an answer key.
- **Accessibility** checks of the HTML page (keyboard navigation, screen readers).

## Pull requests

- One topic per pull request, with tests.
- If you change the HTML template, regenerate the example pages (see
  `chronology/examples/README.md`) so the live demo stays current.
- Calendar or astronomy changes: say what you checked them against.
