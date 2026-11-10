"""One command: raw sources -> validated, chunked, embedding-ready files.

    python run_pipeline.py            # use cached data/raw/ (offline, reproducible)
    python run_pipeline.py --refresh  # re-download every source politely, then rebuild
    python run_pipeline.py --no-waivers  # see the validator fail loudly on a real source defect

Stages: ingest -> parse/normalise -> validate -> chunk -> export.
Exits non-zero if validation finds any unwaived error. No embedding or LLM calls anywhere.
"""
import argparse
import sys

from pipeline import chunk, export, ingest, parse, validate


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-download all sources")
    ap.add_argument("--no-waivers", action="store_true",
                    help="ignore data/manual/validation_waivers.csv (shows the validator failing on real source defects)")
    args = ap.parse_args()

    manifest = ingest.run(refresh=args.refresh)
    kb = parse.run(manifest)
    report = validate.run(kb, use_waivers=not args.no_waivers)
    if report["errors"]:
        print(f"\n[validate] FAILED with {len(report['errors'])} error(s):", file=sys.stderr)
        for e in report["errors"]:
            print(f"  - [{e['check']}] {e['record']}: {e['detail']}", file=sys.stderr)
        print("Fix the source/normaliser or add a justified waiver in data/manual/validation_waivers.csv",
              file=sys.stderr)
        return 1
    chunks = chunk.run(kb)
    export.run(kb, chunks, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
