"""JobHarvestBD — orchestrates all scrapers and writes data/jobs.json.

Usage:
    python scrape.py                 # all sources
    python scrape.py --fast          # skip slow bank pages (bdjobs/alljobs/erecruit only)
    python scrape.py --banks         # bank pages only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "jobs.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="skip bank pages")
    ap.add_argument("--banks", action="store_true", help="bank pages only")
    args = ap.parse_args()

    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    all_jobs = []

    t0 = time.time()

    if not args.banks:
        print("== scraping bdjobs.com ==")
        from scrapers.bdjobs import scrape as scrape_bdjobs
        b = scrape_bdjobs(max_detail_pages=3)
        print(f"   bdjobs: {len(b)} jobs")
        all_jobs.extend(b)

        print("== scraping alljobs.teletalk ==")
        from scrapers.alljobs import scrape as scrape_alljobs
        a = scrape_alljobs(max_pages=12)
        print(f"   alljobs: {len(a)} jobs")
        all_jobs.extend(a)

        print("== scraping bb.erecruitment ==")
        from scrapers.erecruitment import scrape as scrape_erec
        e = scrape_erec()
        print(f"   erecruitment: {len(e)} jobs")
        all_jobs.extend(e)

    if not args.fast:
        print("== scraping bank career pages ==")
        from scrapers.bank_pages import scrape as scrape_banks
        bank_jobs, _ = scrape_banks(max_workers=8)
        print(f"   bank pages: {len(bank_jobs)} links")
        all_jobs.extend(bank_jobs)

    # global dedupe
    seen, dedup = set(), []
    for j in all_jobs:
        if j["id"] in seen:
            continue
        seen.add(j["id"])
        dedup.append(j)

    sources = Counter(j["source"] for j in dedup)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(dedup),
        "sources": dict(sorted(sources.items(), key=lambda x: -x[1])),
        "jobs": dedup,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\nDone: {len(dedup)} jobs from {len(sources)} sources -> {OUT}")
    for s, c in list(sources.most_common())[:12]:
        print(f"   {s}: {c}")
    print(f"Took {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
