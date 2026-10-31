"""Generic scraper for the ~65 Bangladeshi bank career pages listed in data/banks.json.

Two-level strategy per bank:
  Level 1  fetch the careers page (fallback: homepage)
  Level 2  follow same-domain candidate listing pages (NOTICE / CAREER / CIRCULAR links),
           then keep only links that look like an actual job circular:
             - document links (.pdf/.doc/.docx) whose text mentions jobs/notices, or
             - links whose text looks like a genuine circular title
Everything else (nav labels like 'Tender', 'Careers', 'Contact') is dropped.
"""
from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .common import (
    BAD_KEYWORDS,
    detect_deadline,
    fetch_html,
    get_session,
    make_id,
    normalize_text,
    now_iso,
)

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANKS_FILE = os.path.join(HERE, "data", "banks.json")

DOC_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png")

# Text that identifies a listing/index page (one level down)
LISTING_PAT = re.compile(
    r"(notice\s*&?\s*|career|recruit|circular|vacancy|job|appointment|নিয়োগ|বিজ্ঞপ্তি|শূন্য\s*পদ|publi[s|c].*notice)",
    re.I,
)
# Text that identifies an actual circular/posting title
CIRCULAR_PAT = re.compile(
    r"(post\s+of|posts?|circular|recruit|application|appointment|requirement|vacanc|"
    r"apply|deadline|advertisement|অফিস|কর্মকর্তা|কর্মচারী|নিয়োগ|বিজ্ঞপ্তি|আবেদন|শূন্য\s*পদ|শুন্য\s*পদ|"
    r"officer|manager|assistant|executive|guard|driver|clerk|probationary|cashier|peon)",
    re.I,
)
STRONG_NOISE = re.compile(
    r"(tender|eoi\b|procurement|corruption|complaint|grievance|whistle|privacy|faq|sitemap|"
    r"copyright|careers?$|^notice$|news\s*&?\s*event|press|media|gallery|contact|branch|deposit|"
    r"loan|sme|remittance|savings|fdr|dps|accounts?\s*open|i\-?bank|net\s*banking|transactions|fx|"
    r"annual|auditor|financial|credit\s*rating|agents?|atm|booth|bkash|nid|e\-?verification|"
    r"code\s*of|policy|ethic|csr|scholarship|donation|unclaimed|share|ipo|right|stock|dividend|"
    r"scam|fraud|executive\s*committee|board\s*of\s*directors|card|balance\s*transfer|"
    r"committee|holiday|joining|কমিটি|নির্দেশিকা|পরিচিতি|সংগঠন|শৃঙ্খলা|অবকাশ|নিষ্পত্তি|"
    r"মালামাল|বদলি|পদায়ন|যোগদান|অন্যান্য\s*বিজ্ঞপ্তি|news\s*&\s*)",
    re.I,
)
# A genuinely recruitment-specific phrase (tighter than CIRCULAR_PAT)
CIRC_TIGHT = re.compile(
    r"(post\s+of|posts\s|circular|recruit|appointment|vacanc|advertisement|requirement|"
    r"apply\s(online|now|for|to)|deadline|যোগ্যতা|নিয়ো(গ|গে?)|বিজ্ঞপ্তি|শূন্য\s*পদ|শুন্য\s*পদ|আবেদন)",
    re.I,
)


def _same_domain(url_a, url_b):
    try:
        return urlparse(url_a).netloc == urlparse(url_b).netloc
    except Exception:
        return False


def _harvest_links(html, base_url):
    soup = None
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        text = normalize_text(a.get_text())
        absu = urljoin(base_url, href)
        t = text or ""
        low = absu.lower()
        if any(skip in low for skip in ("facebook.com", "linkedin.com", "twitter.com", "youtube.com", "instagram.com", "play.google", "apple.com", "cdn-cgi", "pinterest", "wa.me", "whatsapp")):
            continue
        out.append((t, absu, low))
    return out


def _looks_like_circular(text, url_low):
    """Genuine job-circular judgement."""
    blob = f"{text} {url_low}"
    if STRONG_NOISE.search(blob):
        return False
    if any(b in url_low for b in BAD_KEYWORDS):
        return False
    if url_low.endswith(DOC_EXT) or ".pdf" in url_low:
        # doc links: rely on text (tighter)
        return bool(CIRC_TIGHT.search(text))
    if LISTING_PAT.search(blob):
        # listing page itself — only keep if the text is a descriptive circular title
        return len(text) > 25 and CIRC_TIGHT.search(text) is not None
    return bool(CIRC_TIGHT.search(text)) and len(text) > 18


