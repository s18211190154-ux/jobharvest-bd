"""BDJobs scraper — combines:
  1. #ng-state (page 1 embedded JSON), and
  2. network interception of api.bdjobs.com GetJobSearch XHRs while paging with Next.
Because clicking Next re-fetches fresh pages, we get many pageable listings.
"""
from __future__ import annotations

import json as jsonlib

from .common import detect_deadline, make_id, now_iso

PAGE_URL = "https://bdjobs.com/h/jobs/"


def _collect_jobs(obj, out):
    if isinstance(obj, dict):
        if "jobTitle" in obj and ("Jobid" in obj or "companyName" in obj or "deadlineDB" in obj):
            out.append(obj)
        for v in obj.values():
            _collect_jobs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_jobs(v, out)


def _parse_bdjobs_body(body: str, out_jobs):
    try:
        data = jsonlib.loads(body)
    except Exception:
        return
    arrs = []
    if isinstance(data, list):
        arrs.append(data)
    elif isinstance(data, dict):
        for k in ("data", "premiumData"):
            if isinstance(data.get(k), list):
                arrs.append(data[k])
        _collect_jobs(data, arrs)
    for j in arrs:
        for item in j:
            if not isinstance(item, dict) or not item.get("jobTitle"):
                continue
            out_jobs.append(item)


def _normalize_job(j: dict) -> dict | None:
    title = (j.get("jobTitle") or "").strip()
    if not title:
        return None
    location = (j.get("location") or "").strip()
    deadline = (j.get("deadlineDB") or "")[:10] or detect_deadline(j.get("deadline") or "")
    pub = (j.get("publishDate") or "")[:10]
    org = (j.get("companyName") or "").strip() or "BDJobs company"
    jd = (j.get("jobDescription") or j.get("eduRec") or "")[:400]
    for tag, rep in (("<p>", ""), ("</p>", " "), ("<li>", "• "), ("</li>", " "), ("<strong>", ""), ("</strong>", "")):
        jd = jd.replace(tag, rep)
    return {
        "id": make_id(title, str(j.get("Jobid") or ""), org),
        "title": title[:250],
        "organization": org[:120],
        "org_type": "private",
        "source": "bdjobs",
        "url": f"https://jobs.bdjobs.com/JobDetails.asp?id={j.get('Jobid')}" if j.get("Jobid") else PAGE_URL,
        "deadline": deadline,
        "published_date": pub,
        "location": location or "Bangladesh",
        "description": jd.strip() or title,
        "scraped_at": now_iso(),
        "trust": "official-api",
        "premium": j.get("AdType") == "1",
    }


def scrape(max_pages: int = 8):
    """max_pages counts total listing pages visited (1 initial + clicks)."""
    raw_items = []

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pg = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126")

            def on_resp(r):
                try:
                    if "api.bdjobs.com" in r.url and r.status == 200 and "JobSearch" in r.url:
                        body = r.text()
                        if body and len(body) > 100:
                            _parse_bdjobs_body(body, raw_items)
                except Exception:
                    pass

            pg.on("response", on_resp)
            pg.goto(PAGE_URL, timeout=90000, wait_until="domcontentloaded")
            pg.wait_for_selector("#ng-state", timeout=25000, state="attached")
            pg.wait_for_timeout(3000)
            # page 1 from transfer state
            _parse_bdjobs_body(pg.eval_on_selector("#ng-state", "el => el.textContent") or "", raw_items)
            n1 = len(raw_items)
            print(f"   bdjobs page 1: {n1} items")

            prev = n1
            no_new = 0
            for page in range(2, max_pages + 1):
                try:
                    btn = pg.get_by_text("Next", exact=True).first
                    btn.click()
                    pg.wait_for_timeout(3200)
                    new = len(raw_items)
                    if new == prev:
                        no_new += 1
                        if no_new >= 2:
                            break
                    else:
                        no_new = 0
                    prev = new
                except Exception:
                    break
            browser.close()
    except Exception:
        pass

    jobs, seen = [], set()
    for j in raw_items:
        n = _normalize_job(j)
        if not n:
            continue
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        jobs.append(n)
    return jobs
