"""Bangladesh Bank e-Recruitment scraper — passes the F5 bot-gate via Playwright,
clicks through to career pages like a human, then reads the plain HTML pages."""
from __future__ import annotations

import re

from .common import detect_deadline, make_id, now_iso

BASE = "https://erecruitment.bb.org.bd"
TARGETS = [
    # (org label, link text fragment on homepage/ok page)
    ("Bangladesh Bank", "jobopportunity.php"),
    ("BSCS (Banker's Selection Committee)", "jobopportunity_bscs.php"),
    ("Online Application Jobs", "onlineapp/joblist.php"),
]


def scrape():
    jobs = []
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                locale="en-US",
                viewport={"width": 1366, "height": 800},
            )
            pg = ctx.new_page()
            pg.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )

            def harvest(current_url):
                rows = pg.eval_on_selector_all(
                    "a",
                    "els => els.map(e => ({t: (e.textContent||'').replace(/\\s+/g,' ').trim(), h: e.href}))",
                )
                added = 0
                for r in rows:
                    t, h = r["t"], r["h"]
                    if not t or len(t) < 8 or not h or not h.startswith("http"):
                        continue
                    if not re.search(r"job|circular|recruit|apply|vacan|appointment|notice|নিয়োগ|বিজ্ঞপ্তি", t, re.I):
                        continue
                    for bad in ("payment", "password", "admit", "resume", "faq", "track", "refund", "changepass", "resetpassword", "searchcvid", "offerletter", "docletter", "vivacard", "dplct"):
                        if bad in h.lower():
                            break
                    else:
                        jobs.append(
                            {
                                "id": make_id(t, h, "Bangladesh Bank e-Recruitment"),
                                "title": t[:250],
                                "organization": "Bangladesh Bank e-Recruitment",
                                "org_type": "government",
                                "source": "bb.erecruitment",
                                "url": h,
                                "deadline": "",
                                "published_date": "",
                                "location": "Bangladesh",
                                "description": "Circular / job link listed on BB e-Recruitment portal.",
                                "scraped_at": now_iso(),
                                "trust": "official-portal",
                            }
                        )
                        added += 1
                return added

            pg.goto(BASE, timeout=90000, wait_until="domcontentloaded")
            pg.wait_for_timeout(7000)

            for org, frag in TARGETS:
                # find the link on the live DOM and click through it
                try:
                    link = pg.query_selector(f"a[href*='{frag}']")
                    if link is None:
                        continue
                    link.click()
                    pg.wait_for_timeout(3000)
                    added = harvest(pg.url)
                    print(f"   {org}: {added} links (url={pg.url[:80]})")
                    # go back to base for the next target
                    pg.goto(BASE, timeout=90000, wait_until="domcontentloaded")
                    pg.wait_for_timeout(4000)
                except Exception as ex:
                    print(f"   {org}: failed ({type(ex).__name__})")
            browser.close()
    except Exception:
        pass

    seen, out = set(), []
    for j in jobs:
        k = (j["title"], j["url"])
        if k not in seen:
            seen.add(k)
            out.append(j)
    return out
