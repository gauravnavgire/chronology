"""Score evaluation runs of the CHRONOLOGY skill against the gold standards.

A run folder (made by run_eval.py) holds the case inputs, whatever Claude wrote,
and transcript.jsonl (the `claude -p --output-format stream-json` stream).

What is measured, per case:
  triggered     the skill was invoked (Skill tool)
  script        scripts/chronology.py was run          verify   ... with --verify
  recall        gold events found (all / must-have)   precision  extracted events
                that match a gold event (extras are listed for review)
  dates         matched events whose window agrees with the gold window
  fake_precision vague gold dates given a precise, non-approximate date
  undated       undated items kept    issues   expected consistency issues raised
  quotes        share of extracted events carrying a `quote`
  patterns      required statements in Claude's answer   layout / granularity used

Usage:
  python eval/score.py RUN_DIR [RUN_DIR ...]      score case runs (writes score.json)
  python eval/score.py --report RUNS_PARENT       aggregate report.md for a batch
"""
import argparse
import contextlib
import glob
import io
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "chronology", "scripts"))
import chronology as c  # noqa: E402

VALUE_OPTS = {"-g", "--granularity", "-l", "--layout", "-t", "--title", "--top", "--levels",
              "-o", "--output", "--preset", "--tracks", "--lanes", "--state", "--since",
              "--save-state", "--min-confidence", "--from", "--to", "--as-of", "--before",
              "--after", "--entity", "--tag", "--source", "--search", "--verify",
              "--verify-sample", "--date-col", "--end-col", "--title-col", "--entity-col",
              "--tag-col", "--sql", "--table"}
TABLE_OPTS = {"--date-col": "date_col", "--end-col": "end_col", "--title-col": "title_col",
              "--entity-col": "entity_col", "--tag-col": "tag_col", "--sql": "sql",
              "--table": "table"}
LAYOUT_HINTS = {"tree": "├──", "table": "|---", "bullets": "\n- ", "timeline": "◆"}
SHELL_TOOLS = ("Bash", "PowerShell")


# ---------------------------------------------------------------- transcript

def read_transcript(run_dir):
    """Tool calls (with whether each was refused), text and the final result."""
    tools, texts, final, cost, turns, error = [], [], "", None, None, None
    path = os.path.join(run_dir, "transcript.jsonl")
    if not os.path.exists(path):
        return {"tools": [], "executed": [], "denied": [], "text": "", "final": "",
                "cost": None, "turns": None, "error": "no transcript"}
    by_id, denied_ids = {}, set()
    for line in io.open(path, encoding="utf-8", errors="replace"):
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        body = msg.get("message")
        blocks = body.get("content") if isinstance(body, dict) else None
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if msg.get("type") == "assistant" and block.get("type") == "tool_use":
                    call = (block.get("name"), block.get("input") or {})
                    tools.append(call)
                    by_id[block.get("id")] = call
                elif msg.get("type") == "assistant" and block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_result" and block.get("is_error") and \
                        "denied" in str(block.get("content", "")).lower():
                    denied_ids.add(block.get("tool_use_id"))
        if msg.get("type") == "result":
            final = msg.get("result") or ""
            cost = msg.get("total_cost_usd", msg.get("cost_usd"))
            turns = msg.get("num_turns")
            if msg.get("is_error"):
                error = final[:200] or msg.get("subtype") or "error"
    if not final and not tools and error is None:
        error = "session produced no result"
    denied = [by_id[i] for i in denied_ids if i in by_id]
    executed = [t for t in tools if not any(t is d for d in denied)]
    return {"tools": tools, "executed": executed, "denied": denied,
            "text": "\n".join(texts + [final]), "final": final,
            "cost": cost, "turns": turns, "error": error}


# "$S = '.../chronology.py'" (PowerShell) or "S=.../chronology.py" (sh)
ASSIGN_RE = re.compile(r"""^\s*\$?(\w+)\s*=\s*["']?([^"'\s;]*chronology\.py)["']?\s*$""")


