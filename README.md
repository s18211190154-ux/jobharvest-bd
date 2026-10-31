# 🇧🇩 JobHarvestBD

One place to **search every Bangladeshi job circular** — scraped automatically, hosted for free.

## Where the data comes from

| Source | Method | What you get |
|---|---|---|
| **BDJobs** (bdjobs.com) | Playwright → Angular `#ng-state` JSON | ~60–120 newest postings each run (title, org, deadline, location, Bangladesh national) |
| **AllJobs by Teletalk** | Public JSON API `/api/v1/govt-jobs/list` | All **171+ government circulars** (vacancy, deadline, application site) |
| **Bangladesh Bank e-Recruitment** | Playwright (passes F5 bot gate) | BB / BSCS / online circulars — *fails gracefully when CAPTCHA-challenged* |
| **60+ bank career pages** (from your PDF) | Generic job-link detection with English+Bangla keywords | Circular/notice links per bank (AB Bank, Agrani, BRAC, DBBL, EBL, IFIC, Islami Bank, Sonali, etc.) |

## Freemium pipeline (100% free)

1. **GitHub Actions** runs `python scrape.py` **every 6 hours** (`cron: 0 */6 * * *`).
2. Results merge + de-dupe into **`data/jobs.json`** and get committed automatically.
3. **GitHub Pages** serves `webapp/index.html`, which reads `../data/jobs.json` — instant search & filtering, no backend, no cost.

## Setup (once, ~5 minutes)

1. Create a **new public GitHub repo** (e.g. `jobharvest-bd`).
2. Copy this project's files into it and push:
   ```bash
   git init
   git add .
   git commit -m "JobHarvestBD v1"
   git remote add origin https://github.com/YOURNAME/jobharvest-bd.git
   git branch -M main
   git push -u origin main
   ```
3. Enable **GitHub Pages**: repo → *Settings → Pages → Source: `main` branch, /(root)*.
4. Done — your portal is live at `https://YOURNAME.github.io/jobharvest-bd/webapp/`
   and automation starts on the next cron tick (or run it manually: **Actions → Scrape jobs → Run workflow**).

## Manual / local run

```bash
pip install -r requirements.txt
python -m playwright install chromium   # only needed once
python scrape.py                        # all sources (~2 min)
python scrape.py --fast                 # skip the 65 bank sites
python scrape.py --banks                # only the bank career pages
```

To browse locally:
```bash
python -m http.server 8000
# open http://localhost:8000/webapp/
```

## The webapp

`webapp/index.html` gives you:
- 🔎 Instant search (English **and বাংলা**)
- 🧩 Source dropdown, job-type chips (Government / Private / Bank sites)
- ⏳ Deadline filters (7 / 30 days / no-deadline)
- ↕️ Sort by newest, deadline or organization
- 📄 30-per-page pagination with "Show more"

## Honesty notes

- BDJobs via Playwright relies on their Angular transfer-state payload. If they redesign it, `scrapers/bdjobs.py` may need updating.
- BB e-Recruitment sits behind F5 bot protection; every 6h run retries it. When challenged, that source is skipped for that run (no crash).
- Bank pages use *generic* link detection — expect it to find most of the circulars on simple CMS sites and miss a few on JS-heavy sites (e.g. BRAC's Taleo portal).
- Scraped data is best-effort. Always confirm on the official circular before applying!

## Project layout

```
├── scrape.py                 # orchestrator (runs everything, writes data/jobs.json)
├── scrapers/
│   ├── common.py             # HTTP, URL heuristics, deadline parsing, generic extractor
│   ├── bdjobs.py             # bdjobs.com (Playwright)
│   ├── alljobs.py            # alljobs.teletalk.com.bd (public API)
│   ├── erecruitment.py       # erecruitment.bb.org.bd (Playwright)
│   └── bank_pages.py         # 65 bank career pages (generic)
├── data/
│   ├── banks.json            # bank list extracted from your PDF
│   └── jobs.json             # ← OUTPUT (committed by Actions)
├── webapp/index.html         # search & filter frontend
├── extract_banks.py          # regenerate banks.json from the source PDF
└── .github/workflows/scrape.yml  # the 6-hourly automation
```
