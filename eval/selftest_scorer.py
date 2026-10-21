"""Check that score.py itself works, using fabricated runs (no Claude calls).

For every case an "ideal" run is built straight from the gold standard (all
events, right dates, quotes, skill triggered, self-check run) and a "poor" run
(half the events, vague dates given fake precision, no skill, no self-check).
The ideal run must score perfectly; the poor one must be caught on each fault.

Run:  python eval/selftest_scorer.py
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import score  # noqa: E402


def fake_events(gold, ideal):
    out = []
    for i, g in enumerate(gold["events"]):
        if not ideal and i % 2:
            continue  # the poor run misses every other event
        start, end = g["window"]
        e = {"id": g["key"], "title": " ".join(g["keywords"]) + " event",
             "quote": " ".join(g["keywords"]) if ideal else ""}
        if start == end:
            e["date"] = start
        elif g.get("vague"):
            if ideal:
                e.update(date=start, earliest=start, latest=end)
            else:
                # fake precision: a precise instant/day for a vague window
                e["date"] = (start[:16] if "T" in start else
                             start[:10] if len(start) >= 10 else start + "-01-01")
        else:
            e.update(date=start, end=end)
        out.append(e)
    for kws in gold.get("undated", []):
        if ideal:
            out.append({"title": " ".join(kws), "date": None, "quote": " ".join(kws)})
    return out


def fake_run(root, gold, ideal):
    run_dir = os.path.join(root, gold["id"] + ("-ideal" if ideal else "-poor"))
    os.makedirs(run_dir)
    with io.open(os.path.join(run_dir, "events.json"), "w", encoding="utf-8") as fh:
        json.dump({"source_document": "doc.md", "events": fake_events(gold, ideal)}, fh)
    exp = gold.get("expect", {})
    cmd = "python .claude/skills/chronology/scripts/chronology.py events.json"
    if exp.get("layout"):
        cmd += " -l " + exp["layout"]
    if exp.get("granularity"):
        cmd += " -g " + exp["granularity"]
    tools = []
    if ideal:
        tools.append({"type": "tool_use", "name": "Skill", "input": {"skill": "chronology"}})
        tools.append({"type": "tool_use", "name": "Bash", "input": {"command": cmd}})
        tools.append({"type": "tool_use", "name": "Bash",
                      "input": {"command": cmd.split(" -l")[0] + " --verify doc.md --report-only"}})
    final = "Answer text. " + " ".join(
        {"(11:30|23:30)": "the neighbour says 11:30 but the log says 23:52",
         "1975": "flashback to 1975", "2012": "flash-forward to 2012",
         "launch": "launch was late by 21 days", "design": "design was late by 7 days",
         "api": "the API was early", "instagram": "Instagram launched in 2010",
         "weiss": "Weiss had died before 2017", "weeks": "about 6 to 7 weeks",
         "no (calendar )?dates": "there are no dates, only a sequence"}.values()) \
        if ideal else "Here is your timeline."  # a poor run still answers, badly
    with io.open(os.path.join(run_dir, "transcript.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"content": tools}}) + "\n")
        fh.write(json.dumps({"type": "result", "result": final, "total_cost_usd": 0}) + "\n")
    return score.score_case(run_dir, gold)


def main():
    root = tempfile.mkdtemp(prefix="chronology-scorer-")
    failures = []
    try:
        for name in sorted(os.listdir(os.path.join(HERE, "cases"))):
            gold = json.load(io.open(os.path.join(HERE, "cases", name, "gold.json"),
                                     encoding="utf-8"))
            good = fake_run(root, gold, True)
            bad = fake_run(root, gold, False)
            checks = []
            if gold["events"]:
                checks += [
                    ("ideal recall 1.0", good["recall"] == 1.0),
                    ("ideal precision 1.0", good["precision"] == 1.0),
                    ("ideal dates all exact", good["date_accuracy"] == 1.0),
                    ("ideal no fake precision", not good["fake_precision"]),
                    ("ideal quotes 100%", good["quote_coverage"] == 1.0),
                    ("poor recall lower", bad["recall"] is None or bad["recall"] < good["recall"]),
                ]
                if any(g.get("vague") for g in gold["events"][::2]):
                    checks.append(("poor fake precision caught", bool(bad["fake_precision"])))
            checks += [("ideal triggered + verify", good["triggered"] and good["verify"]),
                       ("poor not triggered", not bad["triggered"] and not bad["verify"])]
            if "undated_kept" in good:
                checks.append(("ideal undated kept", good["undated_kept"] == 1.0))
            if good.get("patterns"):
                checks.append(("ideal patterns all pass", all(good["patterns"].values())))
            if "layout_ok" in good:
                checks.append(("ideal layout ok", good["layout_ok"]))
            if "granularity_ok" in good:
                checks.append(("ideal granularity ok", good["granularity_ok"]))
            failed = [n for n, ok in checks if not ok]
            print("%-30s %s" % (name, "OK (%d checks)" % len(checks) if not failed
                                else "FAILED: " + "; ".join(failed)))
            if failed:
                failures.append((name, failed, good, bad))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    for name, failed, good, bad in failures:
        print("\n%s ideal: %s" % (name, json.dumps({k: good[k] for k in
              ("recall", "precision", "date_accuracy", "fake_precision", "missed", "dates",
               "unmatched_extracted", "patterns")}, ensure_ascii=False)))
    print("\nscorer self-test:", "PASSED" if not failures else "%d case(s) FAILED" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
