"""Print random records next to the raw source text they came from, for manual verification.

    python -m pipeline.spotcheck            # 5 courses, 5 rules, 5 resources (seeded, reproducible)
    python -m pipeline.spotcheck --n 10 --seed 7
"""
import argparse
import json
import random

from .parse import norm_space
from .paths import INTERIM, PROCESSED, RAW


def _pages(source_id: str) -> list[str]:
    f = next(INTERIM.glob(f"{source_id}.*.json"))  # created by run_pipeline.py
    return json.loads(f.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    load = lambda n: json.loads((PROCESSED / f"{n}.json").read_text(encoding="utf-8"))

    print("=" * 30, "COURSES: compare title/credits/prereqs with the page text")
    for c in rnd.sample(load("courses"), a.n):
        page = norm_space(_pages(c["source_id"])[c["page"] - 1])
        i = page.find(c["code"] + " " + c["title"].split()[0])
        print(f"\n{c['code']} | {c['title']} | credits={c['credits']} L-T-P={c['L']}-{c['T']}-{c['P']} | "
              f"prereq='{c['prereq_text']}' | sem={c['semester_labels']}\n  open: {c['source_url']}\n"
              f"  page text: ...{page[max(i, 0): max(i, 0) + 260]}...")

    print("\n" + "=" * 30, "RULES: quote must appear verbatim on the cited page")
    for r in rnd.sample(load("rules"), a.n):
        ok = norm_space(r["text"])[:80] in norm_space(" ".join(_pages(r["source_id"])))
        print(f"\n{r['rule_id']} [{r['category']}] limit={r['numeric_limit']} {r['unit'] or ''} "
              f"verbatim_in_source={ok}\n  open: {r['source_url']}\n  quote: {r['text'][:220]}")

    print("\n" + "=" * 30, "RESOURCES: open the URL, compare title/instructor/licence")
    man = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    for r in rnd.sample(load("resources"), a.n):
        print(f"\n{r['resource_id']} | {r['title']} | {r['instructor'] or '-'} | {r['licence']} | "
              f"lessons={r['n_lessons']}\n  open: {r['url']}\n  raw snapshot: data/raw/{man[r['resource_id']]['file']}")


if __name__ == "__main__":
    main()
