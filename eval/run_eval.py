"""Run the CHRONOLOGY evaluation with headless Claude Code (`claude -p`).

Each case (and each trigger probe) runs in its own folder under eval/runs/<batch>/:
the case inputs are copied in (never the gold standard), the current skill is
installed as a project skill in .claude/skills/chronology, and the full
transcript is saved as transcript.jsonl. Runs are then scored (score.py) and a
report is written to eval/runs/<batch>/report.md.

Usage:
  python eval/run_eval.py --dry-run                 show what would run (no cost)
  python eval/run_eval.py --cases 01,03 --budget 1  run two cases, $1 cap each
  python eval/run_eval.py --probes                  only the trigger probes
  python eval/run_eval.py --all                     cases + probes
Options: --model NAME, --budget USD (per run, default 2), --timeout SECONDS.
"""
import argparse
import datetime as dt
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, "..", "chronology"))
TOOLS = ["Skill", "Read", "Write", "Edit", "Glob", "Grep",
         "Bash(python:*)", "Bash(python3:*)", "Bash(py:*)", "Bash(ls:*)",
         "Bash(mkdir:*)", "Bash(pdftotext:*)"]


def install(run_dir, inputs_dir=None):
    os.makedirs(run_dir, exist_ok=True)
    if inputs_dir:
        for f in os.listdir(inputs_dir):
            shutil.copy2(os.path.join(inputs_dir, f), run_dir)
    shutil.copytree(SKILL, os.path.join(run_dir, ".claude", "skills", "chronology"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def claude_cmd(prompt, a):
    exe = shutil.which("claude") or "claude"
    cmd = [exe, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "dontAsk", "--allowedTools"] + TOOLS + [
           "--max-budget-usd", str(a.budget), "--strict-mcp-config",
           "--setting-sources", "project", "--no-session-persistence"]
    if a.model:
        cmd += ["--model", a.model]
    return cmd


def run_one(run_dir, prompt, meta, a):
    io.open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8").write(
        json.dumps(dict(meta, prompt=prompt, model=a.model, budget=a.budget), indent=1))
    cmd = claude_cmd(prompt, a)
    if a.dry_run:
        print("  would run in %s:\n    %s" % (run_dir, " ".join(
            x if " " not in x else '"%s"' % x for x in cmd[:3]) + " ..."))
        return
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # allow launching from inside a Claude Code session
    if a.use_login:  # bill the stored Claude Code login, not an API key in the env
        for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(var, None)
    t0 = time.time()
    with io.open(os.path.join(run_dir, "transcript.jsonl"), "w", encoding="utf-8") as out, \
            io.open(os.path.join(run_dir, "stderr.txt"), "w", encoding="utf-8") as err:
        try:
            subprocess.run(cmd, cwd=run_dir, stdout=out, stderr=err, env=env,
                           timeout=a.timeout, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            err.write("\nTIMEOUT after %ss\n" % a.timeout)
    print("  done in %.0fs" % (time.time() - t0))
    # Stop the whole batch on authentication failures: every run would fail.
    with io.open(os.path.join(run_dir, "transcript.jsonl"), encoding="utf-8",
                 errors="replace") as fh:
        text = fh.read()
    if re.search(r"(?i)invalid api key|authentication_error|please run /login|"
                 r"not logged in|oauth token has expired", text):
        raise SystemExit("Authentication failed in %s: fix the API key / login and "
                         "re-run (see transcript.jsonl). Stopping the batch." % run_dir)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", help="comma-separated case numbers or names (default: all)")
    ap.add_argument("--probes", action="store_true", help="run the trigger probes")
    ap.add_argument("--all", action="store_true", help="cases and probes")
    ap.add_argument("--model")
    ap.add_argument("--budget", type=float, default=2.0, help="USD cap per run")
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--batch", help="batch folder name (default: timestamp)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--use-login", action="store_true",
                    help="ignore ANTHROPIC_API_KEY in the environment and use the "
                         "Claude Code login stored on this machine")
    a = ap.parse_args(argv)

    batch = os.path.join(HERE, "runs", a.batch or dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    run_cases = a.all or not a.probes or a.cases
    run_probes = a.all or a.probes
    scored = []
    if run_cases:
        names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, "cases", "*")))
        if a.cases:
            want = [w.strip() for w in a.cases.split(",")]
            names = [n for n in names if any(n == w or n.startswith(w + "-") for w in want)]
        for name in names:
            gold = json.load(io.open(os.path.join(HERE, "cases", name, "gold.json"),
                                     encoding="utf-8"))
            run_dir = os.path.join(batch, "cases", name)
            print("case", name)
            install(run_dir, os.path.join(HERE, "cases", name, "inputs"))
            run_one(run_dir, gold["prompt"], {"kind": "case", "case": name}, a)
            scored.append(run_dir)
    if run_probes:
        probes = json.load(io.open(os.path.join(HERE, "trigger_probes.json"), encoding="utf-8"))
        for p in probes:
            run_dir = os.path.join(batch, "probes", p["id"])
            print("probe", p["id"], "(should trigger)" if p["should_trigger"] else "")
            install(run_dir)
            run_one(run_dir, p["prompt"], {"kind": "probe", "probe": p}, a)
            scored.append(run_dir)
    if a.dry_run:
        print("dry run: %d run(s) prepared in %s, nothing sent" % (len(scored), batch))
        return
    sys.path.insert(0, HERE)
    import score
    score.main(scored + ["--report", batch])


if __name__ == "__main__":
    main()
