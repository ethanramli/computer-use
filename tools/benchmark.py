"""Reproducible controller benchmark harness.

Each cell records UTC bounds, perf-counter durations, environment, warm/cold
state, quantiles, and failure rate. Model latency is deliberately excluded.

Run: python3 tools/benchmark.py [--samples 200] [--runs 1]
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from desktop.controller import Controller  # noqa: E402
from tests.test_controller import FakeBackend  # noqa: E402

WARMUPS = 20
DEFAULT_SAMPLES = 200


def environment() -> dict:
    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=5,
        ).stdout.strip()
    except Exception:
        git_commit = "unknown"
    return {
        "os": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "backend": "fake (controller policy layer; OS dispatch measured separately)",
        "git_commit": git_commit,
        "model_included": False,
    }


def timed(fn, samples: int, warmups: int = WARMUPS, *, expected_ok: bool = True) -> dict:
    for _ in range(warmups):
        fn()
    values = []
    failures = 0
    start = datetime.now(timezone.utc)
    for _ in range(samples):
        t0 = time.perf_counter_ns()
        try:
            result = fn()
            if isinstance(result, dict) and bool(result.get("ok")) != expected_ok:
                failures += 1
        except Exception:
            failures += 1
        values.append(time.perf_counter_ns() - t0)
    end = datetime.now(timezone.utc)
    milliseconds = [value / 1e6 for value in values]
    ordered = sorted(milliseconds)
    return {
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "samples": samples,
        "warmups": warmups,
        "median_ms": round(statistics.median(milliseconds), 4),
        "p95_ms": round(ordered[int(0.95 * len(ordered))], 4),
        "p99_ms": round(ordered[int(0.99 * len(ordered))], 4),
        "min_ms": round(min(milliseconds), 4),
        "max_ms": round(max(milliseconds), 4),
        "failure_rate": failures / samples,
        "raw_ns": values,
    }


def run_suite(samples: int) -> dict:
    backend = FakeBackend()
    backend.frontmost = "Finder"
    controller = Controller(backend=backend, dry_run=False)
    observed = controller.command("observe", {"metadata_only": True})
    frame_id = observed["data"]["frame_id"]

    try:
        cells = {}
        cells["single_click"] = timed(
            lambda: controller.command("click", {
                "x": 100,
                "y": 100,
                "frame_id": frame_id,
                "risk": "none",
            }),
            samples,
        )
        cells["keypress"] = timed(
            lambda: controller.command("press", {
                "keys": "return",
                "app": "Finder",
                "risk": "none",
            }),
            samples,
        )
        cells["text_entry_20chars"] = timed(
            lambda: controller.command("type", {
                "text": "x" * 20,
                "app": "Finder",
                "risk": "none",
            }),
            samples,
        )
        cells["focus_verification"] = timed(
            lambda: controller.command("type", {
                "text": "a",
                "app": "Finder",
                "risk": "none",
            }),
            samples,
        )
        batch = {
            "actions": [
                {
                    "op": "click",
                    "x": 10 + index,
                    "y": 10,
                    "frame_id": frame_id,
                    "risk": "none",
                }
                for index in range(10)
            ]
        }
        cells["batch_10_clicks"] = timed(
            lambda: controller.command("batch", dict(batch)),
            samples,
        )
        cells["failure_recovery_stale_frame"] = timed(
            lambda: controller.command("click", {
                "x": 1,
                "y": 1,
                "frame_id": "frame-missing",
                "risk": "none",
            }),
            samples,
            expected_ok=False,
        )
        cells["observe_metadata_only"] = timed(
            lambda: controller.command("observe", {"metadata_only": True}),
            samples,
        )
        for cell in cells.values():
            cell["cold"] = False

        child_environment = dict(os.environ)
        child_environment.update({
            "DESKTOP_FAKE_BACKEND": "1",
            "PYTHONPATH": str(PROJECT_ROOT),
        })

        def cold_cli():
            completed = subprocess.run(
                [sys.executable, "-m", "desktop.cli", "stop"],
                capture_output=True,
                env=child_environment,
                timeout=30,
                check=True,
            )
            return json.loads(completed.stdout)

        cells["cold_cli_process"] = timed(cold_cli, samples)
        cells["cold_cli_process"]["cold"] = True
        return cells
    finally:
        controller.close()


def summarize(all_runs: list) -> str:
    lines = [
        "| benchmark | median | p95 | p99 | failures |",
        "|---|---|---|---|---|",
    ]
    for name, cell in all_runs[-1].items():
        lines.append(
            f"| {name} | {cell['median_ms']} ms | {cell['p95_ms']} ms | "
            f"{cell['p99_ms']} ms | {cell['failure_rate']} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--out", default="benchmarks/latest.json")
    args = parser.parse_args()
    if args.samples < 1 or args.runs < 1:
        parser.error("--samples and --runs must be positive")

    all_runs = []
    for run_index in range(args.runs):
        print(f"run {run_index + 1}/{args.runs}...", file=sys.stderr)
        all_runs.append(run_suite(args.samples))

    results = {
        "environment": environment(),
        "runs": all_runs,
        "note": "Fake-backend controller timings isolate policy, validation, "
                "verification, and receipt overhead from OS dispatch. Model excluded.",
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=1) + "\n")
    print(summarize(all_runs))
    print(f"\nraw data: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