def script_commands(tools):
    """chronology.py invocations (direct or via a variable holding its path):
    lists of argv after the script."""
    out = []
    for name, inp in tools:
        if name not in SHELL_TOOLS:
            continue
        # Windows paths: "\" is a separator, not an escape character.
        cmd = inp.get("command", "").replace("\\", "/")
        aliases = set()
        for seg in re.split(r"&&|\|\||;|\||\n", cmd):
            m = ASSIGN_RE.match(seg)
            if m:
                aliases.update({"$" + m.group(1), "${%s}" % m.group(1)})
                continue
            if "chronology.py" not in seg and not any(a in seg for a in aliases):
                continue
            try:
                toks = shlex.split(seg, posix=True)
            except ValueError:
                toks = seg.split()
            idx = next((i for i, t in enumerate(toks)
                        if t.endswith("chronology.py") or t in aliases), None)
            if idx is not None:
                out.append(toks[idx + 1:])
    return out


def parse_args(argv):
    """(inputs, options dict) from chronology.py argv."""
    inputs, opts, i = [], {}, 0
    while i < len(argv):
        t = argv[i]
        if t == "--how-long":
            i += 3
            continue
        if t in VALUE_OPTS:
            opts.setdefault(t, []).append(argv[i + 1] if i + 1 < len(argv) else "")
            i += 2
            continue
        if t.startswith("-"):
            opts.setdefault(t, []).append(True)
        else:
            inputs.append(t)
        i += 1
    return inputs, opts


def _resolve(run_dir, path):
    p = path if os.path.isabs(path) else os.path.join(run_dir, path)
    if os.path.exists(p):
        return p
    hits = [h for h in glob.glob(os.path.join(run_dir, "**", os.path.basename(path)),
                                 recursive=True) if ".claude" not in h]
    return hits[0] if hits else None


# ---------------------------------------------------------------- extracted events

def load_extracted(run_dir, cmds):
    """Events as the skill's script sees them, from the richest invocation."""
    best = None
    for argv in cmds:
        inputs, opts = parse_args(argv)
        files = [_resolve(run_dir, x) for x in inputs]
        files = [f for f in files if f]
        if files and (best is None or len(files) >= len(best[0])):
            best = (files, opts)
    source = "script"
    if best is None:  # fall back to event files on disk
        files = []
        for f in glob.glob(os.path.join(run_dir, "**", "*.json"), recursive=True):
            if ".claude" in f or os.path.basename(f) in ("score.json", "gold.json"):
                continue
            try:
                data = json.load(io.open(f, encoding="utf-8"))
            except (ValueError, OSError):
                continue
            items = data.get("events") if isinstance(data, dict) else data
            if isinstance(items, list) and items and isinstance(items[0], dict) and \
                    ("title" in items[0] or "date" in items[0]):
                files.append(f)
        if not files:
            return None, [], [], "none"
        best, source = (files, {}), "files-on-disk"
    files, opts = best
    table_opts = {v: opts[k][-1] for k, v in TABLE_OPTS.items() if k in opts}
    if "--dayfirst" in opts:
        table_opts["order"] = "dmy"
    if "--monthfirst" in opts:
        table_opts["order"] = "mdy"
    with contextlib.redirect_stderr(io.StringIO()):
        meta, events, _ = c.load_events(files, table_opts)
    for e in events:
        if e.start is not None:
            e.compute_interval()
    events = c.merge_events(events, auto="--auto-merge" in opts)
    gran = c.norm_level(opts.get("-g", opts.get("--granularity", ["day"]))[-1] or "day")
    if "--collapse" in opts:
        events = c.collapse_events(events, gran)
    by_id = {}
    for e in events:
        for v in getattr(e, "variants", [e]):
            if v.id is not None:
                by_id[v.id] = e
    issues = []
    c.derive_offsets(events, by_id, issues)
    dated = sorted((e for e in events if e.start is not None), key=c.Event.sort_key)
    issues += c.check_events(dated, by_id)
    return files, events, issues, source


# ---------------------------------------------------------------- matching

def gold_window(w):
    lo = c.period_bounds(c.parse_date(w[0]))[0]
    hi = c.period_bounds(c.parse_date(w[1]))[1]
    return lo, hi


def _text(e):
    return " ".join([e.title, e.details, e.quote] +
                    [str(s["event"].title) for s in e.sources]).lower()


def match(gold_events, extracted):
    dated = [e for e in extracted if e.start is not None]
    pairs = []
    for gi, g in enumerate(gold_events):
        glo, ghi = gold_window(g["window"])
        for ei, e in enumerate(dated):
            txt = _text(e)
            hits = sum(1 for k in g["keywords"] if k.lower() in txt)
            if not hits:
                continue
            elo, ehi = e.lo, max(e.hi, e.end_hi)
            overlap = elo <= ghi and glo <= ehi
            near = elo <= ghi + c.DAY and glo - c.DAY <= ehi
            if not near:
                continue
            pairs.append((not overlap, -hits / float(len(g["keywords"])), gi, ei))
    pairs.sort()
    used_g, used_e, result = set(), set(), {}
    for _, _, gi, ei in pairs:
        if gi in used_g or ei in used_e:
            continue
        used_g.add(gi)
        used_e.add(ei)
        result[gi] = dated[ei]
    return result, dated