def _scrape_one(bank: dict) -> tuple:
    name = bank.get("name") or "Unknown Bank"
    category = bank.get("category") or "other"
    careers = bank.get("careers_url") or ""
    website = bank.get("website") or ""
    seeds = []
    for u in (careers, website):
        if u and u not in seeds:
            seeds.append(u)
    session = get_session()

    jobs = []
    errors = []
    seen_texts = set()
    visited = set()

    # ---- Level 1: seeds
    level1_pages = []
    page_url, html = "", ""
    for u in seeds:
        h = fetch_html(session, u)
        if h and len(h) > 500:
            page_url, html = u, h
            level1_pages.append(u)
            break
    if not html:
        return name, [], "fetch-failed"

    for text, absu, low in _harvest_links(html, page_url):
        docish = low.endswith(DOC_EXT) or ".pdf" in low
        if docish and CIRCULAR_PAT.search(text):
            key = text.lower()[:80]
            if key not in seen_texts:
                seen_texts.add(key)
                jobs.append((text, absu))
        elif LISTING_PAT.search(f"{text} {low}") and not low.endswith(DOC_EXT):
            if _same_domain(absu, page_url) and absu not in visited:
                visited.add(absu)
                level1_pages.append((text, absu))

    # ---- Level 2: follow up to 9 listing pages (incl. seed careers page already done)
    follow = [x for x in level1_pages if isinstance(x, tuple)][:9]
    listing_page_url = page_url
    for text, u in follow:
        if not _same_domain(u, page_url):
            continue
        h = fetch_html(session, u)
        if not h or len(h) < 500:
            continue
        for t2, a2, l2 in _harvest_links(h, u):
            if t2 and _looks_like_circular(t2, l2):
                # skip pure-listing duplicates (same text as the parent nav)
                if t2.lower() in ("careers", "career", "notice", "circular", "jobs", "recruitment", "নিয়োগ", "চাকরি", "বিজ্ঞপ্তি"):
                    continue
                key = (t2.lower()[:80], l2.split("?")[0])
                kk = f"{key[0]}|{key[1]}"
                if kk in seen_texts:
                    continue
                seen_texts.add(kk)
                jobs.append((t2, a2))
        if len([j for j in jobs]) >= 45:
            break
    if not jobs:
        # fall back: anything on the careers page that's recruitment-specific
        for text, absu, low in _harvest_links(html, page_url):
            if CIRC_TIGHT.search(f"{text} {low}") and text and not STRONG_NOISE.search(text):
                key = text.lower()[:80]
                if key not in seen_texts:
                    seen_texts.add(key)
                    jobs.append((text, absu))

    norm = []
    deadline_hint = detect_deadline((BeautifulSoup(html, "html.parser").get_text(" ", strip=True) if html else "")[:4000])
    for text, absu in jobs:
        if len(text) > 250:
            text = text[:250]
        norm.append(
            {
                "id": make_id(text, absu, name),
                "title": text,
                "organization": name,
                "org_type": f"bank-{category}",
                "source": f"bank-site ({name})",
                "url": absu,
                "deadline": deadline_hint,
                "published_date": "",
                "location": "Bangladesh",
                "description": f"Job/circular link found on {name} website ({urlparse(page_url).netloc}).",
                "scraped_at": now_iso(),
                "trust": "auto-detected" if not absu.endswith(DOC_EXT) and ".pdf" not in absu else "official-circular-doc",
            }
        )
    return name, norm, ""


def scrape(max_workers: int = 8, only_categories=None, verbose: bool = True):
    with open(BANKS_FILE, encoding="utf-8") as f:
        banks = json.load(f)
    if only_categories:
        banks = [b for b in banks if b.get("category") in only_categories]

    all_jobs, errors = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_scrape_one, b): b["name"] for b in banks if b.get("careers_url") or b.get("website")}
        done = 0
        for fut in as_completed(futs):
            name, jobs, error = fut.result()
            done += 1
            all_jobs.extend(jobs)
            if error and verbose:
                print(f"  [{name}] {error}")
            elif verbose:
                print(f"  [{done}/{len(banks)}] {name}: {len(jobs)} circulars")
    return all_jobs, errors
