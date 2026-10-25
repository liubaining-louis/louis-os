"""Independent file-level acceptance checks for a trusted repository CSV tool."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any


def evaluate_csv_delivery(script: str, cases_path: str | Path) -> dict[str, Any]:
    """Execute trusted source in isolated temp directories, never untrusted code.

    The oracle is hand-written CSV/JSON, not the cleaner under test. Python -I
    isolates imports; it is NOT a security sandbox for third-party programs.
    """
    payload = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    cases = payload["cases"]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("cases must be nonempty with distinct ids")
    results: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        errors: list[str] = []
        with tempfile.TemporaryDirectory(prefix="louis-csv-case-") as directory:
            root = Path(directory)
            candidate = root / "process_csv.py"
            candidate.write_text(script, encoding="utf-8")
            source = root / "input.csv"
            original = case["input_csv"].encode("utf-8")
            source.write_bytes(original)
            output, report = root / "cleaned.csv", root / "report.json"
            try:
                process = subprocess.run(
                    [sys.executable, "-I", str(candidate), str(source), str(output), "--report", str(report)],
                    capture_output=True, text=True, timeout=5, cwd=root,
                )
            except subprocess.TimeoutExpired:
                errors.append("execution_timeout")
                process = None
            if not source.exists() or source.read_bytes() != original:
                errors.append("input_modified")
            if process is not None:
                if "expected_error" in case:
                    if process.returncode == 0 or case["expected_error"] not in process.stderr:
                        errors.append("expected_error_not_reported")
                    if output.exists() or report.exists():
                        errors.append("artifacts_written_for_invalid_input")
                else:
                    if process.returncode != 0:
                        errors.append("execution_failed")
                    if not output.exists() or output.read_bytes() != case["expected_csv"].encode("utf-8"):
                        errors.append("cleaned_csv_mismatch")
                    try:
                        actual = json.loads(report.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        errors.append("report_missing_or_invalid")
                    else:
                        expected = dict(case["expected_report"])
                        expected.update({"schema_version": "1.0", "input_sha256": hashlib.sha256(original).hexdigest()})
                        if actual != expected:
                            errors.append("report_mismatch")
        results.append({
            "case_id": case["id"], "passed": not errors, "errors": errors,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
        })
    return {
        "benchmark_id": payload["benchmark_id"],
        "scope": payload["scope"],
        "case_count": len(results),
        "passed_count": sum(case["passed"] for case in results),
        "passed": all(case["passed"] for case in results),
        "model_calls": 0,
        "external_submissions": 0,
        "payment_verified": False,
        "cases": results,
    }