def date_verdict(g, e):
    glo, ghi = gold_window(g["window"])
    elo, ehi = e.lo, max(e.hi, e.end_hi)
    slack = c.DAY if (ghi - glo) >= c.DAY - 1 else 3600
    if not (elo <= ghi and glo <= ehi):
        return "near"  # off by up to a day
    if elo >= glo - slack and ehi <= ghi + slack:
        return "exact"
    return "overlap"


def fake_precision(g, e):
    """A vague gold date given a much narrower, non-approximate date."""
    if not g.get("vague"):
        return False
    glo, ghi = gold_window(g["window"])
    narrow = (e.hi - e.lo) < 0.25 * (ghi - glo)
    flagged = e.approx or e.earliest is not None or e.latest is not None or e.derived
    return narrow and not flagged


# ---------------------------------------------------------------- one case

def score_case(run_dir, gold):
    tr = read_transcript(run_dir)
    if tr["error"]:  # the session failed: not a measurement of the skill
        return {"case": gold["id"], "error": tr["error"], "cost_usd": tr["cost"]}
    all_cmds = script_commands(tr["tools"])        # includes refused attempts
    cmds = script_commands(tr["executed"])         # actually executed
    refused = script_commands(tr["denied"])
    skills = [inp.get("skill", "") for name, inp in tr["tools"] if name == "Skill"]
    reads = [inp.get("file_path", "") for name, inp in tr["tools"] if name == "Read"]
    # Extraction is scored from the files Claude wrote, even if running the
    # script on them was refused (that refusal is a harness/permission matter).
    files, extracted, issues, source = load_extracted(run_dir, all_cmds)
    s = {"case": gold["id"], "source": source,
         "triggered": any("chronology" in x for x in skills), "skills": skills,
         "references_read": sorted({os.path.basename(r) for r in reads
                                    if "references" in r.replace("\\", "/")}),
         "script": bool(cmds), "script_refused": len(refused),
         "verify": any("--verify" in a for a in cmds),
         "verify_attempted": any("--verify" in a for a in all_cmds),
         "tests_run": any("unittest" in inp.get("command", "") for n, inp in tr["tools"]
                          if n in SHELL_TOOLS),
         "cost_usd": tr["cost"], "turns": tr["turns"]}
    gold_events = gold["events"]
    matched, dated = match(gold_events, extracted)
    s["gold_events"] = len(gold_events)
    s["extracted_dated"] = len(dated)
    s["extracted_undated"] = sum(1 for e in extracted if e.start is None)
    musts = [i for i, g in enumerate(gold_events) if g.get("must", True)]
    s["recall"] = round(len(matched) / float(len(gold_events)), 3) if gold_events else None
    s["recall_must"] = round(sum(1 for i in musts if i in matched) / float(len(musts)), 3) \
        if musts else None
    s["precision"] = round(len(matched) / float(len(dated)), 3) if dated else None
    verdicts = [date_verdict(gold_events[i], e) for i, e in matched.items()]
    s["dates"] = {v: verdicts.count(v) for v in ("exact", "overlap", "near")}
    s["date_accuracy"] = round(verdicts.count("exact") / float(len(verdicts)), 3) \
        if verdicts else None
    s["fake_precision"] = [gold_events[i]["key"] for i, e in matched.items()
                           if fake_precision(gold_events[i], e)]
    s["missed"] = [g["key"] for i, g in enumerate(gold_events) if i not in matched]
    used = set(map(id, matched.values()))
    s["unmatched_extracted"] = ["%s (%s)" % (e.title, e.exact()) for e in dated
                                if id(e) not in used][:15]
    # Undated items kept
    und = gold.get("undated", [])
    undated_text = [_text(e) for e in extracted if e.start is None]
    if und:
        s["undated_kept"] = sum(1 for kws in und if any(all(k in t for k in kws)
                                                         for t in undated_text)) / float(len(und))
    # Expected issues
    exp = gold.get("expect", {})
    if exp.get("issues"):
        found = []
        for want in exp["issues"]:
            hit = any(k == want["kind"] and any(w in m.lower() for w in want["keywords"])
                      for _, k, m, _ in issues)
            found.append(hit)
        s["issues_found"] = sum(found) / float(len(found))
    # Behaviours visible in the extracted data
    beh = {}
    for b in exp.get("behaviours", []):
        beh[b] = {
            "derived_dates": any(e.derived or e.offset for e in extracted),
            "merge_ids": any(e.doc_count() > 1 for e in extracted),
            "hedged": any(e.hedged or e.certainty for e in extracted),
            "planned": any(e.planned is not None for e in extracted),
            "julian": any(e.cal_start and "Julian" in e.cal_start[0] for e in extracted),
            "panchang": any(e.cal_start and re.search(r"\b(VS|Shaka)\b", e.cal_start[0])
                            for e in extracted),
            "table_input": any(f.lower().endswith((".csv", ".tsv", ".db", ".sqlite"))
                               for f in (files or [])),
        }.get(b, False)
    s["behaviours"] = beh
    json_events = [e for e in extracted if not str(e.doc).lower().endswith((".csv", ".tsv", ".db"))]
    s["quote_coverage"] = round(sum(1 for e in json_events if e.quote) / float(len(json_events)), 3) \
        if json_events else None
    # Answer patterns, layout, granularity, artifacts
    text = tr["text"]
    pats = exp.get("answer_patterns", [])
    s["patterns"] = {p[:50]: bool(re.search(p, text)) for p in pats}
    layouts = {c.LAYOUT_ALIASES.get(v.lower(), v.lower()) for a in cmds
               for v in parse_args(a)[1].get("-l", []) + parse_args(a)[1].get("--layout", [])}
    if exp.get("layout"):
        want = exp["layout"]
        s["layout_ok"] = want in layouts or LAYOUT_HINTS.get(want, "\x00") in tr["final"]
    if exp.get("granularity"):
        grans = set()
        for a in cmds:
            for v in parse_args(a)[1].get("-g", []) + parse_args(a)[1].get("--granularity", []):
                try:
                    grans.add(c.norm_level(v))
                except ValueError:
                    pass
        s["granularity_ok"] = exp["granularity"] in grans
    if exp.get("artifacts"):
        made = [os.path.relpath(f, run_dir) for f in glob.glob(os.path.join(run_dir, "**", "*"),
                                                              recursive=True)
                if os.path.isfile(f) and ".claude" not in f]
        s["artifacts_ok"] = all(any(re.search(p, m) for m in made) for p in exp["artifacts"])
    if exp.get("forbidden_dates"):
        real = [e for e in dated if 1000 <= e.start.year <= 2100]
        s["no_invented_dates"] = not real or "relative" in text.lower()
    return s


