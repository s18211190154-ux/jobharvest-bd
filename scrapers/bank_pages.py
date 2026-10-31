"""Generic scraper for the ~65 Bangladeshi bank career pages listed in data/banks.json."""
from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .common import get_session, generic_scrape_org, now_iso

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANKS_FILE = os.path.join(HERE, "data", "banks.json")

progress_lock = threading.Lock()
progress = {"done": 0, "total": 0}


def _progress_status():
    with progress_lock:
        return progress["done"], progress["total"]


def _scrape_one(bank: dict) -> tuple:
    name = bank.get("name") or "Unknown Bank"
    careers = bank.get("careers_url") or ""
    website = bank.get("website") or ""
    urls = [careers, website] if careers != website else [careers or website]
    urls = [u for u in urls if u]
    org_type = "bank-" + (bank.get("category") or "other")
    session = get_session()
    session.headers["User-Agent"] += f" JobPortalScraper/{1.0}"
    jobs, error = generic_scrape_org(session, name, org_type, urls, max_links=40, source_note=f"bank-site ({name})")
    with progress_lock:
        progress["done"] += 1
    return name, jobs, error


def scrape(max_workers: int = 8, only_categories=None, verbose: bool = True):
    with open(BANKS_FILE, encoding="utf-8") as f:
        banks = json.load(f)
    if only_categories:
        banks = [b for b in banks if b.get("category") in only_categories]
    with progress_lock:
        progress["done"], progress["total"] = 0, len(banks)

    all_jobs, errors = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_scrape_one, b): b["name"] for b in banks if b.get("careers_url") or b.get("website")}
        for fut in as_completed(futs):
            name, jobs, error = fut.result()
            all_jobs.extend(jobs)
            if error and verbose:
                print(f"  [{name}] error: {error}")
            elif verbose:
                print(f"  [{progress['done']}/{progress['total']}] {name}: {len(jobs)} links")
    return all_jobs, errors
