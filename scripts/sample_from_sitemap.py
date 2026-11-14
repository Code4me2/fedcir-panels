"""Draw a year-stratified sample of opinions from the court's sitemap, download them, extract fields, match to argument recordings."""
import csv, collections, datetime, os, random, re, subprocess, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from extract_header import extract, extract_more

urls_path, out_dir, per_year = sys.argv[1], sys.argv[2], int(sys.argv[3])
pdf_dir = os.path.join(out_dir, "pdfs"); os.makedirs(pdf_dir, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (fedcir-panel-research)"}
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()

DATE_TAIL = r"-\d{1,2}-\d{1,2}-\d{2,4}(?:_\d+|-\d+)?$"

def appeal_numbers(slug):
    """Appeal numbers (YY-NNNN) from an opinion posting slug, ignoring the posting date and decision date."""
    rest = re.sub(r"^\d{1,2}-\d{1,2}-\d{4}-", "", slug)       # drop posting date prefix
    rest = re.sub(DATE_TAIL, "", rest)                          # drop decision date suffix
    nums = set()
    lead = re.match(r"(\d{4}|\d{2})-(\d{4})", rest)
    if lead: nums.add(f"{lead[1][-2:]}-{lead[2]}")
    tail = rest.rsplit("opinion", 1)[-1]                        # e.g. "-13-1184-1185"
    for m in re.finditer(r"(?<!\d)(\d{2}|\d{4})-(\d{4})((?:-\d{4})*)(?!\d)", tail):
        yy = m[1][-2:]
        nums.add(f"{yy}-{m[2]}")
        nums.update(f"{yy}-{x}" for x in re.findall(r"\d{4}", m[3]))
    return nums

def case_name(slug):
    rest = re.sub(r"^\d{1,2}-\d{1,2}-\d{4}-(\d{2,4}-[\dm]{4}-)?", "", slug)
    return rest.split("-opinion")[0].replace("-", " ").strip()

urls = open(urls_path).read().split()
audio = collections.defaultdict(list)   # appeal number -> argument dates
opinions = []
for u in urls:
    slug = u.rstrip("/").rsplit("/", 1)[1].lower()
    m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})-", slug)
    if not m: continue
    posted = datetime.date(int(m[3]), int(m[1]), int(m[2]))
    rest = slug[m.end():]
    if slug.endswith("audio-uploaded"):
        num = re.match(r"(\d{4})-(\d{4})", rest)
        if num: audio[f"{num[1][-2:]}-{num[2]}"].append(posted)
    elif "opinion" in rest and "errata" not in rest and posted != datetime.date(2025, 3, 10):
        opinions.append((posted, u, slug))

random.seed(20261114)
by_year = collections.defaultdict(list)
for o in opinions:
    if o[0].year >= 2013: by_year[o[0].year].append(o)
sample = []
for y in sorted(by_year):
    sample += random.sample(by_year[y], min(per_year, len(by_year[y])))
print("opinion postings 2013+ by year:", {y: len(v) for y, v in sorted(by_year.items())})
print("sample size:", len(sample))

rows = []
for posted, url, slug in sample:
    r = dict(posted=str(posted), posting_url=url)
    try:
        cache = os.path.join(out_dir, "pages", re.sub(r"[^a-z0-9]+", "_", slug)[:150] + ".html")
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        if os.path.exists(cache): page = open(cache).read()
        else:
            page = get(url).decode("utf-8", "replace"); open(cache, "w").write(page); time.sleep(1.5)
        link = next(l for l in re.findall(r'href="([^"]+\.pdf)"', page) if "opinions-orders" in l)
        pdf_url = link if link.startswith("http") else "https://www.cafc.uscourts.gov" + link
        fn = os.path.join(pdf_dir, os.path.basename(pdf_url))
        if not os.path.exists(fn):
            open(fn, "wb").write(get(pdf_url)); time.sleep(1.5)
        text = subprocess.run(["pdftotext", "-l", "4", fn, "-"], capture_output=True, text=True).stdout
        e, x = extract(text), extract_more(text)
        title = re.search(r"<title>(.*?)</title>", page, re.S)
        r.update(pdf_url=pdf_url, case_name=case_name(slug),
                 decided=x["decided"], precedential=x["precedential"], origin=x["origin_from_text"],
                 panel="; ".join(e["panel"] or []), author=e["author"] or "",
                 separate_opinions="; ".join(e["separate_opinions"]), panel_line=e["panel_raw"] or "")
    except Exception as ex:
        r.update(error=repr(ex)[:200])
    nums = appeal_numbers(slug)
    r["appeal_numbers"] = "; ".join(sorted(nums))
    try:
        decided = datetime.datetime.strptime(r.get("decided", "").replace(".", "").replace(",", ""), "%B %d %Y").date()
    except ValueError:
        decided = None
    args = sorted(d for n in nums for d in audio.get(n, []) if decided is None or d <= decided)
    r["argued"] = str(args[-1]) if args else ""
    r["days_to_decision"] = (decided - args[-1]).days if (args and decided) else ""
    probs = []
    if r.get("error"): probs.append("download error")
    if len((r.get("panel") or "").split("; ")) != 3: probs.append("panel")
    if not r.get("author"): probs.append("author")
    if not r.get("decided"): probs.append("date")
    if not r.get("origin"): probs.append("origin")
    r["flag"] = ", ".join(probs)
    rows.append(r)

cols = ["decided", "appeal_numbers", "case_name", "origin", "precedential", "panel", "author", "separate_opinions",
        "argued", "days_to_decision", "flag", "panel_line", "pdf_url", "posted", "posting_url", "error"]
with open(os.path.join(out_dir, "sample_results.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print("flagged:", sum(bool(r["flag"]) for r in rows), "| argued match:", sum(bool(r["argued"]) for r in rows),
      "| with separate opinions:", sum(bool(r.get("separate_opinions")) for r in rows))