# ---------------------------------------------------------------- probes

def score_probe(run_dir, probe):
    tr = read_transcript(run_dir)
    if tr["error"]:
        return {"probe": probe["id"], "should_trigger": probe["should_trigger"],
                "error": tr["error"], "cost_usd": tr["cost"]}
    skills = [inp.get("skill", "") for name, inp in tr["tools"] if name == "Skill"]
    triggered = any("chronology" in x for x in skills)
    return {"probe": probe["id"], "should_trigger": probe["should_trigger"],
            "triggered": triggered, "correct": triggered == probe["should_trigger"],
            "cost_usd": tr["cost"]}


# ---------------------------------------------------------------- report

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / float(len(xs)), 3) if xs else None


def report(batch_dir):
    cases = [json.load(io.open(f, encoding="utf-8"))
             for f in sorted(glob.glob(os.path.join(batch_dir, "cases", "*", "score.json")))]
    probes = [json.load(io.open(f, encoding="utf-8"))
              for f in sorted(glob.glob(os.path.join(batch_dir, "probes", "*", "score.json")))]
    lines = ["# CHRONOLOGY skill — evaluation report", "", "Batch: `%s`" % batch_dir, ""]
    failed = [x for x in cases + probes if x.get("error")]
    if failed:
        lines += ["## ⚠ %d run(s) failed and are excluded" % len(failed), ""]
        lines += ["- %s: %s" % (x.get("case") or x.get("probe"), x["error"]) for x in failed]
        lines.append("")
    cases = [x for x in cases if not x.get("error")]
    probes = [x for x in probes if not x.get("error")]
    if probes:
        tp = sum(1 for p in probes if p["should_trigger"] and p["triggered"])
        fn = sum(1 for p in probes if p["should_trigger"] and not p["triggered"])
        fp = sum(1 for p in probes if not p["should_trigger"] and p["triggered"])
        tn = sum(1 for p in probes if not p["should_trigger"] and not p["triggered"])
        lines += ["## Triggering (%d probes)" % len(probes), "",
                  "| | triggered | not triggered |", "|---|---|---|",
                  "| should trigger | %d | %d |" % (tp, fn),
                  "| should not | %d | %d |" % (fp, tn), ""]
        wrong = [p["probe"] for p in probes if not p["correct"]]
        if wrong:
            lines += ["Wrong: " + ", ".join(wrong), ""]
    if cases:
        def rate(key):
            vals = [x.get(key) for x in cases if key in x]
            return "%d/%d" % (sum(1 for v in vals if v), len(vals)) if vals else "—"
        lines += ["## Cases (%d)" % len(cases), "",
                  "| Metric | Value |", "|---|---|",
                  "| Skill triggered | %s |" % rate("triggered"),
                  "| Ran the script | %s |" % rate("script"),
                  "| Ran the self-check (--verify) | %s |" % rate("verify"),
                  "| Attempted the self-check (incl. refused) | %s |" % rate("verify_attempted"),
                  "| Cases with script runs refused by permissions | %d |" % sum(
                      1 for x in cases if x.get("script_refused")),
                  "| Recall, all gold events (mean) | %s |" % _mean([x["recall"] for x in cases]),
                  "| Recall, must-have events (mean) | %s |" % _mean([x["recall_must"] for x in cases]),
                  "| Precision (mean) | %s |" % _mean([x["precision"] for x in cases]),
                  "| Date accuracy of matched events (mean) | %s |" % _mean([x["date_accuracy"] for x in cases]),
                  "| Fake-precision dates (total) | %d |" % sum(len(x["fake_precision"]) for x in cases),
                  "| Quote coverage (mean) | %s |" % _mean([x["quote_coverage"] for x in cases]),
                  "| Expected issues raised (mean) | %s |" % _mean([x.get("issues_found") for x in cases]),
                  "| Layout as requested | %s |" % rate("layout_ok"),
                  "| Granularity as requested | %s |" % rate("granularity_ok"),
                  "| Cost (USD, total) | %s |" % (round(sum(x["cost_usd"] or 0 for x in cases), 2)), "",
                  "| Case | Trig | Script | Verify | Recall (must) | Prec. | Dates exact | Fake prec. | Patterns | Missed |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for x in cases:
            pats = x.get("patterns", {})
            lines.append("| %s | %s | %s | %s | %s (%s) | %s | %s | %s | %s | %s |" % (
                x["case"], "✓" if x["triggered"] else "✗", "✓" if x["script"] else "✗",
                "✓" if x["verify"] else "✗", x["recall"], x["recall_must"], x["precision"],
                x["date_accuracy"], len(x["fake_precision"]) or "",
                "%d/%d" % (sum(pats.values()), len(pats)) if pats else "",
                ", ".join(x["missed"][:6])))
        lines.append("")
        for x in cases:
            notes = []
            for k in ("behaviours", "issues_found", "undated_kept", "layout_ok",
                      "granularity_ok", "artifacts_ok", "no_invented_dates", "references_read"):
                if k in x and x[k] not in ({}, None, []):
                    notes.append("%s: %s" % (k, x[k]))
            if x["unmatched_extracted"]:
                notes.append("unmatched extracted (review): " + "; ".join(x["unmatched_extracted"][:6]))
            if notes:
                lines += ["**%s** — %s" % (x["case"], " · ".join(notes)), ""]
    path = os.path.join(batch_dir, "report.md")
    io.open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--report", metavar="BATCH_DIR")
    a = ap.parse_args(argv)
    for run_dir in a.runs:
        meta = json.load(io.open(os.path.join(run_dir, "run.json"), encoding="utf-8"))
        if meta.get("kind") == "probe":
            s = score_probe(run_dir, meta["probe"])
        else:
            gold = json.load(io.open(os.path.join(HERE, "cases", meta["case"], "gold.json"),
                                     encoding="utf-8"))
            s = score_case(run_dir, gold)
        io.open(os.path.join(run_dir, "score.json"), "w", encoding="utf-8").write(
            json.dumps(s, ensure_ascii=False, indent=1))
        print("scored", run_dir)
    if a.report:
        print("report:", report(a.report))


if __name__ == "__main__":
    main()
