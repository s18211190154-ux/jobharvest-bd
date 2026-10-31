"""Shared utilities: HTTP fetching, normalization, deadline parsing, and the generic extractor."""
from __future__ import annotations

import hashlib
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

SKIP_DOMAINS = (
    "facebook.com", "linkedin.com", "twitter.com", "x.com", "youtube.com",
    "instagram.com", "google.com", "mailto:", "tel:", "javascript:", "#",
)

# Links whose href/page name look like a job posting
KEYWORDS_EN = (
    "job", "career", "vacan", "recruit", "circular", "appointment", "opportunit",
    "notice", "carrer", "hiring", "apply", "position",
)
KEYWORDS_BN = ("নিয়োগ", "চাকরি", "বিজ্ঞপ্তি", "পদক্ষেপ", "বিজনেস", "শুন্যস্থান", "শূন্যপদ")
BAD_KEYWORDS = (
    "login", "sign", "password", "policy", "contact-us", "sitemap", "subscribe",
    "tender-award", "faq", "welfare", "annual-report", "budget", "tenders",
)

DATE_PATTERNS = [
    # 31 Oct 2026 / 31 October, 2026
    (r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s*(\d{4})", "%d %b %Y"),
    # 2026-11-07 / 2026/11/07
    (r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", "%Y-%m-%d"),
    # 07/11/2026 or 07-11-2026 (day-first, BD convention)
    (r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", "%d-%m-%Y"),
    # 31 Oct
    (r"\b(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", "%d %b"),
]

BN_DIGITS = {"০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4", "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_id(title: str, url: str, org: str) -> str:
    h = hashlib.sha1(f"{org}|{title}|{url}".encode("utf-8", "ignore")).hexdigest()[:16]
    return h


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def detect_deadline(text: str):
    """Best-effort deadline extraction; returns ISO date string like 2026-11-07 or ''. """
    t = (text or "")
    for bn, en in BN_DIGITS.items():
        t = t.replace(bn, en)
    for pat, fmt in DATE_PATTERNS:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        groups = list(m.groups())
        try:
            year = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            if fmt == "%d %b":
                # missing year: assume nearest upcoming November-ish year (roll forward)
                today_y = datetime.now().year
                for y in (today_y, today_y + 1, today_y - 1):
                    normalized = " ".join(groups) + f" {y}"
                    try:
                        dt = datetime.strptime(normalized, "%d %b %Y")
                        break
                    except ValueError:
                        continue
                else:
                    continue
            elif fmt == "%d-%m-%Y":
                if len(groups[2]) == 2:
                    groups[2] = "20" + groups[2]
                normalized = f"{groups[2]}-{groups[1]}-{groups[0]}"
                dt = datetime.strptime(normalized, "%Y-%m-%d")
            else:
                normalized = " ".join(groups)
                dt = datetime.strptime(normalized, fmt)
            iso = dt.date().isoformat()
            if len(iso) == 10:
                return iso
        except ValueError:
            continue
    return ""


def get_session():
    s = requests.Session()
    s.headers.update({"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "bn,en;q=0.9"})
    return s


def fetch_html(session: requests.Session, url: str, timeout: int = 20) -> str:
    try:
        r = session.get(url, timeout=timeout, verify=False)
        if r.status_code and 200 <= r.status_code < 400:
            enc = r.encoding or "utf-8"
            if enc.lower() in ("utf-16",):
                enc = "utf-8"
            return r.content.decode(enc, errors="replace")
    except requests.exceptions.SSLError:
        try:
            r = session.get(url.replace("https://", "http://"), timeout=timeout, verify=False)
            if 200 <= r.status_code < 400:
                return r.content.decode(r.encoding or "utf-8", errors="replace")
        except Exception:
            pass
    except Exception:
        pass
    return ""


TEXTY_EXT = (".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png")


def is_job_link(href: str, link_text: str, base_domain: str) -> bool:
    h = (href or "").lower()
    txt = (link_text or "").lower()
    for d in SKIP_DOMAINS:
        if d in h:
            return False
    if any(b in h for b in BAD_KEYWORDS):
        return False
    combined = h + " " + txt
    for kw in KEYWORDS_EN:
        if kw in combined:
            if any(b in h for b in BAD_KEYWORDS):
                continue
            return True
    for kw in KEYWORDS_BN:
        if kw in txt:
            return True
    # PDF/DOC circular links with any text mentioning date/notice
    if h.endswith(TEXTY_EXT) and any(k in txt for k in ("notice", "circular", "recruit", "নিয়োগ", "বিজ্ঞপ্তি")):
        return True
    return False


def extract_title_from_link(a) -> str:
    txt = normalize_text(a.get_text())
    if txt and len(txt) > 3:
        return txt[:300]
    return ""


def generic_scrape_org(session, org_name: str, org_type: str, urls, max_links=40, source_note="") -> tuple:
    """
    Generic job-link harvesting for one careers page (or several candidate URLs).
    Returns (jobs, error). Each job is a dict.
    """
    jobs = []
    error = ""
    seen = set()
    try:
        page_url = ""
        html = ""
        for u in urls:
            if not u:
                continue
            html = fetch_html(session, u)
            if html and len(html) > 500:
                page_url = u
                break
        if not html:
            return jobs, "fetch-failed/unreachable"

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        page_title = normalize_text(title_tag.get_text()) if title_tag else ""
        deadline_hint = detect_deadline(soup.get_text(" ", strip=True)[:4000])

        count = 0
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href:
                continue
            absu = urljoin(page_url, href)
            link_txt = extract_title_from_link(a)
            same_domain = urlparse(absu).netloc and (
                urlparse(absu).netloc.endswith(urlparse(page_url).netloc)
                if urlparse(page_url).netloc
                else False
            )
            if not is_job_link(absu, link_txt, urlparse(page_url).netloc):
                continue
            if absu in seen:
                continue
            seen.add(absu)
            if len(link_txt) < 3 and not absu.endswith(TEXTY_EXT):
                link_txt = page_title or org_name
            dedup_key = absu.split("?")[0].lower()
            if dedup_key in seen and count > 0:
                continue
            jobs.append(
                {
                    "id": make_id(link_txt, absu, org_name),
                    "title": link_txt[:250],
                    "organization": org_name,
                    "org_type": org_type,
                    "source": source_note or f"bank-site ({page_url.split('/')[2]})",
                    "url": absu,
                    "deadline": deadline_hint,
                    "published_date": "",
                    "location": "Bangladesh",
                    "description": f"Circular / job link found on {page_title or org_name} career page."[:300],
                    "scraped_at": now_iso(),
                    "trust": "auto-detected",
                }
            )
            count += 1
            if count >= max_links:
                break
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    return jobs, error
