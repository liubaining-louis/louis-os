from __future__ import annotations
import argparse, json
from .runner import run_all
from .report import generate_report

def main() -> None:
    parser = argparse.ArgumentParser(prog="atlas")
    parser.add_argument("command", choices=["run-all", "report"])
    args = parser.parse_args()
    if args.command == "run-all":
        print(json.dumps(run_all(), indent=2))
    else:
        print(generate_report())

if __name__ == "__main__":
    main()
