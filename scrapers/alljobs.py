"""AllJobs by Teletalk scraper — uses their public JSON API (/api/v1/govt-jobs/list)."""
from __future__ import annotations

import requests

from .common import detect_deadline, make_id, now_iso

API = "https://alljobs.teletalk.com.bd/api/v1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Origin": "https://alljobs.teletalk.com.bd",
    "Referer": "https://alljobs.teletalk.com.bd/jobs/government",
}


def scrape(max_pages: int = 12, page_size: int = 20):
    jobs = _scrape_list("govt-jobs/list", max_pages, page_size, "government")
    # private postings (may be 0; endpoint exists officially)
    jobs += _scrape_list("private-jobs/list", 5, page_size, "private")
    return jobs


def _scrape_list(path, max_pages: int, page_size: int, org_type: str):
    jobs = []
    key = "govtJobs" if org_type == "government" else "privateJobs"
    try:
        for page in range(1, max_pages + 1):
            r = requests.get(
                f"{API}/{path}?page={page}&limit={page_size}",
                headers=HEADERS, timeout=25,
            )
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get(key) or []
            if not items:
                break
            for it in items:
                title = (it.get("job_title") or "").strip()
                title_bn = (it.get("job_title_bn") or "").strip()
                if not title and title_bn:
                    title = title_bn
                if not title:
                    continue
                deadline = detect_deadline(str(it.get("deadline_date") or "")) or ""
                pub = str(it.get("published_date") or "")[:10]
                org = (
                    ((it.get("job_utilities_govtorganization") or {}).get("name") if isinstance(it.get("job_utilities_govtorganization"), dict) else it.get("job_utilities_govtorganization"))
                    or ("Government Organization" if org_type == "government" else "Private Company")
                )
                url = it.get("application_site") or (
                    f"https://alljobs.teletalk.com.bd/jobs/{'government' if org_type == 'government' else 'private'}/"
                )
                if not title_bn:
                    title_bn = title
                jobs.append(
                    {
                        "id": make_id(title, str(it.get("job_id") or url), str(org)),
                        "title": title,
                        "title_bn": title_bn,
                        "organization": str(org)[:120],
                        "org_type": org_type,
                        "source": "alljobs.teletalk",
                        "url": url,
                        "alljobs_job_id": it.get("job_id"),
                        "vacancy": str(it.get("vacancy") or ""),
                        "deadline": deadline,
                        "published_date": pub,
                        "location": "Bangladesh",
                        "description": f"{'Government' if org_type == 'government' else 'Private'} job circular (vacancy: {it.get('vacancy') or '—'}).",
                        "scraped_at": now_iso(),
                        "trust": "official-api",
                    }
                )
            if len(items) < page_size:
                break
    except Exception:
        pass
    return jobs
