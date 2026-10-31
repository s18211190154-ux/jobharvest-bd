"""Extract the bank careers directory from the PDF into structured JSON."""
import json
import re

import pdfplumber

PDF = r"C:\Users\AI312\Desktop\newProject\bangladesh_bank_careers_directory_2026.xlsx.pdf"
OUT = r"C:\Users\AI312\Desktop\newProject\data\banks.json"


def extract_urls(cell: str):
    """Split ';' separated URLs and heal line-breaks inserted mid-URL by the PDF."""
    if not cell:
        return []
    segments = re.split(r"\s*;\s*", cell)
    healed = []
    for seg in segments:
        seg = (seg or "").replace("\n", "").replace(" ", "")
        if seg.lower() in ("", "notreliablyverifiedinthispass", "-"):
            continue
        m = re.match(r"(https?):(\s*/\s*/)?(.+)", seg, re.I)
        if m:
            seg = f"{m.group(1)}://{m.group(3)}"
        seg = seg.rstrip(".")
        if not seg.startswith("http"):
            continue
        healed.append(seg)
    return healed


def categorize(cls: str):
    c = (cls or "").lower()
    if "central" in c:
        return "central-bank"
    if "non-scheduled" in c:
        return "non-scheduled"
    if "islamic" in c:
        return "state-owned-islamic" if "state-owned" in c else "private-islamic"
    if "state-owned" in c:
        return "state-owned"
    if "foreign" in c:
        return "foreign"
    if "private" in c:
        return "private"
    return "other"


rows, seen = [], set()
with pdfplumber.open(PDF) as pdf:
    for page in pdf.pages:
        for table in page.extract_tables():
            for row in table:
                row = [(c or "").replace("\n", " ").strip() for c in row]
                row = [re.sub(r"\s+", " ", c) for c in row]
                if len(row) < 6:
                    continue
                name = row[0]
                if name in ("Bank", "Institution") or name.startswith("Sources"):
                    continue
                if "Bank" not in name or name in seen:
                    continue
                if name.startswith(("Sources", "Other Bank Employers", "Bangladesh Bank's current")):
                    continue
                cls, website, careers = row[1], row[2], row[3]
                if not website and not careers:  # title/header rows
                    continue
                seen.add(name)
                urls_web = extract_urls(website)
                urls_career = extract_urls(careers)
                website_clean = urls_web[0] if urls_web else ""
                careers_clean = ""
                for u in urls_career:
                    if "bb.org.bd" not in u and "legacyscript" not in u:
                        careers_clean = u
                        break
                rows.append(
                    {
                        "name": name,
                        "type": cls,
                        "category": categorize(cls),
                        "website": website_clean,
                        "careers_url": careers_clean or website_clean,
                        "verification": row[5],
                    }
                )

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=2, ensure_ascii=False)

print(f"wrote {len(rows)} banks to {OUT}")
for r in rows:
    print(f"- {r['name']:40} | {r['category']:18} | {r['careers_url']}")
