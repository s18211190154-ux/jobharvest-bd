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
        b = scrape_bdjobs(max_pages=8)
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
        bank_jobs, bank_errors = scrape_banks(max_workers=8)
        print(f"   bank pages: {len(bank_jobs)} circulars")
        all_jobs.extend(bank_jobs)

    # ---- per-source counts incl. every bank (even the ones that found 0) ----
    sources = Counter(j["source"] for j in all_jobs)
    bank_counts = {}
    for j in all_jobs:
        if j["source"].startswith("bank-site ("):
            bank_name = j["source"][len("bank-site ("):-1]
            bank_counts[bank_name] = bank_counts.get(bank_name, 0) + 1
    dir_entries = []
    try:
        with open(os.path.join(HERE, "data", "banks.json"), encoding="utf-8") as f:
            for b in json.load(f):
                dir_entries.append(
                    {
                        "name": b["name"],
                        "kind": "bank",
                        "type": b.get("type") or "",
                        "category": b.get("category") or "other",
                        "website": b.get("website") or "",
                        "careers_url": b.get("careers_url") or "",
                        "verification": b.get("verification") or "",
                        "jobs_found": int(bank_counts.get(b["name"], 0)),
                    }
                )
    except Exception:
        pass
    dir_entries += [
        {
            "name": "BDJobs", "kind": "job-board", "type": "Bangladesh's largest private job portal",
            "category": "private", "website": "https://www.bdjobs.com/",
            "careers_url": "https://www.bdjobs.com/h/jobs/", "verification": "Scraped live",
            "jobs_found": int(sources.get("bdjobs", 0)),
        },
        {
            "name": "AllJobs by Teletalk", "kind": "job-board", "type": "Bangladesh government job portal by Teletalk",
            "category": "government", "website": "https://alljobs.teletalk.com.bd/",
            "careers_url": "https://alljobs.teletalk.com.bd/jobs/government", "verification": "Scraped live",
            "jobs_found": int(sources.get("alljobs.teletalk", 0)),
        },
        {
            "name": "Bangladesh Bank e-Recruitment", "kind": "government-portal", "type": "BB & BSCS official recruitment",
            "category": "government", "website": "https://www.bb.org.bd/",
            "careers_url": "https://erecruitment.bb.org.bd/", "verification": "Scraped live (bot-protected)",
            "jobs_found": int(sources.get("bb.erecruitment", 0)),
        },
    ]

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

    with open(os.path.join(HERE, "data", "sources.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": payload["generated_at"],
                "directory": dir_entries,
            },
            f, ensure_ascii=False, indent=1,
        )

    print(f"\nDone: {len(dedup)} jobs | directory: {len(dir_entries)} sites -> {OUT}")
    for s, c in list(sources.most_common())[:12]:
        print(f"   {s}: {c}")
    print(f"Took {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
