#!/usr/bin/env python3
"""Simulator-free reporter regression with hand-checkable synthetic outcomes."""
import contextlib
import importlib.util
import io
import os
import tempfile


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTER = os.path.join(REPO, "tools", "report_pick_diverse_object.py")
spec = importlib.util.spec_from_file_location("report_pick_diverse_object", REPORTER)
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)

# Even seeds (Seen): 3/4. Odd seeds (Unseen): 1/4.
OUTCOMES = (True, False, True, True, False, False, True, False)
with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
    path = handle.name
    for seed, succeeded in enumerate(OUTCOMES):
        handle.write("Success!\n" if succeeded else "Fail!\n")
        handle.write(f"current seed: {seed}\n")

try:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        reporter.report_eval_log(path)
    text = output.getvalue()
finally:
    os.unlink(path)

checks = {
    "scene-level interpretation warning": (
        "independent scenes; NOT a target-only same-scene causal gap" in text
    ),
    "Seen micro is 75%": "3/4 = 75.0%" in text,
    "Unseen micro is 25%": "1/4 = 25.0%" in text,
    "balanced average is 50%": "balanced average               : 50.0%" in text,
    "absolute gap is 50%": "absolute gap (Seen - Unseen)   : 50.0%" in text,
    "retention is one third": "retention (Unseen / Seen)      : 33.3%" in text,
    "scheduled dumbbell exact target appears": (
        "unseen dumbbell           052_dumbbell base0" in text
    ),
    "scheduled Apple exact target appears": (
        "unseen apple              035_apple base1" in text
    ),
    "scheduled wooden mallet exact target appears": (
        "unseen wooden mallet      084_woodenmallet base3" in text
    ),
    "scheduled paintbrush exact target appears": (
        "unseen paintbrush         093_brush-pen base1" in text
    ),
}

for name, passed in checks.items():
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
print(f"\n==== {sum(checks.values())}/{len(checks)} passed ====")
raise SystemExit(0 if all(checks.values()) else 1)
