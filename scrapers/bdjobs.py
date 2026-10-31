"""BDJobs scraper — loads bdjobs.com/h/jobs/ with Playwright and extracts the
Angular transfer-state JSON (#ng-state), which contains the newest ~120 postings."""
from __future__ import annotations

import json as jsonlib

from .common import detect_deadline, make_id, now_iso

PAGE_URL = "https://bdjobs.com/h/jobs/"


def _normalize_job(j: dict, src_key: str) -> dict | None:
    title = (j.get("jobTitle") or "").strip()
    if not title:
        return None
    location = (j.get("location") or "").strip()
    deadline = (j.get("deadlineDB") or "")[:10] or detect_deadline(j.get("deadline") or "")
    pub = (j.get("publishDate") or "")[:10]
    org = (j.get("companyName") or "").strip() or "BDJobs company"
    jd = j.get("jobDescription") or j.get("eduRec") or ""
    jd = jd[:600]
    return {
        "id": make_id(title, str(j.get("Jobid") or ""), org),
        "title": title[:250],
        "organization": org[:120],
        "org_type": "private" if j.get("OnlineJob") else "private",
        "source": "bdjobs",
        "url": f"https://jobs.bdjobs.com/JobDetails.asp?id={j.get('Jobid')}" if j.get("Jobid") else PAGE_URL,
        "deadline": deadline,
        "published_date": pub,
        "location": location or "Bangladesh",
        "description": ("Requirements: " + jd) if jd else title,
        "scraped_at": now_iso(),
        "trust": "official-api",
        "premium": j.get("AdType") == "1",
    }


def scrape(max_detail_pages: int = 3):
    jobs, all_state = [], []
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pg = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126")
            for attempt in range(3):
                try:
                    pg.goto(PAGE_URL, timeout=90000, wait_until="domcontentloaded")
                    pg.wait_for_selector("#ng-state", timeout=20000)
                    pg.wait_for_timeout(3000)
                    raw = pg.eval_on_selector("#ng-state", "el => el.textContent")
                    if raw:
                        all_state.append(raw)
                        break
                except Exception:
                    pg.wait_for_timeout(5000)
            # click through next pages to capture more listings
            for _ in range(max_detail_pages - 1):
                clicked = False
                try:
                    btn = pg.query_selector("a[aria-label='Next'], .pagination-next, li.next a")
                    if btn:
                        btn.click()
                        pg.wait_for_timeout(4000)
                        raw = pg.eval_on_selector("#ng-state", "el => el.textContent")
                        if raw:
                            all_state.append(raw)
                        clicked = True
                except Exception:
                    pass
                if not clicked:
                    break
            browser.close()

        for raw in all_state:
            state = jsonlib.loads(raw)
            for key, val in state.items():
                if not isinstance(val, dict):
                    continue
                b = val.get("b")
                if not isinstance(b, dict):
                    continue
                pool = []
                for lst_key in ("data", "premiumData"):
                    v = b.get(lst_key)
                    if isinstance(v, list):
                        pool.extend(v)
                for j in pool:
                    if isinstance(j, dict) and j.get("jobTitle"):
                        n = _normalize_job(j, key)
                        if n:
                            jobs.append(n)
    except Exception:
        pass

    # dedupe by id
    seen, out = set(), []
    for j in jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            out.append(j)
    return out
