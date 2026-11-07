"""Calibrate the requirement-level job-match score against reviewed resume-job pairs.

Input: a CSV with columns
    resume   path to a parsed-profile JSON file or a PDF/DOCX resume
    job_id   id of a job in the jobs database
    label    1 = a reviewer (or a real outcome: interview/offer) says this is a strong match,
             0 = not a strong match
    outcome  optional free text (e.g. "interview", "rejected") - reported, not used

For the current config and a small grid of alternative multipliers/credits it prints how well
"score >= threshold" agrees with the labels (precision, recall, F1, accuracy), so weights are
changed on evidence. It never edits the config: copy a better setting into the JSON file named
by CAFY_MATCH_CONFIG yourself.

    uv run python -m backend.scripts.calibrate_matching reviewed_pairs.csv [--threshold 85]
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from backend.database import JobDatabase  # noqa: E402
from backend.requirement_matching import MATCH_CONFIG, ResumeContext, _deep_merge, score_job  # noqa: E402
from backend.resume_service import ResumeService  # noqa: E402


def load_profile(path: str) -> Dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    return ResumeService().parse_resume(p.name, p.read_bytes())


def metrics(pairs: List[Tuple[int, int]], threshold: int) -> Dict[str, float]:
    tp = sum(1 for s, y in pairs if s >= threshold and y == 1)
    fp = sum(1 for s, y in pairs if s >= threshold and y == 0)
    fn = sum(1 for s, y in pairs if s < threshold and y == 1)
    tn = sum(1 for s, y in pairs if s < threshold and y == 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "accuracy": (tp + tn) / len(pairs) if pairs else 0.0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv")
    parser.add_argument("--threshold", type=int, default=MATCH_CONFIG["top_band"]["min_score"])
    args = parser.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    if not rows:
        print("No rows in", args.csv)
        return 1
    jobs = {str(j.get("id")): j for j in JobDatabase().get_jobs(limit=100000)}
    profiles: Dict[str, Dict[str, Any]] = {}
    cases = []
    for row in rows:
        job = jobs.get(str(row["job_id"]))
        if not job:
            print(f"skip: job {row['job_id']} not found")
            continue
        profiles.setdefault(row["resume"], load_profile(row["resume"]))
        cases.append((profiles[row["resume"]], job, int(row["label"]), row.get("outcome", "")))
    print(f"{len(cases)} reviewed pairs, threshold {args.threshold}\n")

    grid = [{}]
    for essential, weak, transferable in itertools.product((1.5, 2.0, 3.0), (0.25, 0.5, 0.75), (0.25, 0.4, 0.6)):
        grid.append({"importance": {"essential": essential, "desirable": 1.0},
                     "evidence_credit": {"weak": weak, "transferable": transferable}})

    results = []
    for override in grid:
        config = _deep_merge(MATCH_CONFIG, override)
        contexts: Dict[int, ResumeContext] = {}
        pairs = []
        for profile, job, label, _ in cases:
            ctx = contexts.setdefault(id(profile), ResumeContext(profile, config))
            pairs.append((score_job(profile, job, ctx, config)["score"], label))
        results.append((metrics(pairs, args.threshold), override))

    current = results[0][0]
    print("current config:", {k: round(v, 3) for k, v in current.items()})
    print("\nbest alternatives by F1:")
    for m, override in sorted(results[1:], key=lambda r: r[0]["f1"], reverse=True)[:5]:
        print({k: round(v, 3) for k, v in m.items()}, json.dumps(override))
    if len(cases) < 50:
        print(f"\nNote: only {len(cases)} pairs - treat differences as indicative, not conclusive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
